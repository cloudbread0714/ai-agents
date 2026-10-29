---
disable-model-invocation: true
description: 진행 중인 미션 단계나 시나리오를 검증
argument-hint: [값 — 미션 단계가 값을 요구할 때]
---

`agents/troubleshoot-lab/bin/lab check $ARGUMENTS` 를 실행한다.

`LAB_RESULT` 줄의 `sync_suggested`가 true이면 AskUserQuestion으로 "진행 기록을 커밋하고 push할까요?"를 묻는다
(선택지: 예 / 아니요). 예를 고르면 `agents/troubleshoot-lab/bin/lab sync` 를 실행하고 결과를 전한다.
아니요면 기록은 로컬에만 남고 다음에 올릴 수 있다고 알려 준다.

## 규칙 (명령 실행 중 항상 지킨다)

0. 6단계 중 사용자가 해야 할 단계(측정, 진단, 원인 분석, 보고서 작성)를 대신하지 않는다.
1. 위 명령을 레포 루트에서 실행하고, 표준 출력을 그대로 보여 준다. 마지막 `LAB_RESULT ...` 줄은 보여 주지 않는다.
2. 출력에 없는 원인 추측, 추가 힌트, 해결 방법을 덧붙이지 않는다.
3. 진행 중인 미션·시나리오의 `hints.md`, `solution.md`, `inject.sh`, `verify.sh`, `reset.sh`, `setup.sh`와
   `agents/troubleshoot-lab/.lab-state/`를 읽지 않는다.
4. 사용자가 이 명령과 별개로 도움을 요청하면 그때는 일반 대화로 돕는다.
5. 종료 코드 3(로컬 샌드박스 아님)이 나오면 출력 내용을 전하고, 우회하려고 하지 않는다.
6. 종료 코드 5(환경 준비 안 됨)가 나오면 `make -C agents/troubleshoot-lab up` 을 실행할지 묻는다. 직접 실행하지 않는다.
7. 출력 끝의 Slack ✅ 안내 줄(달았어요/달지 못했어요/남은 항목 등)도 그대로 보여 준다. `LAB_RESULT`의 `slack_reaction`이
   `no_config`·`failed`·`not_open`이면 "Slack 오늘의 문제 메시지에 직접 ✅를 달아도 된다"는 한 줄만 덧붙일 수 있다.
