"""
거인의 어깨(youtube-mentor) — 지식팩 검증기 (가이드 §6 자가검증의 자동화)

큐레이션 산출물(_curated/<slug>.json)이 실제 수집 자료(transcripts)와 정합한지 검사한다.
- quotes: 인용 원문이 해당(또는 다른) 자료의 text에 실제로 존재하는가 (공백·문장부호 정규화 후 부분일치)
- insights: date가 근거 자료의 게시일과 일치하는가 / video URL이 수집된 자료에 존재하는가
- 미큐레이션 리포트: 수집돼 있으나 어떤 인사이트·인용도 참조하지 않는 자료 수(주간 증분 큐레이션 대상)

원칙: 검증기는 보고만 한다 — 자동 삭제·수정 금지(누적 원칙). 판단은 사람/Claude가 한다.

사용법:
  python src/verify_pack.py hongchunwook kimdante
  python src/verify_pack.py --all
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
CURATED_DIR = ROOT / "data" / "knowledge-packs" / "_curated"
TRANSCRIPT_DIR = ROOT / "data" / "transcripts"
PERSONA_DIR = ROOT / "personas"


def norm(s: str) -> str:
    """공백·문장부호 제거(한글·영문·숫자만) — 자동자막의 띄어쓰기 편차 흡수."""
    return re.sub(r"[\W_]+", "", s or "", flags=re.UNICODE).lower()


def vid_from_url(url: str) -> str:
    m = re.search(r"[?&]v=([\w-]{6,})", url or "")
    if m:
        return m.group(1)
    return (url or "").rstrip("/").split("/")[-1]


def load_transcripts(slug: str) -> dict:
    """video_id → {date, url, norm_text, title}. 문서 소스는 url이 .pdf/메모라 id 추출로 못 맞추므로
    별도로 url→record 인덱스도 만든다."""
    out = {}
    for f in glob.glob(str(TRANSCRIPT_DIR / slug / "*.json")):
        d = json.load(open(f, encoding="utf-8"))
        out[d["video_id"]] = {
            "vid": d["video_id"],
            "date": (d.get("published") or "")[:10],
            "url": d.get("url", ""),
            "norm": norm(d.get("text", "")),
            "title": d.get("title", ""),
        }
    return out


def match_record(trs: dict, cite_url: str) -> dict | None:
    """인용/인사이트의 video URL로 자료 레코드를 찾는다. ① url 완전일치 ② YouTube video_id 추출 순."""
    if not cite_url:
        return None
    for t in trs.values():                       # ① url 완전일치(문서·수동 소스 포함)
        if t["url"] and t["url"] == cite_url:
            return t
    return trs.get(vid_from_url(cite_url))        # ② YouTube ?v= / 마지막 segment


def verify(slug: str) -> dict:
    cur_path = CURATED_DIR / f"{slug}.json"
    stats = {"q_ok": 0, "q_other": 0, "q_fail": 0, "i_ok": 0, "i_date": 0, "i_url": 0, "uncurated": 0}
    trs = load_transcripts(slug)
    if not cur_path.exists():
        print(f"\n== {slug} ==  (큐레이션 없음 — 자료 {len(trs)}개 전부 미큐레이션)")
        stats["uncurated"] = len(trs)
        return stats
    cur = json.load(open(cur_path, encoding="utf-8"))
    insights, quotes = cur.get("insights", []), cur.get("quotes", [])
    print(f"\n== {slug} ==  (인사이트 {len(insights)} · 인용 {len(quotes)} · 자료 {len(trs)})")

    # --- quotes: 원문 존재 검사 ---
    for q in quotes:
        nq = norm(q.get("text", ""))
        cited = match_record(trs, q.get("video", ""))
        if cited and nq and nq in cited["norm"]:
            stats["q_ok"] += 1
        elif nq and any(nq in t["norm"] for t in trs.values()):
            stats["q_other"] += 1
            print(f"   ~ 인용이 '다른 자료'에서 발견(출처 url 확인 필요): \"{q['text'][:36]}…\"")
        else:
            stats["q_fail"] += 1
            print(f"   ✗ 인용 원문 미발견: \"{q['text'][:44]}…\" ({q.get('date','?')})")

    # --- insights: date·url 정합 ---
    referenced = set()
    for i in insights:
        t = match_record(trs, i.get("video", ""))
        if not t:
            stats["i_url"] += 1
            print(f"   ✗ 근거 자료 미수집(url 불일치?): [{i.get('date','?')}] {i.get('topic','')} → {i.get('video','')[:60]}")
            continue
        referenced.add(t["vid"])
        if t["date"] and i.get("date") and t["date"] != i["date"]:
            stats["i_date"] += 1
            print(f"   ~ date 불일치: insight={i['date']} vs 자료={t['date']} ({i.get('topic','')})")
        else:
            stats["i_ok"] += 1
    for q in quotes:
        t = match_record(trs, q.get("video", ""))
        if t:
            referenced.add(t["vid"])

    # --- 미큐레이션 자료(증분 큐레이션 대상) ---
    stats["uncurated"] = sum(1 for v in trs if v not in referenced)

    print(f"   → 인용 ✓{stats['q_ok']} ~다른자료{stats['q_other']} ✗{stats['q_fail']}"
          f" | 인사이트 ✓{stats['i_ok']} date불일치{stats['i_date']} url미발견{stats['i_url']}"
          f" | 미큐레이션 자료 {stats['uncurated']}개")
    return stats


def main():
    ap = argparse.ArgumentParser(description="지식팩 검증기 (§6 자동화)")
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all:
        targets = sorted(p.stem for p in PERSONA_DIR.glob("*.yaml") if not p.stem.startswith("_"))
    else:
        targets = args.slugs
    if not targets:
        ap.print_help()
        sys.exit("\n대상 없음. slug 또는 --all")

    tot = {}
    for slug in targets:
        s = verify(slug)
        for k, v in s.items():
            tot[k] = tot.get(k, 0) + v
    print(f"\n=== 합계: 인용 ✓{tot.get('q_ok',0)} ~{tot.get('q_other',0)} ✗{tot.get('q_fail',0)}"
          f" | 인사이트 ✓{tot.get('i_ok',0)} date{tot.get('i_date',0)} url{tot.get('i_url',0)}"
          f" | 미큐레이션 {tot.get('uncurated',0)}개 ===")
    if tot.get("uncurated"):
        print("→ 미큐레이션 자료는 다음 '멘토 인덱싱해줘' 때 증분 큐레이션 대상입니다.")


if __name__ == "__main__":
    main()
