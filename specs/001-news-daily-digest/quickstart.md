# Quickstart: news-digest 검증 가이드

이 기능이 끝까지 동작하는지 확인하는 실행 시나리오다. 인터페이스 세부는 [contracts/](./contracts/), 엔티티는 [data-model.md](./data-model.md)를 참고한다.

## 사전 준비

- Python 3.12, `uv`
- Slack Incoming Webhook 2개: 정상 채널용, 테스트 채널용
- Anthropic API 키

```bash
cp agents/news-digest/.env.example agents/news-digest/.env   # 값 채우기 (.env는 커밋되지 않음)
set -a && source agents/news-digest/.env && set +a
uv sync --all-packages
```

## 1. 자동 테스트 (네트워크·비밀값 불필요)

```bash
uv run pytest shared agents/news-digest
```

기대 결과: 모두 통과한다. 다음 경로를 모킹으로 검증해야 한다.
- 정상 게시
- 이미 게시한 글 제외
- 다른 소스의 같은 원문 중복 처리
- 연속 2회 같은 분류 → 선호 분류 전달
- 하루 1회 가드
- 전 소스 실패 / 새 글 없음 / 비용 초과 / LLM 거절 / 게시 실패 시 테스트 채널 알림만 전송
- 게시 실패 시 이력 미기록

## 2. 드라이런 (실제 RSS + 실제 Claude, Slack 전송 없음)

```bash
uv run --package news-digest news-digest --dry-run --force
```

기대 결과:
- stdout에 주제 1줄, 내용 3~5줄, 적용할 점 1~2개, 원문 링크가 출력된다.
- 마지막 줄 JSON의 `status`가 `POSTED`이고 `actual_cost_usd`가 0.30 이하다.
- `git status`에서 `posted.json`이 변경되지 않는다.

## 3. 테스트 채널 게시

```bash
uv run --package news-digest news-digest --target test --force
```

기대 결과: 테스트 채널에 `[TEST]` 게시물 1건이 올라오고 Slack 형식이 contracts/slack-message.md와 같다. 이력은 바뀌지 않는다.

## 4. 실패 경로 수동 확인

```bash
# 모든 소스를 존재하지 않는 URL로 바꾼 임시 설정
uv run --package news-digest news-digest --target test --force --config-dir agents/news-digest/tests/fixtures/config-broken
```

기대 결과: 테스트 채널에 `COLLECT_FAILED` 알림이 오고 exit 1로 종료한다.

## 5. GitHub Actions

1. 레포 Settings → Secrets에 `ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL_MAIN`, `SLACK_WEBHOOK_URL_TEST`를 등록한다.
2. Actions → news-digest → **Run workflow**를 누르고 `target=test`로 실행한다. 테스트 채널 게시를 확인한다.
3. main에 병합한 뒤 `target=main`으로 1회 실행한다. 다음을 확인한다.
   - 정상 채널에 게시된다.
   - `github-actions[bot]`이 `agents/news-digest/data/posted.json` 커밋을 만든다.
4. 같은 날 다시 `target=main`으로 실행하면 `ALREADY_POSTED`로 끝나고 게시되지 않는다.
5. 다음 날 08:00 KST 전후로 schedule 실행이 일어나는지 확인하고, 실제 시작 지연을 기록한다(research R9).
