# Contract: Slack 메시지

> 004에서 변경: 오늘의 문제 게시·주간 요약 일부는 [`specs/004-lab-solve-gated-daily/contracts/slack-message.md`](../../004-lab-solve-gated-daily/contracts/slack-message.md)를 따른다.

전송은 `shared.slack.send_webhook`으로 하고, 실패 알림은 `shared.alerts`를 쓴다.
`test` 대상이면 헤더 앞에 `[TEST] `를 붙이고, mrkdwn 특수문자는 `shared.slack.escape_mrkdwn`으로 이스케이프한다.

## 오늘의 일차

```
📚 {N}일 차 · {W}주 차: {topic}                       ← header (kind=day)
   🔁 따라잡기 날                                      ← kind=catchup
📚 {N}일 차 · {W}주 차: {topic} (종합: 후보 중 1개)     ← kind=day, pool 일차
   🧩 심화 문제 {n}/5                                  ← kind=extra
   🔁 복습 문제                                        ← kind=review
⏱ 예상 {minutes}분 (60~90분 기준)   {90분 초과면: "⚠️ 오늘 분량이 90분을 넘어요"} {60분 미만이면: "남는 시간에는 '시간이 남으면'이나 밀린 문제를 해 보세요"}
*오늘 실습* {practice}                                 (kind=day)

*🧪 주 문제* {title}   {이미 해결했으면: "· 복습" 다음 줄에 "이번에는 이 관점으로: {practice}"}
*난이도* {초급|중급|고급}   *분야* {①~⑥ 이름}   *#*{curriculum_no}
*증상*
{symptom}
*시작* `/lab-start {id}`  → 정상 상태 측정 → 장애 재현 → 관찰 → 분석 → 해결 → 보고서

(주 항목이 개념 미션이면)
*🧭 개념 미션* {title} — `/lab-start {mission_id}`

*워밍업*
• ✅ {mission title} — 완료됨
• ⬜ {mission title} — `/lab-start {mission_id}`

*시간이 남으면* {second title} — `/lab-start {second id}`          (second 있을 때)
*밀린 문제* (최대 3개)
• {title} — `/lab-start {id}`
⚠️ 진행 중인 시나리오({title})가 있어요. 끝내거나 `/lab-reset` 후 시작하세요.   (있을 때)
context: {YYYY-MM-DD (요일)} · 터미널: agents/troubleshoot-lab/bin/lab start {id}
```

**금지(SC-002)**: 메시지에 다음 내용이 들어가면 안 된다. 테스트는 이 파일들에 넣은 표식 문자열이 payload 어디에도 없는지 확인한다.
- `hints.md`의 내용
- `solution.md`의 내용
- `tags`
- `start_hint`
- `interview`(면접 질문은 보고서에서만 다룬다)
- `measure` 정의

## 주간 요약

```
📊 이번 주 학습 요약 ({MM/DD}~{MM/DD})
*진행* {N}/21일 차 (또는 "심화 n/5", "복습 단계")
*해결* {n}개   *포기* {n}개   *힌트* {n}회
*회고* 완료 {n}개 · 면접 질문 답변 {n}개
*회고 대기* • {title} (시도 {k})  … 최대 5개
*약한 분야* {분야 | 기록 없음}
*밀린 문제* {n}개
*다음 주제* {내일 일차 주제 또는 주 항목 제목}
{활동이 없으면 숫자 줄 대신: "이번 주에는 기록이 없어요. 다음 주제부터 시작해 볼까요?"}
```

## 실패·경고 알림 (항상 테스트 채널)

기존과 같다(`shared.alerts.alert_payload`, `warning_payload`, 에이전트 이름 `troubleshoot-lab`).
plan 오류도 카탈로그 오류와 같은 경고로 보낸다.
