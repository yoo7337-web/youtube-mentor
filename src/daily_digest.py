"""
거인의 어깨 — 텔레그램 '오늘의 거인' 다이제스트

지식팩이 쌓여도 읽지 않으면 없는 것과 같다 → 매일 아침 학습 루틴으로 전달.
구성: 🆕 신규 인사이트(최근 등록분) · 🧭 오늘의 원칙(kind:원칙 로테이션) ·
      🔄 견해 변화 감지(같은 전문가·주제의 direction 이동) · ⚔️ 오늘의 대립(긍정vs부정)

상태 파일 data/digest_state.json 로 중복 발송 방지(이미 보낸 인사이트/변화/대립 기억).
발송: 텔레그램 Bot API (stock-radar와 동일 패턴, .env의 TELEGRAM_BOT_TOKEN/GIANTS_CHANNEL_ID)

사용법:
  python src/daily_digest.py            # 생성+발송
  python src/daily_digest.py --dry-run  # 발송 없이 본문 미리보기(상태 저장 안 함)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = ROOT / "data" / "knowledge-packs"
STATE_PATH = ROOT / "data" / "digest_state.json"
ENV_PATH = ROOT / ".env"

MAX_NEW = 5           # 신규 인사이트 최대 표기 수
TG_MAX_LEN = 3800     # 텔레그램 안전 분할 길이


# ---------- 유틸 ----------
def load_env() -> dict:
    import os
    env = {k: v for k, v in os.environ.items() if k in ("TELEGRAM_BOT_TOKEN", "GIANTS_CHANNEL_ID")}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    env[k.strip()] = v.strip()
    return env


def load_packs() -> list[dict]:
    manifest = json.load(open(PACK_DIR / "manifest.json", encoding="utf-8"))
    packs = []
    for m in manifest:
        try:
            packs.append(json.load(open(PACK_DIR / f"{m['slug']}.json", encoding="utf-8")))
        except Exception:
            pass
    return packs


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.load(open(STATE_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {"seen": [], "principle_idx": 0, "changes": [], "conflicts": []}


def ikey(slug: str, i: dict) -> str:
    return f"{slug}|{i.get('date','')}|{i.get('topic','')}|{(i.get('thesis','') or '')[:30]}"


def short_name(name: str) -> str:
    return (name or "").split(" (")[0]


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def prefix(topic: str) -> str:
    return (topic or "기타").split("/")[0].strip()


# ---------- 섹션 빌더 ----------
def sect_new(packs, state) -> tuple[str, list[str]]:
    """신규(미발송) 인사이트 — 날짜 최신순 상위 MAX_NEW."""
    seen = set(state["seen"])
    items = []
    for p in packs:
        for i in p.get("insights", []):
            k = ikey(p["slug"], i)
            if k not in seen:
                items.append((p, i, k))
    items.sort(key=lambda x: x[1].get("date", ""), reverse=True)
    shown = items[:MAX_NEW]
    new_keys = [k for _, _, k in items]          # 표기 못 한 것도 seen 처리(다음날 폭주 방지)
    if not shown:
        return "", new_keys
    lines = [f"🆕 <b>새 인사이트</b> ({len(items)}건 중 {len(shown)})"]
    for p, i, _ in shown:
        th = (i.get("thesis") or "").strip()
        th = th if len(th) <= 110 else th[:108] + "…"
        lines.append(f"· <b>{esc(short_name(p['name']))}</b> [{esc(i.get('topic',''))}] {esc(th)} <i>({i.get('date','')})</i>")
    return "\n".join(lines), new_keys


def sect_principle(packs, state) -> str:
    """오늘의 원칙 — kind:원칙 전체에서 로테이션 1개."""
    pool = []
    for p in packs:
        for i in p.get("insights", []):
            if i.get("kind") == "원칙":
                pool.append((p, i))
    if not pool:
        return ""
    pool.sort(key=lambda x: (x[0]["slug"], x[1].get("date", ""), x[1].get("topic", "")))
    idx = state.get("principle_idx", 0) % len(pool)
    p, i = pool[idx]
    state["principle_idx"] = idx + 1
    return (f"🧭 <b>오늘의 원칙</b> — {esc(short_name(p['name']))}\n"
            f"{esc(i.get('thesis',''))}\n"
            f"<a href=\"{i.get('video','')}\">근거 자료</a> <i>({i.get('date','')})</i>")


def sect_changes(packs, state) -> str:
    """견해 변화 — 같은 전문가·같은 topic에서 direction이 이동한 최신 쌍(미보고분만)."""
    reported = set(state["changes"])
    found = []
    for p in packs:
        by_topic = {}
        for i in p.get("insights", []):
            if i.get("kind") == "원칙":
                continue                          # 원칙은 방향 이동 개념 없음
            by_topic.setdefault(i.get("topic", ""), []).append(i)
        for topic, arr in by_topic.items():
            if len(arr) < 2:
                continue
            arr.sort(key=lambda x: x.get("date", ""))
            prev, last = arr[-2], arr[-1]
            if prev.get("direction") != last.get("direction"):
                ck = f"{p['slug']}|{topic}|{prev.get('date')}|{last.get('date')}"
                if ck not in reported:
                    found.append((p, topic, prev, last, ck))
    if not found:
        return ""
    lines = ["🔄 <b>견해 변화 감지</b>"]
    for p, topic, prev, last, ck in found[:3]:
        state["changes"].append(ck)
        lines.append(f"· <b>{esc(short_name(p['name']))}</b> [{esc(topic)}] "
                     f"{prev.get('direction')}({prev.get('date')}) → <b>{last.get('direction')}({last.get('date')})</b>")
    return "\n".join(lines)


def sect_conflict(packs, state) -> str:
    """오늘의 대립 — 같은 대분류에 긍정vs부정. 이미 보낸 조합은 제외하고 1건."""
    agg = {}
    for p in packs:
        for i in p.get("insights", []):
            pre = prefix(i.get("topic"))
            e = agg.setdefault(pre, {"pos": set(), "neg": set()})
            if i.get("direction") == "긍정":
                e["pos"].add(short_name(p["name"]))
            elif i.get("direction") == "부정":
                e["neg"].add(short_name(p["name"]))
    sent = set(state["conflicts"])
    best = None
    for pre, e in agg.items():
        if e["pos"] and e["neg"]:
            key = pre + "|" + ",".join(sorted(e["pos"] | e["neg"]))
            if key in sent:
                continue
            span = len(e["pos"]) + len(e["neg"])
            if not best or span > best[3]:
                best = (pre, e, key, span)
    if not best:
        return ""
    pre, e, key, _ = best
    state["conflicts"].append(key)
    return (f"⚔️ <b>오늘의 대립 — {esc(pre)}</b>\n"
            f"🟢 긍정: {esc(', '.join(sorted(e['pos'])))}\n"
            f"🔴 부정: {esc(', '.join(sorted(e['neg'])))}\n"
            f"<i>사이트 '주제별 비교'에서 논거를 나란히 보세요</i>")


# ---------- 발송 ----------
def send_telegram(text: str, env: dict) -> None:
    import requests
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("GIANTS_CHANNEL_ID")
    if not token or not chat:
        raise SystemExit("발송 불가: .env에 TELEGRAM_BOT_TOKEN / GIANTS_CHANNEL_ID 필요")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > TG_MAX_LEN and cur:
            chunks.append(cur); cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    for c in chunks:
        r = requests.post(url, json={"chat_id": chat, "text": c, "parse_mode": "HTML",
                                     "disable_web_page_preview": True}, timeout=30)
        if not r.ok:
            raise SystemExit(f"텔레그램 발송 실패 {r.status_code}: {r.text[:200]}")
        time.sleep(1.5)


def main():
    ap = argparse.ArgumentParser(description="오늘의 거인 다이제스트")
    ap.add_argument("--dry-run", action="store_true", help="발송·상태저장 없이 본문 출력")
    args = ap.parse_args()

    packs = load_packs()
    state = load_state()
    from datetime import date
    today = date.today().isoformat()

    new_txt, new_keys = sect_new(packs, state)
    principle = sect_principle(packs, state)
    changes = sect_changes(packs, state)
    conflict = sect_conflict(packs, state)

    parts = [f"🏛 <b>거인의 어깨 — 오늘의 다이제스트</b> ({today})"]
    for s in (new_txt, changes, principle, conflict):
        if s:
            parts.append(s)
    if len(parts) == 1:
        parts.append("오늘은 새 소식이 없습니다. 🧭 원칙 한 줄로 대신합니다.\n" + (principle or ""))
    body = "\n\n".join(p for p in parts if p.strip())

    if args.dry_run:
        print(body)
        print("\n--- dry-run: 발송·상태저장 생략 ---")
        return

    send_telegram(body, load_env())
    state["seen"] = list(set(state["seen"]) | set(new_keys))
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"발송 완료 · 신규 {len(new_keys)}건 상태 반영")


if __name__ == "__main__":
    main()
