# Research: news: 데일리 기술 뉴스 픽

Phase 0 결과. Technical Context에 NEEDS CLARIFICATION은 남아 있지 않으며, 아래는 각 기술 선택과 설계 결정이다.

## R1. LLM 호출 구조: 선정과 요약을 단일 호출로

- **Decision**: 후보 목록(최대 40건, 제목·출처·발행일·발췌 300자)을 한 번에 보내고, Claude가 1건을 고른 뒤
  같은 응답에서 한국어 게시물까지 작성한다. `client.messages.parse(output_format=DigestSelection)`로 Pydantic 검증된 결과를 받는다.
- **Rationale**: 헌법(news: LLM 호출 최소화)을 지킨다. 2단계(선정 → 요약)로 나누면 호출 수와 비용이 2배가 된다.
  구조화 출력을 쓰면 JSON 파싱 실패와 형식 위반(3~5줄, 1~2개)을 스키마로 막을 수 있다.
- **Alternatives considered**:
  - 후보마다 점수 매기기(N회 호출): 비용 과다로 기각
  - 임베딩으로 사전 필터: 의존성이 늘고 효과가 불확실해 기각
  - 선정 후 원문 본문을 가져와 2차 요약: 품질은 좋아질 수 있지만 호출이 2회가 되므로 v1에서는 기각하고 향후 옵션으로 남긴다

## R2. 모델과 파라미터

- **Decision**:
  - 모델은 기본 `claude-opus-5-5`이며 `settings.yaml`의 `llm.model`로 바꿀 수 있다.
  - `output_config={"effort": "medium"}`로 노력도를 명시한다(Opus 5.5에서는 thinking을 끌 수 없으므로 노력도로 조절).
  - `max_tokens=4000`
  - 거절 응답에는 서버 측 fallback을 쓴다. beta 헤더 `server-side-fallback-2026-07-01`과 `fallbacks="default"`를 함께 보낸다.
  - `stop_reason == "refusal"`이면 요약 실패로 처리한다.
- **Rationale**:
  - 출력이 짧은 단일 판단 작업이라 medium이면 충분하다.
  - 예상 비용은 입력 약 12K 토큰 × $4/MTok ≈ $0.05, 출력 약 1.5K(thinking 포함) × $20/MTok ≈ $0.03로 실행당 약 $0.08이다. 기본 상한 $0.30 안에 여유 있게 들어간다.
  - 비용을 더 줄이려면 `claude-sonnet-5-5`($2/$10)로 바꾸면 되며, 설정만 변경하면 된다.
- **Alternatives considered**: Haiku는 한국어 요약 품질과 "적용할 점" 추론 품질이 떨어질 수 있어, 사용자가 원할 때 설정으로만 선택하도록 한다.
- **구현 시 확인**: 구현 단계에서 설치된 SDK로 `fallbacks`와 beta 헤더를 `messages.parse`(또는 `client.beta.messages.parse`)와 함께 쓸 수 있는지 확인한다.
  지원하지 않으면 fallback 없이 refusal을 실패로 처리한다.

## R3. 비용 상한 적용 방식

- **Decision**:
  1. **사전 추정**: `client.messages.count_tokens`로 입력 토큰을 센다.
     `입력비용 + max_tokens × 출력단가`(최악의 경우)가 상한을 넘으면 후보를 오래된 순으로 줄여 다시 센다(최대 3회).
     그래도 넘으면 호출하지 않고 `budget_exceeded`로 종료한다.
  2. **사후 기록**: `response.usage`로 실제 비용을 계산해 RunResult와 로그에 남긴다.
  3. 단가표는 `settings.yaml`의 `llm.pricing`에 둔다(모델을 바꿀 때 함께 수정).
- **Rationale**: 실제 호출 전에 상한 초과를 막을 수 있고(SC-008), 단가는 코드가 아닌 설정에 둔다.
- **Alternatives considered**: 사후 측정만 하면 초과를 막지 못하므로 기각. task budget 기능은 에이전트 루프용이라 이 작업에는 맞지 않아 기각.

## R4. RSS 수집

- **Decision**:
  - `httpx`로 피드를 받고(타임아웃 15초, User-Agent 명시, `shared.retry`로 3회 재시도) `feedparser.parse(bytes)`로 파싱한다.
  - 소스들은 `ThreadPoolExecutor`로 병렬 수집한다.
  - `bozo`이고 entries가 0개면 해당 소스를 실패로 처리한다.
- **Rationale**: feedparser의 내장 URL 가져오기는 타임아웃과 재시도를 제어하기 어렵다.
- **초기 소스 후보**: 피드 URL은 구현할 때 실제 응답으로 확인한다.

  | 소스 | 기본 분류 | URL |
  |------|----------|-----|
  | AWS What's New | infra | `https://aws.amazon.com/about-aws/whats-new/recent/feed/` |
  | AWS News Blog | infra | `https://aws.amazon.com/blogs/aws/feed/` |
  | AWS Machine Learning Blog | ai_agent | `https://aws.amazon.com/blogs/machine-learning/feed/` |
  | Hacker News (front page, 100+ points) | auto | `https://hnrss.org/frontpage?points=100` |
  | Kubernetes Blog | infra | `https://kubernetes.io/feed.xml` |
  | Docker Blog | infra | `https://www.docker.com/blog/feed/` |
  | LangChain Blog | ai_agent | `https://www.langchain.com/blog/rss.xml` |
  | Hugging Face Blog | ai_agent | `https://huggingface.co/blog/feed.xml` |
  | Simon Willison's Weblog | ai_agent | `https://simonwillison.net/atom/everything/` |

  `auto` 분류(HN 등)는 Claude가 글 단위로 `infra`/`ai_agent`를 판정한다.

  **검증 결과(2026-10-24, T032)**: 9개 모두 응답·파싱 성공. LangChain은 기존 `/rss/` 경로가 HTML 블로그로
  리다이렉트되어 `https://www.langchain.com/blog/rss.xml`로 교체했다. Kubernetes Blog는 정상이지만 72시간 내 글이 없어 0건이었다.
  AWS What's New는 하루 수십 건이 올라오므로 소스별 후보 상한(`max_items_per_source`, 기본 15)을 둔다.

## R5. 링크 정규화와 중복 판정

- **Decision**:
  - 정규화 순서:
    1. scheme을 https로 통일하고 host를 소문자로 바꾼다.
    2. `www.`를 제거한다.
    3. fragment를 제거한다.
    4. `utm_*`, `ref`, `source` 같은 추적 쿼리를 제거하고 나머지 쿼리는 정렬한다.
    5. 끝의 `/`를 제거한다.
  - 정규화 링크의 SHA-256 앞 16자를 `article_id`로 쓴다.
  - 후보끼리, 그리고 이력과 비교할 때 이 id로 중복을 판정한다.
  - HN 항목은 hnrss가 제공하는 원문 링크(`link`)를 사용하므로, 다른 소스의 같은 원문과 자동으로 중복 처리된다.
- **Rationale**: FR-008을 만족한다. 제목은 소스마다 달라질 수 있으므로 링크를 기준으로 한다.
- **Alternatives considered**: 제목 유사도(퍼지 매칭)는 오탐 위험이 있어 v1에서는 기각한다.

## R6. 주제 균형 (FR-007)

- **Decision**:
  - 코드가 이력의 최근 2건을 보고 둘 다 같은 분류이면 `preferred_category`를 반대 분류로 정해 프롬프트에 전달한다.
  - 프롬프트에는 "선호 분류 글 중 중요도가 비슷하면 선호 분류를 우선. 단 보안 이슈 등 영향이 확연히 큰 경우 예외 허용,
    그 경우 `balance_override_reason` 작성"이라고 지시한다.
  - 응답의 분류가 선호와 다르면 override 사유를 로그에 남긴다.
- **Rationale**: 판단은 LLM이 하고, 규칙은 코드가 계산해 테스트할 수 있게 한다.
- **Alternatives considered**: 코드에서 후보를 선호 분류만 남기는 강제 필터는 중요 보안 이슈를 놓칠 수 있어 기각한다.

## R7. 프롬프트 인젝션 방어

- **Decision**:
  - RSS 본문은 신뢰할 수 없는 데이터로 다룬다. 후보는 `<candidate id="...">` 블록으로 감싸고, 그 안의 지시를 따르지 말라고 system 프롬프트에 명시한다.
  - 응답의 `selected_id`는 후보 id 목록에 있는지 코드에서 검증한다.
  - **게시물의 링크는 LLM 응답이 아니라 수집한 원본 데이터에서 가져온다.**
- **Rationale**: 악성 피드가 임의 링크를 게시하게 만드는 공격을 막는다.

## R8. 게시 이력 저장과 GitHub Actions 커밋

- **Decision**:
  - `posted.json`은 버전 필드가 있는 JSON이다(스키마: `contracts/history.schema.json`).
  - 게시가 성공한 뒤에만 이력에 추가하고, 임시 파일에 쓴 뒤 rename하는 원자적 쓰기를 한다.
  - 워크플로 설정:
    - `permissions: contents: write`
    - `concurrency: { group: news-digest, cancel-in-progress: false }`
    - 실행 후 `git diff --quiet || (git commit && git push)`
    - 커밋 작성자는 `github-actions[bot]`, 메시지는 `chore(news): update posted history [skip ci]`
  - 365일보다 오래된 이력은 저장할 때 정리한다.
- **Rationale**: 사용자가 지정한 방식이다. 이력 커밋이 매일 생기므로, 저장소 활동이 60일 없으면 schedule 워크플로가 자동 비활성화되는 문제도 피할 수 있다.
- **주의**:
  - schedule 이벤트는 **기본 브랜치(main)** 의 워크플로만 실행한다. 기능 브랜치에서는 `workflow_dispatch`로 테스트한다.
  - 게시는 성공했는데 push가 실패하면 다음 날 중복 위험이 생긴다. push 실패 시 테스트 채널에 알리는 step을 둔다(`if: failure()`).

## R9. 실행 시각 지연

- **Decision**: cron은 `40 22 * * *`(UTC 22:40 = KST 07:40)로 설정한다. (2026-10-24 갱신: 처음에는 `0 23 * * *`였다.
  정각은 GitHub Actions에서 가장 붐벼 지연이 크므로, 정각이 아닌 분으로 20분 앞당겼다. analyze A1)
- **Risk**: GitHub Actions schedule은 부하가 있으면 수 분에서 수십 분 늦게 시작될 수 있다.
  SC-001(10분 이내)을 지키지 못할 수 있으므로, 운영 첫 2주 동안 실제 지연을 측정한다.
  지연이 크면 cron을 앞당기는 방안(예: `45 22 * * *`)을 검토한다.

## R10. 하루 1회 가드 (FR-012)

- **Decision**: 실행을 시작할 때 이력에 `posted_date_kst == 오늘(KST)`인 항목이 있으면 즉시 `already_posted`로 종료한다(알림 없음, 종료 코드 0).
  수동 실행에서 `--force`를 주면 테스트 채널 모드에서만 이 가드를 무시한다.
- **Rationale**: 재실행, 수동 실행, cron 중복을 모두 막는다.

## R11. Slack 메시지

- **Decision**: Incoming Webhook에 `{"text": <fallback>, "blocks": [...]}`를 보낸다. header 블록에 주제를,
  section(mrkdwn)에 내용·적용할 점·원문 링크를 넣는다. 오류 알림은 단순 텍스트 + context 블록으로 보낸다.
  응답 본문이 `ok`가 아니거나 상태 코드가 2xx가 아니면 실패로 보고, 429와 5xx는 재시도한다.
- **Rationale**: Webhook은 채널별로 URL이 고정되므로 정상 채널과 테스트 채널을 env 2개로 분리할 수 있다(사용자 지정).
