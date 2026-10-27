# Implementation Plan: job: 채용 공고별 맞춤 이력서·포트폴리오 준비

**Branch**: `003-job-tailor-applications` | **Date**: 2026-10-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-job-tailor-applications/spec.md`

## Summary

사용자는 Claude Code에서 `/job-run [개수]` 또는 `/tailor <링크|본문>`을 실행한다. 판단과 결정적 작업은 다음과 같이 나눈다(research R1, R2).
- **세션(모델)이 하는 일**: 공고 요건 추출, 적합도 분석, 이력서 작성, 포트폴리오 문구·순서 계획, 미리보기 이미지 검토
- **`job` CLI가 하는 일**:
  - Slack 읽기·반응·답글·파일 올리기
  - 공고 페이지 가져오기, 폴더와 원본 사본 만들기
  - PPTX 적용과 디자인 보존 검증, 렌더링과 넘침 검출
  - 이력서 PDF 생성, 근거 검사, 중복 확인

두 쪽은 편집 계획 파일 `tailor.json`으로 주고받는다. 모든 변경 항목에 원본 근거 위치(`source`)와 이유(`reason`)가 있어야 하고, `changes.md`는 이 파일로 자동 생성한다.

포트폴리오 처리 방식은 다음과 같다.
- python-pptx로 문단 텍스트와 슬라이드 순서만 바꾼다.
- 나머지 XML이 원본과 같은지 매번 검사한다.
- LibreOffice로 PDF를 만든 뒤, 텍스트 bbox를 도형 영역과 비교해 넘침을 자동으로 찾는다. 원본에 있던 문제는 뺀다.
- 세션이 미리보기 PNG를 직접 확인하고, 문구를 줄여 최대 3회 다시 적용한다.

## Technical Context

**Language/Version**: Python 3.12 (uv workspace 멤버 `agents/job-apply`)

**Primary Dependencies**:
- `shared`(retry, logging, config, files)
- `httpx`(Slack Web API, 공고 가져오기)
- `python-pptx` 1.0.x, `pymupdf` 1.24+(PDF 텍스트·렌더링·이력서 PDF), `trafilatura` 2.x, `markdown` 3.7, `jsonschema` 4.x, `pydantic` v2, `pyyaml`
- 외부 도구: LibreOffice(`soffice`, 26.8.1 설치됨), `fc-list`(글꼴 확인, 없으면 건너뜀)

**Storage**: 파일과 Slack 반응. 모두 `agents/job-apply/` 기준이다.
- `private/`(원본, 읽기 전용)
- `applications/<folder>/`(결과물과 `meta.json`)
- `.job-state/`(수집 캐시, LibreOffice 프로필, 로그)
- 세 경로 모두 gitignore 대상이다.

**Testing**:
- pytest + pytest-httpx. Slack과 웹은 모킹하고, 샘플 이력서·포트폴리오는 픽스처 코드로 만든다(가상 인물).
- 렌더러는 주입식이라 기본 테스트는 고정 PDF를 쓴다.
- 실제 LibreOffice 테스트는 `-m render`이고 `JOB_RENDER=1`일 때만 돈다.

**Target Platform**: macOS 로컬(Claude Code). CI(ubuntu)는 기본 테스트만 돌린다.

**Project Type**: CLI + Claude Code 슬래시 명령(대화형 로컬 도구)

**Performance Goals**:
- 공고 1건 처리 ≤ 10분(SC-003). 렌더링 1회는 30초 이내다.
- `job inbox`는 대상 10건에 1분 이내다.

**Constraints**:
- 원본 불변(해시 검사)
- 원본에 없는 사실 생성 금지(근거 필수 + 검사)
- 디자인 속성 변경 금지
- 제출 자동화 금지
- 비밀값(`SLACK_BOT_TOKEN`)은 환경변수로만 받는다
- 개인정보 파일은 커밋하지 않는다

**Scale/Scope**:
- 사용자 1명, 한 번에 공고 1~10건
- 포트폴리오 슬라이드 ~30장, 이력서 1~3쪽

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|------|------|------|
| I. 모노레포 경계 | ✅(예외 1건) | 코드는 `agents/job-apply/`에 둔다. 공용 유틸은 `shared`의 retry·logging·config·files를 쓴다. Slack Web API 클라이언트는 지금 job-apply만 쓰므로 에이전트 안에 두고, 두 번째 사용처가 생기면 `shared/`로 옮긴다(R9). `.claude/commands/`는 경로가 고정된 예외다 |
| II. Python 3.12 + uv | ✅ | workspace 멤버로 추가하고 `uv.lock`에 반영한다. LibreOffice는 외부 실행 파일이다(doctor로 확인) |
| III. pytest 동반 | ✅ | 모든 CLI 단계에 단위·통합 테스트를 둔다. Slack·웹은 pytest-httpx로 모킹한다. 기본 `uv run pytest`는 네트워크·LibreOffice 없이 통과한다 |
| IV. 비밀값 환경변수 | ✅ | `SLACK_BOT_TOKEN`만 환경변수로 받는다. 채널 ID는 설정 파일에 둔다(비밀 아님, `load_yaml`의 비밀 키 검사 통과). `.env.example`을 제공한다. 로그에 토큰·Authorization 헤더를 남기지 않는다 |
| V. 재시도·로깅 | ✅ | Slack(429 `Retry-After` 존중)과 공고 가져오기는 `shared.retry`를 쓴다. LibreOffice 호출은 제한 시간을 두고, 실패를 구조화 로그로 남긴다 |
| VI. 스펙 명명 | ✅ | `003-job-tailor-applications` (`job:` 접두어) |
| job: 원본에 없는 내용 생성 금지 | ✅ | `tailor.json`의 모든 항목에 `source`가 필수다(스키마). `verify`는 원본에 없는 숫자·기술·부족 요건 키워드를 경고한다. 슬래시 명령 규칙 2 |
| job: 최종 제출은 사람이 | ✅ | 제출·로그인·폼 입력 기능이 없다. 슬래시 명령 규칙 4. 완료 답글에도 "제출은 직접" 문구를 넣는다 |
| job: 개인정보 커밋 금지 | ✅ | `.gitignore`를 `private/`, `applications/`, `.job-state/`로 바꾸고, `doctor`가 `git check-ignore`로 확인한다. 테스트는 가상 데이터만 쓴다 |

**Post-design re-check**: 위반 없음. 예외 1건은 Complexity Tracking에 적었다.

## Project Structure

### Documentation (this feature)

```text
specs/003-job-tailor-applications/
├── plan.md
├── research.md             # R1–R13
├── data-model.md           # 원본·공고 메시지·공고·지원 폴더·편집 계획·변경 내역·렌더링 문제
├── quickstart.md
├── contracts/
│   ├── cli.md              # job 서브커맨드, JOB_RESULT, 종료 코드
│   ├── slash-commands.md   # /job-run, /tailor, 공고별 처리 순서, 규칙
│   ├── slack-message.md    # 완료·본문 요청·중복·마감 답글
│   └── tailor-plan.schema.json
├── checklists/requirements.md
└── tasks.md                # /speckit-tasks
```

### Source Code (repository root)

```text
.claude/commands/job-run.md
.claude/commands/tailor.md
.claude/settings.json                    # Edit/Write 거부: agents/job-apply/private/**
.gitignore                               # data/private/ → private/, applications/, .job-state/
pyproject.toml                           # testpaths·pythonpath·isort에 job_apply 추가, render 마커

agents/job-apply/
├── .env.example                         # SLACK_BOT_TOKEN=
├── README.md
├── bin/job                              # uv run --package job-apply job "$@"
├── config/job.yaml                      # slack.channel_id, resume.font_files, fetch 설정
├── templates/resume.css
├── pyproject.toml
├── src/job_apply/
│   ├── cli.py                           # 서브커맨드, JOB_RESULT, 종료 코드
│   ├── config.py                        # job.yaml 모델, 경로
│   ├── models.py                        # Posting, Meta, TailorPlan, RenderIssue (pydantic)
│   ├── sources.py                       # 원본 확인·해시·base 복사·resume.txt 추출
│   ├── slack_api.py                     # Web API 클라이언트(history, replies, reactions, post, upload)
│   ├── inbox.py                         # 메시지 상태 계산, 대상 선택, ❓ 요청
│   ├── fetch.py                         # 공고 가져오기·JSON-LD/NEXT_DATA·trafilatura·실패 판정
│   ├── dedup.py                         # url_key 정규화, done 폴더 찾기
│   ├── folders.py                       # 이름 규칙, init, meta 상태 기계
│   ├── pptx_dump.py                     # portfolio.json 덤프
│   ├── pptx_apply.py                    # 문단 교체·삽입·삭제, 순서 변경
│   ├── design_guard.py                  # 디자인 보존 검사
│   ├── render.py                        # soffice 실행(주입식), PNG 미리보기
│   ├── layout_check.py                  # bbox 비교, base 문제 제외
│   ├── resume_pdf.py                    # md → HTML → PyMuPDF Story
│   ├── changes.py                       # changes.md 생성
│   ├── verify.py                        # 산출물·analysis 형식·근거 검사
│   ├── report.py                        # 완료·중복·마감 답글 문구, complete 단계 재개
│   └── doctor.py
└── tests/
    ├── conftest.py                      # 가상 이력서 PDF·포트폴리오 PPTX 생성, 가짜 렌더러, Slack 모킹
    ├── fixtures/                        # 고정 렌더링 PDF, 공고 HTML(JSON-LD, NEXT_DATA, 로그인 벽)
    └── test_*.py                        # 모듈별 + cli 흐름(tailor·job-run) + render 마커
```

**Structure Decision**:
- 기존 에이전트(`news-digest`, `troubleshoot-lab`)와 같은 `src/<package>` + `bin/` + `tests/` 구조를 쓴다. 슬래시 명령은 `troubleshoot-lab`처럼 CLI를 부르는 얇은 지침이다.
- PPTX 쪽은 덤프 → 적용 → 보호 → 렌더링 → 검사로 모듈을 나눈다. 각 단계를 따로 테스트할 수 있게 하기 위해서다.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `.claude/commands/job-*.md`, `tailor.md`, `.claude/settings.json`이 `agents/` 밖에 있음 (헌법 I) | Claude Code가 그 경로만 읽는다 | 다른 에이전트와 같은 기존 예외다 |
| Slack Web API 클라이언트를 `shared/`가 아닌 에이전트 안에 둠 (헌법 I·V의 SHOULD) | 현재 사용처가 job-apply 하나뿐이다. 재시도·로깅은 `shared.retry`·`shared.logging`을 그대로 쓴다 | 쓰는 곳이 하나인데 `shared/`에 두면 헌법 I의 "둘 이상이 함께 쓰는 코드" 기준에 맞지 않는다. 두 번째 사용처가 생기면 옮긴다 |
