# troubleshoot-lab

내 컴퓨터의 실습 환경(docker compose + kind)에 장애를 주입하고, 원인을 찾아 고치며 트러블슈팅을 연습하는 에이전트입니다.
[커리큘럼](docs/curriculum.md)의 21일 학습 계획에 맞춰 Slack에 오늘의 문제를 올리고, 일요일에는 한 주 학습 요약을 올립니다.
문제는 한 번에 하나만 열려 있고, 그 메시지에 ✅가 달려야 다음 날 아침에 다음 문제가 올라와요.
스펙: [`specs/002-lab-troubleshoot-practice/`](../../specs/002-lab-troubleshoot-practice/spec.md),
[`specs/004-lab-solve-gated-daily/`](../../specs/004-lab-solve-gated-daily/spec.md)

```
워밍업 미션(명령 따라 하기, 자동 판정) ─▶ 시나리오 열림 ─▶ /lab-start (기본 상태로 복원)
  ① 정상 상태 측정  /lab-measure
  ② 장애 재현       /lab-inject
  ③ 장애 상태 측정  /lab-measure
  ④ 진단·원인 분석  /lab-exec <서비스> <명령>, /lab-hint (3단계)
  ⑤ 해결·검증       /lab-check (해결 후 측정은 자동)
  ⑥ 장애 보고서     /lab-report → 직접 작성 → /lab-report --done
```

### 학습 분야

| id | 분야 |
|----|------|
| `network` | ① 네트워크 |
| `linux` | ② 리눅스 서버 |
| `webserver` | ③ 웹 서버와 소켓 |
| `db-cache` | ④ 데이터베이스와 캐시 |
| `lb-cloud` | ⑤ 부하 분산과 클라우드 (로컬에서는 Kubernetes Service로 대체) |
| `monitoring` | ⑥ 모니터링과 장애 대응 |

AWS 인프라 장애(커리큘럼 4주 차, #16)는 향후 확장으로 남겨 두었어요.

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
| `/lab-measure [--skip 사유]` | 현재 단계(정상·장애·해결 후) 지표 측정 |
| `/lab-inject` | 정상 측정 뒤 장애 재현 |
| `/lab-exec <서비스> <명령>` | 대상 서비스 공간의 진단 컨테이너에서 명령 실행(`ss`, `top`, `free`, `dig` …) |
| `/lab-hint` | 진행 중인 시나리오의 다음 힌트(1→2→3) |
| `/lab-check [값]` | 미션 단계나 시나리오 검증. 값이 필요한 단계는 값을 함께 입력 |
| `/lab-giveup` | 포기하고 해설 보기 |
| `/lab-report [--done]` | 장애 보고서 초안 만들기 / 다 썼는지 확인 |
| `/lab-reset [id]` | 원복 |

슬래시 명령 없이 터미널에서는 `agents/troubleshoot-lab/bin/lab <명령>` 으로 똑같이 쓸 수 있어요(`bin/lab --help`).
대화형 진단 쉘이 필요하면 `bin/lab shell <서비스>` 가 내 터미널에서 칠 명령을 알려 줘요.

- 한 번에 미션이나 시나리오 하나만 진행할 수 있어요.
- 슬래시 명령은 CLI 출력만 전달하고, 힌트나 해설을 따로 덧붙이지 않아요.
- 장애 주입과 원복은 로컬 샌드박스에서만 돼요. 전용 kubeconfig, context, API 서버 127.0.0.1, Docker 로컬 소켓을 확인하고, 아니면 거부합니다(종료 코드 3).
- 환경이 아직 안 떠 있으면 종료 코드 5와 함께 `make up` 을 안내해요.
- `/lab-exec` 는 내가 적은 명령만 실행해요. Claude가 진단 명령을 대신 고르지 않아요.

### 측정

- `lab measure` 는 k6(`grafana/k6` 컨테이너)로 시나리오의 `measure` 경로에 부하를 보내고, 동시에 대상 서비스의 CPU·메모리를 1초마다 샘플링해요.
- 기록하는 지표는 평균·p95 응답 시간, 초당 처리량, 오류율, 요청 수, CPU 평균·최대, 메모리 최대예요.
- 값은 모두 실측값이에요. 값을 얻지 못하면 `측정 불가`, 성공 요청이 없으면 `해당 없음`, `--skip` 이면 `측정 생략(사유)` 로 남기고 추정값을 넣지 않아요.
- 부하는 실습 환경 안의 고정 주소(compose nginx, kind NodePort)로만 보내요.

### 장애 보고서

- `/lab-report` 는 `docs/reports/<날짜>-<id>-<시도>.md` 초안을 만들어요. 측정 비교표와 면접 질문은 미리 채워져요.
- 증상, 원인, 분석 과정, 해결 방법, 재발 방지, 면접 질문 답은 직접 써요. `/lab-report --done` 이 빈 섹션을 알려 줘요.
- 보고서도 진행 기록과 함께 `lab sync` 로 커밋돼요.

## 진행 기록과 매일 알림

- 진행 기록은 `data/progress.json`(이벤트 로그)에 쌓여요.
- `/lab-check` 성공, `/lab-giveup`, `/lab-report --done` 직후에 커밋·push 여부를 물어봐요. 동의하면 `bin/lab sync` 가
  `data/progress.json` 과 `docs/reports/` 만 커밋해서 push 합니다.
  - `main` 브랜치에서만 push 해요. 매일 알림이 main 의 기록을 읽기 때문이에요.
  - 커밋 메시지에 `[skip ci]` 를 붙여서 CI가 돌지 않아요.
- `.github/workflows/troubleshoot-lab.yml` 이 매일 UTC 23:40(KST 08:40)에 실행돼요. 선택은 규칙 기반이고 LLM은 쓰지 않아요.
  - 열린 문제가 없으면 다음 문제를 게시해요.
  - 열린 문제 메시지에 ✅가 있으면 해결로 기록하고 다음 문제를 게시해요. ✅는 내가 달았거나 `/lab-check` 가 자동으로 단 것만 쳐요.
  - ✅가 없으면 새 문제 대신 그 메시지 스레드에 "아직 해결 전" 리마인드를 하루 한 번 남겨요.
    게시 후 3일이 지나면 리마인드에 힌트 1단계가 함께 들어가요(힌트 사용 횟수에는 안 세요).
  - ⏭️ 같은 다른 반응이나 `/lab-giveup` 으로는 넘어가지 않아요. 다음 문제를 받으려면 ✅가 필요해요.
- 학습 계획은 [`curriculum/plan.yaml`](curriculum/plan.yaml)이에요. 1~21일 차 주제, 실습, 시나리오(또는 개념 미션)가 들어 있어요.
  - "N일 차"는 날짜가 아니라 문제를 해결할 때마다 한 칸씩 나아가요. 하루 분량은 주 항목과 연결 워밍업을 합쳐 60~90분이에요.
  - 일차에 시나리오가 2개면 두 번째는 "시간이 남으면"으로 붙어요. ✅는 둘 다 끝냈을 때 달려요.
  - 7일 차는 1~4번 중 아직 약한 것을 골라 종합 문제로 내요.
  - 21일 차 다음은 심화 시나리오, 그다음은 복습 문제예요.
- `/lab-check` 로 오늘의 문제를 끝내면 그 Slack 메시지에 봇이 ✅를 달아요.
  - 열린 문제는 로컬 `data/posted.json` 에서 찾으니, 문제를 풀기 전에 `git pull` 로 최신 게시 기록을 받아 두세요.
  - Slack 값이 없거나 실패해도 검증 결과는 그대로예요. 그때는 Slack에서 직접 ✅를 달면 돼요.
- KST 일요일에는 주간 요약도 함께 올라가요. 계획 진행도, 해결·포기·힌트, 보고서 완료·대기, 약한 분야,
  오늘의 문제 해결 수와 미해결로 멈춘 날 수, 지금 열린 문제, 다음 주제가 들어가요.
- 게시 기록은 `data/posted.json` 이고 봇이 커밋합니다. 메시지 위치(채널·메시지 ID), 해결 여부, 리마인드 날짜도 여기 남아요.

### 채널과 환경변수

| 변수 | 용도 |
|------|------|
| `SLACK_BOT_TOKEN` | Slack 앱 봇 토큰(`xoxb-…`). lab 채널 게시·반응 조회·반응 달기 |
| `SLACK_LAB_CHANNEL_ID` | 정상 채널 #daily-lab 의 채널 ID |
| `SLACK_USER_ID` | 내 Slack 사용자 ID. 이 사람(과 봇)이 단 ✅만 해결로 쳐요 |
| `SLACK_WEBHOOK_URL_TEST` | 테스트 채널 #agent-test (news-digest와 공유, 실패 알림·미리 보기도 여기로) |
| `LAB_SLACK_TARGET` | (선택) `test`(기본) 또는 `lab` |

Slack 앱에는 봇 권한 `chat:write`, `reactions:read`, `reactions:write` 가 필요하고, 봇을 #daily-lab 에 초대해 둬야 해요.

로컬에서는 `.env.example` 을 `.env` 로 복사해 채우세요. `bin/lab` 이 `.env` 를 자동으로 읽어요(셸에 이미 있는 값이 우선).
`/lab-check` 의 자동 ✅도 이 값을 써요.

```bash
agents/troubleshoot-lab/bin/lab daily --dry-run --force                      # 출력만
agents/troubleshoot-lab/bin/lab daily --dry-run --today 2026-11-01           # 일요일: 문제 + 주간 요약
agents/troubleshoot-lab/bin/lab daily --target test --force                  # #agent-test 에 [TEST] 미리 보기
```

테스트 채널 실행은 반응을 읽지 않고 기록도 바꾸지 않아요. 열린 문제가 있으면 오늘 남길 리마인드를, 없으면 다음 문제를 보여 줘요.

GitHub Actions 에는 Secrets `SLACK_BOT_TOKEN`, `SLACK_LAB_CHANNEL_ID`, `SLACK_USER_ID`, `SLACK_WEBHOOK_URL_TEST` 가 필요합니다.
수동 실행은 Actions → troubleshoot-lab → Run workflow(`target`, `post`)에서 할 수 있어요.

## 콘텐츠 추가

[docs/authoring.md](docs/authoring.md) 를 보세요. `templates/` 를 복사해서 만들고 `bin/lab validate` 로 확인합니다.
카탈로그는 미션 30개(워밍업 26개, 개념 미션 4개)와 시나리오 23개예요. 커리큘럼 #1~#20(#16 제외)과 심화 3개를 다뤄요.

## 테스트

```bash
uv run pytest agents/troubleshoot-lab/tests                      # Docker·네트워크 없이 (샌드박스 테스트는 건너뜀)
uv run --directory agents/troubleshoot-lab/environment/api pytest  # 샘플 API
make -C agents/troubleshoot-lab test-sandbox                     # 실제 환경: 시나리오 측정→inject→측정→verify→reset, 미션 단계
```

## 로컬 환경 참고 (macOS + iCloud)

레포가 iCloud 동기화 폴더에 있으면 `.venv` 의 editable 설치가 무시될 수 있어요.
`bin/lab` 래퍼는 소스 경로를 `PYTHONPATH` 로 직접 넣기 때문에 이 문제와 상관없이 동작해요.
