"""임시: 현재 진행 중인 수집이 끝나면 이어서 '나머지 9명' 백필(목표 50개).
동시 수집은 IP 차단 재발 위험이 있어 순차 실행을 보장한다.
현재 collect_transcripts 프로세스가 사라질 때까지 대기 → 백필 1회 실행 후 종료.
"""
import io, sys, os, time, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ["dalio", "eightysixth", "hongchunwook", "kimdante", "marks",
           "parkseik", "sosumonkey", "syuka", "wood"]

PS_COUNT = ("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -like '*collect_transcripts*' }).Count")


def collect_running() -> bool:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", PS_COUNT],
                             capture_output=True, text=True, timeout=30)
        return int((out.stdout or "0").strip() or 0) > 0
    except Exception:
        return False


def main():
    print("현재 수집 종료 대기 중…", flush=True)
    waited = 0
    while collect_running():
        time.sleep(60)
        waited += 1
        if waited % 5 == 0:
            print(f"  …대기 {waited}분", flush=True)
    print("현재 수집 종료 확인 → 나머지 9명 백필(목표 50) 시작", flush=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "src", "collect_transcripts.py"),
                    *TARGETS, "--limit", "50", "--delay", "8"], cwd=ROOT)
    print("=== 백필 수집 완료. 이제 큐레이션 단계 필요(Claude). ===", flush=True)


if __name__ == "__main__":
    main()
