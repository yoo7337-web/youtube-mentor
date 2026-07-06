"""
youtube-mentor — 자막 수집기 (인덱싱 1단계)

전문가 persona YAML을 읽어, 채널/재생목록 RSS 피드(API 키 불필요)로 최근 영상 목록을 얻고
각 영상 자막을 받아 data/transcripts/<slug>/<video_id>.json 에 저장한다(증분).

자막 엔진: yt-dlp 우선(유튜브 플레이어 API 경유, 더 견고) → 실패 시 youtube-transcript-api 폴백.
둘 다 같은 IP를 쓰므로 유튜브가 IP를 rate-limit(429/IpBlocked)하면 어느 쪽도 못 받는다
→ --delay 를 늘리고 백오프 재시도, 그래도 막히면 몇 시간 뒤 재시도(가이드 참고).

사용법:
  python src/collect_transcripts.py kimdante syuka dalio   # 특정 전문가
  python src/collect_transcripts.py --all                  # 전체(TODO 채널 제외)
  python src/collect_transcripts.py --all --limit 50 --max-new 20 --delay 8  # 백필(야간 분산)
  python src/collect_transcripts.py wazoski --delay 8      # IP 제한 시 지연 늘리기
"""
from __future__ import annotations

import argparse
import glob as _glob
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml
import yt_dlp

# youtube-transcript-api 는 폴백용(있으면 사용, 없어도 동작)
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    _YTA_OK = True
except Exception:
    _YTA_OK = False

# Windows 콘솔(cp949)에서 한글·기호 출력 시 크래시 방지
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIR = ROOT / "personas"
TRANSCRIPT_DIR = ROOT / "data" / "transcripts"

RSS_CHANNEL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
RSS_PLAYLIST = "https://www.youtube.com/feeds/videos.xml?playlist_id={pid}"
UA = {"User-Agent": "Mozilla/5.0 (youtube-mentor collector)"}
# 한국어 우선, 없으면 영어(자동생성 포함). 순서가 우선순위.
LANG_PREFERENCE = ["ko", "en"]

_yta = YouTubeTranscriptApi() if _YTA_OK else None
_channel_id_cache: dict[str, str | None] = {}


def _is_rate_limited(msg: str) -> bool:
    m = msg.lower()
    return "429" in m or "too many requests" in m or "ipblocked" in m or "blocking requests" in m


def resolve_channel_id(handle_or_url: str) -> str | None:
    """@handle 또는 커스텀 URL 조각을 UC... 채널ID로 해석(페이지 HTML에서 추출)."""
    if handle_or_url in _channel_id_cache:
        return _channel_id_cache[handle_or_url]
    h = handle_or_url.strip().lstrip("/")
    if h.startswith("youtube.com/"):
        h = h.split("youtube.com/", 1)[1]
    if h.startswith("@"):
        url = f"https://www.youtube.com/{h}"
    elif h.startswith("UC"):
        _channel_id_cache[handle_or_url] = h
        return h
    else:
        url = f"https://www.youtube.com/@{h}" if not h.startswith("http") else h
    cid = None
    try:
        req = urllib.request.Request(url, headers=UA)
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
        m = re.search(r'"(?:channelId|externalId)":"(UC[\w-]{20,})"', html) or re.search(
            r"channel/(UC[\w-]{20,})", html
        )
        if m:
            cid = m.group(1)
    except Exception as exc:
        print(f"      ! 채널ID 해석 실패 {handle_or_url}: {type(exc).__name__}: {exc}")
    _channel_id_cache[handle_or_url] = cid
    return cid


def load_persona(slug: str) -> dict:
    path = PERSONA_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"persona 없음: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def feed_videos(rss_url: str, limit: int = 15) -> list[dict]:
    """RSS(채널 또는 재생목록)로 최근 영상 목록(최대 ~15개)을 얻는다. API 키 불필요.
    유튜브 RSS는 채널당 최신 15개까지만 준다 → 그 이상은 list_videos_flat 사용."""
    feed = feedparser.parse(rss_url)
    out = []
    for e in feed.entries[:limit]:
        vid = e.get("yt_videoid") or e.get("id", "").split(":")[-1]
        if not vid:
            continue
        out.append(
            {
                "id": vid,
                "title": e.get("title", ""),
                "published": e.get("published", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
            }
        )
    return out


def list_videos_flat(list_url: str, limit: int) -> list[dict]:
    """yt-dlp flat-playlist 로 채널/재생목록 영상 ID·제목을 최대 limit개(최신→과거).
    RSS 15개 캡을 넘어 백필할 때 사용. 자막 API와 다른 경로라 IP 제한과 독립적.
    날짜(published)는 flat 모드가 주지 않으므로 여기선 빈 값 → 자막 fetch 시 보강."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": limit,
        "skip_download": True,
        "extractor_args": {"youtube": {"lang": ["ko"]}},  # 제목 한국어 우선
    }
    out = []
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(list_url, download=False) or {}
        for e in info.get("entries") or []:
            vid = e.get("id")
            if vid:
                out.append(
                    {
                        "id": vid,
                        "title": e.get("title", "") or "",
                        "published": "",
                        "url": f"https://www.youtube.com/watch?v={vid}",
                    }
                )
    except Exception as exc:
        print(f"      ! flat 목록 실패: {type(exc).__name__}: {str(exc)[:120]}")
    return out


def merged_video_list(rss_url: str, list_url: str, limit: int) -> list[dict]:
    """대상 영상 목록. limit<=15 면 RSS만(빠름·안전). limit>15 면 flat 목록으로 백필하되,
    RSS가 주는 정확한 날짜·한글 제목을 우선 병합한다(최신→과거 순서 유지)."""
    rss = feed_videos(rss_url, 15)
    if limit <= 15:
        return rss[:limit]
    flat = list_videos_flat(list_url, limit)
    if not flat:
        return rss[:limit]  # flat 실패 → RSS 폴백
    by_id = {v["id"]: v for v in flat}
    for r in rss:  # RSS 메타(날짜·한글 제목) 우선
        if r["id"] in by_id:
            by_id[r["id"]]["published"] = r["published"]
            by_id[r["id"]]["title"] = r["title"] or by_id[r["id"]]["title"]
        else:
            by_id[r["id"]] = r
            flat.insert(0, r)  # RSS 전용(더 최신) 항목은 앞에
    return [by_id[v["id"]] for v in flat][:limit]


def _parse_json3(path: str) -> list[dict]:
    """yt-dlp json3 자막 → [{'text','start','duration'}, ...] 로 변환."""
    data = json.load(open(path, encoding="utf-8"))
    snippets = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text:
            continue
        snippets.append(
            {
                "text": text,
                "start": ev.get("tStartMs", 0) / 1000.0,
                "duration": ev.get("dDurationMs", 0) / 1000.0,
            }
        )
    return snippets


def _fmt_date(upload_date: str | None) -> str:
    """yt-dlp upload_date('YYYYMMDD') → 'YYYY-MM-DD'. 없으면 ''."""
    if upload_date and len(upload_date) == 8 and upload_date.isdigit():
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    return ""


def _fetch_meta_date(video_id: str) -> str:
    """자막 폴백(youtube-transcript-api)으로 날짜를 못 얻은 경우에만 메타데이터 1회 조회."""
    try:
        opts = {"quiet": True, "no_warnings": True, "skip_download": True,
                "extractor_args": {"youtube": {"lang": ["ko"]}}}
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            ) or {}
        return _fmt_date(info.get("upload_date"))
    except Exception:
        return ""


def _fetch_ytdlp(video_id: str):
    """yt-dlp 로 자막(json3) 다운로드→파싱 + 같은 추출에서 업로드일·한글 제목 확보(추가 요청 없음).
    반환 (snippets, lang, date, title) 또는 None. 429 는 예외로 전파."""
    with tempfile.TemporaryDirectory() as td:
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": LANG_PREFERENCE,
            "subtitlesformat": "json3",
            "outtmpl": os.path.join(td, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "retries": 1,
            "extractor_retries": 1,
            "extractor_args": {"youtube": {"lang": ["ko"]}},  # 제목·자막 한국어 우선
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=True
            ) or {}
        date, title = _fmt_date(info.get("upload_date")), info.get("title") or ""
        for lang in LANG_PREFERENCE:  # ko 우선
            matches = _glob.glob(os.path.join(td, f"*.{lang}.json3"))
            if matches:
                snips = _parse_json3(matches[0])
                if snips:
                    return snips, lang, date, title
    return None


def _fetch_yta(video_id: str):
    """폴백: youtube-transcript-api(날짜·제목은 안 줌 → 빈 값). 429 는 예외로 전파."""
    if not _YTA_OK:
        return None
    fetched = _yta.fetch(video_id, languages=LANG_PREFERENCE)
    return fetched.to_raw_data(), getattr(fetched, "language_code", "?"), "", ""


def fetch_transcript(video_id: str, retries: int = 3):
    """(snippets, lang, date, title) 반환. 자막 없으면 None. IP 제한(429/IpBlocked)은 백오프 재시도.
    엔진: yt-dlp 우선(자막+업로드일+한글 제목 동시) → 실패 시 youtube-transcript-api 폴백(날짜·제목 빈 값)."""
    for attempt in range(retries):
        yt_rl = yta_rl = False
        # 1) yt-dlp (자막+업로드일+한글 제목 동시)
        try:
            res = _fetch_ytdlp(video_id)
            if res:
                return res
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                yt_rl = True
        # 2) 폴백: youtube-transcript-api — yt-dlp가 429여도 항상 시도한다.
        #    (엔진별 차단 상태가 다를 수 있음: yt-dlp timedtext는 막혔어도 yta는 열린 경우 실측됨)
        try:
            res = _fetch_yta(video_id)
            if res:
                return res
            if not yt_rl:
                return None  # 두 엔진 모두 '자막 없음'
        except Exception as exc:
            if _is_rate_limited(str(exc)):
                yta_rl = True
            elif not yt_rl:
                return None  # yta 비-429 오류 & yt-dlp도 429 아님 → 자막 문제
        # 3) 최소 한 엔진이 IP 제한 → 백오프 재시도
        if (yt_rl or yta_rl) and attempt < retries - 1:
            wait = 20 * (attempt + 1)  # 20s, 40s
            print(f"      … {video_id} IP제한(429), {wait}s 대기 후 재시도({attempt+1}/{retries-1})")
            time.sleep(wait)
            continue
        if yt_rl or yta_rl:
            print(f"      ! {video_id} 자막 실패: IP제한(429) 지속")
        return None
    return None


def collect_for(slug: str, limit: int = 15, delay: float = 1.5,
                max_new: int | None = None) -> dict:
    persona = load_persona(slug)
    name = persona.get("name", slug)
    out_dir = TRANSCRIPT_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n== {name} ({slug}) ==  (목표 {limit}개" + (f", 이번 신규 상한 {max_new}" if max_new else "") + ")")
    stats = {"new": 0, "skip": 0, "no_transcript": 0, "todo": 0}

    for src in persona.get("channels", []):
        if max_new and stats["new"] >= max_new:
            break  # 다채널 인물도 신규 상한 넘으면 중단(다음 실행에서 이어감)
        raw_id = str(src.get("id", "")).strip()
        stype = src.get("type")

        if not raw_id or raw_id.upper() == "TODO":
            print(f"   - 스킵(미확정 TODO): {src.get('handle') or stype}")
            stats["todo"] += 1
            continue

        # 채널 탭 지정(videos 기본, streams=라이브 다시보기 등). RSS는 videos·playlist만 존재.
        tab = str(src.get("tab", "videos")).strip() or "videos"
        use_rss = True
        if stype == "playlist" and raw_id.startswith("PL"):
            rss = RSS_PLAYLIST.format(pid=raw_id)
            list_url = f"https://www.youtube.com/playlist?list={raw_id}"
            label = f"재생목록 {raw_id}"
        else:
            # channel: UC 이면 그대로, 아니면(@handle/커스텀) 해석
            cid = raw_id if raw_id.startswith("UC") else resolve_channel_id(raw_id)
            if not cid:
                print(f"   - 스킵(채널ID 해석 실패): {raw_id!r}")
                stats["todo"] += 1
                continue
            rss = RSS_CHANNEL.format(cid=cid)
            list_url = f"https://www.youtube.com/channel/{cid}/{tab}"
            label = f"채널 {cid}[{tab}]" + (f" ({raw_id})" if cid != raw_id else "")
            if tab != "videos":
                use_rss = False  # streams 등은 RSS 피드가 없어 flat 목록만 사용

        if use_rss:
            vids = merged_video_list(rss, list_url, limit)
            mode = " (RSS)" if limit <= 15 else " (flat 백필)"
        else:
            vids = list_videos_flat(list_url, limit)  # 날짜는 자막 fetch 시 업로드일로 보강
            mode = " (flat: 탭 직접)"
        print(f"   {label}: 대상 영상 {len(vids)}개" + mode)
        for v in vids:
            if max_new and stats["new"] >= max_new:
                print(f"   · 이번 실행 신규 상한({max_new}) 도달 → 나머지는 다음 실행에서")
                break
            dest = out_dir / f"{v['id']}.json"
            if dest.exists():
                stats["skip"] += 1
                continue
            time.sleep(delay)  # 요청 간 간격 → IP 차단 예방
            res = fetch_transcript(v["id"])
            if res is None:
                stats["no_transcript"] += 1
                print(f"      · 자막없음 {v['id']} {v['title'][:40]}")
                continue
            snippets, lang, fdate, ftitle = res
            published = v.get("published") or fdate  # RSS 날짜 우선, 없으면 fetch에서 얻은 업로드일
            if not published:  # yta 폴백 등으로 여전히 없으면 메타 1회 보강
                published = _fetch_meta_date(v["id"])
            title = v.get("title") or ftitle or ""
            text = " ".join(s["text"].replace("\n", " ") for s in snippets).strip()
            record = {
                "slug": slug,
                "video_id": v["id"],
                "title": title,
                "published": published,
                "url": v["url"],
                "lang": lang,
                "char_count": len(text),
                "snippets": snippets,
                "text": text,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
            dest.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            stats["new"] += 1
            print(f"      ✓ {v['id']} [{lang}] {published or '날짜?'} {len(text):>6}자  {title[:34]}")

    print(f"   → 신규 {stats['new']} / 기존 {stats['skip']} / 자막없음 {stats['no_transcript']} / 미대상 {stats['todo']}")
    return stats


def resolve_targets(args) -> list[str]:
    if args.all:
        return sorted(
            p.stem for p in PERSONA_DIR.glob("*.yaml") if not p.stem.startswith("_")
        )
    return args.slugs


def main():
    ap = argparse.ArgumentParser(description="youtube-mentor 자막 수집기")
    ap.add_argument("slugs", nargs="*", help="전문가 slug (예: kimdante syuka dalio)")
    ap.add_argument("--all", action="store_true", help="전체 전문가")
    ap.add_argument("--limit", type=int, default=15,
                    help="채널당 목표 영상 수(기본 15). 15 초과 시 flat 백필로 옛 영상까지 수집")
    ap.add_argument("--delay", type=float, default=1.5, help="요청 간 지연 초(기본 1.5, 차단 시 8 권장)")
    ap.add_argument("--max-new", type=int, default=None, dest="max_new",
                    help="이번 실행에서 전문가당 새로 받을 영상 수 상한(야간 분산 수집용)")
    args = ap.parse_args()

    targets = resolve_targets(args)
    if not targets:
        ap.print_help()
        sys.exit("\n대상이 없습니다. slug를 지정하거나 --all 사용.")

    mode = f"목표 {args.limit}개" + (" · flat 백필" if args.limit > 15 else " · RSS")
    print(f"대상: {', '.join(targets)}  ({mode}" + (f", 회당 신규≤{args.max_new}" if args.max_new else "") + ")")
    total = {"new": 0, "skip": 0, "no_transcript": 0, "todo": 0}
    for slug in targets:
        try:
            s = collect_for(slug, limit=args.limit, delay=args.delay, max_new=args.max_new)
            for k in total:
                total[k] += s[k]
        except FileNotFoundError as e:
            print(f"   ! {e}")
    print(
        f"\n=== 합계: 신규 {total['new']} / 기존 {total['skip']} / "
        f"자막없음 {total['no_transcript']} / 미대상 {total['todo']} ==="
    )


if __name__ == "__main__":
    main()
