# Data Model: news: 데일리 기술 뉴스 픽

모든 엔티티는 `agents/news-digest/src/news_digest/models.py`에 Pydantic v2 모델로 정의한다.

## Category (enum)

`infra` | `ai_agent`. 소스 설정에서는 `auto`(글 단위로 LLM이 판정)도 쓸 수 있다.

## Source

| 필드 | 타입 | 규칙 |
|------|------|------|
| `name` | str | 필수, 소스 목록 안에서 고유 |
| `url` | HttpUrl | 필수 |
| `category` | `infra` \| `ai_agent` \| `auto` | 필수 |
| `enabled` | bool | 기본 `true` |
| `max_items` | int \| None | 없으면 settings의 `max_items_per_source`를 사용 |

## Article (후보 글)

| 필드 | 타입 | 규칙 |
|------|------|------|
| `id` | str | `sha256(normalized_url)[:16]` |
| `title` | str | 공백 정리, 최대 300자 |
| `url` | str | 원본 링크(게시에 사용) |
| `normalized_url` | str | research R5 규칙 |
| `source` | str | Source.name |
| `category_hint` | Category \| `auto` | 소스의 기본 분류 |
| `published_at` | datetime (UTC, tz-aware) | 없으면 수집 시각으로 대체하고 `published_inferred=true` |
| `excerpt` | str | HTML 제거, 최대 300자 |

**검증**: `published_at`이 `now - freshness_hours`보다 이전이면 후보에서 제외한다. `id`가 이력에 있으면 제외한다.
후보끼리 `id`가 같으면 먼저 수집된 것(소스 목록 순서)만 남긴다.

## SourceResult

| 필드 | 타입 |
|------|------|
| `source` | str |
| `ok` | bool |
| `item_count` | int |
| `error` | str \| None (예외 클래스와 메시지 요약, 비밀값 없음) |

## DigestSelection (LLM 구조화 출력)

[contracts/llm-output.md](./contracts/llm-output.md) 참고.

| 필드 | 타입 | 규칙 |
|------|------|------|
| `selected_id` | str | 후보 id 중 하나여야 함(코드에서 검증) |
| `category` | `infra` \| `ai_agent` | |
| `title_ko` | str | 1줄, 최대 80자 |
| `summary_ko` | list[str] | 3~5개 |
| `apply_points_ko` | list[str] | 1~2개 |
| `selection_reason` | str | 로그용, 게시하지 않음 |
| `balance_override_reason` | str \| None | 선호 분류와 다른 글을 고른 경우 |
| `low_relevance` | bool | 모든 후보의 관련도가 낮을 때 true |

## DigestPost (게시물)

| 필드 | 출처 |
|------|------|
| `title_ko`, `summary_ko`, `apply_points_ko` | DigestSelection |
| `url`, `source` | **선택된 Article**(LLM 응답이 아님) |

## PostRecord (게시 이력 항목)

스키마: [contracts/history.schema.json](./contracts/history.schema.json)

| 필드 | 타입 |
|------|------|
| `article_id` | str |
| `url` | str (정규화 링크) |
| `title` | str (원문 제목) |
| `title_ko` | str |
| `category` | `infra` \| `ai_agent` |
| `source` | str |
| `posted_at` | datetime (UTC ISO-8601) |
| `posted_date_kst` | date (YYYY-MM-DD) |

`posted.json` = `{ "version": 1, "posts": [PostRecord, ...] }`. 시간순으로 정렬하고, 저장할 때 365일이 지난 항목은 정리한다.

## Settings

[contracts/config.schema.md](./contracts/config.schema.md) 참고. 관심 분야(InterestProfile), 신선도, 후보 상한, LLM 설정, 비용 상한, 단가표를 포함한다.

## RunResult와 상태 전이

```text
start
  ├─ 오늘 이미 게시됨 ───────────────▶ ALREADY_POSTED   (알림 없음, exit 0)
  ├─ 수집: 전 소스 실패 ──────────────▶ COLLECT_FAILED   (테스트 채널 오류, exit 1)
  ├─ 후보 0건 ──────────────────────▶ NO_NEW_ARTICLES  (테스트 채널 알림, exit 0)
  ├─ 비용 사전 추정 상한 초과 ─────────▶ BUDGET_EXCEEDED  (테스트 채널 오류, exit 1)
  ├─ LLM 실패/거절/검증 실패 ──────────▶ SELECT_FAILED    (테스트 채널 오류, exit 1)
  ├─ Slack 게시 실패 ─────────────────▶ POST_FAILED      (테스트 채널 오류, 이력 미기록, exit 1)
  └─ 게시 성공 → 이력 저장 ────────────▶ POSTED           (부분 실패·low_relevance면 테스트 채널 경고, exit 0)
```

| 필드 | 타입 |
|------|------|
| `run_at` | datetime |
| `status` | 위 enum |
| `source_results` | list[SourceResult] |
| `candidate_count` | int |
| `selected` | DigestSelection \| None |
| `estimated_cost_usd` / `actual_cost_usd` | float \| None |
| `warnings` | list[str] |
| `error` | str \| None |
