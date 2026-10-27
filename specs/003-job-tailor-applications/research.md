# Research: job: 채용 공고별 맞춤 이력서·포트폴리오 준비

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-10-27

## R1. 판단(LLM)은 누가 하나: Claude Code 세션 vs. Python에서 API 호출

- **Decision**: 공고 요건 추출, 적합도 분석, 이력서 작성, 포트폴리오 문구 수정, 미리보기 이미지 확인은 **명령을 실행한 Claude Code 세션**이 한다.
  Python CLI `job`는 결정적인 작업만 맡는다: Slack 입출력, 공고 페이지 가져오기, 폴더·사본 만들기, PPTX 적용·검증, 렌더링, PDF 생성, 중복 확인.
- **Rationale**:
  - 스펙은 "사용자가 Claude Code에서 명령을 실행"하는 흐름이다. 세션 안에 이미 모델이 있으므로 API 키와 비용 관리를 따로 둘 필요가 없다.
  - 처리 전 확인(목록, 마감, 중복)은 사용자와 대화하며 진행해야 해서, 세션이 흐름을 이끄는 쪽이 자연스럽다.
  - 렌더링한 슬라이드 이미지를 세션이 직접 보고 판단할 수 있다(R7).
  - 결정적 단계를 CLI로 분리하면 pytest로 테스트할 수 있다(헌법 III).
- **Alternatives considered**:
  - Python에서 `shared.llm`으로 Anthropic API 호출: 혼자 끝까지 실행할 수는 있다. 하지만 대화형 확인을 따로 구현해야 하고, 비용 상한 관리가 필요하며, 이미지 검토도 따로 붙여야 한다. 예약 실행 요구가 없어서 장점이 작다.
  - 결과적으로 `ANTHROPIC_API_KEY`는 필요 없다. `agents/job-apply/.env`에서 빼도 된다.

## R2. 세션과 CLI 사이의 계약: "편집 계획" 파일

- **Decision**: 세션은 맞춤 내용을 `tailor.json` 한 파일에 적는다(contracts/tailor-plan.schema.json). CLI가 이 파일을 검증·적용하고 `changes.md`를 만든다.
  - 이력서 변경과 포트폴리오 문단 교체·슬라이드 순서를 모두 이 파일에 담는다.
  - 항목마다 `source`(원본 근거 위치)와 `reason`(바꾼 이유)이 필수다.
- **Rationale**:
  - FR-011(근거 필수)과 changes.md(변경 내역과 근거)를 같은 데이터에서 만든다.
  - 세션이 PPTX XML을 직접 만지지 않으니 디자인이 깨질 일이 구조적으로 줄어든다(FR-013).
  - 다시 고칠 때도 이 파일만 고친 뒤 `apply`를 다시 돌리면 된다(FR-014 반복).
- **Alternatives considered**: 세션이 python-pptx 코드를 즉석에서 짜서 실행하는 방식은 매번 결과가 달라지고 테스트할 수 없다.

## R3. PPTX 편집: 텍스트·순서만 바꾸고 디자인 보존

- **Decision**: `python-pptx`(1.0.x)로 base 사본을 열어 다음만 한다.
  - **텍스트 교체**: 문단 단위(`slide/shape_id/paragraph`)로 바꾼다. 새 텍스트는 그 문단의 첫 run에 넣고 run 서식(`a:rPr`)은 그대로 둔다. 나머지 run은 지운다.
    한 문단 안에서 서식이 섞여 있으면(굵게 일부 등) `runs` 배열로 run별 텍스트를 줄 수 있다. 이때 run 개수는 원본과 같아야 한다.
  - **문단 추가·삭제**: 같은 도형 안에서만 한다. 추가할 때는 같은 도형의 기존 문단을 복제해 서식(`a:pPr`, 글머리표, 들여쓰기)을 물려받는다.
  - **슬라이드 순서**: `p:sldIdLst`의 순서만 바꾼다. 슬라이드 추가·삭제는 없다(스펙 가정).
- **디자인 보존 검증(`job apply`가 매번 실행)**:
  1. 슬라이드 집합이 같다. 각 슬라이드를 원본 슬라이드와 짝짓고, 순서만 다르다.
  2. 각 슬라이드 XML에서 텍스트 노드(`a:t`)와 문단 개수 차이를 무시하고 비교했을 때, 도형·위치·크기·채우기·이미지·레이아웃 참조가 같다.
  3. 바뀐 문단이 쓰는 run·문단 서식이 모두 같은 도형의 원본 서식 중 하나다.
  4. 테마·마스터·레이아웃·미디어 파트가 바이트 단위로 같다.
  - 하나라도 어긋나면 적용을 실패로 끝낸다(exit 4). 출력 파일은 남기지 않는다.
- **Alternatives considered**:
  - `bodyPr`의 자동 맞춤(shrink on overflow)을 켜는 방법은 디자인 속성 변경이라 FR-013에 어긋난다. 그래서 넘침은 문구를 줄여서 해결한다.
  - 글자 크기를 줄이는 방법도 같은 이유로 제외한다.

## R4. PPTX → PDF 렌더링

- **Decision**: LibreOffice headless(`soffice --headless --convert-to pdf`)를 쓴다.
  - 호출에는 제한 시간 120초를 둔다.
  - 동시 실행 충돌을 피하려고 `-env:UserInstallation=file://<.job-state/lo-profile>`로 전용 프로필을 쓴다.
- **Rationale**: macOS와 Linux CI에서 같은 방식으로 돌릴 수 있는 사실상 유일한 무료 PPTX 렌더러다.
- **Caveat**: `brew install --cask libreoffice`로 설치한다(2026-10-27 설치 확인: LibreOffice 26.8.1, `soffice`는 `/opt/homebrew/bin`). `job doctor`가 확인한다.
  - 원본 PPTX가 쓰는 글꼴이 시스템에 없으면 LibreOffice가 다른 글꼴로 바꿔 줄 바꿈이 달라지고, 넘침을 잘못 판단할 수 있다.
  - 그래서 `doctor`는 PPTX가 쓰는 글꼴 목록을 `fc-list`(Homebrew fontconfig, Linux 기본 포함)와 비교해 없는 글꼴을 알린다.
    `fc-list`가 없으면 글꼴 확인은 경고로 건너뛴다.
- **Alternatives considered**:
  - PowerPoint/Keynote AppleScript 자동화: macOS 전용이고 테스트할 수 없으며 앱 상태에 좌우된다.
  - Aspose 등 상용 라이브러리: 비용이 든다.

## R5. PDF → 미리보기 PNG, 원본 이력서 텍스트 추출

- **Decision**: `PyMuPDF`(`pymupdf` 1.24+)를 쓴다.
  - 렌더링한 portfolio.pdf에서 바뀐 슬라이드만 150dpi PNG로 저장해 `preview/slide-NN.png`를 만든다. NN은 결과물 기준 순서다.
  - 원본 resume.pdf 텍스트도 PyMuPDF로 뽑아 `base/resume.txt`에 저장한다. 세션은 이 텍스트를 근거 자료로 쓴다.
- **Rationale**: pip 패키지 하나로 시스템 의존성 없이 PDF 읽기·렌더링·텍스트 좌표 추출(R6)을 모두 한다. 개인 로컬 도구라 AGPL 라이선스도 문제없다.
- **Alternatives considered**:
  - `pdftoppm`(poppler): 시스템 설치가 필요하다.
  - `pypdf`: 렌더링을 못 한다.

## R6. 글자 넘침·레이아웃 깨짐 검출

- **Decision**: 두 단계로 확인한다.
  1. **자동 검출(`job apply`)**: 렌더링한 PDF에서 PyMuPDF로 각 슬라이드의 텍스트 줄 bbox를 얻고, PPTX의 텍스트 도형 영역(EMU→pt)과 비교한다.
     - 텍스트가 자기 도형 영역 밖으로 4pt 넘게 나가면 `overflow`다.
     - 슬라이드 경계 밖으로 나가면 `offslide`다.
     - 다른 텍스트 도형과 겹치면 `overlap`이다.
     - **같은 검사를 base 렌더링에도 해서, 원본에 이미 있던 문제는 빼고 새로 생긴 문제만 보고한다.**
  2. **눈으로 확인(세션)**: 세션이 `preview/` PNG를 직접 보고, 자동 검출이 놓친 문제(어색한 줄 바꿈, 한 글자 고아 줄 등)를 찾는다.
  - 문제가 있으면 `tailor.json`의 해당 문구를 줄이고 `job apply`를 다시 돌린다. 최대 3회 시도한다(FR-014).
  - 3회 뒤에도 남은 문제는 `changes.md`의 "남은 렌더링 문제"와 완료 답글에 적는다.
- **Rationale**: 실제 렌더링 결과를 기준으로 하므로 글꼴 메트릭을 추정할 필요가 없다. base와 비교해서 원래 디자인 의도(일부러 겹친 장식 텍스트 등)를 잘못 잡지 않는다.
- **Alternatives considered**: Pillow 글꼴 메트릭으로 줄 수를 추정하는 방식은 PowerPoint·LibreOffice의 줄 바꿈 규칙(한글 어절 단위 등)과 어긋난다.

## R7. 이력서 PDF 생성

- **Decision**: `resume.md` → HTML(`markdown` 3.7)로 바꾼 뒤, PyMuPDF `Story` API로 A4 PDF를 만든다.
  - 레포에 둔 간단한 CSS 템플릿(`templates/resume.css`)을 쓴다.
  - 한글 글꼴은 `config/job.yaml`의 `resume.font_files`(기본: Pretendard → Noto Sans KR → AppleSDGothicNeo 순으로 찾기)를 `fitz.Archive`로 넣는다.
  - 후보가 하나도 없으면(예: Ubuntu CI) PyMuPDF 내장 CJK 글꼴(`fitz.Font("cjk")`)로 대신하고, `doctor`는 경고만 한다. 그래서 기본 테스트가 시스템 글꼴 없이 통과한다(헌법 III).
- **Rationale**: R5와 같은 라이브러리라 시스템 의존성이 늘지 않는다.
  - 원본 resume.pdf의 디자인을 그대로 재현하는 것은 범위 밖이다. 스펙의 산출물도 resume.md 기반이다.
- **Alternatives considered**:
  - WeasyPrint: CSS 지원은 더 좋지만 macOS에서 `pango`를 따로 설치해야 하고, iCloud venv 문제와도 겹친다.
  - LibreOffice HTML→PDF: CSS를 거의 무시한다.

## R8. 공고 페이지 가져오기와 "가져오지 못함" 판정

- **Decision**: `httpx`로 받은 뒤 `trafilatura`(2.x)로 본문을 추출한다.
  - 받기: 제한 시간 15초, `shared.retry`로 3회 재시도, 일반 브라우저 User-Agent.
  - 다음 중 하나면 **가져오지 못함**(FR-017)이다.
    - HTTP 오류 또는 최종 재시도 소진
    - 추출한 본문이 400자 미만
    - 로그인·차단 페이지 신호("로그인", "login", "access denied" 등)가 본문의 대부분을 차지함
  - 일부 채용 사이트처럼 본문이 JSON(`__NEXT_DATA__`, `application/ld+json`의 `JobPosting`)에 들어 있으면, trafilatura 전에 이것을 먼저 시도한다.
- **Rationale**: 사이트별 파서를 늘리지 않고 흔한 두 방식만 지원한다. 그 밖은 사용자가 본문을 붙이는 흐름으로 처리한다.
- **Alternatives considered**:
  - 헤드리스 브라우저(Playwright): 설치가 무겁고 로그인 벽은 어차피 못 넘는다.
  - 세션의 웹 가져오기 도구: 결과가 결정적이지 않고 테스트할 수 없다. CLI 실패 판정과 따로 놀게 된다.

## R9. Slack 연동: 봇 토큰 + Web API

- **Decision**: Slack 앱 봇 토큰(`SLACK_BOT_TOKEN`, 환경변수)으로 Web API를 `httpx`로 직접 호출한다.
  - 메시지 조회: `conversations.history`, `conversations.replies`
  - 반응 달기: `reactions.add`
  - 답글: `chat.postMessage`(thread_ts)
  - 파일 올리기: `files.getUploadURLExternal` → 업로드 → `files.completeUploadExternal`. 예전 `files.upload`는 폐기됐다.
  - 필요 권한: `channels:history`(비공개 채널이면 `groups:history`), `reactions:read`, `reactions:write`, `chat:write`, `files:write`
  - 채널 ID는 비밀값이 아니라 설정이므로 `config/job.yaml`에 둔다.
  - 연결 확인(`doctor`)은 `auth.test`와 `conversations.history`(limit=1) 호출로 한다. 이미 받은 권한 안에서 토큰과 채널 접근을 함께 확인할 수 있다.
- **재시도**: `shared.retry`를 쓴다.
  - 429는 `Retry-After`를 존중한다.
  - `ok:false`이면서 `ratelimited`나 `internal_error`면 재시도한다.
  - 그 밖의 `ok:false`는 바로 실패로 처리한다.
  - 로그에는 토큰을 남기지 않는다(`Authorization` 헤더를 로깅하지 않음).
- **Rationale**: 기존 `shared/slack.py`(웹훅 전송)와 같은 방식이고 의존성이 늘지 않는다. 웹훅으로는 읽기·반응·파일 올리기를 할 수 없다.
- **위치**: 지금은 job-apply만 쓰므로 `agents/job-apply/src/job_apply/slack_api.py`에 둔다. 두 번째 에이전트가 쓰게 되면 `shared/`로 옮긴다(헌법 I).
- **Alternatives considered**: `slack_sdk`는 기능이 충분하지만, 재시도·로깅을 `shared.retry` 규칙에 맞추려면 어차피 감싸야 하고 의존성만 늘어난다.

## R10. "처리됨" 판단과 중복 확인

- **Decision**:
  - **메시지 상태**: Slack 반응이 기준이다. ✅(`white_check_mark`)가 있으면 누가 달았든 완료로 본다. 사용자가 직접 ✅를 달아 대상에서 빼는 것도 허용한다.
    ❓(`question`)가 있으면 본문 대기다. 이때 스레드에 봇이 아닌 사용자의 답글이 있으면, 그 답글들을 이어 붙인 텍스트를 공고 본문으로 쓴다.
  - **URL 중복(FR-016)**: `applications/*/meta.json`의 `posting.url_key`로 확인한다.
    - `url_key`는 정규화한 URL이다: 스킴·호스트 소문자, `utm_*`·`ref`·`fbclid` 등 추적 파라미터 제거, 프래그먼트 제거, 끝 `/` 제거.
    - 본문만 있는 공고는 본문 SHA-256 앞 16자(`text:<hash>`)를 키로 쓴다.
  - 상태가 `done`인 폴더만 중복으로 본다. `failed`나 `in_progress`는 같은 폴더를 다시 써서 이어서 처리한다(FR-019).
- **Rationale**: 별도 DB 없이 폴더 자체가 이력이다. 폴더를 지우면 이력도 함께 사라져 직관적이다.

## R11. 경로, 개인정보, gitignore

- **Decision**: 모두 `agents/job-apply/` 기준이다.
  - `private/`: 원본(사용자가 넣음)
  - `applications/`: 결과물
  - `.job-state/`: 수집 캐시, LibreOffice 프로필, 로그
  - `.gitignore`의 `agents/job-apply/data/private/`를 위 세 경로로 바꾼다.
  - `doctor`는 `git check-ignore`로 세 경로가 무시되는지 확인하고, 아니면 실패한다(FR-024).
- **원본 보호(FR-007)**:
  - CLI는 `private/`를 읽기 전용으로만 연다.
  - 처리 시작과 끝에 원본 SHA-256을 비교하고, 다르면 실패를 보고한다.
  - 슬래시 명령 규칙에도 "private/ 아래 파일을 쓰거나 옮기지 않는다"를 넣고, `.claude/settings.json`에 `Edit`/`Write` 거부 규칙(`agents/job-apply/private/**`)을 추가한다.

## R12. 날짜·이름 규칙

- **Decision**:
  - 폴더 이름은 `YYYY-MM-DD_<회사>_<직무>`다. 날짜는 처리한 날의 KST 기준이다.
  - 이름 정리 규칙:
    - 유니코드 NFC로 정규화한다.
    - `/\:*?"<>|`와 제어문자를 지운다.
    - 공백은 `-`로 바꾼다.
    - 각 부분은 40자로 자른다.
  - 이름이 겹치면 `_2`, `_3`을 붙인다.
  - 마감일은 `YYYY-MM-DD` 또는 없음(상시·미상)이다. KST 오늘보다 이전이면 마감이 지난 것이다.
- **Rationale**: 한글 회사명을 그대로 쓰되 macOS·Linux 모두에서 안전한 이름이 된다.

## R13. 테스트 전략

- **Decision**:
  - **기본 `uv run pytest`**: 네트워크·LibreOffice 없이 통과한다.
    - Slack과 공고 페이지는 `pytest-httpx`로 흉내 낸다.
    - 샘플 PPTX는 테스트 픽스처 코드가 python-pptx로 만든다(가상 인물). 샘플 이력서 PDF는 PyMuPDF로 만든다.
    - 렌더링 단계는 고정 PDF 픽스처로 바꿔 끼운다(`renderer` 주입).
  - **실제 LibreOffice 렌더링 테스트**: `-m render` 마커를 붙이고 `JOB_RENDER=1`일 때만 실행한다. CI 기본 실행에서는 빠진다.
- **Rationale**: 기존 `sandbox` 마커 방식과 같다. 헌법 III(외부 의존 모킹)을 지킨다.
