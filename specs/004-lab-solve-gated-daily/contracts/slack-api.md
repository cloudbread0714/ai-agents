# Contract: `shared.slack` 봇 토큰 API

기존 `send_webhook`은 그대로 둔다(실패 알림·테스트 대상 미리 보기용). 아래 함수를 같은 모듈에 더한다.

## 공통

- 요청: `POST https://slack.com/api/<method>`, 헤더 `Authorization: Bearer <token>`, 본문 JSON(`reactions.get`만 GET 쿼리).
- 응답 본문의 `ok`가 false면 `error` 코드로 분기한다(research R3).
- 재시도: `shared.retry.retryable`, 최대 3회, 대상 표기 `slack-api:<method>`(토큰 없음).
- 예외:
  - `SlackApiError(method, code)` — 최종 실패. 메시지는 `"<method>: <code>"`. 토큰·본문 전문을 담지 않는다.
  - `SlackMessageGone(SlackApiError)` — `message_not_found` 전용.
- 모든 함수는 `client: httpx.Client | None`, `base_delay: float` 키워드를 받는다(테스트에서 지연 0).

## 함수

| 함수 | Web API | 반환 | 특이 사항 |
|---|---|---|---|
| `auth_test(token)` | `auth.test` | 봇 사용자 ID `str` | |
| `post_message(token, channel, payload, *, thread_ts=None)` | `chat.postMessage` | `(channel, ts)` | `payload`는 기존 `{"text", "blocks"}` 형식 그대로. `thread_ts`가 있으면 스레드 답글 |
| `get_reactions(token, channel, ts)` | `reactions.get` (`full=true`) | `dict[str, set[str]]` 반응 이름 → 사용자 ID 집합 | 반응이 없으면 `{}` |
| `add_reaction(token, channel, ts, name)` | `reactions.add` | `bool` 새로 달았으면 True | `already_reacted`면 False(오류 아님) |

## 필요한 봇 권한

`chat:write`, `reactions:read`, `reactions:write`. 봇은 lab 채널에 초대돼 있어야 한다(`not_in_channel` 방지).

## 테스트 계약

- `httpx_mock`으로 각 메서드의 성공, `ok:false` 오류, 429→성공 재시도, 5xx 소진을 검증한다.
- 어떤 경우에도 예외 메시지·로그에 토큰 문자열이 없어야 한다(픽스처 토큰 `xoxb-test-secret`로 검사).
