# Contract: `lab` CLI

> 004에서 변경: 오늘의 문제 게시·주간 요약 일부는 [`specs/004-lab-solve-gated-daily/contracts/cli.md`](../../004-lab-solve-gated-daily/contracts/cli.md)를 따른다.

진입점은 `agents/troubleshoot-lab/bin/lab <subcommand>`(R10)이다.
- stdout: 사람이 읽는 한국어 텍스트
- stderr: 구조화 로그(JSON 한 줄)
- 학습 명령은 출력 마지막 줄에 `LAB_RESULT {json}`을 붙인다.

## 공통 종료 코드

| 코드 | 뜻 |
|------|-----|
| 0 | 성공 |
| 1 | 실행 실패(검증 실패, 스크립트·측정 오류, 게시 실패) |
| 2 | 사용법·설정 오류(알 수 없는 id, 카탈로그 오류, 필수 환경변수 누락) |
| 3 | 로컬 샌드박스가 아님(가드 거부) |
| 4 | 상태 충돌(진행 중 항목 있음, 잠김, 진행 중 항목 없음, 단계 순서 위반) |
| 5 | 실습 환경 준비 안 됨(`make -C agents/troubleshoot-lab up` 안내) |

## 학습 명령 (6단계, research R22)

| 명령 | 동작 | 주요 outcome | 종료 코드 |
|------|------|--------------|-----------|
| `lab list` | 분야(①~⑥)별 미션·시나리오 목록과 상태 | `ok` | 0 |
| `lab start <id>` | 미션: setup 후 첫 단계 안내. 시나리오: 진행 중 항목·잠금 확인 → 가드 → `restore.sh <env>` → `scenario_started(attempt)` → "1단계: 정상 상태를 측정하세요(/lab-measure)" 안내. **장애는 아직 주입하지 않는다** | `ok`, `locked`, `busy` | 0/1/2/3/4/5 |
| `lab measure [--skip 사유]` | 진행 중 시나리오의 단계(baseline·fault·after)를 상태로 정해 측정 1회(contracts/measurement.md). 결과 표를 출력 | `measured`, `skipped`, `failed`(측정 도구 오류), `none` | 0/1/4 |
| `lab inject` | baseline 측정(또는 skip)이 있어야 한다. 장애 주입 → `fault_injected` → 증상·`start_hint`·다음 단계 안내 | `ok`, `need_measure` | 0/1/4 |
| `lab exec <service> -- <cmd...>` | 진행 중 시나리오의 env(없으면 `--env compose\|kind`, 기본 compose)에서 toolbox 컨테이너로 대상의 네트워크·PID 공간에 붙어 명령 실행. 출력은 그대로 보인다 | `ok`, `target_down`, `unknown_service` | 명령 종료 코드 또는 2/3/5 |
| `lab shell <service>` | 사용자가 자기 터미널에서 실행할 대화형 진단 쉘 명령을 출력 | `ok` | 0 |
| `lab hint` | 진행 중 시나리오의 다음 힌트 | `ok`, `none` | 0/4 |
| `lab check [answer]` | 미션: 현재 단계 verify. 시나리오: fault 측정(또는 skip)이 없으면 `need_measure`. 있으면 verify. 성공 시 `scenario_solved` 기록 → after 측정 자동 실행 → 해설·회고 안내 | `failed`, `need_measure`, `solved`, `mission_step_passed`, `mission_completed` | 0/1/4 |
| `lab giveup` | `scenario_gave_up` 기록, 해설·회고 안내 | `gave_up`, `none` | 0/4 |
| `lab report [--done] [id]` | 인자 없이: 마지막으로 끝난 시도의 보고서 초안 생성(있으면 경로만). `--done`: 필수 섹션 검사 후 `report_completed` | `created`, `exists`, `incomplete`, `reviewed`, `none` | 0/1/4 |
| `lab reset [id]` | 기존과 같음. 측정 기록과 보고서는 지우지 않는다 | `ok`, `failed` | 0/1/3/5 |
| `lab sync` | `data/progress.json`과 `docs/reports/`만 커밋·push(main 브랜치) | `pushed`, `unchanged`, `wrong_branch`, `failed` | 0/1/4 |
| `lab validate` | 카탈로그와 plan 검사(분야, env, measure, interview, minutes, 60~90분 규칙) | — | 0/2 |
| `lab env` | `export KUBECONFIG, COMPOSE_FILE, COMPOSE_PROJECT_NAME, LAB_WORK` 출력 | — | 0 |

`sync_suggested`는 outcome이 `solved`, `gave_up`, `reviewed`일 때 true다.

`LAB_RESULT` 예:

```
LAB_RESULT {"command":"inject","kind":"scenario","id":"site-connection-refused","outcome":"need_measure","sync_suggested":false,"attempt":1,"stage":"started"}
```

## 게시 명령

```
lab daily [--target test|lab] [--dry-run] [--force] [--post daily|weekly|both] [--today YYYY-MM-DD]
```

옵션, 환경변수, 기록 규칙은 기존과 같다. 선택은 학습 계획 기반이다(data-model.md 일차 선택).
마지막 줄 요약 JSON의 `daily`에는 `{status, kind, day, main_id, second_id, backlog}`가 들어간다.
