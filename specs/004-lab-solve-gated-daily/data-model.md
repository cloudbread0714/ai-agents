# Data Model: lab: 해결해야 다음 문제가 열리는 오늘의 문제

## 게시 기록 `agents/troubleshoot-lab/data/posted.json` (version 2, 확장)

기존 구조는 그대로 두고 `DailyPost`에 선택 필드만 더한다. 형식 전문은 [contracts/posted.md](contracts/posted.md).

### DailyPost

| 필드 | 타입 | 기존/신규 | 설명 |
|---|---|---|---|
| `date_kst` | date | 기존 | 게시한 날짜(KST). 기록 전체에서 유일 |
| `kind` | `day`\|`catchup`\|`extra`\|`review` | 기존 | 새로 만드는 항목에는 `catchup`을 쓰지 않는다(옛 기록 읽기용) |
| `day` | int 1–21 \| null | 기존 | `kind=day`일 때만 |
| `main_kind`, `main_id`, `second_id` | | 기존 | 게시한 항목 |
| `posted_at` | datetime(UTC) | 기존 | |
| `channel` | str \| null | **신규** | 게시한 채널 ID |
| `ts` | str \| null | **신규** | 게시한 메시지 ID(Slack `ts`) |
| `outcome` | `open`\|`solved` \| null | **신규** | null = 기능 도입 전 기록(끝난 문제로 취급) |
| `resolved_at` | datetime(UTC) \| null | **신규** | `outcome=solved`가 된 판정 시각 |
| `reminders` | list[date] | **신규** | 리마인드를 남긴 KST 날짜. 기본 `[]` |
| `reposted_at` | datetime(UTC) \| null | **신규** | 메시지가 사라져 다시 게시한 마지막 시각 |

### 검증 규칙

- `channel`과 `ts`는 둘 다 있거나 둘 다 없다.
- `outcome`은 `channel`·`ts`가 있을 때만 값이 있다.
- `outcome=solved` ⇔ `resolved_at`이 있다.
- `reminders`는 중복 없이 오름차순이고, 모두 `date_kst`보다 뒤다.
- 기록 전체에서 `outcome=open`인 항목은 최대 1개다(FR-003, SC-001).

### 상태 전이 (DailyPost.outcome)

```text
(게시) ──► open ──✅ 확인(아침 실행)──► solved
             │
             ├─ ✅ 없음 ──► open (reminders에 오늘 추가)
             └─ 메시지 없음 ──► open (channel/ts 교체, reposted_at 갱신)
```

`solved`에서 되돌아가는 전이는 없다. 아침에 ✅를 확인한 뒤 반응이 지워져도 기록은 그대로다.

## 파생 개념

- **열린 문제**: `outcome == "open"`인 항목. 없으면 다음 실행에서 새 문제를 게시한다.
- **미해결 경과 일수**: `오늘(KST) − date_kst`. 3 이상이면 리마인드에 힌트 1단계 포함(R7).
- **완료된 항목(자동 ✅ 판단용)**: 시나리오는 진행 기록상 `solved`, 미션은 `mission_completed`가 있는 것. 열린 문제의
  `main_id`·`second_id`가 모두 완료면 그 문제는 ✅ 대상이다.

## 반응 판정 (메모리 내 값, 저장 안 함)

| 필드 | 설명 |
|---|---|
| `solved_by` | ✅(`white_check_mark`/`heavy_check_mark`)를 단 사람 중 학습자 또는 봇. 없으면 null |
| `verdict` | `solved` \| `unsolved` \| `gone` |

## 실행 결과 `RunStatus` (daily 명령 요약 JSON)

| 값 | 의미 | 종료 코드 |
|---|---|---|
| `POSTED` | 새 문제 게시(직전 문제 해결 포함) | 0 |
| `REMINDED` | 미해결이라 리마인드만 남김 | 0 |
| `REPOSTED` | 메시지가 없어져 같은 문제를 다시 게시 | 0 (경고 알림) |
| `ALREADY_POSTED` | 오늘 이미 게시함 | 0 |
| `ALREADY_REMINDED` | 오늘 이미 리마인드함 | 0 |
| `NO_SCENARIO` | 게시할 항목 없음 | 1 |
| `POST_FAILED` | Slack 호출 최종 실패(게시·조회·리마인드) | 1 |
| `UNEXPECTED_ERROR` | 그 밖의 예외 | 1 |

## 주간 요약 `WeeklySummary` 변경

| 필드 | 변경 | 계산 |
|---|---|---|
| `solved_posts` | 신규 | 이번 주 `resolved_at`이 있는 게시 수 |
| `stalled_days` | 신규 | 이번 주에 속한 `reminders` 날짜 수 |
| `open_post` | 신규 | 열린 문제의 (제목, 경과 일수) 또는 null |
| `backlog` | 삭제 | 한 번에 한 문제라 의미 없음 |

기존 `solved`(진행 기록의 `scenario_solved` 이벤트 수) 등 다른 필드는 그대로 둔다.
