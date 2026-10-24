# Implementation Plan: news: 데일리 기술 뉴스 픽

**Branch**: `001-news-daily-digest` | **Date**: 2026-10-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-news-daily-digest/spec.md`

## Summary

매일 KST 07:40(8시 무렵 게시 목표)에 GitHub Actions cron이 `news-digest` CLI를 실행한다. 실행 순서는 다음과 같다.

1. YAML에 등록된 RSS 소스를 feedparser로 수집한다.
2. 코드에서 중복 제거, 신선도(72h) 필터, 후보 수 제한을 적용한다.
3. **Claude API를 1회 호출**해 글 1개를 선정하고, 한국어 요약과 적용 포인트를 구조화된 출력으로 받는다.
4. `shared/`의 Slack 모듈로 Incoming Webhook에 게시한다.

게시 이력은 레포 안 JSON 파일(`agents/news-digest/data/posted.json`)에 저장하고, 실행 후 워크플로가 커밋·푸시한다.
실패 경로(전체 수집 실패, 새 글 없음, 비용 상한 초과, 요약·게시 실패)에서는 테스트 채널 웹훅으로만 알린다.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**:
- `feedparser`: RSS/Atom 수집
- `httpx`: 피드 다운로드(타임아웃 제어)와 Slack 웹훅 POST
- `anthropic`: Claude API. `messages.parse` + Pydantic 구조화 출력, `count_tokens`
- `pydantic` v2: 설정·이력·LLM 출력 검증
- `pyyaml`: 소스·설정 파일
- `tenacity`: 공통 재시도

**Storage**: 레포 내 JSON 파일 `agents/news-digest/data/posted.json`. GitHub Actions가 실행 후 커밋한다.

**Testing**: pytest, `pytest-httpx`(HTTP 모킹), 고정 RSS 픽스처 파일. Anthropic 클라이언트는 테스트 더블로 주입한다.

**Target Platform**: GitHub Actions `ubuntu-latest`. cron은 `40 22 * * *`(UTC, KST 07:40)이고 `workflow_dispatch`로 수동 실행도 지원한다.

**Project Type**: CLI(배치 잡). uv workspace 모노레포의 멤버 패키지 2개(`agents/news-digest`, `shared`)로 구성한다.

**Performance Goals**: 1회 실행이 5분 안에 끝난다. 수집은 소스별 타임아웃 15초를 두고 병렬로 실행한다.

**Constraints**:
- 실행당 LLM 호출 1회(재시도 제외)
- 실행당 비용 상한 기본값 USD 0.30(설정으로 변경). `count_tokens`로 사전 추정하고, 상한을 넘으면 후보를 줄인 뒤 다시 추정한다.
- 비밀값은 환경변수로만 받는다.

**Scale/Scope**: 소스 약 10개, 실행당 후보 최대 40건, 하루 게시 1건, 이력은 1년치(약 365건, 수십 KB).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|------|------|------|
| I. 모노레포 경계 | ✅ | 에이전트 코드는 `agents/news-digest/`, Slack·LLM 클라이언트·재시도·설정 로딩은 `shared/`. 워크플로 파일은 예외(아래 Complexity Tracking) |
| II. Python 3.12 + uv | ✅ | 루트 uv workspace, `pyproject.toml`과 `uv.lock`을 커밋하고, 워크플로는 `astral-sh/setup-uv` 사용 |
| III. pytest 동반 | ✅ | 모듈별 단위 테스트와 파이프라인 통합 테스트. 외부 호출은 모두 모킹 |
| IV. 비밀값 환경변수 | ✅ | `ANTHROPIC_API_KEY`, `SLACK_WEBHOOK_URL_MAIN`, `SLACK_WEBHOOK_URL_TEST`는 GitHub Secrets에서 env로 주입. 로그에서 웹훅 URL 마스킹 |
| V. 재시도·로깅 | ✅ | `shared/retry.py`(tenacity, 지수 백오프, 최대 3회). Anthropic SDK는 `max_retries=3`. 실패 시 구조화 로그 |
| VI. 스펙 명명 | ✅ | `news:` 접두어 → `001-news-daily-digest` |
| news: LLM 호출 최소화·비용 상한 | ✅ | 선정과 요약을 단일 호출로 합치고, 비용 상한은 설정값으로 사전·사후 검증 |
| news: 중복 게시 금지 | ✅ | 정규화 링크 기준 dedup, KST 날짜 단위 1회 게시 가드 |

**Post-design re-check (Phase 1 이후)**: 위반 없음. 설계 산출물 어디에도 비밀값 저장이나 에이전트 간 직접 import가 없다.

## Project Structure

### Documentation (this feature)

```text
specs/001-news-daily-digest/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── cli.md           # CLI 인터페이스·종료 코드
│   ├── config.schema.md # sources.yaml / settings.yaml 스키마
│   ├── history.schema.json
│   ├── llm-output.md    # Claude 구조화 출력 스키마·프롬프트 계약
│   └── slack-message.md # 정상 게시물·오류 알림 형식
└── tasks.md             # /speckit-tasks 에서 생성
```

### Source Code (repository root)

```text
pyproject.toml                      # uv workspace 루트 (members: shared, agents/*)
uv.lock

shared/
├── pyproject.toml                  # package: shared
├── src/shared/
│   ├── __init__.py
│   ├── slack.py                    # Incoming Webhook 전송 (재시도·URL 마스킹)
│   ├── llm.py                      # Anthropic 클라이언트 팩토리, 사용량→비용 계산
│   ├── config.py                   # YAML + env 로딩 헬퍼
│   ├── retry.py                    # tenacity 기반 공통 재시도 데코레이터
│   └── logging.py                  # 구조화 로깅 설정
└── tests/

agents/news-digest/
├── pyproject.toml                  # package: news_digest, script: news-digest
├── config/
│   ├── sources.yaml                # RSS 소스 목록
│   └── settings.yaml               # 관심 분야, 비용 상한, 모델, 신선도 등
├── data/
│   └── posted.json                 # 게시 이력 (Actions가 커밋)
├── src/news_digest/
│   ├── __init__.py
│   ├── cli.py                      # 진입점, 인자 파싱, 종료 코드
│   ├── collector.py                # feedparser 수집 (소스별 결과·오류)
│   ├── normalize.py                # 링크 정규화, 후보 dedup
│   ├── history.py                  # posted.json 로드/저장, 오늘 게시 여부
│   ├── balance.py                  # 최근 이력 → 선호 주제 분류 계산
│   ├── selector.py                 # 프롬프트 구성, 비용 사전 추정, Claude 호출
│   ├── formatter.py                # Slack 블록 메시지 구성
│   ├── alerts.py                   # 테스트 채널 오류·경고 메시지
│   ├── pipeline.py                 # 전체 흐름·상태 결정 (RunResult)
│   └── models.py                   # Pydantic 엔티티
└── tests/
    ├── fixtures/                   # 샘플 RSS XML, 이력 JSON
    ├── unit/
    └── integration/

.github/workflows/
└── news-digest.yml                 # cron + workflow_dispatch, 이력 커밋
```

**Structure Decision**: 루트 `pyproject.toml`을 uv workspace로 두고 `shared`와 `agents/news-digest`를 멤버 패키지로 만든다.
`news_digest`는 `shared`를 workspace 의존성(`shared = { workspace = true }`)으로 사용한다.
troubleshoot-lab과 job-apply도 나중에 같은 방식으로 멤버를 추가한다.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `.github/workflows/news-digest.yml`이 `agents/news-digest/` 밖에 위치 | GitHub Actions는 `.github/workflows/`의 워크플로만 인식한다 | 에이전트 디렉터리 안에 두면 실행되지 않는다. 워크플로에는 로직 없이 `uv run news-digest` 호출만 둔다 |
| 실행 결과(`posted.json`)를 봇이 레포에 커밋 | 사용자가 레포 내 JSON 저장을 지정했고, 외부 저장소 없이 실행 간 상태를 유지할 수 있다 | Actions cache와 artifact는 만료·유실될 수 있어 중복 방지 보장이 깨진다. 동시 실행은 `concurrency` 그룹으로 막는다 |
