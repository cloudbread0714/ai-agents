# 미션·시나리오 작성 가이드

새 워밍업 미션이나 장애 시나리오를 추가하는 방법입니다. 전체 계약은
[contracts/content.md](../../../specs/002-lab-troubleshoot-practice/contracts/content.md)에 있습니다.

## 1. 템플릿 복사

```bash
# 미션
cp -R agents/troubleshoot-lab/templates/mission agents/troubleshoot-lab/missions/<분야>/<id>
# 시나리오
cp -R agents/troubleshoot-lab/templates/scenario agents/troubleshoot-lab/scenarios/<대표 분야>/<id>
```

- 디렉터리 이름이 곧 `id` 입니다(소문자, 숫자, `-`).
- 분야는 `network`(① 네트워크), `linux`(② 리눅스 서버), `webserver`(③ 웹 서버와 소켓), `db-cache`(④ 데이터베이스와 캐시),
  `lb-cloud`(⑤ 부하 분산과 클라우드), `monitoring`(⑥ 모니터링과 장애 대응) 중 하나이고, 상위 디렉터리로 정해집니다.
- 시나리오는 `fields` 에 1~3개 분야를 적고, 첫 번째가 상위 디렉터리와 같아야 합니다.
- 장애를 넣을 환경은 분야와 별개로 `env: compose | kind` 로 적습니다. 가드, 복원, 측정 대상이 이 값으로 정해집니다.

## 2. 지켜야 할 규칙

| 항목 | 규칙 |
|------|------|
| 이름 | `id` 와 `title` 은 **증상 기준**으로 짓습니다. 원인 단어(selector, port, env, cache 설정 이름 등)를 넣지 않습니다. 시작 명령 `/lab-start <id>` 가 Slack에 그대로 나가기 때문입니다 |
| 공개 범위 | `symptom` 은 Slack에, `start_hint` 는 시작할 때 CLI에 보입니다. 원인은 `hints.md` 의 힌트 3과 `solution.md` 에만 씁니다. `tags` 는 어디에도 게시되지 않습니다 |
| 힌트 | `## 힌트 1`, `## 힌트 2`, `## 힌트 3` 제목이 정확히 3개 있어야 합니다. 1은 어디를 볼지, 2는 무엇이 이상한지, 3은 거의 답을 씁니다 |
| 워밍업 | 시나리오마다 1~2개입니다. 시나리오를 풀 때 실제로 쓰는 명령을 익히는 미션을 연결합니다 |
| 스크립트 첫 줄 | shebang 다음에 `set -euo pipefail` 과 `source "$LAB_ROOT/lib/common.sh"` 두 줄로 시작합니다 |
| 환경 접근 | `kubectl`·`docker`·`docker compose` 를 직접 부르지 않고 `k`·`dk`·`dc` 를 씁니다. 이 함수들이 로컬 샌드박스 가드를 먼저 실행합니다 |
| inject | `environment/` 의 기본 파일은 고치지 않습니다. 작업 사본(`$LAB_WORK`)과 실행 중인 리소스만 바꾸고, 증상이 실제로 재현된 뒤에 0으로 끝냅니다 |
| verify | 특정 수정 방법이 아니라 **증상**으로 판정합니다(HTTP 200, rollout 완료 등). 실패 이유는 출력하지 않습니다 |
| reset | 시나리오 전용 정리 후 `environment/restore.sh <compose|kind>` 로 끝냅니다. 여러 번 실행해도 결과가 같아야 합니다 |
| 미션 command | 레포 루트에서 그대로 복사해 실행할 수 있는 비대화형 명령으로 씁니다(`-it`, 에디터, 페이저 금지). 샌드박스 테스트가 이 명령을 실행합니다 |
| 미션 answer | 기대값은 `setup.sh` 에서 `answer_set <step> <값>` 으로 저장하고, `verify.sh` 에서 `answer_is <step> "$answer"` 로 비교합니다 |
| 소요 시간 | `minutes` 를 현실적으로 적습니다. 워밍업 5~60, 개념 미션(`kind: concept`) 30~90, 시나리오 20~90입니다. 계획의 각 일차(주 항목 + 연결 워밍업 합)가 60~90분이어야 합니다 |
| 측정 | `measure` 에 경로·메서드·VU·시간·서비스를 적습니다. 정상 상태 오류율은 0%여야 하고, 장애 상태는 아래 기준 중 하나 이상을 만족해야 합니다(SC-005) |
| 면접 질문 | `interview` 에 1~2개. `docs/curriculum.md` §7 에서 고르고, 맞는 질문이 없으면 새로 씁니다 |
| 진단 경로 | 힌트의 진단 명령은 `/lab-exec <서비스> <명령>` 으로 씁니다. Mac 호스트에 없는 `ss`, `free`, `vmstat`, `top`, `dig` 를 호스트에서 치게 하지 않습니다 |
| YAML 키 | `token`, `password`, `*_key` 처럼 비밀값으로 보이는 키는 쓸 수 없습니다(로더가 거부) |

### 장애 상태 측정 기준 (SC-005)

샌드박스 테스트는 정상 측정과 장애 측정을 비교해 다음 중 하나 이상이 맞는지 확인합니다.

| 지표 | 기준 |
|------|------|
| 오류율 | +0.05 이상 |
| 평균 또는 p95 응답 시간 | ×1.5 이상, 또는 ÷1.5 이하(캐시가 잘못 적용되면 빨라져요) |
| CPU 최대 | +20%p 이상 |
| 메모리 최대 | ×1.3 이상 |
| 응답 시간 | `not_applicable` 로 바뀜(성공 요청 0건) |

### 학습 계획에 넣기

새 시나리오는 `curriculum/plan.yaml` 의 일차 `items` 나 `extras` 에 넣어야 합니다. `days` 와 `extras` 를 합쳐 모든 시나리오가 한 번 이상 나와야
`lab validate` 를 통과합니다.

## 3. 쓸 수 있는 헬퍼 (`lib/common.sh`)

| 함수 | 용도 |
|------|------|
| `need_kind` / `need_docker` | 준비 상태(종료 코드 5)와 로컬 샌드박스(종료 코드 3) 확인 |
| `k`, `dk`, `dc` | 고정된 kubeconfig·context의 kubectl, docker, 실습 프로젝트의 docker compose |
| `wait_http <url> <code> [초]`, `http_code <curl 인자...>` | HTTP 확인 |
| `wait_until <초> <명령...>` | 조건이 맞을 때까지 기다리기 |
| `http_burst <개수> <동시> <url> [curl 인자...]`, `http_burst_ok ...` | 동시 요청을 보내 상태 코드를 한 줄씩 출력 / 모두 200인지 확인 |
| `compose_override <서비스>` | 표준 입력의 YAML을 작업 사본 override 에 넣고 그 서비스를 다시 띄우기 |
| `tb <컨테이너> <명령...>` | 진단 toolbox 를 대상의 네트워크·PID 공간에 붙여 실행(inject·reset·setup 전용, `TB_CAPS=NET_ADMIN` 로 권한 추가) |
| `rand_token` | 8자리 무작위 값 |
| `answer_set` / `answer_get` / `answer_is` | 미션 answer 단계의 기대값 저장·비교 |
| `sed_inplace <파일> <식>` | macOS·Linux 공통 sed 편집 |
| `nginx_location <이름>` | 표준 입력의 location 블록을 compose nginx에 추가하고 reload |
| `nginx_reload` | compose nginx reload |
| `work_reset` | 작업 사본을 기본값으로 다시 만들기 |

## 4. 확인

```bash
agents/troubleshoot-lab/bin/lab validate   # 형식 검사: 오류 0 이어야 해요
uv run pytest agents/troubleshoot-lab/tests/content   # 정적 검사
make -C agents/troubleshoot-lab test-sandbox           # 실제 환경에서 측정 → inject → 측정 → verify → reset 검증 (Docker, kind 필요)
```

PR에서 `missions/`, `scenarios/`, `environment/`, `lib/` 가 바뀌면 GitHub Actions가 샌드박스 테스트를 자동으로 실행합니다.
