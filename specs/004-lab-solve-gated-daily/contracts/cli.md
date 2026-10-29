# Contract: `lab` CLI 변경분

002의 [contracts/cli.md](../../002-lab-troubleshoot-practice/contracts/cli.md)에서 바뀌는 부분만 적는다.

## `lab daily`

인자는 그대로(`--target test|lab`, `--post daily|weekly|both`, `--dry-run`, `--force`).

### 필수 환경변수

| 대상 | 필수 |
|---|---|
| `--target lab` | `SLACK_BOT_TOKEN`, `SLACK_LAB_CHANNEL_ID`, `SLACK_USER_ID`, `SLACK_WEBHOOK_URL_TEST` |
| `--target test` | `SLACK_WEBHOOK_URL_TEST` |
| `--dry-run` | 없음 |

빠진 값이 있으면 이름만 stderr에 출력하고 종료 코드 2. `SLACK_WEBHOOK_LAB_URL`은 더 이상 읽지 않는다.

### 동작 (`--target lab`, daily 부분)

1. 오늘 날짜의 게시가 있으면 `ALREADY_POSTED`.
2. 열린 문제가 없으면 다음 문제 게시 → `POSTED`.
3. 열린 문제가 있으면 반응 판정:
   - ✅(학습자 또는 봇) → 해결 기록 + 다음 문제 게시 → `POSTED`(요약 JSON의 `daily.resolved_id`에 해결한 항목)
   - ✅ 없음, 오늘 리마인드 전 → 스레드 리마인드 → `REMINDED`(`daily.hint_included` true/false)
   - ✅ 없음, 오늘 리마인드 후 → `ALREADY_REMINDED`
   - 메시지 없음 → 같은 문제 재게시 → `REPOSTED` + 테스트 채널 경고
4. Slack 호출이 최종 실패하면 `posted.json`을 저장하지 않고 `POST_FAILED`, 테스트 채널 알림.

`--force`는 1번(오늘 이미 게시) 검사만 건너뛴다. 반응 판정은 건너뛰지 않는다.

### 동작 (`--target test` / `--dry-run`)

반응을 조회하지 않는다. 열린 문제가 있으면 "지금 열린 문제"와 오늘 보낼 리마인드 문구를, 없으면 다음에 올라갈 문제를
테스트 웹훅(또는 stdout)으로 보여 준다. 기록은 바꾸지 않는다.

## `lab check`

출력 끝에 자동 반응 결과 한 줄이 붙고, `LAB_RESULT`에 `slack_reaction` 필드가 생긴다.
해결·완료가 아닌 결과(검증 실패 등)에서는 필드가 없다.

| `slack_reaction` | 출력 문구 |
|---|---|
| `added` | `Slack 오늘의 문제에 ✅를 달았어요. 내일 아침에 다음 문제가 올라와요.` |
| `already` | `Slack 오늘의 문제에 이미 ✅가 있어요.` |
| `partial` | `오늘의 문제에 남은 항목이 있어요: <제목>. 다 끝내면 ✅를 달아 줄게요.` |
| `not_open` | 출력 없음(열린 문제와 다른 항목). 로컬 기록에 열린 문제가 없으면 `최신 게시 기록이 없어요. git pull 뒤 다시 확인하거나 Slack에서 직접 ✅를 달아 주세요.` |
| `no_config` | `Slack 값(SLACK_BOT_TOKEN 등)이 없어 ✅를 달지 못했어요. Slack에서 직접 달아 주세요.` |
| `failed` | `✅ 자동 반응을 달지 못했어요(<오류 코드>). Slack에서 직접 달아 주세요.` |

종료 코드와 진행 기록은 `slack_reaction` 값과 무관하다.

## `lab giveup`

변경 없음. 반응을 달지 않으며 열린 문제는 그대로 남는다(FR-014).

## `bin/lab`

`agents/troubleshoot-lab/.env`가 있으면 읽어 환경변수로 내보낸 뒤 실행한다. 이미 셸에 있는 값이 우선한다.
