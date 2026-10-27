# Contract: #job-apply Slack 메시지

모든 메시지는 원래 공고 메시지의 **스레드 답글**이다(`thread_ts = 공고 메시지 ts`). 채널에 새 최상위 메시지는 올리지 않는다.
텍스트는 mrkdwn이며 사용자 입력(회사명 등)은 `escape_mrkdwn`으로 처리한다.

## 1. 완료 보고 (FR-020)

```text
✅ 지원 자료 준비 완료 — 예시회사 · 백엔드 개발자
• 마감: 2026-11-10 (D-14)
• 적합도: 72/100 — 백엔드 경험·Python은 일치, Kubernetes 운영 경험 부족
• 공고 요약: (job.md 요약 3줄)
• 폴더: agents/job-apply/applications/2026-10-27_예시회사_백엔드-개발자
• 렌더링: 문제 없음  |  ⚠️ 남은 문제 1건 (슬라이드 4: 글자 넘침)
• 처리하지 않은 링크: https://…   (메시지에 링크가 여러 개일 때만)
제출은 직접 해 주세요.
```

이어서 같은 스레드에 `resume.pdf`, `portfolio.pdf`를 올린다. 올린 파일 이름은 `<회사>_<직무>_resume.pdf`와 `<회사>_<직무>_portfolio.pdf`이고, 한 번의 `completeUploadExternal` 호출로 묶는다.
마지막으로 공고 메시지에 `white_check_mark` 반응을 단다.

## 2. 본문 요청 (FR-017)

공고 메시지에 `question` 반응을 달고, 스레드에 다음 답글을 남긴다.

```text
❓ 공고 페이지를 가져오지 못했어요 (사유: HTTP 403 / 본문이 너무 짧음 / 로그인 필요).
이 스레드에 공고 본문을 붙여 주시면 다음 /job-run 때 처리할게요.
```

같은 메시지에 `question` 반응이 이미 있으면 다시 요청하지 않는다(FR-018).

## 3. 중복으로 건너뜀 (FR-016)

```text
🔁 이미 처리한 공고예요 → agents/job-apply/applications/2026-10-01_가상테크_플랫폼-엔지니어 (적합도 65/100)
```

이어서 `white_check_mark` 반응을 단다.

## 4. 마감이 지나 정리 (`skip --reason expired --mark-done`)

```text
⏰ 마감(2026-10-20)이 지나 처리하지 않았어요.
```

이어서 `white_check_mark` 반응을 단다.

## 봇 답글 구분

`conversations.replies`에서 `bot_id`가 있거나 `user`가 우리 봇 사용자 id(`auth.test`로 얻음)인 답글은 사용자 본문으로 보지 않는다.
