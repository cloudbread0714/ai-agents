# AI Agents Monorepo Constitution

## Core Principles

### I. 모노레포 경계와 공유 코드

- 이 레포는 여러 개의 AI 에이전트를 담는 모노레포다.
- 각 에이전트의 코드는 MUST `agents/<에이전트명>/` 아래에만 작성한다.
  현재 에이전트: `news-digest`, `troubleshoot-lab`, `job-apply`.
- 둘 이상의 에이전트가 함께 쓰는 코드(Slack 전송, LLM 호출, 설정 로딩 등)는 MUST `shared/`에 둔다.
- 에이전트끼리 서로의 디렉터리를 직접 import 해서는 MUST NOT 한다. 공유가 필요하면 `shared/`로 옮긴다.

근거: 에이전트를 독립적으로 개발·테스트·배포하면서도 공통 인프라 코드가 중복되지 않게 하기 위함.

### II. 표준 기술 스택 (Python 3.12 + uv)

- 언어는 MUST Python 3.12를 사용한다.
- 패키지·가상환경 관리는 MUST `uv`를 사용한다. `pip install`로 직접 설치하거나
  `requirements.txt`만으로 의존성을 관리해서는 MUST NOT 한다.
- 의존성은 `pyproject.toml`에 선언하고 lock 파일(`uv.lock`)을 커밋한다.

근거: 모든 에이전트에서 실행 환경을 재현할 수 있고 도구도 일관되게 맞추기 위함.

### III. 테스트 동반 (pytest)

- 모든 기능은 MUST pytest 테스트와 함께 작성한다. 테스트가 없는 기능 PR은 병합하지 않는다.
- 외부 API(LLM, Slack, 웹 등)는 테스트에서 MUST 모킹하며, 테스트가 실제 네트워크나 비밀값에
  의존해서는 MUST NOT 한다.
- `uv run pytest`가 레포 루트와 각 에이전트 디렉터리 모두에서 통과해야 한다.

근거: LLM 기반 코드는 회귀가 눈에 잘 띄지 않으므로 자동 테스트가 유일하게 믿을 수 있는 안전망이다.

### IV. 비밀값은 환경변수로만

- API 키, 웹훅 URL, 토큰 등 비밀값은 MUST 환경변수로만 받는다.
- 비밀값을 코드, 설정 파일, 테스트 픽스처, 로그에 포함해서는 MUST NOT 한다.
- `.env` 파일은 MUST `.gitignore`에 등록하고, 키 이름만 적은 `.env.example`을 제공한다.

근거: 비밀값이 한 번이라도 커밋되면 이력에서 완전히 지우기 어렵고, 노출되는 즉시 폐기해야 한다.

### V. 외부 호출의 재시도와 로깅

- 외부 API 호출은 MUST 지수 백오프 재시도(최대 횟수 제한 포함)를 적용한다.
- 모든 외부 호출의 실패와 최종 재시도 소진은 MUST 로깅한다(대상, 시도 횟수, 오류 요약).
  이때 비밀값은 로그에 남기지 않는다.
- 재시도·로깅 로직은 SHOULD `shared/`의 공통 유틸로 구현해 에이전트끼리 재사용한다.

근거: 일시적인 네트워크·레이트리밋 오류로 전체 실행이 실패하지 않게 하고, 실패 원인을 추적할 수 있게 하기 위함.

### VI. 스펙 명명 규칙

- 모든 스펙 이름은 MUST 어떤 에이전트의 스펙인지 나타내는 접두어로 시작한다:
  `news:` (news-digest), `lab:` (troubleshoot-lab), `job:` (job-apply).
- 여러 에이전트에 걸치는 `shared/` 작업은 `shared:` 접두어를 사용한다.
- 브랜치·디렉터리 이름에서는 `:`가 `-`로 바뀌므로 실제로는 `NNN-news-<이름>` 형태가 된다
  (예: `003-news-dedup`).

근거: 하나의 `specs/` 디렉터리 안에서 에이전트별 작업을 바로 구분하기 위함.

## 에이전트별 원칙

### news-digest

- LLM 호출은 MUST 실행 1회당 최소한으로 한다(가능하면 배치·요약 단위로 묶어서 호출).
- 실행당 비용 상한은 MUST 설정값으로 관리하며, 상한에 도달하면 호출을 중단하고 그 사실을 로깅한다.
- 이미 게시한 글은 MUST NOT 다시 게시한다. 게시 이력을 영속적으로 저장하고 게시 전에 중복을 검사한다.

### troubleshoot-lab

- 장애 주입은 MUST 로컬 샌드박스(kind, docker compose)에서만 수행한다.
  원격 클러스터나 공유 환경을 대상으로 해서는 MUST NOT 한다.
- 장애 주입 코드는 SHOULD 실행 전에 대상 컨텍스트가 로컬 샌드박스인지 검증한다.
- 모든 시나리오에는 MUST 원복(reset) 스크립트가 있어야 하며, 원복 결과도 테스트로 검증한다.

### job-apply

- 원본 이력서에 없는 경력, 기술, 성과를 MUST NOT 생성한다. 생성된 문서는 원본 이력서에 근거가 있어야 한다.
- 지원서 최종 제출은 MUST 사람이 직접 한다. 에이전트는 초안 작성과 준비까지만 수행한다.
- 이력서 등 개인정보 파일은 MUST NOT 레포에 커밋한다(`.gitignore`로 차단하고,
  테스트에는 가상의 샘플 데이터를 사용한다).

## 개발 워크플로

- 새 기능은 Spec Kit 흐름(`/speckit-specify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`)을 따른다.
- plan 단계의 Constitution Check에서 위 원칙을 위반하는 설계가 있으면, 위반 사유와 대안을
  Complexity Tracking에 명시해야 한다.
- 커밋 전에 `uv run pytest`가 통과해야 하며, 비밀값·개인정보가 포함되지 않았는지 확인한다.

## Governance

- 이 헌법은 레포의 다른 관행과 문서보다 우선한다.
- 개정은 `/speckit-constitution`으로 수행하며, 변경 내용과 버전 변경을 커밋 메시지에 남긴다.
- 버전 정책(Semantic Versioning):
  - MAJOR: 원칙 삭제 또는 호환되지 않는 재정의
  - MINOR: 원칙·섹션 추가 또는 지침의 실질적 확장
  - PATCH: 문구 명확화, 오타 수정 등 의미 변화 없는 수정
- 모든 PR 리뷰는 이 헌법을 준수하는지 확인한다.

**Version**: 1.0.0 | **Ratified**: 2026-10-24 | **Last Amended**: 2026-10-24
