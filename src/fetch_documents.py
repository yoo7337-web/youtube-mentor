"""
거인의 어깨 — 1차 문서 소스 수집기 (하워드 막스 Oaktree 메모 · 버핏 Berkshire 주주서한)

거장의 정수는 유튜브 인터뷰가 아니라 공개 문서(메모·서한)에 있다.
공식 사이트에서 원문을 받아 유튜브 자막과 같은 스키마(+source:"memo"|"letter")로
data/transcripts/<slug>/doc_*.json 에 저장한다(증분). 이후 큐레이션(§3·§3.6, 대부분 kind:원칙)·
빌드는 기존 파이프라인 그대로.

사용법:
  python src/fetch_documents.py marks --limit 10     # Oaktree 메모 최근 10편
  python src/fetch_documents.py buffett --limit 5    # 주주서한 최근 5개년
  python src/fetch_documents.py --all
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPT_DIR = ROOT / "data" / "transcripts"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}


def get(url: str, binary: bool = False):
    """GET + gzip/brotli 해제. binary=True면 bytes 반환."""
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40)
    raw = r.read()
    enc = r.headers.get("Content-Encoding", "")
    if enc == "br":
        import brotli
        raw = brotli.decompress(raw)
    elif enc == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw if binary else raw.decode("utf-8", "replace")


def html_text(html: str) -> str:
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", body)
    text = text.replace("&rsquo;", "'").replace("&lsquo;", "'").replace("&ldquo;", '"') \
               .replace("&rdquo;", '"').replace("&amp;", "&").replace("&nbsp;", " ").replace("&mdash;", "—")
    return re.sub(r"\s+", " ", text).strip()


def parse_us_date(s: str) -> str:
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})", s)
    if not m:
        return ""
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


def save_record(slug: str, doc_id: str, title: str, date: str, url: str,
                text: str, source: str) -> bool:
    out_dir = TRANSCRIPT_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{doc_id}.json"
    if dest.exists():
        return False
    rec = {"slug": slug, "video_id": doc_id, "title": title, "published": date,
           "url": url, "lang": "en", "source": source, "char_count": len(text),
           "snippets": [], "text": text,
           "collected_at": datetime.now(timezone.utc).isoformat()}
    dest.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def fetch_marks(limit: int) -> dict:
    """Oaktree 메모: 목록 → 최근 limit편 본문."""
    print(f"\n== 하워드 막스 — Oaktree 메모 (최근 {limit}편) ==")
    stats = {"new": 0, "skip": 0, "fail": 0}
    idx = get("https://www.oaktreecapital.com/insights/memos")
    paths = list(dict.fromkeys(re.findall(r'href="(/insights/memo/[^"#?]+)"', idx)))[:limit]
    print(f"   목록 확보: {len(paths)}편")
    for p in paths:
        slug_id = "doc_memo_" + re.sub(r"[^\w-]", "", p.split("/")[-1])[:50]
        if (TRANSCRIPT_DIR / "marks" / f"{slug_id}.json").exists():
            stats["skip"] += 1
            continue
        url = "https://www.oaktreecapital.com" + p
        try:
            html = get(url)
            text = html_text(html)
            # 게시일: <time class="embedded-date" datetime="…"> 메타가 정답(본문 인용 날짜 오탐 방지)
            mt = re.search(r'<time[^>]*datetime="[^\d]*(\d{4}-\d{2}-\d{2})', html)
            date = mt.group(1) if mt else parse_us_date(text[:2500])
            # 본문 트리밍: 법적 고지 이후 제거(메모 표준 푸터)
            cut = text.find("Legal Information and Disclosures")
            if cut > 2000:
                text = text[:cut]
            title = (re.search(r"<title>([^<]+)</title>", html) or [None, p.split("/")[-1]])[1]
            title = title.split("|")[0].strip()[:70]
            if len(text) < 3000:
                print(f"      ! 본문 너무 짧음(스킵): {p}")
                stats["fail"] += 1
                continue
            save_record("marks", slug_id, title, date, url, text, "memo")
            stats["new"] += 1
            print(f"      ✓ [memo] {date or '날짜?'} {len(text):>6}자  {title[:40]}")
        except Exception as e:
            stats["fail"] += 1
            print(f"      ! 실패 {p}: {type(e).__name__} {str(e)[:60]}")
        time.sleep(2)
    print(f"   → 신규 {stats['new']} / 기존 {stats['skip']} / 실패 {stats['fail']}")
    return stats


def fetch_buffett(limit: int) -> dict:
    """Berkshire 주주서한: 인덱스 → 최근 limit개년 PDF/HTML."""
    print(f"\n== 워런 버핏 — Berkshire 주주서한 (최근 {limit}개년) ==")
    stats = {"new": 0, "skip": 0, "fail": 0}
    idx = get("https://www.berkshirehathaway.com/letters/letters.html")
    links = re.findall(r'href=[\'"]?([^\'" >]+)', idx, flags=re.I)
    yearly = {}
    for l in links:
        m = re.search(r"((19|20)\d{2})", l)
        if m:
            yearly[int(m.group(1))] = l
    years = sorted(yearly)[-limit:]
    print(f"   대상 연도: {years}")
    for y in years:
        doc_id = f"doc_letter_{y}"
        if (TRANSCRIPT_DIR / "buffett" / f"{doc_id}.json").exists():
            stats["skip"] += 1
            continue
        link = yearly[y]
        url = link if link.startswith("http") else f"https://www.berkshirehathaway.com/letters/{link}"
        try:
            if url.lower().endswith(".pdf"):
                raw = get(url, binary=True)
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(raw))
                text = re.sub(r"\s+", " ", " ".join((pg.extract_text() or "") for pg in reader.pages)).strip()
            else:
                text = html_text(get(url))
            if len(text) < 5000:
                print(f"      ! 본문 너무 짧음(스킵): {y}")
                stats["fail"] += 1
                continue
            # 서한 서명일: 통상 이듬해 2월 하순. 파싱된 날짜가 '이듬해 상반기'가 아니면(본문 인용 날짜 오탐) 근사치 사용
            cand = parse_us_date(text[-4000:]) or parse_us_date(text[:4000])
            date = cand if (cand and cand.startswith(str(y + 1)) and cand[5:7] in ("01", "02", "03", "04", "05", "06")) else f"{y+1}-02-28"
            save_record("buffett", doc_id, f"{y} Berkshire Shareholder Letter", date, url, text, "letter")
            stats["new"] += 1
            print(f"      ✓ [letter] {date} {len(text):>7}자  {y}년 주주서한")
        except Exception as e:
            stats["fail"] += 1
            print(f"      ! 실패 {y}: {type(e).__name__} {str(e)[:60]}")
        time.sleep(2)
    print(f"   → 신규 {stats['new']} / 기존 {stats['skip']} / 실패 {stats['fail']}")
    return stats


def fetch_damodaran(limit: int) -> dict:
    """Aswath Damodaran 블로그: RSS에 본문 전체가 담겨 페이지별 요청 불필요."""
    import feedparser
    print(f"\n== 애스워스 다모다란 — Valuation 블로그 (최근 {limit}편) ==")
    stats = {"new": 0, "skip": 0, "fail": 0}
    feed = feedparser.parse(
        f"https://aswathdamodaran.blogspot.com/feeds/posts/default?alt=rss&max-results={limit}")
    for e in feed.entries[:limit]:
        link = e.get("link", "")
        slug_id = "doc_blog_" + re.sub(r"[^\w-]", "", link.rstrip("/").split("/")[-1].replace(".html", ""))[:50]
        if (TRANSCRIPT_DIR / "damodaran" / f"{slug_id}.json").exists():
            stats["skip"] += 1
            continue
        raw_html = (e.content[0].value if e.get("content") else e.get("summary", "")) or ""
        text = html_text(raw_html)
        pp = e.get("published_parsed")
        date = f"{pp.tm_year}-{pp.tm_mon:02d}-{pp.tm_mday:02d}" if pp else ""
        if len(text) < 2500:
            print(f"      ! 본문 짧음(스킵): {link}")
            stats["fail"] += 1
            continue
        save_record("damodaran", slug_id, (e.get("title", "") or "")[:80], date, link, text, "blog")
        stats["new"] += 1
        print(f"      ✓ [blog] {date or '날짜?'} {len(text):>6}자  {e.get('title','')[:44]}")
    print(f"   → 신규 {stats['new']} / 기존 {stats['skip']} / 실패 {stats['fail']}")
    return stats


def main():
    ap = argparse.ArgumentParser(description="문서 수집기 (메모·주주서한·블로그)")
    ap.add_argument("targets", nargs="*", choices=["marks", "buffett", "damodaran"],
                    help="marks | buffett | damodaran")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="수집 개수(marks=10 / buffett=5 / damodaran=12 기본)")
    args = ap.parse_args()
    targets = ["marks", "buffett", "damodaran"] if args.all or not args.targets else args.targets
    for t in targets:
        if t == "marks":
            fetch_marks(args.limit or 10)
        elif t == "buffett":
            fetch_buffett(args.limit or 5)
        elif t == "damodaran":
            fetch_damodaran(args.limit or 12)
    print("\n다음: 큐레이션(§3.6 — 문서는 대부분 kind:원칙) → build_knowledge_pack → verify_pack")


if __name__ == "__main__":
    main()
