"""완만한 재시도: IP 차단 해제 시 지정 slug 1명 수집. 2시간 간격 단발 프로브(요청 1건)만 → 악화 최소.
사용: python src/_retry_one.py <slug> <probe_video_id> [limit]"""
import io,sys,os,time,tempfile,glob,subprocess
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLUG=sys.argv[1]; PROBE=sys.argv[2]; LIMIT=sys.argv[3] if len(sys.argv)>3 else '25'
INTERVAL=7200; MAX=12
def unblocked():
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        YouTubeTranscriptApi().fetch(PROBE, languages=['ko','en']); return True
    except Exception: return False
for a in range(1,MAX+1):
    print(f'[{a}/{MAX}] {SLUG} 차단 확인…',flush=True)
    if unblocked():
        print('해제 감지 → 수집',flush=True)
        subprocess.run([sys.executable,os.path.join(ROOT,'src','collect_transcripts.py'),SLUG,'--limit',LIMIT,'--delay','8'],cwd=ROOT)
        print(f'=== {SLUG} 수집 완료 → 큐레이션 필요 ===',flush=True); sys.exit()
    if a<MAX: print(f'  아직 차단 → {INTERVAL//60}분 후',flush=True); time.sleep(INTERVAL)
print('=== 최대 시도 도달, 여전히 차단 ===',flush=True)
