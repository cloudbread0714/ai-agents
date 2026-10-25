# Research: lab: 트러블슈팅 실습

Phase 0 결정 기록. 각 항목은 Decision / Rationale / Alternatives considered 순서다.
2026-10-24 커리큘럼 개정분은 R17 이후에 있다.

## R1. 로직은 Python CLI, 슬래시 명령은 얇은 래퍼

**Decision**: 진행 기록, 잠금 판정, 힌트 순서, 검증 실행, 선택 규칙, Slack 게시는 모두 Python 패키지 `troubleshoot_lab`의
CLI(`lab <subcommand>`)가 맡는다. Claude Code 슬래시 명령(`.claude/commands/lab-*.md`)은 이 CLI를 실행하고 출력을 그대로
전달하는 역할만 한다. 커밋·푸시 여부를 묻는 것만 슬래시 명령이 한다.

**Rationale**:
- 규칙이 코드에 있어야 pytest로 검증할 수 있다(헌법 III). 슬래시 명령 본문은 테스트할 수 없다.
- 같은 CLI를 슬래시 명령 없이 터미널에서도 쓸 수 있다.
- 선택·게시에 LLM을 쓰지 않는다는 요구(FR-022)를 구조로 보장한다. 슬래시 명령을 실행하는 Claude는 CLI 출력만 전달한다.

**Alternatives considered**:
- 슬래시 명령 본문에 로직을 서술하고 Claude가 판단: 결과가 매번 달라질 수 있고 테스트할 수 없다.
- `.claude/skills/`로 작성: 설명만 보고 자동으로 실행될 수 있다. `/lab-giveup`처럼 사용자가 직접 부를 때만 실행되어야
  하는 명령에는 사용자 호출 전용인 `.claude/commands/`가 맞다.

## R2. 슬래시 명령이 답을 새지 않게 하는 규칙

**Decision**: 각 명령 파일에 다음 규칙을 둔다.
- CLI 출력 외의 원인 추측이나 추가 힌트를 덧붙이지 않는다.
- 진행 중인 항목의 `hints.md`, `solution.md`, `inject.sh`, `verify.sh`, `reset.sh`를 읽지 않는다.
- 사용자가 따로 도움을 요청하면 따른다. 이것은 사용자의 선택이다.

시나리오 ID와 제목은 증상 기준으로 짓는다(예: `k8s-api-unreachable`). 원인을 드러내는 이름(예: `k8s-selector-mismatch`)은
작성 가이드에서 금지한다. ID는 시작 명령에 그대로 나오기 때문이다.

**Rationale**: Slack 메시지에서 원인·힌트를 빼는 것(FR-017)만으로는 부족하다. 시작 명령의 ID나 Claude의 덧붙임으로도
답이 샐 수 있다.

**Alternatives considered**: 번호 ID(`k8s-03`): 새지는 않지만 목록에서 알아보기 어렵다.

## R3. 로컬 샌드박스 강제 (헌법 troubleshoot-lab)

**Decision**: 두 겹으로 막는다.

1. **전용 kubeconfig**: `make up`이 `kind create cluster --name troubleshoot-lab --kubeconfig environment/.kube/config`로
   클러스터를 만든다. 사용자의 `~/.kube/config`는 건드리지 않는다. 모든 스크립트는 `lib/common.sh`를 source하고, 이 파일이
   다음을 한다.
   - `KUBECONFIG`를 이 파일로 고정한다.
   - `kubectl`을 `--context kind-troubleshoot-lab`을 강제하는 `k` 함수로만 호출하게 한다.
   - API 서버 주소가 `https://127.0.0.1:*`인지 확인한다. 아니면 종료 코드 3으로 중단한다.
2. **Docker**:
   - `DOCKER_HOST`가 비어 있거나 `unix://`여야 한다. `docker context inspect`의 엔드포인트도 unix 소켓이어야 한다.
   - compose는 항상 `-p troubleshoot-lab -f environment/compose.yaml`로 실행한다.
3. **Python 쪽 재확인**: CLI가 스크립트를 실행하기 전에 같은 검사(`guard.py`)를 다시 한다.

정적 테스트가 모든 `*.sh`를 검사한다. 맨 앞에서 `common.sh`를 source하는지, 맨 `kubectl`이나 `docker compose`를 직접
호출하지 않는지 본다.

**Rationale**: 컨텍스트 이름만 비교하면 같은 이름의 원격 컨텍스트를 막지 못한다. 전용 kubeconfig와 서버 주소 확인을
함께 하면 원격 클러스터를 대상으로 할 길이 없다.

**Alternatives considered**: 사용자 kubeconfig의 current-context만 확인: kind가 기본으로 current-context를 바꿔 버려
사용자의 다른 작업에 영향을 준다.

**준비 상태와 거부의 구분**: 전용 kubeconfig 파일이 없거나 클러스터가 없거나 Docker 데몬이 응답하지 않으면 "환경 준비 안 됨"이다.
이 경우는 종료 코드 5와 `make up` 안내를 낸다. 가드의 종료 코드 3은 설정이 로컬이 아닌 곳을 가리킬 때만 쓴다. 둘을 섞으면
단순히 환경을 안 띄운 사용자에게 "원격 클러스터"라고 잘못 알리게 된다.

**사용자 쉘**: 워밍업에서 사용자가 직접 kubectl을 칠 때를 위해 `make env`가 `export KUBECONFIG=...`를 출력한다. 각 Kubernetes
미션의 첫 단계에서 `eval "$(agents/troubleshoot-lab/bin/lab env)"`를 안내한다. (구현 갱신: `make -C` 는 디렉터리 이동 메시지를 출력해 eval 이 깨지므로 `bin/lab env` 를 쓴다. 이 명령은 `COMPOSE_FILE`, `COMPOSE_PROJECT_NAME` 도 함께 설정한다.)

## R4. 기본 파일은 건드리지 않고 작업 사본에 장애를 주입

**Decision**:
- `make up`과 원복은 `environment/`의 기본 설정을 `.lab-state/work/`(gitignore)로 복사한다. 대상은 nginx 설정과 compose
  override다.
- 서비스는 이 작업 사본을 마운트하거나 참조한다.
- `inject.sh`는 작업 사본이나 실행 중인 리소스(kubectl apply/patch, docker compose up)만 바꾼다.
- `reset.sh`는 작업 사본을 기본값으로 다시 만들고 기본 리소스를 다시 적용한다. 그런 다음 기본 상태 점검
  (`environment/healthcheck.sh`)이 통과할 때까지 기다린다.

**Rationale**:
- 원복이 항상 같은 기본값으로 돌아간다(FR-014, 멱등).
- 레포 작업 트리가 장애 주입으로 더러워지지 않는다.
- 사용자는 작업 사본을 고치거나 kubectl·docker 명령으로 고칠 수 있다.

**Alternatives considered**: 기본 파일을 직접 고치고 `git checkout`으로 원복: 사용자의 다른 변경까지 날아갈 수 있다.

**공통 복원 `environment/restore.sh`**: 일부 워밍업(예: `k8s-rollout`)은 환경을 바꾼다. 시나리오 inject는 기본 상태를 가정하므로,
CLI가 다음 시점에 공통 복원을 실행한다.
- 시나리오 inject 직전
- 미션 완료·원복 때
- 각 `reset.sh`의 마지막 단계

복원 방법: 기본 리소스에 `lab.managed=true` 라벨을 붙이고 `kubectl apply --prune`과 `docker compose up -d --remove-orphans`를
실행한다. 변경이 없으면 거의 즉시 끝나므로 inject 시간(SC-004)에 큰 부담이 없다.

## R5. 워밍업 단계별 자동 판정

**Decision**:
- `mission.yaml`의 각 단계에는 `id`, `guide`(설명), `command`(따라 할 명령), `check`가 있다. `check`는 `state` 또는 `answer`다.
- `verify.sh <step-id> [answer]`가 종료 코드 0이면 그 단계를 통과한 것으로 본다.
- `answer` 단계에서는 `setup.sh`가 매번 무작위 토큰을 만든다. 토큰은 로그, 응답 헤더, Pod 라벨 등에 심고
  `.lab-state/missions/<id>/`에 저장한다. 사용자는 명령을 실행해서만 그 값을 알 수 있다.
- `/lab-check <값>`으로 값을 넘기면 `verify.sh`가 저장된 토큰과 비교한다.
- `state` 단계는 환경 상태로 판정한다. 예: 이미지가 존재하는지, Deployment가 이전 리비전인지.

**Rationale**:
- "로그를 봤다" 같은 행동은 상태로 남지 않는다. 명령으로만 얻을 수 있는 값을 입력받으면 실제로 실행했는지 판정할 수 있다
  (FR-005).
- 토큰이 무작위라 `mission.yaml`을 읽어서 맞힐 수 없다.

**Alternatives considered**: 쉘 히스토리 검사: 쉘마다 다르고 사생활 문제가 있다.

**`command`는 그대로 실행 가능해야 한다**: 각 단계의 `command`는 비대화형으로 그대로 실행할 수 있어야 한다. 샌드박스 테스트가
이 명령을 실행해 단계 통과를 확인한다. `answer` 단계의 값은 테스트가 `answers.json`에서 읽는다.

**동시 진행 금지**: 미션과 시나리오를 통틀어 한 번에 하나만 진행한다. 시나리오 진행 중에 미션 setup이 돌면 주입된 장애가
바뀔 수 있다. `lab check`가 무엇을 검증할지도 이 규칙으로 하나로 정해진다.

## R6. 진행 기록은 이벤트 로그

**Decision**:
- `data/progress.json`은 시간순 이벤트 목록이다.
  - 이벤트 종류: `mission_completed`, `scenario_started`, `hint_opened`, `scenario_solved`, `scenario_gave_up`,
    `scenario_reset`
  - 시나리오별 상태, 진행 중 항목, 주간 통계는 모두 이벤트에서 계산한다.
- 미션의 현재 단계와 무작위 토큰은 커밋하지 않는 로컬 상태(`.lab-state/session.json`)에 둔다.

**Rationale**:
- 주간 요약(FR-026)은 "이번 주에 일어난 일"을 세야 하므로 시각이 있는 이벤트가 필요하다.
- 추가만 하므로 쓰기가 단순하고, 상태 계산을 테스트하기 쉽다.

**Alternatives considered**: 시나리오별 최종 상태만 저장: 주간 힌트 수나 포기 수를 다시 계산할 수 없다.

## R7. 진행 기록 커밋·푸시 (`lab sync`)

**Decision**:
- `/lab-check` 성공 직후와 `/lab-giveup` 직후에 슬래시 명령이 AskUserQuestion으로 "진행 기록을 커밋하고 push할까요?"를 묻는다.
- 동의하면 `lab sync`가 다음을 실행한다.
  1. 현재 브랜치가 `main`인지 확인한다. 아니면 이유를 알리고 중단한다(종료 코드 4).
  2. `git commit -m "lab: progress ... [skip ci]" -- agents/troubleshoot-lab/data/progress.json`. 경로를 지정해서 다른 staged
     변경이 섞이지 않게 한다.
  3. `git pull --rebase --autostash` 후 `git push`. 실패하면 `shared.retry.retryable`로 지수 백오프 재시도한다(최대 3회, 헌법 V).
- 거절하거나 실패해도 로컬 기록은 그대로 둔다. 다음 sync 때 함께 올라간다.

**Rationale**:
- 사용자 지시는 "/lab-check 성공 시 물어본다"였다. `/lab-giveup`도 포기 수와 힌트 수를 바꾸므로, 주간 요약(FR-026)이 맞으려면
  같은 질문이 필요해 추가했다.
- `main`이 아닌 브랜치에 푸시하면 매일 게시(main에서 실행)에 반영되지 않는다.
- `[skip ci]`로 기록 커밋마다 CI가 도는 것을 막는다.

**Alternatives considered**:
- 매 변경마다 자동 커밋(스펙 첫 결정): 사용자가 plan 입력에서 "물어본다"로 바꿨다.
- 임시 worktree로 어느 브랜치에서든 main에 커밋: 로컬 브랜치의 같은 파일과 어긋나 병합 충돌이 생긴다.

## R8. 매일 게시와 주간 요약은 워크플로 하나

**Decision**:
- `.github/workflows/troubleshoot-lab.yml`이 cron `40 23 * * *`(KST 08:40)에 `lab daily --target lab`을 실행한다.
  - 정각 cron은 GitHub Actions에서 가장 붐벼 수십 분 늦을 수 있다. 정각이 아닌 분으로 20분 앞당겨 9시 무렵 게시를 맞춘다(analyze A1).
  - 실행 시각은 UTC로 전날이다. 따라서 오늘 날짜와 요일은 반드시 KST로 계산한다(UTC 토요일 23:40 = KST 일요일 08:40).
- `lab daily`는 KST 기준 일요일이면 오늘의 문제를 게시한 뒤 주간 요약도 게시한다.
- `workflow_dispatch` 입력:
  - `target`: test | lab, 기본 test
  - `post`: daily | weekly | both, 기본 daily
- 게시 기록 `data/posted.json`은 `target=lab`일 때만 갱신하고, news-digest와 같은 방식으로 봇이 커밋한다(`[skip ci]`).
- concurrency 그룹은 `troubleshoot-lab`이다.

**Rationale**:
- cron이 하나면 일요일에 두 실행이 겹치거나 순서가 뒤바뀔 일이 없다.
- 요일 판단이 코드에 있어 테스트할 수 있다.

**Alternatives considered**: 주간 요약용 cron `0 0 * * 0`을 따로 둠: 같은 시각에 두 잡이 돌아 게시 순서와 커밋이 경합한다.

## R9. 게시 대상 전환

**Decision**:
- `--target test|lab`. 옵션이 없으면 환경변수 `LAB_SLACK_TARGET`을 쓰고, 그것도 없으면 `test`다.
- 웹훅:
  - `lab` → `SLACK_WEBHOOK_LAB_URL`
  - `test` → `SLACK_WEBHOOK_URL_TEST` (news-digest와 공유)
- 실패 알림은 항상 `SLACK_WEBHOOK_URL_TEST`로 보낸다.
- `test` 대상 메시지에는 `[TEST]` 접두어를 붙인다.
- `--dry-run`은 전송하지 않고 출력만 한다.

**Rationale**: 사용자가 지정한 "개발 중 기본은 테스트 채널" 요구와 news-digest의 `--target` 관례를 따른다.

## R10. 패키지와 실행 래퍼

**Decision**:
- 패키지와 진입점: `agents/troubleshoot-lab/pyproject.toml`(패키지 `troubleshoot_lab`, 의존성 `shared`·`pyyaml`·`pydantic`),
  스크립트 `lab`.
- 래퍼 `agents/troubleshoot-lab/bin/lab`:
  - `PYTHONPATH`에 `shared/src`와 `agents/troubleshoot-lab/src`를 넣는다.
  - 그 상태에서 `uv run --package troubleshoot-lab python -m troubleshoot_lab "$@"`를 실행한다.
- 슬래시 명령과 Makefile은 이 래퍼를 쓴다.
- pytest 설정:
  - 루트 `pythonpath`에 이 에이전트의 `src`와 `tests`를 추가한다.
  - `testpaths`에 `agents/troubleshoot-lab/tests`를 추가한다.

**Rationale**: 이 맥에서는 iCloud 폴더 안 `.venv`의 `.pth`가 숨김 처리되어 editable 설치가 import되지 않는다.
`PYTHONPATH`를 직접 넣으면 어느 환경에서든 동작한다.

## R11. 샘플 서비스 구성 → R19로 개정

2026-10-24 커리큘럼 개정으로 R19가 대체한다(엔드포인트와 보조 서비스 추가).

## R12. 초기 카탈로그 → R18로 개정

2026-10-24 커리큘럼 개정으로 R18이 대체한다(6개 분야, 커리큘럼 시나리오 번호).

## R13. 원복 테스트 (헌법 troubleshoot-lab)

**Decision**: 두 층으로 검증한다.

1. **정적 테스트**: 항상 실행하며, 네트워크와 Docker가 필요 없다.
   - 카탈로그 전체 유효성을 본다. 필수 파일, 워밍업 1~2개, 힌트 정확히 3단계, 존재하는 미션 참조인지 확인한다.
   - 스크립트는 `bash -n` 문법을 통과해야 하고 실행 권한이 있어야 한다.
   - 스크립트가 `common.sh`를 source하는지, 맨 kubectl을 쓰지 않는지 본다.
2. **샌드박스 테스트**: `@pytest.mark.sandbox`를 붙이고, `LAB_SANDBOX=1`일 때만 실행한다.
   - 시나리오마다 다음 순서로 확인한다.
     1. `inject`
     2. `verify` 실패
     3. `reset`
     4. 기본 점검 통과
     5. `reset`을 한 번 더
     6. 다시 기본 점검 통과(멱등)
     7. inject 전과 reset 후의 `fingerprint.sh` 값이 같음(SC-003)
   - inject 소요 시간이 180초 미만인지 확인한다(SC-004).
   - 미션을 마친 뒤 `restore.sh`가 돌고 나면 healthcheck와 지문이 기본값과 같은지 확인한다.
   - 미션마다 `setup` 뒤 `verify`가 실패하고, 기대 동작을 수행하면 통과하는지 확인한다.
   - 로컬에서는 `make test-sandbox`로 실행한다.
   - CI에서는 `.github/workflows/troubleshoot-lab-sandbox.yml`이 실습 콘텐츠 경로가 바뀐 PR에서만 실행한다.
     kind 바이너리만 설치하고, 클러스터는 `make up`이 만든다.

**Rationale**: 원복 결과를 실제로 확인하려면 실제 컨테이너와 클러스터가 필요하다. 기본 `uv run pytest`는 비밀값과
Docker 없이 통과해야 하므로(헌법 III) 샌드박스 테스트는 따로 켠다.

## R14. 설정 파일의 비밀값 키 검사와 충돌 방지

`shared.config.load_yaml`은 `token`, `password`, `*_key` 같은 키를 거부한다. `mission.yaml`과 `scenario.yaml`에서는
이 이름의 키를 쓰지 않는다. 미션의 무작위 값은 `answer` 단계로 표현하고 `.lab-state/`에만 저장한다. PostgreSQL 비밀번호
같은 실습용 값은 `environment/`의 compose와 매니페스트에만 둔다. 이 값은 로컬 전용 고정값(`lab`)이고 비밀값이 아니다.

## R15. 실패 알림과 Slack 이스케이프는 `shared/`로 옮긴다 (헌법 I)

**Decision**:
- `shared/src/shared/slack.py`에 `escape_mrkdwn`과 `slack_link(url, label)`을 둔다.
- `shared/src/shared/alerts.py`를 새로 만든다.
  - `run_url(env)`
  - `alert_payload(agent, status, *, stage, cause, context_parts, env)`
  - `warning_payload(agent, warnings, *, context_parts, env)`
  - cause와 warnings는 `mask_secrets`와 이스케이프를 거친다.
- news-digest의 `alerts.py`는 `RunResult`를 이 함수 인자로 바꿔 주는 얇은 어댑터가 된다. `formatter.py`는 공유 이스케이프를 쓴다.
  기존 news-digest 테스트는 그대로 통과해야 한다.
- troubleshoot-lab은 처음부터 공유 함수를 쓴다.

**Rationale**: 두 에이전트가 같은 알림 형식과 이스케이프를 쓴다. 복사하면 헌법 I(MUST)을 어기고 마스킹 규칙도 따로 놀게 된다.

## R16. 샘플 API 테스트 (헌법 III)

**Decision**:
- `environment/api/tests/`에 FastAPI `TestClient` 테스트를 둔다.
- DB와 Redis는 의존성 주입으로 가짜 객체로 바꾼다.
- 확인할 것:
  - `/healthz`가 200과 503으로 갈리는지
  - `/items` 조회와 추가
  - `/counter`
  - `/profile`의 쿠키 처리와 `Cache-Control: private`
  - `/version`
  - `DATABASE_URL`이 없으면 종료하는지
- 이 프로젝트는 workspace에서 빠져 있으므로 `ci.yml`에 `uv run --directory agents/troubleshoot-lab/environment/api pytest` 단계를 추가한다.

**Rationale**: 시나리오의 증상과 판정이 이 앱의 동작에 의존한다. 앱이 바뀌어 시나리오가 조용히 깨지는 일을 막는다.

---

# 2026-10-24 커리큘럼 개정

## R17. 분야(field)와 실행 환경(env)을 분리한다

**Decision**:
- 학습 분야는 6개 고정 id를 쓴다.

  | id | 분야 |
  |----|------|
  | `network` | ① 네트워크 |
  | `linux` | ② 리눅스 서버 |
  | `webserver` | ③ 웹 서버와 소켓 |
  | `db-cache` | ④ 데이터베이스와 캐시 |
  | `lb-cloud` | ⑤ 부하 분산과 클라우드 |
  | `monitoring` | ⑥ 모니터링과 장애 대응 |

- 디렉터리는 `missions/<field>/<id>/`, `scenarios/<field>/<id>/`이고, 대표 분야가 디렉터리 이름이다.
- 시나리오는 `fields`(대표 분야를 첫 번째로 둔 1~3개)를 YAML에 둔다.
- 장애를 넣을 환경은 분야와 별개로 `env: compose | kind` 로 적는다. 가드, 복원 모드, 측정 대상, 진단 방식은 모두 `env`로 정한다.

**Rationale**: 기존 구현은 카테고리(docker/kubernetes/web)로 환경까지 정했다. 새 분야는 학습 주제라 환경과 일대일이 아니다. 예를 들어 ⑤ 시나리오는 kind, ④ 시나리오는 compose에서 돈다.

**Alternatives considered**: 분야마다 환경을 고정 — #18(배포 후 장애, ⑥)은 kind, #20(⑥ 포함)은 compose 라서 성립하지 않는다.

## R18. 시나리오 카탈로그 (spec FR-004)

**Decision**: 시나리오 id는 증상 기준 slug이고, `curriculum_no`(문자열 `"3"`, `"18-B"`, `"extra-1"`)로 커리큘럼 번호를 단다. 원인 열은 이 문서와 `solution.md`에만 있다.

| no | id | 대표 분야 | env | 난이도 | 장애 주입(비공개) | 측정 대상 | 워밍업 |
|----|----|-----------|-----|--------|-------------------|-----------|--------|
| 1 | `api-unreachable-via-proxy` | linux | compose | 초급 | api가 `127.0.0.1`에만 바인드 | GET /api/items | socket-check, process-check |
| 2 | `api-partial-errors` (기존 docker-api-partial) | network | compose | 초급 | redis가 compose 네트워크에서 분리(서비스 이름 해석 실패) | GET /api/counter | dns-lookup, docker-exec |
| 3 | `site-connection-refused` (기존 docker-api-unreachable) | network | compose | 초급 | nginx 설정 문법 오류로 nginx 종료 | GET /healthz | socket-check, docker-logs |
| 4 | `site-hangs` | network | compose | 중급 | nginx netns에 iptables DROP(80) | GET /healthz | curl-timing, socket-check |
| 5 | `api-bad-gateway` (기존 docker-api-restarting) | webserver | compose | 중급 | `DATABASE_URL` 빈 값 → 재시작 반복 | GET /api/items | proxy-errors, docker-logs |
| 6 | `report-gateway-timeout` | webserver | compose | 중급 | `/report` 업스트림 지연(5s) > nginx `proxy_read_timeout` 3s | GET /api/report | proxy-errors, curl-timing |
| 7 | `api-slow-under-load` | linux | compose | 중급 | `REPORT_ALGO=naive`(CPU 집약 계산) | GET /api/report | process-check, k6-basics |
| 8 | `api-keeps-dying` | linux | compose | 중급 | 요청마다 메모리 누수 + `mem_limit 160m` → OOMKilled | GET /api/items | memory-disk, docker-logs |
| 9 | `saves-start-failing` | linux | compose | 중급 | 크기 제한 로그 볼륨에 디버그 로그 폭주 → ENOSPC | POST /api/items | memory-disk |
| 10 | `api-degrades-over-time` | webserver | compose | 중급 | 외부 호출 소켓을 닫지 않음 → CLOSE_WAIT 누적 | GET /api/upstream | tcp-states, socket-check |
| 11 | `errors-under-traffic` | linux | compose | 중급 | api `ulimits.nofile` 축소(값은 샌드박스에서 "평소 정상·40 VU에서만 오류"가 되도록 정한다, 128부터 시도) | GET /api/upstream (40 VU) | fd-limits, k6-basics |
| 12 | `api-waits-for-db` | db-cache | compose | 중급 | 오류 경로에서 커넥션 미반환 + 풀 크기 3 | GET /api/items | psql-basics, k6-basics |
| 13 | `catalog-db-load` | db-cache | compose | 중급 | 캐시 TTL 1ms → 적중률 0 | GET /api/catalog/{id} | redis-cli-basics, cache-headers |
| 14 | `popular-page-spikes` | db-cache | compose | 고급 | 인기 키 TTL 짧음 + 재생성 락·jitter 꺼짐 → stampede | GET /api/popular | redis-cli-basics, k6-basics |
| 15 | `k8s-api-no-response` (기존) | lb-cloud | kind | 중급 | Service selector 불일치(엔드포인트 없음) | GET :30080/api/items | k8s-service-basics, k8s-describe |
| 17 | `https-errors` | network | compose | 중급 | nginx가 다른 이름(SAN)의 인증서를 씀 | GET https :8443/healthz | tls-inspect, curl-basics |
| 18 | `k8s-api-crashing` (기존) | monitoring | kind | 중급 | 잘못된 command → CrashLoopBackOff | GET :30080/api/items | k8s-get-pods, k8s-logs |
| 18-B | `k8s-bad-release` (기존 k8s-deploy-stuck 개정) | monitoring | kind | 고급 | 새 버전이 잘못된 DB 비밀번호를 갖고, readiness가 `/version`만 확인해 끝까지 배포됨 | GET :30080/api/items | k8s-rollout, k8s-describe |
| 19 | `orders-slow` | db-cache | compose | 고급 | `orders(customer_id)` 인덱스 삭제 → 순차 스캔 | GET /api/orders?customer=… | psql-basics, curl-timing |
| 20 | `checkout-sometimes-times-out` | webserver | compose | 고급 | 외부 서비스 30% 요청 5s 지연 + api에 타임아웃 없음 | GET /api/checkout | proxy-errors, k6-basics |
| extra-1 | `web-api-404` (기존) | webserver | compose | 초급 | nginx location 오타 | GET /api/items | curl-basics, http-headers |
| extra-2 | `web-stale-data` (기존) | db-cache | compose | 중급 | nginx가 no-store를 무시하고 10분 캐시 | GET /api/items | http-headers, cache-headers |
| extra-3 | `web-wrong-profile` (기존) | db-cache | compose | 고급 | 쿠키 없는 키로 private 응답 공유 캐시 | GET /api/profile | cache-headers, curl-basics |

- **id 변경**: 기존 id 중 원인·도구 이름이 드러나는 것(`docker-api-*`)은 증상 기준으로 바꾼다. 아직 커밋 전이라 진행 기록 이전 문제가 없다.
- **#16**: AWS·HPA가 필요해 향후 확장으로 둔다. **#15**: 로컬 대체(Kubernetes Service)만 다룬다.
- **#18-B 개정(구현 중)**: 기존 "배포가 끝나지 않음(없는 이미지 태그)"은 `maxUnavailable: 0`이라 기존 Pod가 계속 응답해 측정 지표가 변하지 않는다(SC-005 불가). 그래서 "얕은 readiness 검사로 잘못된 버전이 끝까지 배포됨"으로 바꿨다.
- **#10 보강**: 소켓 누수만으로는 20초 측정 동안 지표가 변하지 않아, inject가 api의 `nofile`을 1024로 함께 낮춘다. 누적된 CLOSE_WAIT가 fd를 다 쓰면 오류가 난다.

## R19. 샘플 서비스 확장

**Decision**: `lab-api` 이미지 하나에 다음 엔드포인트를 둔다. 장애는 환경변수·설정으로 켜고, 기본값은 정상 동작이다.

| 엔드포인트 | 정상 동작 | 장애 스위치 |
|------------|-----------|-------------|
| `/items` GET·POST | PostgreSQL 조회·추가, 요청 로그 기록 | `LEAK_DB_CONN=1`(#12), `LOG_VERBOSE=1`(#9), `LEAK_MB_PER_REQ`(#8) |
| `/report` | 집계 계산 | `REPORT_ALGO=naive`(#7), `REPORT_DELAY_MS`(#6) |
| `/upstream` | `ext` 서비스 호출 후 소켓 닫음 | `LEAK_SOCKETS=1`(#10) |
| `/catalog/{id}` | Redis cache-aside, TTL `CACHE_TTL_MS`(기본 30s) | `CACHE_TTL_MS=1`(#13) |
| `/popular` | 비싼 쿼리(`pg_sleep(0.3)`) 결과를 캐시. 재생성 락(`CACHE_LOCK=1`)과 TTL jitter 켜짐 | `CACHE_LOCK=0 CACHE_JITTER=0 POPULAR_TTL_MS=300`(#14, 2000은 SC-005 측정 차이가 나지 않아 개정) |
| `/orders?customer=` | 20만 행 `orders` 테이블 조회(인덱스 있음) | 인덱스 삭제(#19, DB 측) |
| `/checkout` | `ext` 서비스 호출, `EXT_TIMEOUT_MS`(기본 1000)와 대체 응답 | `EXT_TIMEOUT_MS=0` + ext 지연(#20) |
| `/healthz`, `/counter`, `/profile`, `/version` | 기존과 같음 | — |

- **보조 서비스**: 같은 이미지를 `APP_ROLE=ext` 로 띄운 `ext` 컨테이너(외부 의존성 모의)를 둔다. `EXT_SLOW_RATIO`, `EXT_SLOW_MS` 로 일부 요청을 지연시킨다.
- **DB 연결**: psycopg 커넥션 풀(`DB_POOL_SIZE`, 기본 10)로 바꾼다. 획득 타임아웃은 2s다. nginx `proxy_read_timeout`(3s)보다 짧게 두어, #12에서 항상 API의 503이 먼저 나가게 한다(504와 섞이지 않게).
- **로그 볼륨**: compose api 에 크기 제한 tmpfs `/var/log/app`(32MiB)을 붙인다.
- **TLS**: nginx `:443` 리스너를 compose에 추가하고 호스트 `:8443` 에 연결한다. 인증서는 `make up` 이 toolbox 의 openssl 로 실습용 CA와 `localhost` 인증서, 그리고 다른 이름의 인증서를 만들어 작업 사본에 둔다(`$LAB_WORK/nginx/certs/`, 비밀값 아님, gitignore 디렉터리).
- **초기 데이터**: `orders` 20만 행은 `init.sql` 의 `generate_series` 로 만들어 이미지 빌드 없이 수 초 안에 끝낸다.

**Rationale**: 커리큘럼 실습 예제(CPU 과부하, 타임아웃, 소켓, 캐시 전후, stampede, DB 연결 고갈)를 그대로 재현하면서, 장애 스위치를 작업 사본의 compose override 에만 두어 R4(기본 파일 불변)를 지킨다.

**Alternatives considered**: 시나리오마다 별도 앱 — 이미지와 빌드 시간이 늘고, 정상 상태 비교 기준이 시나리오마다 달라진다.

## R20. 측정: k6 + 컨테이너 자원 샘플링

**Decision**: `lab measure` 가 측정 1회를 다음 순서로 실행한다.

1. **시나리오의 `measure` 정의를 읽는다**: `method`, `path`, `vus`(기본 5), `duration`(기본 20s, 최대 40s), `service`(CPU·메모리를 볼 대상), `scheme`(http|https).
2. **k6 실행**: `grafana/k6:1.0.0` 컨테이너로 `environment/k6/measure.js` 를 돌린다. 이 스크립트는 환경변수로 매개변수를 받는 하나의 공통 스크립트다.
   - compose: k6 컨테이너를 `troubleshoot-lab_lab` 네트워크에 붙이고 `http://nginx` 로 보낸다.
   - kind: docker 네트워크 `kind` 에 붙이고 `http://troubleshoot-lab-control-plane:30080` 으로 보낸다.
   - 결과는 `handleSummary` 로 `$LAB_STATE/measure/<ts>/summary.json` 에 쓴다.
3. **자원 샘플링**: k6 와 동시에 1초 간격으로 대상 서비스의 CPU·메모리를 샘플링한다.
   - compose: `docker stats --no-stream`
   - kind: `kubectl top pod` (metrics-server, 15s 해상도)
4. **기록**: 다음 지표를 진행 기록 이벤트 `measured` 에 저장한다.
   - `avg_ms`, `p95_ms`: `http_req_duration`
   - `rps`: `http_reqs.rate`
   - `error_rate`: `http_req_failed.rate`
   - `requests`
   - `cpu_avg_pct`, `cpu_max_pct`, `mem_max_mib`

**실측값 규칙(FR-017)**:
- 샘플이 0개면 그 지표는 `{"status": "unavailable"}` 이다. kind 에서 metrics-server 가 아직 준비되지 않은 경우가 대표적이다.
- 성공 요청이 0이면 `avg_ms`·`p95_ms` 는 `{"status": "not_applicable"}` 이다. k6 는 실패 요청의 duration 도 내지만, 통계는 성공 요청(`expected_response:true` 태그)만으로 낸다.
- 사용자가 `--skip "<사유>"` 로 생략하면 `{"status": "skipped"}` 와 `skip_reason` 을 남긴다.
- 어떤 경로로도 이전 값이나 기본값을 넣지 않는다.

**제한**:
- 부하 대상은 위 두 내부 주소로 고정한다. 시나리오 YAML 에는 경로만 쓰고 호스트는 쓰지 않는다(FR-027).
- 측정 1회는 `duration`+이미지 준비 시간으로 1분 안에 끝난다(FR-019). k6 이미지는 `make up` 이 미리 받아 둔다.

**Rationale**:
- k6 를 컨테이너로 돌리면 호스트 설치가 필요 없다(SC-010).
- 내부 네트워크로 보내면 Docker Desktop 포트 포워딩 오버헤드가 측정을 흐리지 않는다.
- 공통 스크립트 하나라 정상·장애·해결 후 측정 방법이 같다(FR-019).

**Alternatives considered**:
- 호스트에 k6 설치 — 사용자 요구(호스트 설치 없음)와 맞지 않는다.
- `hey`/`wrk` — 사용자가 k6 를 지정했다.

## R21. 진단 toolbox 컨테이너

**Decision**: `environment/toolbox/Dockerfile`(debian:12-slim)로 `lab-toolbox:dev` 이미지를 `make up` 때 빌드한다.
- 포함 도구: `iproute2`(ss, ip), `procps`(top, ps, free, vmstat), `sysstat`(iostat), `dnsutils`(dig, nslookup), `curl`, `netcat-openbsd`, `lsof`, `tcpdump`, `iptables`, `openssl`, `postgresql-client`, `redis-tools`, `jq`, `util-linux`(prlimit)
- kind 노드에는 `kind load docker-image` 로 넣는다.

`lab exec <service> -- <명령>`:
- **compose**: 다음처럼 대상 컨테이너의 네트워크·PID 네임스페이스에 붙인다. 그래서 `ss` 는 대상의 소켓을, `top` 은 대상의 프로세스를 본다.

  ```
  docker run --rm --network container:<c> --pid container:<c> lab-toolbox:dev sh -c "<명령>"
  ```

  대상이 꺼져 있으면 붙을 수 없다. 이때는 "대상 서비스가 실행 중이 아니에요"와 대안(nginx 컨테이너에서 진단)을 안내한다(spec 경계 상황).
- **kind**: 다음처럼 ephemeral container 로 실행한다. 대상 Deployment 의 첫 Pod 를 고른다.

  ```
  kubectl debug -n lab <pod> --image=lab-toolbox:dev --target=<container> --attach --quiet -- sh -c "<명령>"
  ```

- **대화형 쉘**: `lab shell <service>` 는 사용자가 자기 터미널에서 실행할 `docker run -it ...` 또는 `kubectl debug -it ...` 명령을 출력한다. Claude Code 는 대화형 세션을 열 수 없기 때문이다.
- **장애 주입용 네트워크 조작**: #4 의 iptables 는 같은 이미지를 `--cap-add NET_ADMIN` 으로 붙여 실행한다. 이 권한은 inject·reset 스크립트에서만 쓰고, 사용자용 `lab exec` 에는 주지 않는다.

**Rationale**: macOS 호스트에 `ss`, `free`, `vmstat` 이 없다. 대상과 같은 네임스페이스에서 봐야 "그 서비스의" 소켓·프로세스 상태가 보인다(FR-018).

**Alternatives considered**: 대상 이미지에 도구 설치 — 장애 컨테이너가 죽으면 진단할 수 없고, 샘플 이미지가 커진다.

## R22. 6단계 상태 기계

**Decision**: 시도(attempt) 하나는 다음 단계를 순서대로 거친다. 진행 기록 이벤트로 판정한다.

```
started ──measure(baseline)──▶ baseline_ok ──inject──▶ injected ──measure(fault)──▶ fault_ok
   └────────────────── reset / giveup 은 어느 단계에서나 가능 ──────────────────────┘
fault_ok ──check 성공──▶ solved (+ measure(after) 자동) ──report --done──▶ reviewed
giveup ──▶ gave_up ──report --done──▶ reviewed
```

- `lab measure` 의 단계(phase)는 상태로 자동 결정한다.
  - injected 이전: `baseline`
  - injected 이후: `fault`
  - 해결 후 자동 측정: `after`. 해결 후에는 사용자가 다시 측정하면 `after` 로 추가된다.
- `lab inject` 는 `baseline` 측정(또는 skip)이 없으면 거부한다(outcome `need_measure`).
- `lab check` 는 `fault` 측정(또는 skip)이 없으면 판정하지 않는다(outcome `need_measure`).
- 장애 주입이 시작(`start`)과 분리되었다. 대신 시작할 때 `restore.sh` 로 기본 상태를 만든다. 정상 측정은 깨끗한 환경에서 해야 하기 때문이다.

**Rationale**: FR-009~FR-013 의 순서 강제를 진행 기록만으로 판정할 수 있다. 같은 이벤트로 보고서 측정표와 주간 집계를 만든다.

## R23. 장애 보고서

**Decision**:
- `lab report` 는 마지막으로 끝난(solved/gave_up) 시도의 초안을 만든다.
  - 경로: `agents/troubleshoot-lab/docs/reports/<YYYY-MM-DD>-<id>-<attempt>.md`
  - 이미 있으면 덮어쓰지 않고 경로만 알려 준다.
- 템플릿은 `templates/report.md` 다(contracts/report.md). 다음을 미리 채운다.
  - 장애명, 시나리오 번호·분야, 시도 번호, 결과(해결/포기), 사용한 힌트 수
  - 측정 비교표: 단계별 마지막 측정. FR-017 상태 표기를 그대로 쓰고 "자동 측정 기록" 표시를 붙인다.
  - 면접 질문 1~2개
- 본문 칸에는 `<!-- 직접 작성 -->` 표시를 둔다.
- `lab report --done` 은 필수 섹션을 검사한다.
  - 대상: 증상, 원인, 분석 과정, 해결 방법, 재발 방지, 그리고 면접 질문마다의 답
  - 판정: 주석과 공백을 뺀 본문이 있어야 한다.
  - 통과하면 `report_completed(path, answered=n)` 을 기록하고 sync 질문 대상이 된다.
  - 실패하면 빈 섹션 이름을 알려 준다.
- 파일을 지우면 다음 계산부터 "보고서 미작성"으로 본다. 존재 여부는 실행 때 확인한다.

**Rationale**:
- 사용자가 직접 써야 학습이 되고, 시스템이 원인을 써 주면 FR-020 위반이다.
- 측정표만 자동이라 실측값 원칙(SC-004)을 지킨다.

## R24. 학습 계획 파일과 일차 선택

**Decision**:
- `curriculum/plan.yaml` 에 1~21일 차를 둔다. 일차마다 다음을 가진다.
  - `day`, `week`, `topic`, `practice`
  - `items`: 시나리오·개념 미션 id 목록
  - `minutes`
- 심화 순서는 `extras: [...]` 에 둔다.
- 카탈로그 검증은 다음을 확인한다.
  - plan 의 모든 id 가 유효하다.
  - 21일이 빠짐없이 있다.
  - 각 일차의 첫 항목과 연결 워밍업의 `minutes` 합이 60~90 이다(SC-008).
- 게시 기록 `posted.json` v2 는 `{date_kst, kind: day|catchup|extra|review, day, main_id, main_kind, second_id, posted_at}` 를 남긴다.
- 종합 일차(7일 차)는 `items` 대신 `pool`(후보 시나리오 목록)을 둔다. 게시할 때 규칙으로 1개를 고른다(FR-030 규칙 5). 커리큘럼의 "#1~#4 종합"을 고정 항목 없이 "아직 약한 것" 중심으로 다룬다.
- 선택 규칙(FR-030)은 다음 순서로 적용한다.
  1. **backlog**: 과거에 주·두 번째 항목으로 게시된 시나리오 중 solved/gave_up 이 아닌 것. 게시일 오래된 순이다.
  2. **따라잡기**: backlog 가 3개 이상이면 `catchup`. 가장 오래된 backlog 를 주 항목으로 한다.
  3. **다음 일차**: 그 밖에는 마지막 `day` 게시의 다음 일차로 간다.
  4. **21일 이후**: `extras` 를 앞에서부터 아직 안 낸 것으로 고르고, 끝나면 `review` 로 넘어간다(기존 복습 규칙).
  5. **두 번째 항목**: 일차에 시나리오가 2개면 두 번째를 `second_id`("시간이 남으면")로 둔다.
  6. **복습 표시**: 주 항목 시나리오가 이미 solved 면 메시지에 "복습(오늘 주제 관점)"을 표시한다.

**Rationale**:
- 커리큘럼 순서를 데이터로 두면 문서 개정 때 코드 수정 없이 반영된다.
- 게시 기준 진행은 Clarification Q1 과 맞고, 따라잡기 날로 밀림을 막는다.

## R25. 진행 기록 v2와 sync 범위

**Decision**:
- `progress.json` version 2 의 이벤트에 다음을 추가한다.
  - 공통 필드: `attempt`(정수)
  - 새 이벤트 종류: `measured`(`phase`, `metrics`, `skip_reason`), `fault_injected`, `report_completed`(`report`, `answered`)
- 지금 파일은 빈 v1 이라 로더가 v1 빈 파일만 v2 로 올린다. 이벤트가 있는 v1 은 오류로 처리한다. 아직 실사용 데이터가 없다.
- `lab sync` 는 `-- data/progress.json docs/reports/` 경로만 커밋한다.
- 질문 시점은 `/lab-check` 성공, `/lab-giveup`, `/lab-report --done` 직후다(FR-035).

## R26. 새 슬래시 명령

**Decision**: 기존 6개에 4개를 더한다.
- `/lab-measure [--skip 사유]`
- `/lab-inject`
- `/lab-exec <서비스> <명령...>`
- `/lab-report [--done]`

`/lab-exec` 는 사용자가 적은 명령만 그대로 실행한다. Claude 가 진단 명령을 스스로 골라 실행하지 않는다. 그렇게 하면 원인 분석 단계가 대신 수행된다.
허용 목록(`.claude/settings.json`)에는 `measure`, `inject`, `report` 를 추가한다. `exec` 와 `sync` 는 넣지 않는다. 임의 명령 실행과 push 는 권한 확인을 거친다.

## R27. 커리큘럼 문서 위치

**Decision**: 사용자가 `agents/troubleshoot-lab/docs/curriculum.md` 로 지칭했으므로 그 위치로 옮기고 spec Assumptions 의 경로를 맞춘다. 보고서(`docs/reports/`)와 작성 가이드(`docs/authoring.md`)가 같은 `docs/` 아래에 모인다.

## R28. 기존 구현 재사용 범위

**Decision**:
- **그대로 쓰는 것**: 가드(R3), 작업 사본·복원(R4), 미션 판정(R5), sync(R7), 게시 워크플로·대상 전환(R8, R9), 래퍼(R10), shared 알림
- **바꾸는 것**:
  - `models`(Field·env·measure·interview·minutes·plan)
  - `catalog`(plan 검증)
  - `progress`(v2·상태 기계)
  - `learn`(start/measure/inject/check 분리)
  - `picker` → `planner`
  - `messages`, `weekly`
- **새로 만드는 것**: `measure.py`, `diag.py`, `report.py`
- **콘텐츠**:
  - 기존 미션 14개와 시나리오 9개는 디렉터리를 새 분야로 옮긴다. `measure`, `interview`, `minutes`, `env` 를 보완한다.
  - 새 시나리오 14개(#1, #4, #6~#14, #17, #19, #20), 새 워밍업 12개, 개념 미션 4개를 추가한다.
