---
disable-model-invocation: true
description: Slack #job-apply에 모아 둔 공고를 오래된 순으로 처리 (제출은 직접)
argument-hint: [개수]
---

처리할 개수: $ARGUMENTS (비어 있으면 대상 전부)

모든 `agents/job-apply/bin/job ...` 명령은 레포 루트에서 실행한다. 출력 마지막의 `JOB_RESULT {...}` 줄로 결과를 판단하고, 그 줄은 사용자에게 보여 주지 않는다.

## 순서

1. `agents/job-apply/bin/job doctor` 를 실행한다. `slack_ready` 가 false이거나 `missing` 이 있으면 무엇이 빠졌는지 알리고 멈춘다.
2. `agents/job-apply/bin/job inbox [--limit <개수>]` 를 실행한다.
3. `fetch` 가 `images` 인 항목은 `/tailor` 의 3-1단계를 그대로 한다(이미지를 모두 열어 본문을 `text_path` 에 옮겨 적기).
   그다음 각 `items[].text_path` 를 읽고 회사·직무·마감일(YYYY-MM-DD, 없으면 상시)을 추출한다. 찾지 못한 값은 "미상"으로 둔다.
4. **처리 전 목록**을 아래 형식으로 보여 주고 확인을 받는다. 사용자가 확인하기 전에는 아무 공고도 처리하지 않는다.
   - 회사·직무가 "미상"인 공고의 이름을 묻는다.
   - 마감이 지난 공고: 이번만 건너뛰기 / 건너뛰고 ✅로 정리 / 처리
   - 이미 처리한 공고(`duplicate_of`): 새로 만들기 / 건너뛰기
   - 전체 진행 여부
5. 선택에 따라 실행한다.
   - 마감 지난 공고를 이번만 건너뛰면: 아무것도 하지 않는다(다음 실행 때 다시 나온다).
   - 건너뛰고 ✅로 정리하면: `agents/job-apply/bin/job skip <id> --reason expired --deadline <추출한 마감일> --mark-done`
   - 이미 처리한 공고를 건너뛰면: `agents/job-apply/bin/job skip <id> --reason duplicate`
   - 처리할 공고는 하나씩 `/tailor` 의 **공고별 처리** 1~9단계를 그대로 한다(`.claude/commands/tailor.md`). 새로 만들기를 고른 중복 공고는 `init` 에 `--new` 를 붙인다.
     `complete` 가 Slack 스레드 답글, PDF 2개, ✅를 남긴다. exit 7(Slack 오류)이면 알리고, 같은 `complete` 를 다시 실행하면 빠진 단계부터 이어서 한다.
6. 끝나면 공고별 결과 요약(완료·건너뜀·본문 요청·실패, 적합도, 폴더)을 보여 준다.

## 처리 전 목록 형식

```text
처리 대상 3건 (오래된 순)
 1. 예시회사 · 백엔드 개발자 · 마감 2026-11-10
 2. 샘플랩스 · 데이터 엔지니어 · 마감 2026-10-20 ⚠️ 마감 지남
 3. 가상테크 · 플랫폼 엔지니어 · 상시 · 🔁 이미 처리됨 (applications/2026-10-01_가상테크_플랫폼-엔지니어)
본문 대기 1건: https://…  (스레드에 본문을 붙이면 다음 실행 때 처리)
이번에 본문 요청 1건: https://…
공고가 아닌 메시지 2건 제외
```

- "본문 대기"는 `awaiting_body`, "이번에 본문 요청"은 `requested_now`(❓와 요청 답글은 `inbox` 가 이미 남겼다), "제외"는 `excluded_non_posting` 이다.
- 대상이 0건이면 그 사실과 본문 대기·요청 건수만 알리고 끝낸다.

## 규칙

`/tailor` 의 규칙 1~7을 그대로 지킨다(`.claude/commands/tailor.md`). 특히 원본에 없는 사실을 만들지 않고, 지원서를 제출하지 않는다.
