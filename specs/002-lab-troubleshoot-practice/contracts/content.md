# Contract: 미션·시나리오 콘텐츠와 스크립트

스키마는 data-model.md의 카탈로그 절을 따른다. 이 문서는 스크립트가 지켜야 할 실행 계약이다.

## 디렉터리

```text
agents/troubleshoot-lab/
├── missions/<field>/<id>/          # field: network | linux | webserver | db-cache | lb-cloud | monitoring
│   ├── mission.yaml
│   ├── setup.sh
│   └── verify.sh
├── scenarios/<대표 field>/<id>/
│   ├── scenario.yaml
│   ├── inject.sh
│   ├── verify.sh
│   ├── reset.sh
│   ├── hints.md
│   ├── solution.md
│   └── files/                 # (선택) inject가 쓰는 장애 설정 조각
├── curriculum/plan.yaml       # 1~21일 차와 심화 순서 (data-model.md Plan)
├── docs/curriculum.md         # 커리큘럼 원문 (research R27)
├── docs/reports/              # 장애 보고서 (contracts/report.md)
├── environment/k6/measure.js  # 공통 측정 스크립트 (contracts/measurement.md)
├── environment/toolbox/       # 진단 도구 이미지 (research R21)
├── templates/report.md        # 보고서 템플릿
├── templates/mission/         # 새 미션 복사용
├── templates/scenario/        # 새 시나리오 복사용
└── docs/authoring.md          # 작성 가이드
```

## 스크립트 실행 환경

CLI가 넣어 주는 환경변수:

| 변수 | 값 |
|------|-----|
| `LAB_ROOT` | `agents/troubleshoot-lab` 절대 경로 |
| `LAB_STATE` | `$LAB_ROOT/.lab-state` |
| `LAB_WORK` | `$LAB_STATE/work` |
| `LAB_ITEM_DIR` | 해당 미션·시나리오 디렉터리 |
| `KUBECONFIG` | `$LAB_ROOT/environment/.kube/config` |
| `COMPOSE_PROJECT_NAME` | `troubleshoot-lab` |

- 작업 디렉터리는 `$LAB_ITEM_DIR`이다.
- 제한 시간: setup·inject·reset은 300초, verify는 60초. 넘으면 실패로 처리한다.

## 공통 라이브러리 `lib/common.sh`

모든 스크립트는 첫 줄 다음에 반드시 아래 두 줄로 시작한다.

```bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
```

이 파일이 하는 일:
1. 샌드박스 가드를 실행한다(R3). 실패하면 종료 코드 3으로 끝난다.
2. 함수를 제공한다.
   - `k ...`: 고정 kubeconfig·context로 kubectl을 실행한다.
   - `dk ...`: 같은 가드 뒤에서 docker를 실행한다(exec, network, inspect 등).
   - `dc ...`: 고정 프로젝트로 `docker compose -p troubleshoot-lab -f environment/compose.yaml -f $LAB_WORK/compose.override.yaml`
     을 실행한다.
   - `wait_http <url> <code> [timeout]`
   - `answer_set <step> <value>`, `answer_get <step>`
   - `work_reset`: 작업 사본을 기본값으로 다시 만든다.
   - `tb <대상 컨테이너> <명령...>`: toolbox 이미지를 대상의 네트워크·PID 공간에 붙여 실행(inject·reset 전용, `TB_CAPS=NET_ADMIN`로 권한 추가 가능).
   - `compose_override <yaml>`: 표준 입력의 YAML을 작업 사본 override에 서비스 단위로 병합하고 `dc up -d <서비스>`.

정적 테스트가 강제하는 것:
- 두 줄로 시작하는지
- `kubectl`, `docker`, `docker compose`를 `k`, `dk`, `dc` 없이 직접 부르지 않는지
- `bash -n`을 통과하는지
- 실행 권한이 있는지

## 스크립트별 의미

| 스크립트 | 종료 코드 0의 뜻 | 출력 |
|----------|------------------|------|
| mission `setup.sh` | 미션 준비 완료. answer 단계 토큰 생성 | 로그로만 남는다 |
| mission `verify.sh <step> [answer]` | 그 단계 통과 | 실패해도 원인을 출력하지 않는다(로그에만) |
| scenario `inject.sh` | 장애가 재현됨(증상 확인까지 마친 뒤 0). `lab inject`가 baseline 측정 뒤에만 호출한다 | 로그로만 남는다 |
| scenario `verify.sh` | 증상이 사라짐(사용자가 해결함) | 로그로만 남는다 |
| scenario `reset.sh` | 시나리오 전용 정리 후 `environment/restore.sh`를 호출해 기본 상태로 복구되고 `environment/healthcheck.sh`가 통과함. 몇 번을 실행해도 결과가 같다 | 로그로만 남는다 |

## 기본 상태 복원과 상태 지문

- `environment/restore.sh`: 공통 기본 상태 복원. 몇 번을 실행해도 결과가 같다. CLI가 다음 시점에 실행한다.
  - 시나리오 inject 직전
  - 미션 완료와 미션 원복 때
  - 각 `reset.sh`의 마지막 단계
- 복원 내용:
  - `work_reset`
  - `k apply --prune -l lab.managed=true -f environment/k8s/` 후 rollout status
  - `dc up -d --remove-orphans`
  - `healthcheck.sh`
- 기본 리소스에는 라벨 `lab.managed=true`를 붙인다. 미션 setup이 바꾼 상태도 이 복원으로 사라진다(spec 경계 상황).
- `environment/fingerprint.sh`: 정규화한 상태 요약의 해시를 출력한다. 샌드박스 테스트가 inject 전과 reset 후의 값이 같은지 비교한다(SC-003). 요약 대상:
  - `lab` 네임스페이스 리소스 스펙(상태·메타데이터 제외)
  - `dc config` 결과
  - `$LAB_WORK` 파일 해시

## 준비 상태와 가드의 구분

`common.sh`는 가드(종료 코드 3)보다 먼저 준비 상태를 확인한다. 다음 경우에는 종료 코드 5와 `make up` 안내를 낸다.
- 필요한 쪽이 kind일 때: 전용 kubeconfig 파일이 없거나 클러스터 `troubleshoot-lab`이 없음
- 필요한 쪽이 Docker일 때: 데몬이 응답하지 않음

파일이 있는데 내용이 다른 곳을 가리킬 때만 가드가 3으로 거부한다.

## 작성 규칙 (docs/authoring.md에 포함)

- **이름**: id와 title은 증상 기준으로 짓는다. 원인 단어(selector, port, env, cache 설정 이름 등)를 넣지 않는다.
- **공개 범위**: `symptom`과 `start_hint`는 공개된다. 원인은 `hints.md`의 힌트 3과 `solution.md`에만 둔다.
- **힌트 3단계**:
  1. 어디를 볼지
  2. 무엇이 이상한지
  3. 거의 답
- **inject**: 기본 파일(`environment/`)을 직접 고치지 않는다. 작업 사본과 실행 중인 리소스만 바꾼다.
- **verify**: 사용자가 다른 방법으로 고쳐도 통과하도록 증상을 기준으로 판정한다(예: HTTP 200, Pod Ready, 응답 헤더). 특정
  수정 방법을 검사하지 않는다.
- **reset**: inject가 만든 것을 모두 되돌리고 기본 점검으로 끝낸다.
- **설정 키**: 비밀값처럼 보이는 키(`token`, `password`, `*_key`)를 YAML에 쓰지 않는다(R14).
- **미션 `command`**: 그대로 복사해 실행할 수 있는 비대화형 명령으로 쓴다(`-it`, 에디터, 페이저 금지). 샌드박스 테스트가 이 명령을 실행한다. `answer` 단계에서는 명령 출력에서 값을 찾는 대신 테스트가 `answers.json`의 값을 쓴다.
- **미션 상태 변경**: 미션이 환경을 바꿔도 된다. 끝날 때 CLI가 `restore.sh`로 되돌린다.
- **분야와 환경**: 대표 분야 디렉터리에 두고, `fields`(1~3개, 첫째 = 디렉터리)와 `env`(compose | kind)를 적는다.
- **측정 정의**: `measure`(경로, 메서드, VU, 시간, 서비스)를 적는다.
  - 정상 상태에서는 오류율 0%여야 한다.
  - 장애 상태에서는 다음 중 최소 1개를 만족해야 한다(SC-005). 샌드박스 테스트가 이 기준으로 확인한다.
    - 오류율 +0.05 이상
    - 평균 또는 p95 ×1.5 이상 또는 ÷1.5 이하(캐시가 잘못 적용되면 빨라진다)
    - CPU 최대 +20%p 이상
    - 메모리 최대 ×1.3 이상
    - 응답 시간이 `not_applicable`로 바뀜
- **개념 미션**: `kind: concept`이면 `minutes` 30~90이다. 개념 일차를 혼자 채운다.
- **면접 질문**: `interview`에 1~2개. 커리큘럼 §7에서 고르고, 맞는 질문이 없으면 새로 쓴다.
- **소요 시간**: `minutes`를 현실적으로 적는다. plan의 각 일차가 60~90분이 되는지 `lab validate`가 확인한다.
- **진단 경로**: 힌트에 쓰는 진단 명령은 `/lab-exec <서비스> <명령>`(toolbox 안에서 실행)로 적는다. 호스트에 없는 명령(`ss`, `free` 등)을 호스트에서 치게 하지 않는다.
