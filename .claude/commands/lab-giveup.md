---
disable-model-invocation: true
description: 진행 중인 시나리오를 포기하고 해설 보기
---

1. 먼저 AskUserQuestion으로 정말 포기할지 묻는다(선택지: 포기하고 해설 보기 / 계속 풀기).
2. 포기를 고르면 `agents/troubleshoot-lab/bin/lab giveup` 을 실행한다.
3. `LAB_RESULT` 줄의 `sync_suggested`가 true이면 AskUserQuestion으로 "진행 기록을 커밋하고 push할까요?"를 묻는다
(선택지: 예 / 아니요). 예를 고르면 `agents/troubleshoot-lab/bin/lab sync` 를 실행하고 결과를 전한다.
아니요면 기록은 로컬에만 남고 다음에 올릴 수 있다고 알려 준다.

## 규칙 (명령 실행 중 항상 지킨다)

1. 위 명령을 레포 루트에서 실행하고, 표준 출력을 그대로 보여 준다. 마지막 `LAB_RESULT ...` 줄은 보여 주지 않는다.
2. 출력에 없는 원인 추측, 추가 힌트, 해결 방법을 덧붙이지 않는다.
3. 진행 중인 미션·시나리오의 `hints.md`, `solution.md`, `inject.sh`, `verify.sh`, `reset.sh`, `setup.sh`와
   `agents/troubleshoot-lab/.lab-state/`를 읽지 않는다.
4. 사용자가 이 명령과 별개로 도움을 요청하면 그때는 일반 대화로 돕는다.
5. 종료 코드 3(로컬 샌드박스 아님)이 나오면 출력 내용을 전하고, 우회하려고 하지 않는다.
6. 종료 코드 5(환경 준비 안 됨)가 나오면 `make -C agents/troubleshoot-lab up` 을 실행할지 묻는다. 직접 실행하지 않는다.
