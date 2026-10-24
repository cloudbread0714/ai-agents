# ai-agents

여러 AI 에이전트를 담는 모노레포입니다. 원칙은 [헌법](.specify/memory/constitution.md)에 있습니다.

| 에이전트 | 설명 | 상태 |
|----------|------|------|
| [news-digest](agents/news-digest/) | 매일 08:00 KST 무렵 기술 뉴스 1건을 골라 Slack에 한국어로 게시 | 구현 완료 |
| troubleshoot-lab | 로컬 샌드박스 장애 주입·복구 실습 | 예정 |
| job-apply | 이력서 기반 지원서 초안 작성 | 예정 |

## 구조

```text
shared/                 # 에이전트 공용: Slack 전송, LLM 클라이언트, 설정 로딩, 재시도, 로깅
agents/<에이전트명>/      # 에이전트별 코드 (서로 직접 import 하지 않음)
specs/NNN-<prefix>-*/   # Spec Kit 스펙 (news:, lab:, job:, shared: 접두어)
.github/workflows/      # 에이전트별 워크플로
```

## 개발

Python 3.12와 [uv](https://docs.astral.sh/uv/)를 사용합니다. 루트가 uv workspace이고, `shared`와 `agents/*`가 멤버입니다.

```bash
uv sync --all-packages
uv run pytest                 # 전체 테스트 (각 패키지 디렉터리에서도 실행 가능)
uv run ruff check . && uv run ruff format --check .
```

새 에이전트는 `agents/<이름>/pyproject.toml`에 `shared = { workspace = true }` 의존성을 두고 만듭니다.
새 기능은 Spec Kit 흐름(`/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`)을 따릅니다.

비밀값은 환경변수로만 받고 커밋하지 않습니다(`.env`는 `.gitignore`에 등록되어 있습니다).
