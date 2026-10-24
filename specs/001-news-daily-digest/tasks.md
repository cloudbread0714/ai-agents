---

description: "Task list for news: 데일리 기술 뉴스 픽"
---

# Tasks: news: 데일리 기술 뉴스 픽

**Input**: Design documents from `/specs/001-news-daily-digest/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 헌법 원칙 III("모든 기능은 MUST pytest 테스트와 함께 작성")에 따라 테스트 작업을 포함한다.
외부 API(RSS, Claude, Slack)는 모두 모킹한다. 각 스토리의 테스트를 먼저 작성하고, 실패하는 것을 확인한 뒤 구현한다.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

- 공유 모듈: `shared/src/shared/`, `shared/tests/`
- 에이전트: `agents/news-digest/src/news_digest/`, `agents/news-digest/tests/`
- 워크플로: `.github/workflows/news-digest.yml`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: uv workspace와 두 패키지의 뼈대

- [X] T001 루트 uv workspace 생성: `pyproject.toml`(`[tool.uv.workspace] members = ["shared", "agents/*"]`, `requires-python = ">=3.12,<3.13"`, dev 그룹에 `pytest`, `pytest-httpx`, `ruff`), `.python-version`(3.12)
- [X] T002 [P] `shared` 패키지 생성: `shared/pyproject.toml`(deps: `httpx`, `tenacity`, `pyyaml`, `pydantic>=2`, `anthropic`), `shared/src/shared/__init__.py`, `shared/tests/__init__.py`
- [X] T003 [P] `news-digest` 패키지 생성: `agents/news-digest/pyproject.toml`(deps: `shared = { workspace = true }`, `feedparser`; `[project.scripts] news-digest = "news_digest.cli:main"`), `agents/news-digest/src/news_digest/__init__.py`, `agents/news-digest/tests/{unit,integration,fixtures}/`
- [X] T004 [P] `agents/news-digest/.env.example`에 키 이름만 작성(`ANTHROPIC_API_KEY=`, `SLACK_WEBHOOK_URL_MAIN=`, `SLACK_WEBHOOK_URL_TEST=`)
- [X] T005 [P] 루트 `pyproject.toml`에 ruff 설정(`target-version = "py312"`, line-length 100)과 pytest 설정(`testpaths = ["shared/tests", "agents/news-digest/tests"]`) 추가
- [X] T006 `uv sync --all-packages`를 실행해 `uv.lock`을 생성하고, 빈 테스트로 `uv run pytest`가 통과하는지 확인

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 모든 스토리가 쓰는 공유 모듈, 엔티티, 설정 로딩

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Tests (먼저 작성)

- [X] T007 [P] `shared/tests/test_retry.py`: 일시 오류 2회 후 성공하면 3번째 시도에 반환되는지, 최대 3회 소진 시 마지막 예외를 다시 던지는지, 재시도마다 경고 로그를 남기는지(대상·시도 횟수 포함) 테스트
- [X] T008 [P] `shared/tests/test_slack.py`: pytest-httpx로 테스트. 2xx이면서 본문이 `ok`이면 성공, 429/5xx는 재시도, 400은 즉시 실패, 로그에 웹훅 URL이 `https://hooks.slack.com/services/***`로 마스킹되는지 확인
- [X] T009 [P] `shared/tests/test_config.py`: YAML 로드, 필수 env가 없으면 변수 **이름만** 담은 예외 발생, 설정에 `*_key`/`*webhook*` 키가 있으면 거부
- [X] T010 [P] `shared/tests/test_llm.py`: `cost_usd(usage, pricing)` 계산(입력·출력 단가 per 1M tokens), 모델이 pricing에 없으면 오류
- [X] T011 [P] `agents/news-digest/tests/unit/test_models_settings.py`: settings 검증. "`llm.model`은 `pricing`에 있어야 한다", "`max_cost_usd_per_run`은 0보다 커야 한다", "`freshness_hours`는 24 이상"을 위반하면 오류. sources 검증: "`name`은 고유, `url`은 http(s), 활성 소스가 1개 이상"

### Implementation

- [X] T012 [P] `shared/src/shared/retry.py`: tenacity 기반 `retryable(max_attempts=3, retry_on=...)` 데코레이터(지수 백오프 + 지터, 시도마다 경고 로그)
- [X] T013 [P] `shared/src/shared/logging.py`: stderr에 한 줄당 JSON 하나를 쓰는 구조화 로거 `get_logger(name)`, 비밀값 마스킹 필터(웹훅 URL, `sk-ant-` 패턴)
- [X] T014 `shared/src/shared/slack.py`: `send_webhook(url, payload) -> None`(httpx, 타임아웃 10초, T012의 재시도 사용, 429/5xx/네트워크 오류만 재시도, `SlackSendError`), `mask_webhook(url)`
- [X] T015 [P] `shared/src/shared/config.py`: `load_yaml(path, model)`(Pydantic 검증), `require_env(*names)`, 비밀값 키 거부
- [X] T016 [P] `shared/src/shared/llm.py`: `make_client(max_retries)`가 `anthropic.Anthropic(max_retries=...)` 반환, `cost_usd(input_tokens, output_tokens, model, pricing)`
- [X] T017 `agents/news-digest/src/news_digest/models.py`: data-model.md의 Pydantic 모델 정의
  - `Category`
  - `Source`(`max_items: int | None`)
  - `Article`(`title` "공백 정리, 최대 300자", `excerpt` "HTML 제거, 최대 300자", `published_at` tz-aware UTC, `published_inferred`)
  - `SourceResult`
  - `DigestSelection`(`title_ko` max_length=80, `summary_ko` min 3 / max 5, `apply_points_ko` min 1 / max 2)
  - `DigestPost`, `PostRecord`
  - `RunStatus` enum(`POSTED`, `ALREADY_POSTED`, `COLLECT_FAILED`, `NO_NEW_ARTICLES`, `BUDGET_EXCEEDED`, `SELECT_FAILED`, `POST_FAILED`), `RunResult`
  - `Settings`, `SourcesFile`
- [X] T018 [P] `agents/news-digest/config/settings.yaml`, `agents/news-digest/config/sources.yaml`: contracts/config.schema.md 값으로 작성. 소스 9개는 research R4 표를 따른다
- [X] T019 `agents/news-digest/tests/fixtures/`: 샘플 RSS/Atom XML 4종(AWS 블로그, AWS What's New, hnrss, Atom 블로그), 깨진 XML 1종, 공용 `conftest.py`(고정 시각 `2026-10-25T23:00:00Z`, FakeAnthropic 테스트 더블, 임시 이력 경로)

**Checkpoint**: `uv run pytest shared agents/news-digest/tests/unit/test_models_settings.py` 통과

---

## Phase 3: User Story 1 - 매일 아침 가장 중요한 글 1개 받기 (Priority: P1) 🎯 MVP

**Goal**: RSS 수집 → Claude 1회 호출로 선정·요약 → 정상 채널에 지정 형식으로 1건 게시. 매일 KST 08:00에 cron으로 실행한다.

**Independent Test**: 새 글이 있는 RSS 픽스처와 FakeAnthropic으로 파이프라인을 실행했을 때, 정상 웹훅에 4개 항목(주제, 3~5줄 내용,
1~2개 적용할 점, 원문 링크)을 갖춘 메시지가 정확히 1건 전송되는지 확인한다. 실제 환경에서는 quickstart §2(드라이런)와 §3(테스트 채널 게시)으로 검증한다.

### Tests for User Story 1

- [X] T020 [P] [US1] `agents/news-digest/tests/unit/test_collector.py`: 픽스처 피드를 Article로 변환하는지 확인. 제목·발췌 300자 절단, HTML 제거, 발행일이 없으면 수집 시각 + `published_inferred=true`, 소스별 `max_items` 적용, 신선도(`freshness_hours`)가 지난 글 제외
- [X] T021 [P] [US1] `agents/news-digest/tests/unit/test_selector.py`: 프롬프트 계약(contracts/llm-output.md) 검증
  - system 프롬프트가 요청마다 바이트 단위로 동일한지
  - 후보가 `<candidate id=...>` 블록으로 감싸지고 URL이 포함되지 않는지
  - `selected_id`가 후보 목록에 없으면 `SELECT_FAILED`
  - `stop_reason == "refusal"`이면 `SELECT_FAILED`
  - 파싱이나 검증에 실패하면 1회 재요청
- [X] T022 [P] [US1] `agents/news-digest/tests/unit/test_formatter.py`: contracts/slack-message.md 블록 구조 검증. header에 주제, `•` 내용 3~5줄, 번호 매긴 적용할 점, `<url|source 원문 보기>`, mrkdwn `& < >` 이스케이프, test 모드면 `[TEST] ` 접두어, **링크는 Article.url에서 가져오는지**
- [X] T023 [P] [US1] `agents/news-digest/tests/unit/test_budget.py`: count_tokens 결과 + `max_tokens × 출력단가`가 상한을 넘으면 오래된 후보부터 줄여 다시 추정(최대 3회), 그래도 넘으면 `BUDGET_EXCEEDED`이고 LLM을 호출하지 않음
- [X] T024 [US1] `agents/news-digest/tests/integration/test_pipeline_happy.py`: 픽스처 RSS(pytest-httpx) + FakeAnthropic + 웹훅 모킹으로 실행하면 정상 웹훅에 1건 전송, `RunResult.status == POSTED`, `actual_cost_usd`가 기록되는지 확인

### Implementation for User Story 1

- [X] T025 [P] [US1] `agents/news-digest/src/news_digest/collector.py`: `collect(sources, settings, now) -> (list[Article], list[SourceResult])`
  - httpx(타임아웃 15초, User-Agent 명시) + `shared.retry` + `feedparser.parse(bytes)`
  - `ThreadPoolExecutor`로 병렬 수집
  - `bozo`이면서 entries가 0이면 해당 소스를 실패로 처리
- [X] T026 [P] [US1] `agents/news-digest/src/news_digest/normalize.py`: `normalize_url(url)`(research R5 규칙), `article_id(url) = sha256(normalized)[:16]`, 후보 간 중복은 소스 목록 순서상 먼저 나온 것을 유지, `max_candidates` 상한 적용(최신순)
- [X] T027 [US1] `agents/news-digest/src/news_digest/selector.py`
  - `build_system_prompt(settings)`(고정 문자열)
  - `build_user_message(candidates, today_kst, recent_categories, preferred)`
  - `estimate_and_trim(client, ...)`(count_tokens, research R3)
  - `select(client, ...) -> DigestSelection`: `messages.parse(output_format=DigestSelection, output_config={"effort": settings.llm.effort})`. fallbacks 설정이 `default`이면 beta 헤더 `server-side-fallback-2026-07-01` + `fallbacks="default"`를 보내며, 구현 전에 설치된 SDK에서 지원하는지 확인(research R2)
- [X] T028 [P] [US1] `agents/news-digest/src/news_digest/formatter.py`: `build_post_payload(selection, article, date_kst, test_mode)`, `escape_mrkdwn()`
- [X] T029 [US1] `agents/news-digest/src/news_digest/pipeline.py`: `run(settings, sources, env, target, dry_run, now, client, http) -> RunResult`의 정상 경로(수집 → 정규화 → 추정 → 선정 → 포맷 → 게시)와 비용 기록
- [X] T030 [US1] `agents/news-digest/src/news_digest/cli.py`: contracts/cli.md의 `--target main|test`, `--dry-run`, `--config-dir`, 필수 env 검증(누락 시 exit 2 + 변수 이름만 출력), stdout 마지막 줄에 RunResult 요약 JSON, 종료 코드 매핑
- [X] T031 [US1] `.github/workflows/news-digest.yml`(초안)
  - 트리거: `schedule: cron "40 22 * * *"`(2026-10-24 A1 결정으로 `0 23`에서 변경), `workflow_dispatch`(input `target`: main|test, 기본 test)
  - 실행: `astral-sh/setup-uv`, `uv sync --package news-digest --frozen`, `uv run --package news-digest news-digest --target ${{ inputs.target || 'main' }}`
  - Secrets 3개를 env로 주입
- [X] T032 [US1] 실제 피드 URL 9개의 응답과 파싱을 1회 확인하고, 실패하는 소스는 `sources.yaml`에서 URL을 고치거나 `enabled: false`로 바꾼 뒤 결과를 research.md R4에 반영

**Checkpoint**: US1 테스트 통과, `news-digest --dry-run`으로 실제 RSS와 Claude를 써서 게시물 1건 출력 확인(quickstart §2)

---

## Phase 4: User Story 2 - 중복 없이 주제가 고르게 섞인 게시 (Priority: P2)

**Goal**: 게시 이력 영속화, 이미 게시한 글 제외(다른 소스 포함), 하루 1회 가드, 인프라와 AI 에이전트 주제 균형

**Independent Test**: 이력 픽스처를 미리 채워 둔 상태에서 파이프라인을 실행했을 때 다음을 확인한다.
(a) 이력에 있는 글이 후보에서 빠진다.
(b) 최근 2건이 `infra`이면 프롬프트에 `선호 분류: ai_agent`가 들어간다.
(c) 오늘 날짜로 게시한 기록이 있으면 `ALREADY_POSTED`로 끝나고 아무것도 전송하지 않는다.

### Tests for User Story 2

- [X] T033 [P] [US2] `agents/news-digest/tests/unit/test_normalize.py`: `utm_*`·`ref`·`source` 쿼리 제거, fragment 제거, `www.`·끝 `/` 제거, https 통일, 나머지 쿼리 정렬. hnrss 항목과 AWS 블로그 항목이 같은 원문이면 같은 `article_id`가 되는지
- [X] T034 [P] [US2] `agents/news-digest/tests/unit/test_history.py`: contracts/history.schema.json 형식으로 로드·저장, 파일이 없으면 빈 이력, 원자적 쓰기(임시 파일 + rename), 저장할 때 365일 지난 항목 정리, `posted_today(kst_date)`, `"article_id"`가 `^[0-9a-f]{16}$` 패턴인지
- [X] T035 [P] [US2] `agents/news-digest/tests/unit/test_balance.py`: 최근 `balance_window`(2)건이 모두 같은 분류면 반대 분류 반환, 섞여 있거나 이력이 2건 미만이면 None
- [X] T036 [US2] `agents/news-digest/tests/integration/test_pipeline_history.py`
  - 시나리오 1: 최고 점수 글이 이미 게시된 글이면 다음 미게시 글을 선정
  - 시나리오 2: 같은 원문이 두 소스에 있으면 중복 처리
  - 시나리오 3: 같은 날 두 번째 실행이면 `ALREADY_POSTED`(전송 0건)
  - 시나리오 4: `--target test`나 `--dry-run`이면 이력을 바꾸지 않음
  - 시나리오 5: 선호 분류와 다른 글을 골랐는데 `balance_override_reason`이 없으면 경고 로그

### Implementation for User Story 2

- [X] T037 [P] [US2] `agents/news-digest/src/news_digest/history.py`: `load(path)`, `save(path, history)`(원자적 쓰기, 365일 정리), `posted_ids()`, `posted_today(date_kst)`, `recent_categories(n)`, `append(record)`. 경로 기본값은 `agents/news-digest/data/posted.json`이고 env `NEWS_DIGEST_HISTORY_PATH`로 바꿀 수 있음
- [X] T038 [P] [US2] `agents/news-digest/src/news_digest/balance.py`: `preferred_category(recent, window) -> Category | None`
- [X] T039 [US2] `agents/news-digest/src/news_digest/pipeline.py` 확장
  - 시작할 때 `posted_today` 가드 → `ALREADY_POSTED`(exit 0, 알림 없음)
  - 후보에서 `posted_ids` 제외
  - 선호 분류를 selector에 전달
  - **게시 성공 후에만** `--target main`일 때 `PostRecord`를 추가하고 저장(FR-018)
- [X] T040 [US2] `agents/news-digest/src/news_digest/cli.py`에 `--force` 추가. `--target test` 또는 `--dry-run`과 함께가 아니면 exit 2
- [X] T041 [P] [US2] `agents/news-digest/data/posted.json` 초기 파일 `{"version": 1, "posts": []}`
- [X] T042 [US2] `.github/workflows/news-digest.yml` 확장
  - `permissions: contents: write`
  - `concurrency: { group: news-digest, cancel-in-progress: false }`
  - 실행 후 `git diff --quiet agents/news-digest/data/posted.json || (git commit -m "chore(news): update posted history [skip ci]" && git push)`, 커밋 작성자는 `github-actions[bot]`

**Checkpoint**: US1과 US2 테스트 모두 통과. 이력이 쌓인 상태에서도 중복 없이 1건만 게시

---

## Phase 5: User Story 3 - 실패 시 테스트 채널로 알림 (Priority: P3)

**Goal**: 실패 상태별로 테스트 채널에만 알리고, 정상 채널은 오염시키지 않음

**Independent Test**: 다음 상황을 모킹으로 만들어 각 상태에서 테스트 웹훅에만 전송되는지(정상 웹훅 0건), 종료 코드가 contracts/cli.md와 맞는지 확인한다.
상황: 전 소스 실패, 후보 0건, 비용 초과, LLM 거절, 정상 게시 실패, 일부 소스 실패, 관련도 낮음.

### Tests for User Story 3

- [X] T043 [P] [US3] `agents/news-digest/tests/unit/test_alerts.py`: contracts/slack-message.md의 오류·경고 알림 블록(상태, 단계, 원인, 실행 시각 KST, 후보 수, 실패 소스, Actions run URL은 `GITHUB_SERVER_URL`/`GITHUB_REPOSITORY`/`GITHUB_RUN_ID`가 있을 때만), 원인 텍스트에 비밀값이 없는지
- [X] T044 [US3] `agents/news-digest/tests/integration/test_pipeline_failures.py`: 상태별 파라미터화 테스트
  - `COLLECT_FAILED` → exit 1
  - `NO_NEW_ARTICLES` → exit 0
  - `BUDGET_EXCEEDED` → exit 1
  - `SELECT_FAILED`(refusal / 검증 실패) → exit 1
  - `POST_FAILED` → exit 1, 이력 미기록
  - 부분 실패 → `POSTED` + 경고 1건
  - `low_relevance` → `POSTED` + 경고 1건
  - 테스트 웹훅 전송까지 실패 → stderr 로그만 남기고 exit 1

### Implementation for User Story 3

- [X] T045 [P] [US3] `agents/news-digest/src/news_digest/alerts.py`: `build_alert_payload(run_result, stage, now)`, `build_warning_payload(kind, details)`
- [X] T046 [US3] `agents/news-digest/src/news_digest/pipeline.py` 확장
  - 각 단계의 예외를 `RunStatus`로 매핑(data-model.md 상태 전이)
  - 실패하면 테스트 웹훅으로 알림
  - 부분 수집 실패와 `low_relevance`는 게시 후 경고
  - 알림 전송이 실패하면 로그만 남김
- [X] T047 [US3] `agents/news-digest/src/news_digest/cli.py`의 종료 코드 매핑을 완성하고(0: POSTED / ALREADY_POSTED / NO_NEW_ARTICLES, 1: 나머지 실패, 2: 사용법), 처리되지 않은 예외가 나도 테스트 채널 알림을 시도하는 최상위 핸들러 추가
- [X] T048 [US3] `.github/workflows/news-digest.yml`에 `if: failure()` step 추가: 이력 push 실패나 잡 실패 시 `SLACK_WEBHOOK_URL_TEST`로 `WARNING: history not pushed` 또는 잡 실패 알림을 curl로 전송(URL은 secret으로만 참조)
- [X] T049 [P] [US3] `agents/news-digest/tests/fixtures/config-broken/`: 모든 소스가 존재하지 않는 URL인 설정(quickstart §4용)

**Checkpoint**: 모든 스토리 테스트 통과

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T050 [P] `agents/news-digest/README.md`: 개요, 환경변수, 소스 추가·삭제 방법, 수동 실행, 비용 설정, 모델 변경 시 `pricing` 함께 수정할 것
- [X] T051 [P] 루트 `README.md`: 모노레포 구조, uv workspace 사용법, 에이전트 목록
- [X] T052 `uv run ruff check . && uv run ruff format --check .` 통과시키기
- [X] T053 보안 점검
  - `git grep -nE "hooks.slack.com/services/[A-Z0-9]|sk-ant-"` 결과가 0건인지
  - `.env`가 커밋되지 않았는지
  - 로그 마스킹 테스트가 통과하는지
- [ ] T054 quickstart.md §1~§4 실행(로컬), §5 Actions 수동 실행(`target=test`) 검증
- [ ] T055 main 병합 후 `workflow_dispatch target=main`으로 1회 실행하고, 같은 날 다시 실행해 `ALREADY_POSTED`가 나오는지 확인한 뒤 첫 schedule 실행의 시작 지연을 기록(research R9, SC-001)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 의존성 없음
- **Foundational (Phase 2)**: Setup 완료 후 진행. 모든 스토리를 막는다
- **US1 (Phase 3)**: Foundational 완료 후 진행
- **US2 (Phase 4)**: Foundational 완료 후 진행. `pipeline.py`, `cli.py`, 워크플로 파일을 US1과 함께 수정하므로 **US1 이후에 순차 진행 권장**
- **US3 (Phase 5)**: Foundational 완료 후 진행. 같은 이유로 US2 이후 권장
- **Polish (Phase 6)**: 원하는 스토리를 모두 마친 뒤

### User Story Dependencies

- **US1**: 독립. MVP
- **US2**: `history.py`, `balance.py`, `normalize` 테스트는 US1과 병렬로 진행할 수 있다. 파이프라인 통합(T039)은 T029 이후
- **US3**: `alerts.py`(T045)는 병렬로 진행할 수 있다. 파이프라인 통합(T046)은 T029 이후

### Within Each User Story

- 테스트를 먼저 작성해 실패를 확인한다 → 독립 모듈 → `pipeline.py` 통합 → `cli.py` → 워크플로
- 각 체크포인트에서 `uv run pytest`로 전체를 통과시킨 뒤 커밋한다

## Parallel Example: User Story 1

```bash
# 테스트 동시 작성
Task: "test_collector.py in agents/news-digest/tests/unit/"
Task: "test_selector.py in agents/news-digest/tests/unit/"
Task: "test_formatter.py in agents/news-digest/tests/unit/"
Task: "test_budget.py in agents/news-digest/tests/unit/"

# 독립 모듈 동시 구현
Task: "collector.py"   Task: "normalize.py"   Task: "formatter.py"
```

## Parallel Example: User Story 2 / 3 (US1 진행 중에도 가능)

```bash
Task: "history.py + test_history.py"
Task: "balance.py + test_balance.py"
Task: "alerts.py + test_alerts.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 → Phase 2 → Phase 3
2. **STOP and VALIDATE**: `--dry-run`, `--target test`(quickstart §2, §3)
3. 이 시점에는 이력이 없으므로 **schedule로 정상 채널을 운영하지 않는다**. US2 전까지는 `workflow_dispatch target=test`로만 실행한다

### Incremental Delivery

1. Setup + Foundational
2. US1 → 테스트 채널에서 품질 확인
3. US2 → 중복 방지와 이력 커밋까지 갖추면 **정상 채널 운영 시작 가능**
4. US3 → 실패 알림 완성
5. Polish → main 병합 → schedule 운영

## Notes

- [P] tasks = different files, no dependencies
- 실제 Claude와 Slack 호출은 quickstart 수동 검증(T032, T054, T055)에서만 한다. 비용이 발생하고 채널에 게시된다
- 체크포인트마다 커밋한다(커밋 메시지 접두어 `feat(news):`, `feat(shared):`)

## Implementation Notes (2026-10-24)

- **analyze 반영**:
  - D1: 각 패키지 `pyproject.toml`에 pytest 설정을 둬서 루트, `shared/`, `agents/news-digest/` 모두에서 `uv run pytest`가 통과한다.
  - D2: T048의 curl에 `--retry 3 --retry-all-errors`를 넣었다.
  - C1: 재요청 전에 남은 예산을 다시 확인한다(`test_retry_skipped_when_remaining_budget_too_small`).
  - U1: conftest를 `tests/conftest.py`에 두고, import할 수 있는 도우미는 `tests/nd_support.py`로 분리했다.
  - U2: `--import-mode=importlib`을 쓰고 `tests/__init__.py`는 만들지 않았다.
  - I2: T033(normalize 테스트)을 US1에서 T026보다 먼저 작성했다.
  - U3: push 전에 `git pull --rebase`를 하고 최대 3회 재시도한다.
  - I5: schedule 트리거는 US2(T042)에서 활성화했다.
- **R2 확인**: anthropic SDK 2.3.0의 `client.beta.messages.parse`가 `betas`와 `fallbacks="default"`를 지원한다.
  fallback이 꺼져 있으면 GA `client.messages.parse`를 쓴다. 가격표에 없는 fallback 모델이 응답하면 가장 비싼 단가로 비용을 계산한다.
- **T032**: LangChain 피드 URL을 `https://www.langchain.com/blog/rss.xml`로 교체했다(research R4).
- **T054**: §1(테스트, 루트와 각 디렉터리)과 §4(broken config 드라이런 → `COLLECT_FAILED`, exit 1)만 실행했다.
  §2, §3, §5는 `ANTHROPIC_API_KEY`와 Slack 웹훅이 있어야 해서 아직 하지 못했다.
- **로컬 환경**: iCloud 동기화 폴더 안의 `.venv` 파일에 `hidden` 플래그가 붙어 editable `.pth`가 무시된다.
  그래서 pytest `pythonpath`에 `src`를 추가했다. 해결 방법은 README에 적었다.
