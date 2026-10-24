---
disable-model-invocation: true
description: troubleshoot-lab 미션 또는 시나리오 시작
argument-hint: <미션 또는 시나리오 id>
---

인자: $ARGUMENTS

- 인자가 비어 있으면 `agents/troubleshoot-lab/bin/lab list` 를 실행해 보여 주고, 무엇을 시작할지 묻는다.
- 인자가 있으면 `agents/troubleshoot-lab/bin/lab start $ARGUMENTS` 를 실행한다.
- `LAB_RESULT`의 outcome이 `locked`이면, `missing_warmups`의 첫 미션부터 시작할지 묻고 동의하면
  `agents/troubleshoot-lab/bin/lab start <미션 id>` 를 실행한다.
- outcome이 `busy`이면 진행 중인 항목을 끝내거나 `/lab-reset` 하라는 출력 내용을 그대로 전한다.

## 규칙 (명령 실행 중 항상 지킨다)

1. 위 명령을 레포 루트에서 실행하고, 표준 출력을 그대로 보여 준다. 마지막 `LAB_RESULT ...` 줄은 보여 주지 않는다.
2. 출력에 없는 원인 추측, 추가 힌트, 해결 방법을 덧붙이지 않는다.
3. 진행 중인 미션·시나리오의 `hints.md`, `solution.md`, `inject.sh`, `verify.sh`, `reset.sh`, `setup.sh`와
   `agents/troubleshoot-lab/.lab-state/`를 읽지 않는다.
4. 사용자가 이 명령과 별개로 도움을 요청하면 그때는 일반 대화로 돕는다.
5. 종료 코드 3(로컬 샌드박스 아님)이 나오면 출력 내용을 전하고, 우회하려고 하지 않는다.
6. 종료 코드 5(환경 준비 안 됨)가 나오면 `make -C agents/troubleshoot-lab up` 을 실행할지 묻는다. 직접 실행하지 않는다.
