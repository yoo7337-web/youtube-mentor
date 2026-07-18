"""현재 수집 종료 후 기존 6명(중복 언급) 증분 갱신 수집."""
import io,sys,os,time,subprocess
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS=['leehyoseok','syuka','newyorker','kimdante','sosumonkey','mijooeun']
PS=("@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
    "Where-Object { $_.CommandLine -like '*collect_transcripts*' }).Count")
def running():
    try:
        o=subprocess.run(['powershell','-NoProfile','-Command',PS],capture_output=True,text=True,timeout=30)
        return int((o.stdout or '0').strip() or 0)>0
    except Exception: return False
print('기존 6명 갱신 대기: 현재 수집 종료 기다림…',flush=True)
w=0
while running():
    time.sleep(60); w+=1
    if w%10==0: print(f'  …대기 {w}분',flush=True)
print('종료 확인 → 기존 6명 갱신 수집 시작',flush=True)
subprocess.run([sys.executable,os.path.join(ROOT,'src','collect_transcripts.py'),*TARGETS,'--limit','20','--max-new','10','--delay','7'],cwd=ROOT)
print('=== 기존 6명 갱신 수집 완료 → 큐레이션 필요 ===',flush=True)
