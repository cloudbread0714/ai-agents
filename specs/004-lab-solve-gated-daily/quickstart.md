# Quickstart: 해결해야 다음 문제가 열리는 오늘의 문제 검증

## 1. 자동 테스트 (Slack 모킹, 비밀값 불필요)

```bash
uv run pytest shared/tests/test_slack.py agents/troubleshoot-lab/tests -q
```

확인할 시나리오(테스트 이름은 tasks 단계에서 정한다):

| 시나리오 | 기대 결과 | 근거 |
|---|---|---|
| 열린 문제 없음 → daily | `POSTED`, 새 항목에 `channel/ts`, `outcome=open` | US1-1, FR-002 |
| 열린 문제 + 학습자 ✅ | 해결 기록 + 다음 문제 `POSTED`, 열린 문제 1개 유지 | US1-2, SC-001 |
| 열린 문제 + 봇 ✅ | 위와 같음 | US2-6 |
| 열린 문제 + 다른 사람 ✅만 | `REMINDED` | US1-6 |
| ✅ 없음, 같은 날 두 번 실행 | 1회차 `REMINDED`, 2회차 `ALREADY_REMINDED`, 답글 요청 1건 | US1-4, SC-003 |
| 게시 후 3일, ✅ 없음 | 리마인드에 힌트 1 본문 포함 | US1-5, SC-005 |
| ⏭️만 있음 | `REMINDED`(넘어가지 않음) | FR-006 |
| 메시지 없음 | `REPOSTED`, `ts` 교체, 테스트 채널 경고 | R9 |
| 반응 조회 5xx 소진 | `POST_FAILED`, `posted.json` 변경 없음 | FR-024 |
| 필수 값 누락 | 종료 코드 2, 이름만 출력 | FR-022 |
| 기존 기록(신규 필드 없음)만 있음 | 끝난 문제로 보고 `POSTED` | 엣지 케이스 |
| `lab check` 해결 + 열린 문제 일치 | `slack_reaction=added`, `reactions.add` 1건 | US2-1 |
| 두 항목 중 하나만 해결 | `slack_reaction=partial`, 요청 없음 | US2-2 |
| Slack 값 없음/실패 | `no_config`/`failed`, 종료 코드는 성공 그대로 | US2-5 |
| 일요일 요약 | `해결 2 · 미해결로 멈춘 날 3일` | US3-1, SC-006 |

## 2. 실제 Slack으로 확인 (수동)

사전 준비:
1. Slack 앱에 봇 권한 `chat:write`, `reactions:read`, `reactions:write`를 주고, 봇을 lab 채널에 초대한다.
2. GitHub Secrets에 `SLACK_BOT_TOKEN`, `SLACK_LAB_CHANNEL_ID`, `SLACK_USER_ID`를 넣는다.
3. 로컬 자동 ✅용으로 `agents/troubleshoot-lab/.env`에 같은 세 값을 넣는다(`.env.example` 참고).

확인 순서:
1. Actions에서 `troubleshoot-lab`을 `target=test`로 수동 실행 → 테스트 채널에 미리 보기, `posted.json` 변경 없음.
2. `target=lab`으로 수동 실행 → lab 채널에 문제 게시, "Commit posting record" 단계가 `channel/ts`를 커밋.
3. 다시 `target=lab` 실행(✅ 없음) → 그 메시지 스레드에 리마인드 1건. 한 번 더 실행해도 추가 답글 없음.
4. `git pull` 후 로컬에서 그 문제를 풀고 `/lab-check` → "✅를 달았어요" 출력, Slack 메시지에 봇의 ✅.
5. 다음 날 아침(또는 날짜가 바뀐 뒤 수동 실행) → 다음 문제 게시.
