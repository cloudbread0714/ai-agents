# Contract: Slack 메시지

전송은 `shared.slack.send_webhook(url, payload)`로 한다. 성공 조건은 HTTP 2xx이면서 응답 본문이 `ok`인 것이다.
429, 5xx, 네트워크 오류는 재시도하고(최대 3회, 지수 백오프), 4xx(429 제외)는 즉시 실패로 처리한다.
로그에서 웹훅 URL은 `https://hooks.slack.com/services/***`로 마스킹한다.

## 정상 게시물 (정상 채널, 또는 `--target test`일 때 테스트 채널)

```json
{
  "text": "📰 <title_ko>",
  "blocks": [
    { "type": "header", "text": { "type": "plain_text", "text": "📰 <title_ko>" } },
    { "type": "section", "text": { "type": "mrkdwn",
      "text": "*내용*\n• <summary_ko[0]>\n• <summary_ko[1]>\n• <summary_ko[2]>" } },
    { "type": "section", "text": { "type": "mrkdwn",
      "text": "*나에게 적용할 점*\n1. <apply_points_ko[0]>\n2. <apply_points_ko[1]>" } },
    { "type": "section", "text": { "type": "mrkdwn",
      "text": "*원문*  <<url>|<source> 원문 보기>" } },
    { "type": "context", "elements": [ { "type": "mrkdwn",
      "text": "분류: <infra|ai_agent> · 2026-10-25" } ] }
  ]
}
```

- 사용자가 지정한 형식 이름 "주제"는 header로 표시한다.
- LLM 출력에 들어 있는 `&`, `<`, `>`는 Slack mrkdwn 규칙에 따라 이스케이프한다.
- `--target test`일 때는 header 앞에 `[TEST] `를 붙인다.

## 오류·경고 알림 (테스트 채널만)

```json
{
  "text": "⚠️ news-digest <STATUS>",
  "blocks": [
    { "type": "section", "text": { "type": "mrkdwn",
      "text": "*⚠️ news-digest: <STATUS>*\n단계: <collect|select|post|budget>\n원인: <error 요약>" } },
    { "type": "context", "elements": [ { "type": "mrkdwn",
      "text": "실행: 2026-10-25 08:03 KST · 후보 <n>건 · 실패 소스: <a, b> · <GitHub Actions run URL>" } ] }
  ]
}
```

| 상황 | 제목 | 정상 채널 게시 |
|------|------|---------------|
| 전 소스 수집 실패 | `COLLECT_FAILED` | 안 함 |
| 새 글 없음 | `NO_NEW_ARTICLES` | 안 함 |
| 비용 상한 초과 | `BUDGET_EXCEEDED` | 안 함 |
| LLM 실패·거절 | `SELECT_FAILED` | 안 함 |
| 게시 실패 | `POST_FAILED` | 실패 |
| 일부 소스 실패 | `WARNING: partial collect` | 함 |
| 관련도 낮음 | `WARNING: low relevance` | 함 |
| 이력 push 실패(워크플로 step) | `WARNING: history not pushed` | 이미 함 |

테스트 채널 전송까지 실패하면 stderr 로그만 남기고 exit 1로 종료한다. 이 경우 Actions 실패 메일로 사용자가 알게 된다.
