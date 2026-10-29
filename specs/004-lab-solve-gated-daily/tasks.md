---

description: "Task list for lab: 해결해야 다음 문제가 열리는 오늘의 문제"
---

# Tasks: lab: 해결해야 다음 문제가 열리는 오늘의 문제

**Input**: Design documents from `/specs/004-lab-solve-gated-daily/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: 포함한다. 헌법 III(모든 기능은 pytest 동반, 외부 API는 모킹)에 따라 각 스토리에 테스트 작업을 먼저 둔다.
Slack은 모두 `httpx_mock`으로 모킹하고, 시계는 기존 lab 테스트처럼 `now`를 주입한다.

**Organization**: 사용자 스토리별로 묶는다. 경로는 레포 루트 기준이다. `lab/` = `agents/troubleshoot-lab/`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 다른 파일이고 미완료 작업에 의존하지 않아 병렬 가능
- **[Story]**: US1(풀어야 다음 문제), US2(자동 ✅), US3(주간 요약)

---

## Phase 1: Setup

**Purpose**: 비밀값 키 이름과 로컬 실행 준비

- [X] T001 [P] `agents/troubleshoot-lab/.env.example`을 키 이름만으로 다시 쓰기: `SLACK_BOT_TOKEN=`, `SLACK_LAB_CHANNEL_ID=`, `SLACK_USER_ID=`, `SLACK_WEBHOOK_URL_TEST=`, `LAB_SLACK_TARGET=test` (`SLACK_WEBHOOK_LAB_URL` 삭제). 파일을 git에 추가하고 `.env`가 `.gitignore`에 걸리는지 `git check-ignore agents/troubleshoot-lab/.env`로 확인
- [X] T002 [P] `agents/troubleshoot-lab/bin/lab`에서 `exec` 전에 `agents/troubleshoot-lab/.env`가 있으면 읽어 내보내되 이미 셸에 있는 값은 덮어쓰지 않게 하기(research R8). 예: 각 `KEY=VALUE` 줄에 대해 `[ -z "${!KEY+x}" ] && export KEY=VALUE`. 주석·빈 줄은 건너뛴다

---

## Phase 2: Foundational (모든 스토리의 전제)

**Purpose**: Slack 봇 토큰 API와 게시 기록 확장. 이게 끝나야 어떤 스토리도 시작할 수 없다

**⚠️ CRITICAL**: 이 단계가 끝나기 전에는 스토리 작업을 시작하지 않는다

### Tests

- [X] T003 [P] `shared/tests/test_slack.py`에 Web API 테스트 추가(contracts/slack-api.md "테스트 계약"): `auth_test`가 `user_id` 반환 / `post_message`가 `(channel, ts)` 반환하고 `thread_ts`를 본문에 실음 / `get_reactions`가 `full=true` 쿼리로 `{name: set(users)}` 반환, 반응 없으면 `{}` / `add_reaction`이 `already_reacted`에 False / `ok:false, error:"not_in_channel"`은 재시도 없이 `SlackApiError` / `message_not_found`는 `SlackMessageGone` / 429→성공은 재시도 후 성공 / 5xx 3회는 소진 후 `SlackApiError` / 모든 경우 `Authorization: Bearer xoxb-test-secret` 헤더로만 전송되고 예외 문자열·`caplog`에 `xoxb-test-secret`이 없음
- [X] T004 [P] `agents/troubleshoot-lab/tests/unit/test_posted.py`에 확장 필드 테스트 추가: 신규 필드 없는 기존 항목을 읽으면 `channel/ts/outcome/resolved_at/reposted_at = None`, `reminders = []` / "`channel`과 `ts`는 둘 다 있거나 둘 다 없다" 위반 시 검증 오류 / "`outcome`은 `channel`·`ts`가 있을 때만 값이 있다" 위반 시 오류 / "`outcome=solved` ⇔ `resolved_at`이 있다" 위반 시 오류 / "`reminders`는 중복 없이 오름차순이고, 모두 `date_kst`보다 뒤다" 위반 시 오류 / "`outcome=open`인 항목은 최대 1개" 위반 시 `Posted` 검증 오류 / `open_post()`가 열린 항목 또는 None 반환 / `save()`가 1년 지난 항목을 지워도 `outcome=open` 항목은 남김

### Implementation

- [X] T005 `shared/src/shared/slack.py`에 봇 토큰 API 추가(contracts/slack-api.md, research R1·R3·R12): `SlackApiError(method, code)`(메시지 `"<method>: <code>"`), `SlackMessageGone(SlackApiError)`, 내부 `_call(token, method, *, json=None, params=None, client, base_delay)` — `https://slack.com/api/<method>`, 헤더 `Authorization: Bearer`, `ok:false` 분기, 429/5xx/`httpx.TransportError`만 `retryable(target=f"slack-api:{method}", max_attempts=3)`로 재시도(429는 `Retry-After`를 10초 상한으로 존중), 나머지 오류 코드는 즉시 실패. 공개 함수 `auth_test`, `post_message(token, channel, payload, *, thread_ts=None)`, `get_reactions(token, channel, ts)`(GET, `full=true`), `add_reaction(token, channel, ts, name)`. 최종 실패는 메서드·시도 횟수·오류 코드로 로깅. T003 통과
- [X] T006 `agents/troubleshoot-lab/src/troubleshoot_lab/models.py`의 `DailyPost`에 선택 필드 추가(data-model.md): `channel: str | None = None`, `ts: str | None = None`, `outcome: Literal["open", "solved"] | None = None`, `resolved_at: AwareDatetime | None = None`, `reminders: list[date] = []`(Field default_factory), `reposted_at: AwareDatetime | None = None`. `DailyPost` 검증기에 T004의 네 규칙, `Posted` 검증기에 "열린 항목 최대 1개" 추가. `kind`의 `catchup`은 옛 기록 읽기용으로 남김
- [X] T007 `agents/troubleshoot-lab/src/troubleshoot_lab/posted.py`에 `open_post(posted) -> DailyPost | None` 추가, `save()`의 보존 규칙에서 `outcome == "open"` 항목은 기간과 무관하게 유지(contracts/posted.md 호환 규칙). T004 통과

**Checkpoint**: `uv run pytest shared agents/troubleshoot-lab -q` 통과(기존 테스트 포함)

---

## Phase 3: User Story 1 - 풀어야 다음 문제가 올라온다 (Priority: P1) 🎯 MVP

**Goal**: 아침 실행이 열린 문제의 ✅를 확인해, 있으면 해결 기록 + 다음 문제 게시, 없으면 하루 한 번 스레드 리마인드(3일 이상이면 힌트 1단계)

**Independent Test**: quickstart.md §1 표의 daily 행들(US1, FR-006, R9, FR-024, FR-022, 기존 기록)을 `httpx_mock`으로 재현해 상태·기록·요청 수를 확인

### Tests for User Story 1

- [X] T008 [P] [US1] 새 파일 `agents/troubleshoot-lab/tests/unit/test_gate.py`: `judge(reactions, user_id, bot_id)`가 `white_check_mark` 또는 `heavy_check_mark`를 학습자·봇이 달았으면 `solved`, 다른 사람만 달았으면 `unsolved`, `fast_forward`(⏭️)만 있으면 `unsolved` / `reminder_due(post, today)`가 오늘이 `reminders`에 있으면 False / `hint_due(post, today)`가 `(today - date_kst).days >= 3`에서 True, 2에서 False / `hint_source(post, catalog)`가 본 문제가 시나리오면 그 ID, 미션이면 `second_id`의 시나리오, 둘 다 아니면 None
- [X] T009 [P] [US1] `agents/troubleshoot-lab/tests/unit/test_planner.py`: catchup 관련 테스트를 "밀린 문제가 3개 이상이어도 `kind`는 `day`/`extra`/`review` 중 하나이고 `catchup`은 나오지 않는다"로 바꾸기. 마지막 게시가 `day=2`면 날짜가 며칠 지나도 다음은 `day=3`
- [X] T010 [P] [US1] `agents/troubleshoot-lab/tests/unit/test_messages_daily.py`: 오늘의 문제 맨 아래 context에 contracts/slack-message.md의 안내 문구가 있음, "밀린 문제" 줄 없음 / `build_reminder(title, days, hint=None)`이 `⏳ 아직 해결 전이에요 · 게시 후 {N}일`과 `text`=`아직 해결 전: {제목}`을 만들고, `hint`가 있으면 `💡 힌트 1단계` 블록과 `더 필요하면 /lab-hint`를 붙이며 `<`,`>`,`&`를 이스케이프 / 재게시 본문 맨 위 context `이전 메시지를 찾을 수 없어 같은 문제를 다시 올려요.`
- [X] T011 [US1] `agents/troubleshoot-lab/tests/integration/test_daily.py`를 봇 토큰 흐름으로 갱신(환경 픽스처에 `SLACK_BOT_TOKEN=xoxb-test-secret`, `SLACK_LAB_CHANNEL_ID=C0LAB`, `SLACK_USER_ID=U0ME`, `SLACK_WEBHOOK_URL_TEST`; `auth.test`는 `U0BOT` 반환). quickstart.md §1의 daily 행을 각각 테스트로: 열린 문제 없음→`POSTED`+`channel/ts/outcome=open` 저장 / 학습자 ✅→해결(`resolved_at`)+다음 문제 `POSTED`, 열린 항목 1개, 요약 `daily.resolved_id` / 봇(`U0BOT`) ✅→같음 / 다른 사람 ✅만→`REMINDED` / 같은 날 두 번→`REMINDED` 후 `ALREADY_REMINDED`, `chat.postMessage`(thread_ts) 1건 / 게시 후 3일→리마인드 본문에 시나리오 `hints.md`의 `## 힌트 1` 내용, `daily.hint_included=true`, 진행 기록에 `hint_opened` 없음 / ⏭️만→`REMINDED` / `reactions.get`이 `message_not_found`→`REPOSTED`, `ts` 교체, `reposted_at`, 테스트 웹훅 경고 1건 / `reactions.get` 5xx 소진→`POST_FAILED`, `posted.json` 바이트 동일, 테스트 웹훅 알림 / 해결 판정 후 다음 게시 실패→`POST_FAILED`, `posted.json` 바이트 동일 / 필수 값 하나 누락→종료 코드 2, stderr에 이름만, 토큰 문자열 없음 / 신규 필드 없는 기존 기록만→`POSTED` / `--target test`→`reactions.get` 요청 0건, 기록 불변 / `--force`가 반응 판정을 건너뛰지 않음 / 기존 웹훅 lab 게시 테스트는 삭제

### Implementation for User Story 1

- [X] T012 [P] [US1] 새 파일 `agents/troubleshoot-lab/src/troubleshoot_lab/gate.py`: Slack 호출 없는 순수 함수 `CHECK_MARKS = {"white_check_mark", "heavy_check_mark"}`, `judge(reactions, user_id, bot_id) -> Literal["solved","unsolved"]`(✅ 외 반응 무시, FR-006·FR-007), `reminder_due`, `hint_due`(`HINT_AFTER_DAYS = 3`), `hint_source`(research R7). T008 통과
- [X] T013 [P] [US1] `agents/troubleshoot-lab/src/troubleshoot_lab/planner.py`에서 `CATCHUP_AT` 분기 제거(research R5): 항상 `day`→`extra`→`review` 순서. `backlog()`는 메시지의 백로그 표시가 사라지므로 호출처(T015·T024)를 정리한 뒤 쓰이지 않으면 삭제. T009 통과
- [X] T014 [P] [US1] `agents/troubleshoot-lab/src/troubleshoot_lab/messages.py`: `build_daily`에서 catchup 형식·백로그 줄 제거, 하단 안내 문구 추가, `build_reminder(title, days, hint)`와 재게시용 `reposted=True` 옵션 추가(contracts/slack-message.md). T010 통과
- [X] T015 [US1] `agents/troubleshoot-lab/src/troubleshoot_lab/daily.py`를 contracts/cli.md `lab daily` 동작으로 재작성: `RunStatus`에 `REMINDED`, `REPOSTED`, `ALREADY_REMINDED` 추가(FAILURES에는 넣지 않음), 상수 `BOT_TOKEN="SLACK_BOT_TOKEN"`, `LAB_CHANNEL="SLACK_LAB_CHANNEL_ID"`, `LEARNER="SLACK_USER_ID"`, `LAB_WEBHOOK` 삭제. lab 대상 흐름(research R6): 오늘 게시 있음→`ALREADY_POSTED` / `auth_test` / `open_post` 없음→게시 / 있음→`get_reactions`→`gate.judge`: solved면 `outcome="solved"`, `resolved_at=now` 후 `plan_today`로 다음 게시, unsolved면 `reminder_due`일 때 `post_message(thread_ts=open.ts)`로 리마인드 후 `reminders`에 오늘 추가(아니면 `ALREADY_REMINDED`), `SlackMessageGone`이면 같은 항목 재게시 후 `channel/ts/reposted_at` 갱신 + `_notify` 경고. 모든 Slack 호출이 성공한 경우에만 `posted_mod.save`. `SlackApiError`는 `POST_FAILED`(stage `"post"`, error는 예외 문자열). `PartResult`에 `resolved_id`, `hint_included` 추가. test 대상·dry-run은 반응 조회 없이 열린 문제가 있으면 리마인드 미리 보기, 없으면 다음 문제 미리 보기를 테스트 웹훅/stdout으로
- [X] T016 [US1] `agents/troubleshoot-lab/src/troubleshoot_lab/cli.py`의 `_daily`: `--target lab` 필수 값을 `SLACK_BOT_TOKEN`, `SLACK_LAB_CHANNEL_ID`, `SLACK_USER_ID`, `SLACK_WEBHOOK_URL_TEST`로 교체(contracts/cli.md 필수 환경변수). 누락 시 기존처럼 이름만 출력하고 종료 코드 2. T011 통과
- [X] T017 [US1] `.github/workflows/troubleshoot-lab.yml`의 "Post daily problem" 단계 env에서 `SLACK_WEBHOOK_LAB_URL` 제거, `SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}`, `SLACK_LAB_CHANNEL_ID: ${{ secrets.SLACK_LAB_CHANNEL_ID }}`, `SLACK_USER_ID: ${{ secrets.SLACK_USER_ID }}` 추가. 커밋 단계·알림 단계는 그대로

**Checkpoint**: US1만으로 "✅가 있어야 다음 문제" 흐름이 완성된다(학습자가 직접 ✅). `uv run pytest agents/troubleshoot-lab -q` 통과

---

## Phase 4: User Story 2 - 실습에서 해결하면 ✅가 자동으로 달린다 (Priority: P2)

**Goal**: `/lab-check`가 열린 문제의 모든 항목이 끝났다고 확인하면 봇이 그 메시지에 ✅를 단다. 실패해도 검증 결과는 그대로

**Independent Test**: 열린 문제가 기록된 임시 `posted.json`과 `httpx_mock`으로 `lab check` 결과의 `slack_reaction` 값과 `reactions.add` 요청 수를 확인

### Tests for User Story 2

- [X] T018 [P] [US2] 새 파일 `agents/troubleshoot-lab/tests/unit/test_reactor.py`: 열린 문제의 유일한 항목을 해결→`added`, `reactions.add`(name `white_check_mark`, 기록된 channel/ts) 1건 / `already_reacted`→`already` / `second_id`가 남음→`partial`, 요청 0건, 남은 항목 제목 반환 / 열린 문제와 다른 항목→`not_open`, 요청 0건 / 로컬 기록에 열린 문제 없음→`not_open`, "git pull" 안내 문구 / `SLACK_BOT_TOKEN` 없음→`no_config`, 요청 0건 / 5xx 소진→`failed`, 오류 코드 포함 / 미션 항목은 `mission_completed` 기준으로 완료 판단
- [X] T019 [P] [US2] `agents/troubleshoot-lab/tests/unit/test_learn.py`: 가짜 Reactor 주입 시 시나리오 해결·미션 완료 뒤 Reactor가 1번 불리고 출력 끝에 contracts/cli.md 표의 문구, `LAB_RESULT`에 `slack_reaction` / 검증 실패·`giveup`에서는 불리지 않고 필드 없음 / Reactor가 `failed`여도 종료 코드·진행 기록·`sync_suggested` 동일 / Reactor 미주입(None)이면 기존 출력 그대로

### Implementation for User Story 2

- [X] T020 [US2] 새 파일 `agents/troubleshoot-lab/src/troubleshoot_lab/reactor.py`: `Reactor(lab_root, env, http, base_delay)`의 `after_done(item_id, progress) -> ReactionResult(status, message)`. 로컬 `data/posted.json`의 `open_post` 확인 → 항목 포함 여부 → 모든 항목 완료 여부(시나리오 `scenario_status == "solved"`, 미션은 `done_missions`) → `add_reaction(..., "white_check_mark")`. 상태값은 `added|already|partial|not_open|no_config|failed`, 문구는 contracts/cli.md 표 그대로. 예외를 밖으로 던지지 않는다(FR-015). T018 통과
- [X] T021 [US2] `agents/troubleshoot-lab/src/troubleshoot_lab/learn.py`: `Learner.__init__`에 `reactor: Reactor | None = None` 추가, `_check`의 `scenario_solved` 기록 직후와 `_check_mission`의 `mission_completed` 기록 직후 `reactor.after_done` 호출, 문구를 출력 끝에 붙이고 `Outcome`에 `slack_reaction` 필드(결과 dict에는 값이 있을 때만) 추가. `giveup`은 변경 없음(FR-014). T019 통과
- [X] T022 [US2] `agents/troubleshoot-lab/src/troubleshoot_lab/cli.py`: 학습 명령용 `Learner` 생성 시 `Reactor(LAB_ROOT, os.environ, httpx.Client(), base_delay=1.0)` 주입. 테스트 경로(`environ` 주입)에서는 주입받은 env를 쓰게 해 `tests/unit/test_cli_learn.py`가 실제 네트워크를 타지 않게 한다
- [X] T023 [P] [US2] `.claude/commands/lab-check.md`: 출력 마지막의 "✅를 달았어요/달지 못했어요" 줄은 그대로 보여 준다는 규칙 추가. `no_config`·`failed`·`not_open`이면 "Slack에서 직접 ✅를 달면 된다"고 한 줄 덧붙이는 것만 허용

**Checkpoint**: US1 + US2로 학습자가 Slack을 열지 않고도 다음 날 다음 문제를 받는다(SC-004)

---

## Phase 5: User Story 3 - 일요일 요약에서 한 주의 진행을 본다 (Priority: P3)

**Goal**: 주간 요약에 해결 수와 미해결로 멈춘 날 수, 지금 열린 문제를 싣는다

**Independent Test**: 해결 2건·리마인드 3일이 있는 한 주 치 `posted.json`으로 일요일 실행 시 요약 문구 확인

### Tests for User Story 3

- [X] T024 [P] [US3] `agents/troubleshoot-lab/tests/unit/test_weekly.py`: 이번 주(월~일 KST) `resolved_at` 2건→`solved_posts == 2`, 지난주 것은 제외 / 이번 주 `reminders` 날짜 3개→`stalled_days == 3` / 열린 문제→`open_post == (제목, 경과 일수)`, 없으면 None / `backlog` 필드 없음. `build_weekly` 출력에 `오늘의 문제: 해결 2 · 미해결로 멈춘 날 3일`, `지금 열린 문제: {제목} (게시 후 N일)`, 열린 문제가 없으면 그 줄 없음, "밀린 문제" 문구 없음
- [X] T025 [P] [US3] `agents/troubleshoot-lab/tests/integration/test_daily.py`: 일요일 + 열린 문제 미해결이면 리마인드와 주간 요약이 모두 게시되고 상태 `REMINDED`, `weekly.status == "POSTED"`(US3-2)

### Implementation for User Story 3

- [X] T026 [US3] `agents/troubleshoot-lab/src/troubleshoot_lab/weekly.py`: `WeeklySummary`에 `solved_posts`, `stalled_days`, `open_post` 추가, `backlog` 삭제, 계산은 data-model.md "주간 요약 변경"과 research R10대로 `posted.json`만 사용. `planner.backlog` 의존 제거. T024 통과
- [X] T027 [US3] `agents/troubleshoot-lab/src/troubleshoot_lab/messages.py`의 `build_weekly`: contracts/slack-message.md "주간 요약" 줄 추가·교체. T024·T025 통과

**Checkpoint**: 세 스토리 모두 독립적으로 동작

---

## Phase 6: Polish & Cross-Cutting

- [X] T028 [P] `agents/troubleshoot-lab/README.md`: 오늘의 문제 흐름(✅가 있어야 다음 문제, 리마인드, 3일 힌트, `/lab-check` 자동 ✅, 문제 풀기 전 `git pull`), Slack 앱 준비(봇 권한 `chat:write`·`reactions:read`·`reactions:write`, 채널 초대), Secrets 3개, `.env` 설정으로 갱신. catchup·`SLACK_WEBHOOK_LAB_URL` 설명 삭제
- [X] T029 [P] `specs/002-lab-troubleshoot-practice/contracts/`의 `cli.md`·`slack-message.md` 맨 위에 "004에서 변경: specs/004-lab-solve-gated-daily/contracts/ 참고" 한 줄 추가
- [X] T030 레포 전체에서 `SLACK_WEBHOOK_LAB_URL`, `catchup`(옛 기록 읽기용 `Literal` 제외), `backlog` 잔여 참조를 `grep`으로 확인해 정리
- [X] T031 `uv run ruff check . && uv run ruff format --check . && uv run pytest` 통과 확인, 출력·로그·커밋 diff에 비밀값 없음 확인(SC-007)
- [ ] T032 quickstart.md §2 수동 확인 순서를 실제 Slack으로 수행(사용자 준비 후). Secrets 등록과 봇 채널 초대는 사용자가 직접 한다

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 의존 없음
- **Foundational (Phase 2)**: Setup 뒤. 모든 스토리를 막는다
- **US1 (Phase 3)**: Foundational 뒤
- **US2 (Phase 4)**: Foundational 뒤. US1의 `gate`·`daily` 없이도 테스트 가능하지만(로컬 `posted.json`만 읽음), 실제로 쓸모 있으려면 US1이 `channel/ts`를 기록해야 한다
- **US3 (Phase 5)**: Foundational 뒤. 지표가 의미 있으려면 US1이 `resolved_at`·`reminders`를 기록해야 한다. T026은 T013(backlog 정리)과 같은 함수를 건드리므로 T013 뒤
- **Polish (Phase 6)**: 원하는 스토리가 끝난 뒤

### Within Each User Story

- 테스트 작업을 먼저 쓰고 실패를 확인한 뒤 구현
- US1: T012·T013·T014(병렬) → T015 → T016 → T017
- US2: T020 → T021 → T022, T023은 아무 때나
- US3: T026 → T027

### Parallel Opportunities

- Phase 1: T001, T002
- Phase 2: T003, T004 동시 작성 → T005와 T006·T007은 다른 패키지라 병렬
- US1: T008, T009, T010 동시 작성 → T012, T013, T014 동시 구현
- US2: T018, T019 동시 작성, T023은 독립
- US3: T024, T025 동시 작성
- US2와 US3는 Foundational 뒤 서로 병렬 가능(파일 겹침 없음, 단 `messages.py`는 US1의 T014 뒤)

## Parallel Example: User Story 1

```bash
# 테스트 먼저(서로 다른 파일)
Task: "T008 tests/unit/test_gate.py"
Task: "T009 tests/unit/test_planner.py catchup 제거 반영"
Task: "T010 tests/unit/test_messages_daily.py 안내·리마인드·재게시"

# 구현(서로 다른 파일)
Task: "T012 gate.py"
Task: "T013 planner.py catchup 제거"
Task: "T014 messages.py 리마인드·안내"
```

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 + Phase 2
2. Phase 3(US1) → `uv run pytest` 통과 → quickstart §2의 1~3단계로 실제 Slack 확인(학습자가 직접 ✅)
3. 여기서 PR을 내도 "✅ 없으면 새 문제 없음"이 완성된다

### Incremental Delivery

1. US1 → 직접 ✅로 운영 시작
2. US2 → `/lab-check` 자동 ✅
3. US3 → 주간 요약 지표
4. Polish → 문서 정리, 전체 검증
