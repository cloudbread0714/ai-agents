# news-digest

매일 08:00 KST 무렵 RSS를 모아 **가장 중요한 글 1개**를 골라 Slack에 한국어로 게시하는 에이전트입니다.
스펙: [`specs/001-news-daily-digest/`](../../specs/001-news-daily-digest/spec.md)

```
RSS 수집 ─▶ 정규화·중복/이력 제외 ─▶ Claude 1회 호출(선정+요약) ─▶ Slack 게시 ─▶ posted.json 기록
                                                       └─ 실패 시 테스트 채널에만 알림
```

## 환경변수

| 변수 | 용도 |
|------|------|
| `ANTHROPIC_API_KEY` | Claude API |
| `SLACK_WEBHOOK_URL_MAIN` | 정상 채널 Incoming Webhook |
| `SLACK_WEBHOOK_URL_TEST` | 테스트 채널(오류 알림, `--target test` 게시) |
| `NEWS_DIGEST_HISTORY_PATH` | (선택) 게시 이력 경로. 기본 `data/posted.json` |

`.env.example`을 `.env`로 복사해 채우세요. `.env`는 커밋되지 않습니다.
코드는 `.env`를 직접 읽지 않으므로 `uv run --env-file agents/news-digest/.env ...`로 넘깁니다(아래 실행 예시).

## 실행

```bash
# 레포 루트에서
export UV_ENV_FILE=agents/news-digest/.env                    # 또는 매번 --env-file 지정
uv sync --all-packages
uv run --package news-digest news-digest --dry-run --force   # Slack 전송 없이 결과만 출력
uv run --package news-digest news-digest --target test        # 테스트 채널에 게시 (이력 기록 안 함)
uv run --package news-digest news-digest                      # 정상 채널에 게시 + 이력 기록
```

종료 코드: `0` 게시/오늘 이미 게시/새 글 없음, `1` 실패(테스트 채널에 알림), `2` 사용법·설정 오류.
자세한 내용은 [contracts/cli.md](../../specs/001-news-daily-digest/contracts/cli.md)에 있습니다.

## 설정

- **소스 추가·삭제**: `config/sources.yaml`에서 `name`, `url`, `category`(`infra` | `ai_agent` | `auto`)를 편집합니다.
  잠시 끄려면 `enabled: false`로 둡니다.
- **관심 분야, 신선도, 후보 수**: `config/settings.yaml`의 `interests`와 `selection`
- **비용 상한**: `budget.max_cost_usd_per_run`(기본 $0.30). 호출 전에 `count_tokens`로 추정하고,
  상한을 넘으면 오래된 후보부터 줄입니다. 그래도 넘으면 호출하지 않고 알림을 보냅니다.
- **모델 변경**: `llm.model`을 바꿀 때는 `pricing`에도 그 모델의 단가를 넣어야 합니다(없으면 시작할 때 오류).
  예: 비용을 줄이려면 `claude-sonnet-5-5`

## GitHub Actions

`.github/workflows/news-digest.yml`이 매일 UTC 22:40(KST 07:40)에 실행되고, 게시 이력이 바뀌면 커밋합니다.
정각 cron은 GitHub Actions에서 수십 분씩 늦어지는 일이 잦아서, 20분 앞당겨 8시 무렵 게시되게 했습니다.
레포 Secrets에 위 환경변수 3개를 등록해야 합니다. 수동 실행은 Actions → news-digest → Run workflow
(`target`: test | main)에서 합니다. schedule은 기본 브랜치(main)에서만 동작합니다.

## 테스트

```bash
uv run pytest            # 레포 루트 또는 이 디렉터리에서
```

외부 호출(RSS, Claude, Slack)은 모두 모킹되어 있어 네트워크와 비밀값 없이 실행됩니다.

## 로컬 환경 참고 (macOS + iCloud)

레포가 iCloud로 동기화되는 폴더(예: `~/Documents`) 안에 있으면 `.venv` 안의 파일에 `hidden` 플래그가 붙어
Python이 editable 설치(`.pth`)를 무시하고, `ModuleNotFoundError: news_digest`가 납니다.
테스트는 pytest `pythonpath` 설정으로 영향을 받지 않습니다. CLI를 직접 실행할 때는 다음 중 하나를 쓰세요.

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/ai-agents"   # venv를 iCloud 밖에 두기 (권장)
# 또는
PYTHONPATH=shared/src:agents/news-digest/src uv run news-digest --dry-run --force
```
