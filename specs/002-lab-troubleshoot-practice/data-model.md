# Data Model: lab: 트러블슈팅 실습 (커리큘럼 개정판)

모든 모델은 `troubleshoot_lab/models.py`의 Pydantic v2 모델로 검증한다. 시각은 UTC ISO 8601로 저장하고,
날짜·요일·주 계산은 KST(`Asia/Seoul`)로 한다.

## 공통 열거형

| 이름 | 값 |
|------|----|
| `Field` | `network`(① 네트워크), `linux`(② 리눅스 서버), `webserver`(③ 웹 서버와 소켓), `db-cache`(④ 데이터베이스와 캐시), `lb-cloud`(⑤ 부하 분산과 클라우드), `monitoring`(⑥ 모니터링과 장애 대응). 순서는 ①→⑥이고, 동점 처리에 쓴다 |
| `Env` | `compose`, `kind` |
| `Difficulty` | `beginner`(초급, 커리큘럼 하), `intermediate`(중급, 중), `advanced`(고급, 상) |
| `Phase` | `baseline`(정상), `fault`(장애), `after`(해결 후) |
| `MetricStatus` | `unavailable`(측정 불가), `skipped`(측정 생략), `not_applicable`(해당 없음) |

## 카탈로그 (레포에 커밋, 사람이 작성)

### Mission — `missions/<field>/<id>/mission.yaml`

| 필드 | 타입 | 규칙 |
|------|------|------|
| `id` | str | 디렉터리 이름과 같아야 한다. `^[a-z0-9]+(-[a-z0-9]+)*$`. 미션·시나리오 전체에서 유일 |
| `field` | Field \| null | 디렉터리에서 정하고, 파일에 적었다면 일치해야 한다 |
| `env` | Env | 가드·복원 모드 |
| `kind` | `warmup` \| `concept` | 기본 `warmup`. `concept`는 학습 계획의 개념 일차용 |
| `title` | str | 1~60자 |
| `minutes` | int | 예상 소요 시간. `kind=warmup`이면 5~60, `kind=concept`이면 30~90(개념 일차를 혼자 채우므로) |
| `goals` | list[str] | 1~5개 |
| `steps` | list[MissionStep] | 1~10개, `id` 유일 |

**MissionStep**은 기존과 같다: `id`, `guide`, `command`(비대화형, 필수), `check`(`state` \| `answer`), `prompt`(answer일 때 필수).

필요한 파일: `setup.sh`, `verify.sh`

### Scenario — `scenarios/<field>/<id>/scenario.yaml`

| 필드 | 타입 | 규칙 |
|------|------|------|
| `id` | str | Mission과 같은 규칙. 증상 기준 이름 |
| `curriculum_no` | str | `^(\d{1,2}(-[A-Z])?\|extra-\d+)$` (예: `3`, `18-B`, `extra-1`). 카탈로그 전체에서 유일 |
| `fields` | list[Field] | 1~3개. 첫 번째가 대표 분야이고 디렉터리 이름과 같아야 한다 |
| `env` | Env | |
| `title` | str | 1~60자, 원인을 드러내지 않는다 |
| `difficulty` | Difficulty | |
| `minutes` | int | 20~90 |
| `symptom` | str | 공개(Slack, CLI) |
| `tags` | list[str] | 작성자용. 어디에도 게시하지 않는다 |
| `warmups` | list[str] | 미션 id 1~2개. `kind=warmup`이어야 한다 |
| `start_hint` | str \| null | 장애 주입 후 CLI에만 보이는 확인 명령 |
| `measure` | MeasureSpec | 아래 |
| `interview` | list[str] | 면접 질문 1~2개, 각 1~200자 |

**MeasureSpec**

| 필드 | 타입 | 규칙 |
|------|------|------|
| `method` | `GET` \| `POST` | 기본 `GET` |
| `path` | str | `/`로 시작. 호스트·스킴 포함 금지(FR-027) |
| `scheme` | `http` \| `https` | 기본 `http`. https는 compose nginx 443(실습용 CA로 검증) |
| `body` | str \| null | POST 본문(JSON 문자열) |
| `vus` | int | 1~50, 기본 5 |
| `duration_s` | int | 5~40, 기본 20 |
| `service` | str | CPU·메모리를 샘플링할 서비스(compose 서비스 이름 또는 kind Deployment 이름) |

필요한 파일: `inject.sh`, `verify.sh`, `reset.sh`, `hints.md`(정확히 3단계), `solution.md`

### Plan — `curriculum/plan.yaml`

```yaml
days:
  - {day: 1, week: 1, topic: "TCP/IP, OSI 7계층", practice: "웹사이트 접속 과정 설명", items: [concept-web-request-flow]}
  - {day: 4, week: 1, topic: "포트와 방화벽", practice: "포트 접근 실패 재현", items: [api-unreachable-via-proxy, site-hangs]}
  - {day: 7, week: 1, topic: "종합 트러블슈팅", practice: "서버 접속 장애 분석", pool: [api-unreachable-via-proxy, api-partial-errors, site-connection-refused, site-hangs]}
extras: [k8s-api-no-response, k8s-bad-release, web-api-404, web-stale-data, web-wrong-profile]
```

| 규칙 | 내용 |
|------|------|
| 일차 | `day` 1~21이 빠짐없이 순서대로 있다. `week`는 1~3 |
| items / pool | 일차마다 둘 중 하나만 쓴다. `items`: 1~2개, 시나리오 id 또는 `kind=concept` 미션 id, 첫 항목이 주 항목. `pool`: 종합 일차용 시나리오 id 2~6개, 게시할 때 1개를 고른다(일차 선택 규칙 3-1) |
| 시간 | 주 항목 `minutes` + 그 항목에 연결된 워밍업 전부의 `minutes` 합이 60~90(SC-008, FR-032 계획 검증). 개념 미션은 자기 `minutes`만 센다. `pool`이면 후보 각각이 이 범위여야 한다 |
| extras | 유효한 시나리오 id이고, `days`에 나오지 않은 것이어야 한다 |
| 범위 | `days`와 `extras`를 합치면 카탈로그의 모든 시나리오가 한 번 이상 나온다 |

유효하지 않으면 `CatalogError(kind="plan")`이 되고 게시는 테스트 채널 알림으로 끝난다(FR-040).

## 진행 기록 — `data/progress.json` (version 2)

```json
{ "version": 2, "events": [ {"ts": "...", "type": "...", "id": "...", "attempt": 1, "...": "..."} ] }
```

| `type` | 추가 필드 | 언제 |
|--------|-----------|------|
| `mission_completed` | — | 미션 마지막 단계 통과 |
| `scenario_started` | `attempt` | 잠금 해제된 시나리오 시작(복원 후, 주입 전) |
| `measured` | `attempt`, `phase`, `metrics`, `skip_reason?` | `lab measure` 또는 해결 직후 자동 측정 |
| `fault_injected` | `attempt` | inject 성공 |
| `hint_opened` | `attempt`, `level` | `/lab-hint` |
| `scenario_solved` | `attempt`, `hints_used` | verify 성공 |
| `scenario_gave_up` | `attempt`, `hints_used` | `/lab-giveup` |
| `scenario_reset` | `attempt`, `was_active` | 해결·포기 전 원복 |
| `report_completed` | `attempt`, `report`, `answered` | `lab report --done` 통과 |

**metrics** (Phase별 1회 측정)

| 키 | 단위 | 값 또는 상태 |
|----|------|--------------|
| `avg_ms`, `p95_ms` | ms | 성공 요청 0건이면 `not_applicable` |
| `rps` | req/s | |
| `error_rate` | 0~1 | |
| `requests` | 개수 | |
| `cpu_avg_pct`, `cpu_max_pct` | % | 샘플 0개면 `unavailable` |
| `mem_max_mib` | MiB | 샘플 0개면 `unavailable` |

- 각 값은 `{"value": number}` 또는 `{"status": MetricStatus}`이다.
- `skip_reason`이 있으면 모든 키가 `skipped`이다.
- 다른 형태는 스키마가 거부한다. 추정값 필드는 없다.

### 계산 결과 (저장하지 않음)

**Attempt**: `(scenario_id, attempt)`마다 다음을 계산한다.
- 시작 시각
- 단계 상태: started → baseline_ok → injected → fault_ok → solved \| gave_up \| reset
- 단계별 마지막 측정
- 힌트 수
- 종료 종류
- 보고서 완료 여부

| 판정 | 조건 |
|------|------|
| `baseline_ok` | 같은 시도에 `measured(phase=baseline)`이 있음 |
| `fault_ok` | `fault_injected` 이후 `measured(phase=fault)`가 있음 |

**ScenarioStatus**는 기존과 같다(new/pending/solved/gave_up). pending의 조건은 "게시되었거나 시작한 적 있음"이다.

**ActiveItem**: 진행 중인 시도 또는 미션 세션 중 하나(FR-025).

**ReportStatus**는 시도마다 계산한다.

| 상태 | 조건 |
|------|------|
| `none` | 해결·포기 전 |
| `draft` | 파일은 있으나 `report_completed` 없음 |
| `missing` | 끝났는데 파일이 없음 |
| `done` | `report_completed`가 있고 파일이 존재 |

## 보고서 — `docs/reports/<YYYY-MM-DD>-<id>-<attempt>.md`

형식은 contracts/report.md를 따른다.

- `--done` 필수 섹션: 증상, 원인, 분석 과정, 해결 방법, 재발 방지, 그리고 면접 질문마다 답
- `answered`: 답이 채워진 질문 수

## 게시 기록 — `data/posted.json` (version 2)

```json
{ "version": 2,
  "daily": [ {"date_kst": "2026-10-27", "kind": "day", "day": 2, "main_kind": "scenario", "main_id": "site-connection-refused",
              "second_id": null, "posted_at": "..."} ],
  "weekly": [ {"week_start_kst": "2026-10-26", "posted_at": "..."} ] }
```

| 필드 | 규칙 |
|------|------|
| `kind` | `day` \| `catchup` \| `extra` \| `review` |
| `day` | `kind=day`일 때 1~21, 아니면 null |
| `main_kind` | `scenario` \| `mission` |

- `date_kst`, `week_start_kst`는 유일해야 한다.
- 기존 v1 빈 파일은 v2로 올린다.

## 일차 선택 (FR-030, research R24)

입력: 카탈로그(유효한 항목), plan, 진행 기록, 게시 기록, 오늘(KST).

1. **backlog**: 과거 게시(main 또는 second)에 나온 시나리오 중 상태가 solved·gave_up이 아닌 것이다. 오늘 날짜 게시는 빼고, 마지막 게시일이 오래된 순으로 정렬한다.
2. **따라잡기**: backlog가 3개 이상이면 `kind=catchup`, main = backlog[0], second = null이다.
3. **다음 일차**: 마지막 `kind=day` 게시의 `day`+1이다(없으면 1). 21 이하이면 `kind=day`로 그 일차의 items를 쓴다.
   - 3-1. **종합 일차**: `pool`이면 주 항목 1개를 다음 순서로 고르고, second는 없다(spec FR-030 규칙 5).
     1. 해결·포기 안 한 것 중 게시한 적 없는 것
     2. 해결·포기 안 한 것 중 마지막 게시가 오래된 것
     3. gave_up
     4. 최대 힌트 수가 많은 것(포기는 3으로 센다)
     5. curriculum_no 순
4. **심화**: 22 이상이면 `extras` 중 아직 main으로 게시하지 않은 첫 항목으로 `kind=extra`이다.
5. **복습**: 심화도 끝나면 `kind=review`다. 포기(오래된 순) 다음 해결(힌트 많은 순, 같으면 먼저 해결한 순)으로 고르고, 전날 main과 같은 것은 다른 후보가 있으면 뺀다.
6. **표시 정보**:
   - backlog 표시: main·second를 뺀 backlog 앞에서 최대 3개
   - 복습 표시: main이 시나리오이고 이미 solved면 "복습"과 그 일차의 `practice`를 관점 안내로 함께 쓴다
   - 시간 표시: 주 항목과 아직 완료하지 않은 연결 워밍업의 minutes 합. 90 초과면 경고, 60 미만이면 여유 시간 안내(FR-032)
7. **결과 없음**: 카탈로그·plan이 유효하지 않거나 고를 것이 없으면 `NO_SCENARIO`다.

같은 입력이면 같은 결과다(SC-007).

## 주간 요약 (FR-038, FR-039)

기간은 이번 주 월요일 00:00 KST부터 실행 시각까지다.

| 항목 | 계산 |
|------|------|
| 계획 진행도 | 마지막 `kind=day` 게시의 day(/21). 21 이후면 "심화 n/5" 또는 "복습" |
| 해결·포기·힌트 | 기간 안의 해당 이벤트 수 |
| 회고 완료 | 기간 안의 `report_completed` 수 |
| 회고 대기 | 끝났지만 ReportStatus가 `done`이 아닌 시도 목록(기간 무관, 최대 5개, 오래된 순) |
| 면접 질문 답변 | 기간 안 `report_completed.answered` 합 |
| 약한 분야 | 기간 안에 시작해 끝난 시도의 대표 분야별 `hints + 2×(gave_up + reset)` 최댓값. 진행 중 제외. 동점이면 해결 수가 적은 분야, 그다음 ①→⑥. 0이거나 없으면 "기록 없음" |
| 밀린 문제 | 오늘 기준 backlog 수 |
| 다음 주제 | 내일 날짜로 계산한 일차 선택 결과의 주제(또는 주 항목 제목) |

## 실행 결과

RunStatus는 기존과 같다: `POSTED`, `ALREADY_POSTED`, `NO_SCENARIO`, `POST_FAILED`, `UNEXPECTED_ERROR`.
카탈로그·plan 오류는 warnings로 테스트 채널에 보낸다. 고를 것이 없으면 `NO_SCENARIO`(종료 코드 1)다.
