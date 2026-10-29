# Research: lab: 해결해야 다음 문제가 열리는 오늘의 문제

스펙에 남은 미확정 항목은 없다. 아래는 기술 선택과 기존 002 구조와 맞물리는 지점의 결정이다.

## R1. Slack Web API 클라이언트를 어디에, 무엇으로

- **Decision**: `shared/src/shared/slack.py`에 봇 토큰용 함수 `post_message`, `add_reaction`, `get_reactions`, `auth_test`를
  추가한다. 구현은 기존 웹훅 전송과 같은 `httpx` + `shared.retry.retryable`을 쓴다. 새 의존성은 없다.
- **Rationale**: job-apply의 `.env`에도 이미 `SLACK_BOT_TOKEN`·`SLACK_USER_ID`가 있어 두 에이전트가 같은 API를 쓰게 된다
  (헌법 I: 둘 이상이 쓰면 `shared/`). 기존 테스트가 `pytest-httpx`의 `httpx_mock`으로 Slack을 모킹하므로 같은 방식이
  그대로 통한다. 필요한 API는 4개뿐이다.
- **Alternatives considered**: `slack_sdk` — 기능은 많지만 의존성이 하나 늘고, 자체 재시도 정책이 공통 `retryable`과
  겹친다. lab 안에 두기 — job-apply가 곧 같은 코드를 필요로 하므로 기각.

## R2. 반응 조회와 "누가 달았는지"

- **Decision**: `reactions.get(channel, timestamp, full=true)`로 반응 목록(이름 + 단 사용자 ID 목록)을 받는다.
  ✅의 반응 이름은 `white_check_mark`(Slack이 `heavy_check_mark`와 구분함, 둘 다 인정). 단 사람이 `SLACK_USER_ID`이거나
  봇 자신이면 해결로 본다. 봇 자신의 사용자 ID는 실행마다 `auth.test`로 한 번 얻는다.
- **Rationale**: 봇이 단 ✅(`/lab-check` 자동 반응)를 인정해야 하는데, 봇 사용자 ID를 비밀값으로 따로 받으면 설정이 하나 늘어난다.
  `auth.test`는 토큰만으로 답한다.
- **Alternatives considered**: `conversations.history`에서 메시지째 읽기 — 반응도 오지만 필요 이상으로 넓은 권한(`channels:history`)이 든다.
  환경변수 `SLACK_BOT_USER_ID` — 설정 실수 여지만 늘어 기각.

## R3. 필요한 봇 권한(scope)과 오류 처리

- **Decision**: 봇 권한은 `chat:write`, `reactions:read`, `reactions:write` 3개. Web API는 실패해도 HTTP 200에 `ok:false`를
  주므로 본문의 `error`로 분기한다.

  | 상황 | 처리 |
  |---|---|
  | HTTP 429(`ratelimited`), 5xx, 네트워크 오류 | 재시도(지수 백오프, 최대 3회). 429는 `Retry-After`를 상한 10초 안에서 존중 |
  | `already_reacted` | 성공으로 본다(FR-016) |
  | `message_not_found` | `SlackMessageGone`으로 구분해 재게시 흐름(R9)으로 |
  | `not_in_channel`, `channel_not_found`, `missing_scope`, `invalid_auth`, `token_revoked` | 재시도 없이 실패. 오류 코드만 알림에 싣는다 |

- **Rationale**: 오류 코드는 비밀값이 아니고 원인(채널 초대 누락·권한 부족)을 바로 알려 준다(스펙 엣지 케이스).
- **Alternatives considered**: HTTP 상태만 보기 — Web API 특성상 대부분 실패를 놓친다.

## R4. 상태 파일: 게시 기록 확장

- **Decision**: 새 파일을 만들지 않고 `data/posted.json`의 `DailyPost`에 선택 필드를 더한다: `channel`, `ts`, `outcome`
  (`open`|`solved`), `resolved_at`, `reminders`(KST 날짜 목록). `version`은 2 그대로 두고 필드는 모두 기본값을 가진다.
  `channel`이 없는(기존) 항목은 "끝난 문제"로 읽는다.
- **Rationale**: 이미 Actions가 커밋·push하는 파일이고(재시도 루프 포함), 로컬 `/lab-check`도 같은 파일을 읽을 수 있다.
  선택 필드 추가는 하위 호환이라 기존 기록을 옮기는 작업이 없다.
- **Alternatives considered**: `data/daily-state.json` 별도 파일 — 커밋 단계와 일관성 관리가 두 배가 된다. `version: 3`로 올리기 —
  옛 기록 업그레이드 경로만 늘고 얻는 게 없다.

## R5. 문제 선택(planner)과 catchup 제거

- **Decision**: `plan_today`의 선택 순서(21일 차 → 심화 → 복습)는 유지하고, 밀린 문제 3개 이상일 때의 `catchup` 분기를 없앤다.
  "일 차"는 이미 `posted.json`의 마지막 `day + 1`로 정해지므로, 게시가 해결 뒤에만 일어나면 자연히 "해결할 때마다 한 칸"이 된다.
  `DailyPost.kind`의 `catchup` 값은 옛 기록을 읽기 위해 타입에 남긴다.
- **Rationale**: 바꿀 곳이 최소다. 일 차를 날짜와 분리하는 별도 로직이 필요 없다.
- **Alternatives considered**: 게시 기록과 별개의 "현재 일 차" 카운터 — 기록과 어긋날 수 있어 기각.

## R6. 아침 실행 흐름과 원자성

- **Decision**: `daily` 명령의 lab 대상 흐름을 아래 순서로 바꾼다.
  1. `auth.test`로 봇 ID 확인
  2. 열린 문제(마지막 `outcome=open` 항목)가 없으면 → 다음 문제 게시
  3. 있으면 `reactions.get` → ✅ 있음: `outcome=solved` 기록 + 같은 실행에서 다음 문제 게시 / 없음: 오늘 리마인드를 아직 안 남겼으면 스레드 답글
  4. 모든 Slack 호출이 성공했을 때만 `posted.json`을 저장한다(FR-024)
- 해결 판정은 됐는데 다음 문제 게시가 실패하면 아무것도 저장하지 않는다. 다음 날 ✅가 그대로 있으니 같은 판정이 반복된다.
- 하루 한 번 보장: 오늘 날짜의 게시가 이미 있으면 `ALREADY_POSTED`, 오늘 날짜가 `reminders`에 있으면 `ALREADY_REMINDED`.
- **Rationale**: 실패 시 "기록은 그대로, 내일 다시 판정"이 가장 단순하고 중복 게시를 만들지 않는다.

## R7. 리마인드의 힌트 1단계

- **Decision**: `(오늘 KST − 게시 날짜).days >= 3`이면 리마인드에 힌트 1단계를 담는다. 힌트는 `catalog.hints[scenario_id][0]`.
  게시 항목 중 첫 번째 시나리오(본 문제가 미션이면 두 번째 항목)의 힌트를 쓰고, 시나리오가 없으면 힌트 없이 보낸다.
  `hint_opened` 이벤트는 기록하지 않는다(스펙 Assumptions).
- **Rationale**: 힌트는 시나리오에만 있다(`hints.md`, 미션에는 없음). 리마인드는 Actions에서 돌므로 진행 기록을 바꾸지 않는다.

## R8. `/lab-check`의 자동 ✅

- **Decision**: `Learner`에 선택 의존성 `Reactor`를 주입한다(`Diagnoser`·`Measurer`와 같은 패턴). `scenario_solved` 또는
  `mission_completed`를 기록한 직후 호출된다. `Reactor`는 로컬 `posted.json`에서 열린 문제를 찾아,
  (a) 방금 검증한 항목이 그 문제에 들어 있고 (b) 그 문제의 모든 항목이 진행 기록상 끝났을 때만 `reactions.add`를 부른다.
  결과는 출력 한 줄과 `LAB_RESULT`의 `slack_reaction` 값(`added`|`already`|`partial`|`not_open`|`no_config`|`failed`)으로 알린다.
  `partial`은 방금 검증한 항목은 열린 문제에 들어 있지만 다른 항목이 남은 경우다.
- Slack 값이 없거나(`no_config`) 호출이 실패해도(`failed`) 검증 결과와 종료 코드는 바뀌지 않는다(FR-015).
- 로컬 실행을 위해 `bin/lab`이 `agents/troubleshoot-lab/.env`가 있으면 읽어 환경변수로 내보낸다(`set -a; . .env`).
  이미 셸에 있는 값이 우선이다.
- **Rationale**: 학습 명령은 오프라인에서도 동작해야 하므로 Slack은 부가 기능으로만 붙인다. `.env` 로딩은 의존성 없이 셸에서 끝난다.
- **Alternatives considered**: `python-dotenv` 추가 — 한 곳에서만 쓰려고 의존성을 늘릴 필요가 없다.

## R9. 직전 문제 메시지가 없어졌을 때

- **Decision**: `reactions.get`이 `message_not_found`를 주면 같은 문제를 새 메시지로 다시 게시하고, 그 항목의 `channel`·`ts`를
  새 값으로 바꾸며 `reposted_at`을 남긴다. 결과 상태는 `REPOSTED`, 테스트 채널에 경고 1건.
- **Rationale**: 해결 여부를 알 수 없으니 넘어가지 않는 쪽이 "✅ 없으면 안 준다"는 규칙과 맞다.

## R10. 주간 요약 지표

- **Decision**: 주(월~일, KST) 안에서 `resolved_at`이 있는 게시 수 = 해결 수, `reminders` 날짜 수 = 미해결로 멈춘 날 수.
  기존 "밀린 문제 수" 줄은 "지금 열린 문제: <제목> (게시 후 N일)"로 바꾼다. 열린 문제가 없으면 줄을 뺀다.
- **Rationale**: 둘 다 `posted.json`만으로 계산되어 Actions 안에서 정확하다(진행 기록 동기화 여부와 무관).

## R11. 환경변수와 워크플로

- **Decision**: lab 대상 실행 필수 값: `SLACK_BOT_TOKEN`, `SLACK_LAB_CHANNEL_ID`, `SLACK_USER_ID`, `SLACK_WEBHOOK_URL_TEST`(실패 알림).
  `SLACK_WEBHOOK_LAB_URL`은 더 이상 읽지 않는다. 테스트 대상(`--target test`)은 지금처럼 테스트 웹훅으로 "오늘 올라갈 내용"을
  미리 보여 주고 기록을 바꾸지 않는다. `troubleshoot-lab.yml`에 세 Secrets를 넘기고 웹훅 Secret은 뺀다.
- **Rationale**: 실패 알림 경로를 봇 토큰과 분리해 두면 토큰 문제(만료·권한)도 알릴 수 있다.

## R12. 비밀값 보호

- **Decision**: 토큰은 `Authorization: Bearer` 헤더로만 보낸다(URL·본문에 넣지 않음). 로그에는 API 메서드 이름과 오류 코드만 남긴다.
  httpx가 INFO로 남기는 요청 URL(`https://slack.com/api/<method>`)에는 비밀값이 없다.
- **Rationale**: 헌법 IV·V.
