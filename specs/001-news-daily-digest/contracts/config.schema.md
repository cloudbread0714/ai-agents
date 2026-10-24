# Contract: 설정 파일

두 파일 모두 시작할 때 Pydantic으로 검증한다. 위반하면 exit 2로 종료한다.

## `config/sources.yaml`

```yaml
sources:
  - name: AWS What's New          # 필수, 고유
    url: https://aws.amazon.com/about-aws/whats-new/recent/feed/
    category: infra                # infra | ai_agent | auto
    max_items: 15                  # 선택
  - name: Hacker News
    url: https://hnrss.org/frontpage?points=100
    category: auto
  - name: LangChain Blog
    url: https://www.langchain.com/blog/rss.xml
    category: ai_agent
    enabled: false                 # 선택, 기본 true
```

검증 규칙: `name`은 고유해야 하고, `url`은 http(s)여야 하며, 활성 소스가 1개 이상 있어야 한다.

## `config/settings.yaml`

```yaml
interests:
  infra:
    - 클라우드 인프라(AWS)
    - Docker
    - Kubernetes
    - CI/CD
    - 모니터링
  ai_agent:
    - LLM 활용
    - 에이전트 프레임워크
    - MCP
    - 자동화
  career:
    - DevOps 취업 준비

selection:
  priority: [relevance, practical_impact, learning_value]
  freshness_hours: 72
  max_items_per_source: 15
  max_candidates: 40
  balance_window: 2             # 최근 N건이 같은 분류면 반대 분류 우선

llm:
  model: claude-opus-5-5
  effort: medium
  max_tokens: 4000
  max_retries: 3
  fallbacks: default            # 서버 측 refusal fallback, 끄려면 null

budget:
  max_cost_usd_per_run: 0.30

pricing:                        # USD per 1M tokens, 모델을 바꾸면 함께 수정
  claude-opus-5-5:   { input: 4.00, output: 20.00 }
  claude-sonnet-5-5: { input: 2.00, output: 10.00 }
  claude-haiku-5-5:  { input: 0.10, output: 0.50 }

timezone: Asia/Seoul
```

검증 규칙:
- `llm.model`은 `pricing`에 있어야 한다.
- `max_cost_usd_per_run`은 0보다 커야 한다.
- `freshness_hours`는 24 이상이어야 한다.
- 비밀값 키(`*_key`, `*webhook*`)가 있으면 오류로 처리한다(헌법 IV).
