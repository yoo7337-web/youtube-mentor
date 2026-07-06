"""
youtube-mentor — 수동/반자동 소스 인제스트 (X · 뉴스레터 · 블로그 등)

유튜브처럼 공개 자동수집이 불가한 텍스트 소스를 위해, 전문가 글을 붙여넣은
data/manual/<slug>.md 를 읽어 유튜브 자막과 '같은 스키마 + source 필드'로
data/transcripts/<slug>/<id>.json 에 저장한다(증분). 이후 build_knowledge_pack /
큐레이션(가이드 §3·§3.6) 이 유튜브와 동일하게 처리한다.

※ Threads는 로그인 벽으로 전체 수집이 불가해 인덱싱 후보에서 제외(2026-07-05).
  그래도 특정 글을 직접 복사해 붙여넣는 것은 이 스크립트로 처리 가능하다.

인박스 포맷 (data/manual/<slug>.md) — 관대하게 파싱:
  ## 2026-07-01 | https://www.threads.net/@handle/post/XXXX
  본문 여러 줄...

  ## 2026-06-20 | https://...
  또 다른 글...

- 헤더 `## <YYYY-MM-DD> | <url>` 로 새 글 시작(다음 ## 전까지가 본문). url 은 선택.
- source 는 url 호스트로 자동판별(threads/x/web) 또는 --source 로 지정.

사용법:
  python src/add_source.py hongchunwook            # data/manual/hongchunwook.md
  python src/add_source.py --all                   # data/manual/*.md 전체
  python src/add_source.py kimdante --source x      # 소스 강제 지정
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
MANUAL_DIR = ROOT / "data" / "manual"
TRANSCRIPT_DIR = ROOT / "data" / "transcripts"

HEADER = re.compile(r"^##\s*(\d{4}-\d{2}-\d{2})?\s*\|?\s*(\S+)?\s*$")


def detect_source(url: str) -> str:
    # Threads는 인덱싱 후보에서 제외(2026-07-05). 그래도 수동 붙여넣기는 막지 않음(url로 인식은 유지).
    u = (url or "").lower()
    if "threads." in u:
        return "threads"
    if "x.com" in u or "twitter.com" in u:
        return "x"
    return "web"  # url 없거나 기타 → web


def post_id(url: str, date: str, body: str) -> str:
    """안정적 고유 id: url 마지막 segment 우선, 없으면 date+본문 해시."""
    if url:
        seg = url.rstrip("/").split("/")[-1].split("?")[0]
        if seg:
            return "src_" + re.sub(r"[^\w-]", "", seg)[:40]
    h = hashlib.sha1((date + body[:200]).encode("utf-8")).hexdigest()[:12]
    return "src_" + h


def parse_manual(text: str) -> list[dict]:
    """인박스 텍스트 → [{date,url,body}, ...]. 헤더가 없으면 통째로 1건 취급."""
    lines = text.splitlines()
    posts, cur = [], None
    for ln in lines:
        m = HEADER.match(ln)
        if m and (m.group(1) or m.group(2)):
            if cur:
                posts.append(cur)
            cur = {"date": m.group(1) or "", "url": (m.group(2) or "").strip(), "body": []}
        elif cur is not None:
            cur["body"].append(ln)
    if cur:
        posts.append(cur)
    # 정리: body join·trim, 빈 글 제거
    out = []
    for p in posts:
        body = "\n".join(p["body"]).strip()
        if body:
            out.append({"date": p["date"], "url": p["url"], "body": body})
    return out


def ingest(slug: str, force_source: str | None) -> dict:
    inbox = MANUAL_DIR / f"{slug}.md"
    stats = {"new": 0, "skip": 0, "empty": 0}
    if not inbox.exists():
        print(f"   - 인박스 없음: {inbox.relative_to(ROOT)}")
        return stats
    posts = parse_manual(inbox.read_text(encoding="utf-8"))
    if not posts:
        print(f"   - 파싱된 글 없음: {slug}")
        stats["empty"] += 1
        return stats
    out_dir = TRANSCRIPT_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n== {slug} ==  (수동 소스 {len(posts)}건)")
    for p in posts:
        body, url, date = p["body"], p["url"], p["date"]
        vid = post_id(url, date, body)
        dest = out_dir / f"{vid}.json"
        if dest.exists():
            stats["skip"] += 1
            continue
        source = force_source or detect_source(url)
        title = body.splitlines()[0].strip()[:40]
        rec = {
            "slug": slug,
            "video_id": vid,
            "title": title,
            "published": date,
            "url": url,
            "lang": "ko",
            "source": source,
            "char_count": len(body),
            "snippets": [],
            "text": body,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }
        dest.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        stats["new"] += 1
        print(f"      ✓ [{source}] {date or '날짜?'} {len(body):>5}자  {title}")
    if not date and stats["new"]:
        print("      ! 일부 글에 날짜가 없음 — 시점 정책(§3.6) 위해 헤더에 YYYY-MM-DD 권장")
    print(f"   → 신규 {stats['new']} / 기존 {stats['skip']}")
    return stats


def main():
    ap = argparse.ArgumentParser(description="youtube-mentor 수동 소스 인제스트")
    ap.add_argument("slugs", nargs="*", help="전문가 slug (data/manual/<slug>.md)")
    ap.add_argument("--all", action="store_true", help="data/manual/*.md 전체")
    ap.add_argument("--source", choices=["x", "web"], help="소스 강제 지정(기본: url로 자동판별)")
    args = ap.parse_args()

    if args.all:
        targets = sorted(p.stem for p in MANUAL_DIR.glob("*.md")) if MANUAL_DIR.exists() else []
    else:
        targets = args.slugs
    if not targets:
        ap.print_help()
        sys.exit("\n대상이 없습니다. slug를 지정하거나 --all 사용. (인박스: data/manual/<slug>.md)")

    total = {"new": 0, "skip": 0, "empty": 0}
    for slug in targets:
        s = ingest(slug, args.source)
        for k in total:
            total[k] += s[k]
    print(f"\n=== 합계: 신규 {total['new']} / 기존 {total['skip']} ===")
    if total["new"]:
        print("다음: 큐레이션(가이드 §3·§3.6) → python src/build_knowledge_pack.py " + " ".join(targets))


if __name__ == "__main__":
    main()
