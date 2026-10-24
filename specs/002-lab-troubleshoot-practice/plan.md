# Implementation Plan: lab: 트러블슈팅 실습 (커리큘럼 기반 장애 재현·분석·회고)

**Branch**: `002-lab-troubleshoot-practice` | **Date**: 2026-10-24 (커리큘럼 개정) | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-lab-troubleshoot-practice/spec.md`

## Summary

커리큘럼(`agents/troubleshoot-lab/docs/curriculum.md`)을 기준으로 기존 구현을 개정한다. 실습 환경은 docker compose 와 kind 클러스터
`troubleshoot-lab`이고, 사용자는 Claude Code 슬래시 명령으로 시나리오 하나를 6단계로 진행한다.

1. **정상 상태 측정**: `/lab-measure`. k6 컨테이너로 응답 시간·p95·처리량·오류율을, 컨테이너 통계로 CPU·메모리를 실측한다.
2. **장애 재현**: `/lab-inject`. 정상 측정 뒤에만 허용된다.
3. **증상 관찰**: `/lab-measure`를 다시 실행하고, `/lab-exec <서비스> <명령>`으로 toolbox 컨테이너를 대상의 네트워크·PID 공간에 붙여 `ss`·`top`·`vmstat` 등을 실행한다.
4. **원인 분석**: `/lab-hint` 3단계.
5. **해결**: `/lab-check`. 장애 측정 뒤에만 판정하고, 성공하면 해결 후 측정을 자동으로 한다.
6. **재발 방지·회고**: `/lab-report`가 실측 측정표와 면접 질문이 들어간 보고서 초안을 `docs/reports/`에 만들고, 사용자가 채운 뒤 `--done`으로 완료한다.

매일 08:40 KST의 GitHub Actions 는 `curriculum/plan.yaml`의 21일 학습 계획을 게시 순서대로 진행해 오늘의 주제와 시나리오를 게시한다.
이때 밀린 문제가 3개 이상이면 따라잡기 날로 바꾸고, 21일 이후에는 심화, 그다음 복습으로 넘어간다. 선택은 규칙 기반이고 LLM은 쓰지 않는다.

**바뀌는 기존 설계**:
- 카테고리(docker/kubernetes/web)를 분야(6개) + env 로 바꾼다.
- start 와 inject 를 분리한다.
- 측정, 진단, 보고서를 추가한다.
- 난이도 순 선택을 학습 계획 순 선택으로 바꾼다.

가드, 원복, 미션 판정, sync, 게시 파이프라인, shared 알림은 그대로 쓴다(research R28).

## Technical Context

**Language/Version**:
- Python 3.12: CLI, 샘플 API
- Bash: 미션·시나리오 스크립트
- JavaScript: k6 측정 스크립트 1개 (Complexity Tracking 참고)

**Primary Dependencies**:
- Python: `shared`(Slack·재시도·로깅·설정·파일·알림), `pydantic` v2, `pyyaml`
- 샘플 API: fastapi, uvicorn, redis, psycopg + psycopg_pool
- 컨테이너 이미지:
  - `grafana/k6:1.0.0`: 부하 측정
  - `lab-toolbox:dev`: debian:12-slim 기반 진단 도구(research R21)
  - nginx:1.27-alpine, redis:7-alpine, postgres:16-alpine, busybox:1.36
- 외부 도구: Docker(compose v2), `kind`, `kubectl`, `make`, `jq`
- kind 애드온: metrics-server(매니페스트를 레포에 고정 보관)

**Storage**: 레포 안 파일과 로컬 상태로 나뉜다.
- 사용자 동의 후 커밋: `data/progress.json`(v2 이벤트 로그), `docs/reports/*.md`
- Actions 가 커밋: `data/posted.json`(v2)
- 로컬 전용(gitignore): `.lab-state/`(세션, 작업 사본, 측정 원본, 인증서, 로그)

**Testing**:
- pytest + pytest-httpx. subprocess(스크립트, docker, kubectl, git)는 가짜 runner 로 바꾼다.
- k6 summary 파싱은 고정 JSON 픽스처로 테스트한다.
- 실제 환경 테스트는 `-m sandbox`(`LAB_SANDBOX=1`)로만 돌린다. 시나리오 23개의 6단계 순환과 SC-005 지표 차이를 확인한다.

**Target Platform**:
- 실습: macOS + Docker Desktop + kind
- 게시: GitHub Actions `ubuntu-latest`, cron `40 23 * * *`
- 샌드박스 CI: ubuntu + kind

**Project Type**: CLI(로컬 학습 도구 + 배치 게시)와 실습용 서비스·도구 이미지

**Performance Goals**:
- 측정 1회 ≤ 1분
- 장애 재현 ≤ 3분
- `make up` 첫 실행 ≤ 15분, 이후 ≤ 3분
- 게시 ≤ 1분

**Constraints**:
- 로컬 샌드박스 전용(가드, 부하 대상 고정)
- 실측값만 기록(추정 금지)
- 호스트에 k6·리눅스 진단 도구 설치 불필요
- 슬래시 명령과 Slack 에 원인·힌트·면접 질문 노출 금지
- 하루 60~90분 분량
- LLM 미사용
- 비밀값은 환경변수로만 받는다

**Scale/Scope**:
- 사용자 1명
- 시나리오 23개(커리큘럼 #1~#14, #15 로컬, #17, #18, #18-B, #19, #20, 심화 3)
- 워밍업 26개 + 개념 미션 4개
- 21일 계획

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판정 | 근거 |
|------|------|------|
| I. 모노레포 경계 | ✅(예외 2건) | 코드·콘텐츠·환경·보고서는 `agents/troubleshoot-lab/` 에 둔다. 공용 코드는 `shared/`(R15, files)를 쓴다. 워크플로와 `.claude/` 는 경로가 고정된 예외다 |
| II. Python 3.12 + uv | ✅(예외 2건) | CLI·샘플 API 는 Python 3.12 + uv 다. Bash 콘텐츠 스크립트와 k6 JS 스크립트 1개는 예외(Complexity Tracking) |
| III. pytest 동반 | ✅ | 신규 모듈(measure, diag, report, planner)을 단위·통합 테스트한다. 샘플 API 의 새 엔드포인트는 TestClient 로, 실제 환경은 opt-in 샌드박스로 테스트한다. 기본 `uv run pytest` 는 Docker 없이 통과한다 |
| IV. 비밀값 환경변수 | ✅ | 웹훅은 환경변수·Secrets 로만 받는다. 실습용 TLS 인증서·DB 비밀번호는 로컬 전용 생성값·고정값이고 `.lab-state/` 에 두며 커밋하지 않는다. 진행 기록·보고서에는 비밀값을 쓰지 않도록 스키마와 안내로 막는다 |
| V. 재시도·로깅 | ✅ | Slack 과 git push 는 `shared.retry` 로 재시도한다. k6·docker·kubectl 호출은 제한 시간을 두고 실패를 구조화 로그로 남긴다. 측정 실패는 기록하지 않고 재시도를 안내한다 |
| VI. 스펙 명명 | ✅ | `002-lab-troubleshoot-practice` |
| lab: 로컬 샌드박스에서만 주입 | ✅ | 가드(R3)를 inject, measure, exec, reset 모두에 적용한다. 부하 대상은 내부 주소로 고정한다(R20). 진단 컨테이너는 로컬 docker·kind 에만 붙는다 |
| lab: 모든 시나리오에 reset + 테스트 | ✅ | 시나리오 23개 모두 `reset.sh` 와 샌드박스 순환 테스트(지문 비교)를 갖는다. 측정·진단 컨테이너는 `--rm` 이라 상태를 남기지 않는다 |

**Post-design re-check**: 위반 없음. 예외 4건은 아래에 근거를 적었다.

## Project Structure

### Documentation (this feature)

```text
specs/002-lab-troubleshoot-practice/
├── plan.md
├── research.md            # R1–R16 (기존), R17–R28 (커리큘럼 개정)
├── data-model.md          # 분야·env·측정·보고서·plan·게시 v2·일차 선택·주간 집계
├── quickstart.md
├── contracts/
│   ├── cli.md             # 학습 명령(6단계), exec/shell/report, 종료 코드
│   ├── measurement.md     # k6·자원 샘플링·실측값 규칙
│   ├── report.md          # 장애 보고서 템플릿과 --done 검사
│   ├── slash-commands.md  # /lab-* 10개와 대신하지 않기 규칙
│   ├── content.md         # 미션·시나리오·plan 작성 계약
│   ├── slack-message.md   # 일차 메시지·주간 요약
│   └── progress.schema.json  # v2
└── tasks.md               # /speckit-tasks 에서 재생성
```

### Source Code (repository root)

```text
.claude/commands/lab-{list,start,measure,inject,exec,hint,check,giveup,report,reset}.md
.claude/settings.json
.github/workflows/troubleshoot-lab.yml           # 변경 없음(cron 40 23)
.github/workflows/troubleshoot-lab-sandbox.yml   # make up 에 toolbox·k6·metrics-server 포함

agents/troubleshoot-lab/
├── docs/
│   ├── curriculum.md            # 커리큘럼 원문 (루트에서 이동, R27)
│   ├── authoring.md             # 분야·env·measure·interview·minutes 규칙 추가
│   └── reports/.gitkeep         # 장애 보고서
├── curriculum/plan.yaml         # 1~21일 차, extras
├── templates/{mission,scenario}/, templates/report.md
├── environment/
│   ├── api/                     # 엔드포인트 확장(R19), APP_ROLE=ext 지원, tests 확장
│   ├── compose.yaml             # ext 서비스, api 로그 tmpfs, nginx :443, k6·toolbox 는 run 전용
│   ├── nginx/default.conf       # :443 TLS, /api/report 등 proxy_read_timeout 3s
│   ├── postgres/init.sql        # orders 20만 행 + 인덱스
│   ├── k6/measure.js            # 공통 측정 스크립트
│   ├── toolbox/Dockerfile       # 진단 도구 이미지
│   ├── k8s/ (+ metrics-server.yaml)
│   ├── restore.sh, healthcheck.sh, fingerprint.sh
├── lib/common.sh                # tb, compose_override 헬퍼 추가
├── missions/<field>/<id>/       # 기존 14개 이동·보완 + 새 워밍업 12개 + 개념 미션 4개
├── scenarios/<field>/<id>/      # 기존 9개 이동·보완 + 새 14개
├── src/troubleshoot_lab/
│   ├── models.py                # Field, Env, MeasureSpec, Plan, Event v2, Posted v2
│   ├── catalog.py               # plan 로딩·검증, 60~90분 규칙
│   ├── progress.py              # v2, Attempt 상태 기계, ReportStatus
│   ├── learn.py                 # start / inject / check / giveup / reset (6단계 순서 강제)
│   ├── measure.py               # (신규) k6 실행, summary 파싱, 자원 샘플링, 실측값 규칙
│   ├── diag.py                  # (신규) exec / shell, target_down 처리
│   ├── report.py                # (신규) 초안 렌더링, --done 검사
│   ├── planner.py               # (picker 대체) 학습 계획 기반 일차 선택
│   ├── messages.py, weekly.py, daily.py, posted.py, sync.py, cli.py, guard.py, runner.py, session.py
└── tests/ (unit: measure, diag, report, planner, progress v2, learn 6단계 …; content: plan·measure·interview 검사; sandbox)
```

**Structure Decision**:
- 기존 패키지 구조는 유지한다.
- 측정·진단·보고서는 각자의 모듈로 나눈다. `learn.py` 는 순서 규칙만 담당하고 실제 작업은 이 모듈들에 맡긴다.
- 학습 계획은 데이터(`plan.yaml`)로 두어 커리큘럼 개정을 코드 수정 없이 반영한다.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 미션·시나리오 스크립트를 Bash로 작성 (헌법 II) | 사용자가 지정한 콘텐츠 구조. docker·kubectl 명령을 그대로 보여 주는 학습 자료다 | Python 으로 감싸면 학습 대상 명령이 숨는다. 가드·정적 테스트로 통제한다(기존과 같음) |
| k6 측정 스크립트 `measure.js` (JavaScript, 헌법 II) | 사용자가 k6 를 지정했고, k6 시나리오는 JS 로만 쓸 수 있다 | Python 부하 도구는 사용자 요구와 다르다. 스크립트는 하나이고 매개변수만 받으며 로직은 Python(`measure.py`)에 둔다 |
| `.claude/commands/`, `.claude/settings.json` 이 `agents/` 밖 | Claude Code 가 그 경로만 읽는다 | 기존과 같음 |
| `.github/workflows/troubleshoot-lab*.yml` 이 `agents/` 밖 | GitHub Actions 가 그 경로만 읽는다 | 기존과 같음 |
| `posted.json`(봇)·`progress.json`과 보고서(사용자)를 main 에 커밋 | 원격 게시와 로컬 실습 사이 상태를 레포로 넘긴다(Clarification Q2) | 기존과 같음. 보고서도 같은 커밋에 포함한다 |
