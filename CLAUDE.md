# youtube-mentor — 프로젝트 지침 (세션용)

## 한 줄 목적
유튜브 투자·경제 명사들의 영상을 분석해, 그들의 관점·근거로 답하는 개인 AI 상담가(페르소나) 구축.

## 현황 (2026-07-19)
- **단계**: 운영 중 — 지식팩 **30명**·인사이트 401개(인용 전수 원문 검증 ✓) + 정적웹 사이트(`index.html`) 동작
- **사이트**: 루트 `index.html` 단일 파일, 3탭 구조(해시 라우팅, 탭 순서: 분류→상담→인사이트). 로컬 미리보기 `python -m http.server 8509`
  - `#classify` **분류 탭**: 전문가를 드래그해 국내투자/해외투자/일반 3구역에 배치(localStorage 저장, "JSON 복사"→categories.json 영구 반영, 30명 전원 배정 완료: 국내12·해외10·일반8). 배치가 상담·인사이트 탭 구성을 결정
  - `#ask` **상담 탭**: 분류별 **그룹 패널**(국내🇰🇷/해외🌏/일반🧭 색상 존 + 그룹 전체선택) 안에 전문가 카드. 다중 선택 → 개별 격리 호출(동시 2개 제한+429 자동 재시도) → 답변 카드 나란히. 부가: **🔄 최근 견해 변화**(같은 전문가·같은 topic에서 direction이 바뀐 최근 쌍 자동 감지, 원칙 제외 — 다이제스트와 동일 로직), **⚔️ 오늘의 대립**(같은 topic에 긍정vs부정 자동 감지→CTA로 양쪽 일괄 선택·질문 프리필), **💡 추천 질문 칩**(선택 전문가 top topic 기반), **🕘 상담 일지**(질문·답변 localStorage `ym_consultations` 자동 저장→다시보기)
  - `#insights` **인사이트 라이브러리 탭**: ① 전문가별 보기(방향 분포바·필터·주제별↔시간순·검색·티커·인용) ② `#insights/compare` 주제별 비교(대립 보드, 합성 없음, 63개 주제) ③ `#insights/market` 시장별 보기(분류별 전문가 통합 타임라인+방향 필터) ④ `#insights/search` **🔍 전체 검색**(30명 인사이트·인용을 키워드+방향+원칙/시황으로 가로질러 검색, 2026-07-19 신설). 새로고침 시 sessionStorage로 보던 화면 복원
  - **스타일 태그**(`catFor()`, 자동 도출): domain 키워드로 11종 분류(자산배분·가치투자·사이클리스크·해외성장주·시황전략·거시경제·밸류에이션·재무제표회계·퀀트데이터·투자철학원칙·경제해설). 카드 배지·아바타 색에 반영, 30명 전원 매칭(미분류 0)
  - **📓 개발일지**(우측 상단 헤더 버튼→모달): 개발 단계 타임라인 + 현재 상태 + 아이디어/개발예정 메모(localStorage `ym_devnotes`). 답변 렌더는 `💡 요약`(강조 박스)+`📝 자세히` 구조(buildPrompt가 형식 지시)
- **제외 원칙**: 삼프로TV·언더스탠딩·한국경제TV계열·김작가TV 등 **패널/다인 진행 방송**은 1인=1지식팩 완전 격리 원칙과 안 맞아 인덱싱 후보에서 제외. 본인 채널 없이 남의 프로그램에만 출연하는 인물도 동일하게 제외(예: 이항영)
- 임형록: 자막 다수 확보(라이브 포함)했으나 채널 특성상 공지·라이브예고 비중 높음
- **주의**: 86번가 채널은 2023년 이후 업로드 중단 → 지식팩이 2023년 발언 기준(시점 명시로 커버).
- **자막 엔진**: yt-dlp(주)+youtube-transcript-api(폴백). 유튜브가 연속 요청 시 IP 단위 429/IpBlocked → 두 엔진·WebFetch·전환사이트 모두 우회 불가(검증됨). `--delay 8` 백오프 재시도, 그래도 막히면 **몇 시간 뒤 재시도**가 유일한 무료 해법(프록시는 유료 필요)
- **아키텍처**: 인덱싱=Claude Code 터미널(구독, 별도 API X) → 전문가별 **지식팩 JSON** 생성 / 질문 창구 2개(정적웹+Gemini 무료, 터미널+Claude)
- **추가 비용 0원**: Gemini 무료 키 1개만 필요. 벡터DB·임베딩·RAG·Streamlit 없음(지식팩 통째 투입 방식)
- **대원칙(사용자 확정)**: ① 지식 완전 격리(1명=지식팩1개, 답변도 개별 호출, 합치지 않음) ② 개별 청취(카드 나란히, 합성 금지) ③ 시점 명시(모든 근거에 영상 날짜)
- **포트**: 8509 (정적웹 로컬 미리보기용)

## ⭐ 수동 트리거 문구 (실행 절차)
- **"멘토 인덱싱해줘"** (또는 "○○○ 인덱싱") → **반드시 `docs/INDEXING_GUIDE.md`의 규칙대로** 수행:
  1. `python src/collect_transcripts.py <slug…>` 또는 `--all` (증분 수집. IpBlocked 시 `--delay 8`, 그래도 막히면 몇 시간 뒤 재시도)
     - **더 많은 영상(백필)**: `--limit 50` (RSS 15개 캡을 flat-playlist로 돌파, 옛 영상까지). 요청량 많으니 `--max-new 20 --delay 8`로 **야간 며칠 분산**(이미 받은 건 자동 스킵). 목표 영상 수 기본 50개(사용자 확정 2026-07-05)
     - **수동 소스(X·뉴스레터·블로그, 가이드 §7)**: `data/manual/<slug>.md`에 붙여넣은 글이 있으면 `python src/add_source.py <slug…|--all>`로 인제스트(유튜브와 같은 스키마+source 태그) → 함께 큐레이션. **Threads는 인덱싱 후보에서 제외**(2026-07-05 — 로그인 벽으로 최근 글 일부만 접근 가능)
  2. 큐레이션: 가이드 §3(스키마·표준 topic 태그·direction 판정·채택/배제 기준) 준수. 대용량 자막은 전문가별 병렬 서브에이전트 위임(§3.5). 증분 시 기존 인사이트 삭제 금지—append만(§4, 타임라인 데이터)
     - **시점 정책(§3.6, 사용자 확정)**: 인덱싱 내역은 계속 **누적**. 신규 큐레이션은 **최근 3개월 영상 우선**, 원칙·사고방식 발언은 시효 없이 채택. 휴면 채널(버핏·린치·86번가)은 전체를 사고방식 참고+시대 명시. 답변 가중치(최근 우선/과거는 논리 참고)는 buildPrompt가 date 기준 자동 처리
  3. `python src/build_knowledge_pack.py <slug…>` → 지식팩+manifest 조립 → **`python src/verify_pack.py <slug…>` 필수**(인용 원문 대조·date/url 정합·미큐레이션 리포트) → 가이드 §6 자가검증
- **새 인물 추가** → 가이드 §5 체크리스트(채널 확인→persona YAML→로스터 갱신→①②③→메모리 갱신)
- **"○○○에게 물어봐줘"** → `data/knowledge-packs/<slug>.json` 로드 → 그 사람 페르소나로 답변. 여러 명이면 **답변 각각(카드식)**, 절대 합성 금지. 근거(영상·날짜) 인용, persona YAML 가드레일 준수
- **"○○○에게 심층으로 물어봐줘"** → 지식팩 인사이트뿐 아니라 `data/transcripts/<slug>/`의 **원문 자막·문서를 직접 읽고** 답변(압축 손실 보완). 사이트에선 상담 탭 **🔬 심층 모드** 체크박스(로컬 전용 — 질문 관련 원문 발췌 자동 투입)
- **문서 소스 확장**: `python src/fetch_documents.py marks|buffett` (Oaktree 메모·Berkshire 서한 — 유튜브 밖 정수). 신규 fetcher는 가이드 §7.0 패턴
- **주 1회 자동 수집**: Windows 작업 `youtube-mentor-weekly-collect`(토 03:00, `scripts/weekly_collect.cmd` → `--all --limit 50 --max-new 10` + **git 자동 커밋**). 로그 `data/collect.log`. 수집만 자동 → 그 뒤 "멘토 인덱싱해줘"로 신규분 증분 큐레이션
- **"다이제스트 보내줘"**: `python src/daily_digest.py [--dry-run]` — 텔레그램 '오늘의 거인'(신규 인사이트·🧭원칙 로테이션·🔄견해 변화 감지·⚔️대립 1건). 상태 `data/digest_state.json`(중복 방지, git 커밋). 설정 `.env`(TELEGRAM_BOT_TOKEN·GIANTS_CHANNEL_ID)
- **자동 발송(2026-07-19 연결 완료)**: GitHub Actions `.github/workflows/digest.yml` — 매일 08:00 KST 자동 실행 → 텔레그램 채널 `@giants_shoulder_digest`. 시크릿은 GH repo Secrets(TELEGRAM_BOT_TOKEN·GIANTS_CHANNEL_ID)에 등록됨. 실행 후 `digest_state.json` 변경분을 워크플로가 자동 커밋·푸시 → 로컬은 다음 작업 전 `git pull`로 동기화. 수동 실행: `gh workflow run digest.yml --repo yoo7337-web/youtube-mentor`
- **"스코어카드 갱신해줘"**: `python src/scorecard.py` — 시황 인사이트(티커+긍/부정)를 발언일→현재 수익률로 채점(±3% 문턱) → `data/scorecard.json` → 사이트 전문가 헤더 🎯 배지. 원칙·중립·무티커는 채점 제외(정상)
- **백업**: git 저장소(주간 자동 커밋). 브라우저 데이터(분류·상담일지·메모)는 📓개발일지 모달의 💾 내보내기/복원 버튼

## 다음 단계
1. ~~GitHub Pages 배포~~ **완료(2026-07-19)** — `https://yoo7337-web.github.io/youtube-mentor/` (공개 저장소 `yoo7337-web/youtube-mentor`, 라이브 검증 완료: 30명·4개 인사이트 모드·콘솔 에러 0)
2. 미큐레이션 자료 420여 개(백필로 쌓인 옛 영상) — 다음 "인덱싱해줘" 때 §3.6 증분으로 더 파낼 여지
3. ~~텔레그램 다이제스트~~ **완료(2026-07-19)** — 채널 `@giants_shoulder_digest` 생성·`@dsrkrbot` 관리자 등록·GitHub Actions로 매일 08:00 자동 발송 연결, 테스트 발송 확인됨
4. 추가 전문가 후보(사용자가 원할 시): Munger·Druckenmiller류 해외 인터뷰형은 재생목록 소스로 이미 온보딩됨. 국내 패널형(삼프로TV 등)은 아키텍처상 영구 제외. (참고 제안: SemiAnalysis·Asianometry·TechTechPotato 등 반도체 전문 영어 채널 — 사용자 확정 대기)

## 구조
- `personas/*.yaml` — 전문가 정의(채널·말투·가드레일·**intro** 소개문구 2~3줄, 선택 `documents:` 문서 소스 주석). 새 인물 추가 시 `intro:` 필수(카드에 표시됨). build가 intro→pack→manifest로 전파
- `data/categories.json` — 전문가 지역 분류(국내투자/해외투자/일반). 사이트 **🗂 분류 탭**에서 드래그로 배정, localStorage 저장 후 "JSON 복사"로 이 파일에 영구 반영. (스타일 태그는 별도 — `index.html`의 `DOMAIN_CATS`/`catFor()`가 domain 문자열에서 자동 도출, 파일로 관리 안 함)
- `assets/avatars/<slug>.jpg` — 카드/답변 프로필 사진(유튜브 채널 og:image, 해외 전문가는 위키피디아 대표사진). 사이트가 `<img onerror>`로 로드, 실패 시 이니셜 배지 폴백
- `src/collect_transcripts.py` — 채널 RSS로 최근 영상 자막 수집(증분)
- `src/build_knowledge_pack.py` — 자막목록+페르소나+큐레이션 인사이트 → 지식팩 조립
- `data/knowledge-packs/<slug>.json` — 지식팩(git 커밋, 사이트가 읽음). `_curated/<slug>.json` — Claude가 쓴 인사이트 원본
- `data/transcripts/` — 원본 자막(git 제외), `data/consultations/` — 상담 일지(v1.3)
- `docs/ARCHITECTURE.md` — 상세 설계, `docs/INDEXING_GUIDE.md` — **인덱싱·큐레이션 표준(모든 인덱싱 작업의 기준)**

## 원칙
- 답변엔 항상 **출처(영상+타임스탬프+날짜)** 인용, 환각 억제.
- "AI 재현" 명시(실제 인물 사칭 금지), 투자 조언 면책·매매지시 금지 가드레일.
- 자막은 개인 분석 용도만, 재배포·상업이용 배제.
