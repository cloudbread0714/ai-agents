# Contract: Claude Code 슬래시 명령

파일 위치는 `.claude/commands/lab-*.md`다. 사용자 호출 전용이다(R1). 모든 명령은 레포 루트에서
`agents/troubleshoot-lab/bin/lab ...`을 실행한다.

## 공통 규칙 (모든 명령 본문에 포함)

0. 6단계 중 사용자가 해야 할 단계(측정, 진단, 원인 분석, 보고서 작성)를 대신하지 않는다.
1. CLI를 실행하고 stdout을 그대로 보여 준다. `LAB_RESULT` 줄은 보여 주지 않는다.
2. CLI 출력에 없는 원인 추측, 추가 힌트, 해결 방법을 덧붙이지 않는다.
3. 진행 중인 미션·시나리오의 `hints.md`, `solution.md`, `inject.sh`, `verify.sh`, `reset.sh`, `setup.sh`와 `.lab-state/`를
   읽지 않는다.
4. 사용자가 이 명령과 별개로 도움을 요청하면 그때는 일반 대화로 돕는다. 이 규칙은 명령 실행 중에만 적용한다.
5. 종료 코드 3(로컬 샌드박스 아님)이 나오면 출력 내용을 전하고, 우회하려고 하지 않는다.
6. 종료 코드 5(환경 준비 안 됨)가 나오면 `make -C agents/troubleshoot-lab up`을 실행할지 묻는다. 직접 실행하지 않는다.

## 명령별

| 명령 | 실행 | 추가 동작 |
|------|------|-----------|
| `/lab-list` | `bin/lab list` | — |
| `/lab-start <이름>` | `bin/lab start $ARGUMENTS` | 이름이 없으면 `bin/lab list`를 실행하고 무엇을 시작할지 묻는다. 결과가 `locked`면 출력에 나온 워밍업을 먼저 시작할지 묻고, 동의하면 `bin/lab start <미션>`을 실행한다 |
| `/lab-hint` | `bin/lab hint` | — |
| `/lab-check [값]` | `bin/lab check $ARGUMENTS` | `sync_suggested`가 true이면 AskUserQuestion으로 "진행 기록을 커밋하고 push할까요?"를 묻는다(예 / 아니요). 예면 `bin/lab sync`를 실행하고 결과를 전한다 |
| `/lab-giveup` | 먼저 정말 포기할지 묻는다. 예면 `bin/lab giveup` | `/lab-check`와 같은 커밋·푸시 질문 |
| `/lab-reset` | `bin/lab reset $ARGUMENTS` | — |
| `/lab-measure [--skip 사유]` | `bin/lab measure $ARGUMENTS` | — |
| `/lab-inject` | `bin/lab inject` | outcome `need_measure`면 `/lab-measure` 를 먼저 하라는 출력만 전한다(대신 실행하지 않는다) |
| `/lab-exec <서비스> <명령...>` | `bin/lab exec <서비스> -- <명령...>` | 사용자가 적은 명령만 그대로 실행한다. 명령을 고르거나 덧붙이지 않고, 출력을 해석해 원인을 말하지 않는다 |
| `/lab-report [--done]` | `bin/lab report $ARGUMENTS` | `--done` 결과가 `reviewed`면 `/lab-check`와 같은 커밋·푸시 질문. `incomplete`면 빈 섹션 목록만 전한다. 보고서 내용을 대신 써 주지 않는다 |

## 권한

`.claude/settings.json`에 학습 명령만 서브명령별로 허용한다: `Bash(agents/troubleshoot-lab/bin/lab list:*)`, `start`, `hint`,
`check`, `giveup`, `reset`, `validate`, `env`, `measure`, `inject`, `report`, `shell`.
`exec`(임의 명령 실행)는 허용 목록에 넣지 않는다.

`lab sync`는 git push를 하므로 허용 목록에 넣지 않는다. 슬래시 명령의 질문에 더해, Claude Code 권한 확인이 한 번 더 확인하는 역할을 한다.
