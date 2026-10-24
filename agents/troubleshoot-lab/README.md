# troubleshoot-lab

내 컴퓨터의 실습 환경(docker compose + kind)에 장애를 주입하고, 원인을 찾아 고치며 트러블슈팅을 연습하는 에이전트입니다.
매일 09:00 KST 무렵 오늘 풀 문제를 Slack에 올리고, 일요일에는 한 주 학습 요약을 올립니다.
스펙: [`specs/002-lab-troubleshoot-practice/`](../../specs/002-lab-troubleshoot-practice/spec.md)

```
워밍업 미션(명령 따라 하기, 자동 판정) ─▶ 장애 시나리오 열림 ─▶ /lab-start 로 장애 주입
  ─▶ 증상 보고 원인 찾기 (/lab-hint 3단계) ─▶ /lab-check 자동 검증 ─▶ 해설 ─▶ /lab-reset 원복
```

## 준비

- Docker Desktop, [kind](https://kind.sigs.k8s.io/), kubectl, jq, curl, uv
- 레포 루트에서 실행합니다.

```bash
make -C agents/troubleshoot-lab doctor   # 필요한 도구 확인
make -C agents/troubleshoot-lab up       # compose(:8080) + kind 클러스터 troubleshoot-lab(:8081)
make -C agents/troubleshoot-lab down     # 전부 삭제
```

`make up` 은 kind 클러스터 전용 kubeconfig(`environment/.kube/config`)를 따로 만들어요. 내 `~/.kube/config` 는 건드리지 않습니다.
터미널에서 직접 kubectl·docker compose 를 칠 때는 먼저 이걸 실행하세요.

```bash
eval "$(agents/troubleshoot-lab/bin/lab env)"   # KUBECONFIG, COMPOSE_FILE, COMPOSE_PROJECT_NAME 설정
```

## 실습 (Claude Code 슬래시 명령)

| 명령 | 하는 일 |
|------|---------|
| `/lab-list` | 미션·시나리오 목록과 진행 상황 |
| `/lab-start <id>` | 미션 또는 시나리오 시작. 워밍업이 남았으면 워밍업부터 안내 |
| `/lab-hint` | 진행 중인 시나리오의 다음 힌트(1→2→3) |
| `/lab-check [값]` | 미션 단계나 시나리오 검증. 값이 필요한 단계는 값을 함께 입력 |
| `/lab-giveup` | 포기하고 해설 보기 |
| `/lab-reset [id]` | 원복 |

슬래시 명령 없이 터미널에서는 `agents/troubleshoot-lab/bin/lab <list|start|hint|check|giveup|reset>` 로 똑같이 쓸 수 있어요.

- 한 번에 미션이나 시나리오 하나만 진행할 수 있어요.
- 슬래시 명령은 CLI 출력만 전달하고, 힌트나 해설을 따로 덧붙이지 않아요.
- 장애 주입과 원복은 로컬 샌드박스에서만 돼요. 전용 kubeconfig, context, API 서버 127.0.0.1, Docker 로컬 소켓을 확인하고, 아니면 거부합니다(종료 코드 3).
- 환경이 아직 안 떠 있으면 종료 코드 5와 함께 `make up` 을 안내해요.

## 진행 기록과 매일 알림

- 진행 기록은 `data/progress.json`(이벤트 로그)에 쌓여요.
- `/lab-check` 성공이나 `/lab-giveup` 직후에 커밋·push 여부를 물어봐요. 동의하면 `bin/lab sync` 가 이 파일만 커밋해서 push 합니다.
  - `main` 브랜치에서만 push 해요. 매일 알림이 main 의 기록을 읽기 때문이에요.
  - 커밋 메시지에 `[skip ci]` 를 붙여서 CI가 돌지 않아요.
- `.github/workflows/troubleshoot-lab.yml` 이 매일 UTC 23:40(KST 08:40)에 오늘의 문제를 고릅니다. 선택은 규칙 기반이고 LLM은 쓰지 않아요.
  - 안 푼 문제를 낮은 난이도부터 골라요.
  - 어제 낸 문제는 다시 내지 않아요.
  - 다 풀면 복습 문제를 내요.
- KST 일요일에는 주간 요약도 함께 올라가요.
- 게시 기록은 `data/posted.json` 이고 봇이 커밋합니다.

### 채널과 환경변수

| 변수 | 용도 |
|------|------|
| `SLACK_WEBHOOK_LAB_URL` | 정상 채널 #daily-lab |
| `SLACK_WEBHOOK_URL_TEST` | 테스트 채널 #agent-test (news-digest와 공유, 실패 알림도 여기로) |
| `LAB_SLACK_TARGET` | (선택) `test`(기본) 또는 `lab` |

로컬에서 확인할 때는 `.env.example` 을 `.env` 로 복사해 채우고 다음처럼 실행하세요.

```bash
set -a; . agents/troubleshoot-lab/.env; set +a
agents/troubleshoot-lab/bin/lab daily --dry-run --force                      # 출력만
agents/troubleshoot-lab/bin/lab daily --dry-run --today 2026-11-01           # 일요일: 문제 + 주간 요약
agents/troubleshoot-lab/bin/lab daily --target test --force                  # #agent-test 에 [TEST] 게시
```

GitHub Actions 에는 Secrets `SLACK_WEBHOOK_LAB_URL`, `SLACK_WEBHOOK_URL_TEST` 가 필요합니다.
수동 실행은 Actions → troubleshoot-lab → Run workflow(`target`, `post`)에서 할 수 있어요.

## 콘텐츠 추가

[docs/authoring.md](docs/authoring.md) 를 보세요. `templates/` 를 복사해서 만들고 `bin/lab validate` 로 확인합니다.
첫 카탈로그는 워밍업 미션 14개와 시나리오 9개예요(Docker·Kubernetes·웹 × 초급·중급·고급).

## 테스트

```bash
uv run pytest agents/troubleshoot-lab/tests                      # Docker·네트워크 없이 (샌드박스 테스트는 건너뜀)
uv run --directory agents/troubleshoot-lab/environment/api pytest  # 샘플 API
make -C agents/troubleshoot-lab test-sandbox                     # 실제 환경: 시나리오 inject→verify→reset, 미션 단계
```

## 로컬 환경 참고 (macOS + iCloud)

레포가 iCloud 동기화 폴더에 있으면 `.venv` 의 editable 설치가 무시될 수 있어요.
`bin/lab` 래퍼는 소스 경로를 `PYTHONPATH` 로 직접 넣기 때문에 이 문제와 상관없이 동작해요.
