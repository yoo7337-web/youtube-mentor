@echo off
REM 거인의 어깨 — 주 1회 정기 수집 (schtasks에서 호출). 소량·정기로 IP 차단 예방.
REM 큐레이션은 Claude 필요 → 수집만 자동, 이후 "멘토 인덱싱해줘"로 신규분 증분 큐레이션.
set REPO=C:\Users\yoo73\youtube-mentor
set PY=C:\Users\yoo73\AppData\Local\Programs\Python\Python312\python.exe
cd /d "%REPO%"
echo ==== %DATE% %TIME% weekly collect start ==== >> "%REPO%\data\collect.log"
"%PY%" src\collect_transcripts.py --all --limit 50 --max-new 10 --delay 8 >> "%REPO%\data\collect.log" 2>&1
REM 백업 안전망: 지식팩·큐레이션 등 변경분 주간 자동 커밋(자막·키는 gitignore로 제외)
git -C "%REPO%" add -A >> "%REPO%\data\collect.log" 2>&1
git -C "%REPO%" commit -m "weekly auto-backup (collect + packs)" >> "%REPO%\data\collect.log" 2>&1
echo ==== %DATE% %TIME% weekly collect end ==== >> "%REPO%\data\collect.log"
