# Contract: `news-digest` CLI

```text
uv run --package news-digest news-digest [--target main|test] [--dry-run] [--force] [--config-dir PATH]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--target` | `main` | `main`이면 정상 채널에 게시하고 이력을 기록한다. `test`이면 게시물도 테스트 채널로 보내고 **이력은 기록하지 않는다** |
| `--dry-run` | off | Slack에 아무것도 보내지 않고 게시물을 stdout에 출력한다. 이력도 기록하지 않는다. LLM은 호출한다 |
| `--force` | off | 하루 1회 가드를 무시한다. `--target test` 또는 `--dry-run`과 함께일 때만 허용하고, 그 외에는 exit 2 |
| `--config-dir` | `agents/news-digest/config` | `sources.yaml`과 `settings.yaml`이 있는 위치 |

## 환경변수

| 변수 | 필수 | 용도 |
|------|------|------|
| `ANTHROPIC_API_KEY` | 예 | Claude API |
| `SLACK_WEBHOOK_URL_MAIN` | `--target main`일 때 | 정상 채널 |
| `SLACK_WEBHOOK_URL_TEST` | 예(`--dry-run` 제외) | 테스트 채널(오류 알림, test 모드 게시) |
| `NEWS_DIGEST_HISTORY_PATH` | 아니오 | 기본값 `agents/news-digest/data/posted.json` |

필수 변수가 없으면 시작할 때 exit 2로 종료하고, 어떤 변수가 빠졌는지 변수 **이름만** 출력한다.

## 종료 코드

| 코드 | 의미 | 상태 |
|------|------|------|
| 0 | 정상 종료 | `POSTED`, `ALREADY_POSTED`, `NO_NEW_ARTICLES` |
| 1 | 실행 실패(알림 전송 시도함) | `COLLECT_FAILED`, `BUDGET_EXCEEDED`, `SELECT_FAILED`, `POST_FAILED` |
| 2 | 사용법·설정 오류 | 잘못된 인자, 누락된 env, 설정 스키마 위반 |

`NO_NEW_ARTICLES`는 정상 상황이므로 exit 0으로 둬서 워크플로가 실패로 표시되지 않게 한다. 대신 테스트 채널에 알린다.

## 출력

- stderr: 구조화 로그. 한 줄당 JSON 1개이며 `level`, `event`, `source`, `attempt` 등을 담는다.
- stdout: 마지막 줄에 RunResult 요약 JSON 1개(`status`, `candidate_count`, `actual_cost_usd`, `selected_id`)를 출력한다.
