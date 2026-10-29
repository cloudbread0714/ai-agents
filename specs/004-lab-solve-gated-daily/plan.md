# Implementation Plan: lab: 해결해야 다음 문제가 열리는 오늘의 문제

**Branch**: `004-lab-solve-gated-daily` | **Date**: 2026-10-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-lab-solve-gated-daily/spec.md`

## Summary

오늘의 문제를 웹훅 대신 Slack 봇 토큰으로 게시하고, 메시지 위치를 `posted.json`에 남긴다. 아침 실행은 열린 문제
메시지의 ✅(학습자 또는 봇)를 확인해, 있으면 해결 기록 후 다음 문제를 올리고, 없으면 그 스레드에 하루 한 번 리마인드를
남긴다(3일 이상이면 힌트 1단계 포함). `/lab-check`가 열린 문제를 끝냈다고 확인하면 봇이 ✅를 단다. 기존 catchup 규칙은
없앤다. Slack Web API 호출은 `shared/slack.py`에 더해 job-apply와 함께 쓴다.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: httpx, pydantic v2, tenacity(`shared.retry`) — 모두 기존. 새 의존성 없음

**Storage**: `agents/troubleshoot-lab/data/posted.json`(version 2, 선택 필드 확장), Actions가 `[skip ci]` 커밋

**Testing**: pytest + pytest-httpx(`httpx_mock`), 시계 주입(`now`) — 기존 lab 테스트 패턴

**Target Platform**: GitHub Actions ubuntu-latest(아침 실행), macOS 로컬(`/lab-check`)

**Project Type**: CLI(`lab`) + 공유 라이브러리(`shared`)

**Performance Goals**: 아침 실행 1회당 Slack 호출 최대 4건(auth.test, reactions.get, chat.postMessage, 알림)

**Constraints**: 하루 1회 게시·리마인드(재실행에도), 실패 시 기록 불변, 비밀값 비노출, 학습 명령은 Slack 없이도 동작

**Scale/Scope**: 학습자 1명, 채널 1개, 하루 1회 실행

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 원칙 | 판단 | 근거 |
|---|---|---|
| I. 모노레포 경계와 공유 코드 | ✅ | Slack Web API 함수는 `shared/slack.py`(job-apply도 봇 토큰 사용 예정). lab 전용 판정·게시 로직은 `agents/troubleshoot-lab/`에만 |
| II. Python 3.12 + uv | ✅ | 새 의존성 없음. `uv.lock` 변경 없음 |
| III. 테스트 동반 | ✅ | Slack은 `httpx_mock`으로만 모킹. 실제 네트워크·비밀값 불필요(quickstart §1) |
| IV. 비밀값은 환경변수로만 | ✅ | `SLACK_BOT_TOKEN` 등 환경변수/Secrets. 토큰은 헤더로만, 로그·예외에 미포함(R12). `.env.example`에 키 이름 추가 |
| V. 재시도와 로깅 | ✅ | 모든 Web API 호출에 `shared.retry.retryable`, 최종 실패는 메서드·시도 횟수·오류 코드로 로깅(R3) |
| VI. 스펙 명명 | ✅ | `lab:` 접두어, `004-lab-solve-gated-daily` |
| troubleshoot-lab: 로컬 샌드박스만 | ✅ | 장애 주입·원복 코드 변경 없음 |

**Post-design 재확인 (Phase 1 후)**: 위 판단 그대로. Complexity Tracking 해당 없음.

## Project Structure

### Documentation (this feature)

```text
specs/004-lab-solve-gated-daily/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── posted.md          # posted.json 확장 형식
│   ├── slack-api.md       # shared.slack 봇 토큰 함수
│   ├── cli.md             # lab daily / lab check 변경분
│   └── slack-message.md   # 오늘의 문제·리마인드·주간 요약 문구
└── tasks.md               # /speckit-tasks
```

### Source Code (repository root)

```text
shared/
├── src/shared/slack.py               # + auth_test, post_message, get_reactions, add_reaction, SlackApiError
└── tests/test_slack.py               # + Web API 테스트

agents/troubleshoot-lab/
├── bin/lab                           # .env 로딩
├── .env.example                      # 키 이름 교체 (git 추적)
├── src/troubleshoot_lab/
│   ├── models.py                     # DailyPost 신규 필드 + 검증
│   ├── posted.py                     # open_post(), 보존 규칙 예외
│   ├── planner.py                    # catchup 분기 제거
│   ├── gate.py                       # 신규: 반응 판정·리마인드 결정 (Slack 호출 없는 순수 로직)
│   ├── daily.py                      # 봇 토큰 게시 흐름, 새 RunStatus
│   ├── messages.py                   # 안내 줄, 리마인드, 재게시, 주간 요약 줄
│   ├── weekly.py                     # solved_posts, stalled_days, open_post
│   ├── reactor.py                    # 신규: /lab-check 자동 ✅
│   ├── learn.py                      # Reactor 주입, slack_reaction 결과
│   └── cli.py                        # 필수 환경변수, Reactor 연결
└── tests/
    ├── unit/                         # gate, posted, planner, messages, weekly, reactor
    └── integration/test_daily.py     # 아침 실행 시나리오 (quickstart §1 표)

.github/workflows/troubleshoot-lab.yml # Secrets 교체
.claude/commands/lab-check.md          # slack_reaction 출력 안내
```

**Structure Decision**: 기존 `shared` + `agents/troubleshoot-lab` 구조를 그대로 쓴다. 판정 로직을 `gate.py`로 분리해
Slack 없이 단위 테스트하고, `daily.py`는 호출과 저장 순서만 맡는다. 자동 ✅는 `Diagnoser`처럼 주입되는 `reactor.py`로
두어 학습 명령이 Slack 없이도 동작하게 한다.

## Complexity Tracking

해당 없음.
