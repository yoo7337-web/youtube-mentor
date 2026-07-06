"""임시: 유튜브 IP 차단(429)이 풀리는 즉시 자동 수집. (백그라운드 실행용)
2시간 간격으로 '가벼운 단발 프로브'만 날려 차단 여부 확인 → 풀리면 대상 전체 수집 1회 실행 후 종료.
차단 중엔 프로브 1회(요청 1건)만 하므로 악화 위험 최소. 최대 N회 시도.
"""
import io, sys, os, time, tempfile, glob, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import yt_dlp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ["imhyungrok", "buffett", "lynch", "ohgunyoung", "wazoski"]
PROBE_VID = "mgKVJNQQBt8"     # 홍춘욱 영상(ko 자막 확실) — 차단 해제 신호용
INTERVAL = 7200               # 2시간
MAX_ATTEMPTS = 10             # 최대 ~20시간 커버


def probe_unblocked() -> bool:
    """단발 자막 fetch 1회(백오프 없음). 성공=해제, 429=차단."""
    with tempfile.TemporaryDirectory() as td:
        opts = {"skip_download": True, "writesubtitles": True, "writeautomaticsub": True,
                "subtitleslangs": ["ko", "en"], "subtitlesformat": "json3",
                "outtmpl": os.path.join(td, "%(id)s.%(ext)s"), "quiet": True, "no_warnings": True,
                "retries": 1, "extractor_retries": 1, "extractor_args": {"youtube": {"lang": ["ko"]}}}
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                y.extract_info(f"https://www.youtube.com/watch?v={PROBE_VID}", download=True)
            return bool(glob.glob(os.path.join(td, "*.json3")))
        except Exception:
            return False


def main():
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"[{attempt}/{MAX_ATTEMPTS}] 차단 확인 중…", flush=True)
        if probe_unblocked():
            print("차단 해제 감지 → 수집 시작", flush=True)
            cmd = [sys.executable, os.path.join(ROOT, "src", "collect_transcripts.py"),
                   *TARGETS, "--limit", "50", "--delay", "8", "--max-new", "20"]
            subprocess.run(cmd, cwd=ROOT)
            print("=== 수집 실행 완료. 이제 큐레이션 단계 필요(Claude). ===", flush=True)
            return
        if attempt < MAX_ATTEMPTS:
            print(f"   아직 차단 → {INTERVAL//60}분 후 재확인", flush=True)
            time.sleep(INTERVAL)
    print("=== 최대 시도 도달. 아직 차단 상태 — 수동 재시도 필요. ===", flush=True)


if __name__ == "__main__":
    main()
