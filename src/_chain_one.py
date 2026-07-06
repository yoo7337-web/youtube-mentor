"""임시: 현재 진행 중인 수집이 끝나면 이어서 지정 slug 1명을 수집(순차 보장, IP 차단 회피).
사용: python src/_chain_one.py <slug> [limit]
"""
import io, sys, os, time, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLUG = sys.argv[1] if len(sys.argv) > 1 else "newyorker"
LIMIT = sys.argv[2] if len(sys.argv) > 2 else "25"
PS = ("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
      "Where-Object { $_.CommandLine -like '*collect_transcripts*' }).Count")


def collect_running():
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", PS],
                             capture_output=True, text=True, timeout=30)
        return int((out.stdout or "0").strip() or 0) > 0
    except Exception:
        return False


print(f"[chain-one] {SLUG} 대기: 현재 수집 종료를 기다림…", flush=True)
w = 0
while collect_running():
    time.sleep(60); w += 1
    if w % 10 == 0:
        print(f"  …대기 {w}분", flush=True)
print(f"[chain-one] 종료 확인 → {SLUG} 수집 시작(limit {LIMIT})", flush=True)
subprocess.run([sys.executable, os.path.join(ROOT, "src", "collect_transcripts.py"),
                SLUG, "--limit", LIMIT, "--delay", "8"], cwd=ROOT)
print(f"=== {SLUG} 수집 완료 → 큐레이션 필요(Claude) ===", flush=True)
