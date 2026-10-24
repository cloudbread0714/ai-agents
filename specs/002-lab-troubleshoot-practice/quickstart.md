# Quickstart: lab: 트러블슈팅 실습 검증 가이드 (커리큘럼 개정판)

구현이 스펙대로 동작하는지 끝까지 확인하는 순서다. 명령은 레포 루트에서 실행한다.
세부 동작은 contracts/를 따른다.
- [cli.md](./contracts/cli.md)
- [measurement.md](./contracts/measurement.md)
- [report.md](./contracts/report.md)

## 0. 준비물

- Docker Desktop, `kind`, `kubectl`, `make`, `uv`, `jq`, `curl`
- 호스트에 k6·ss 등을 설치할 필요는 없다(SC-010).
- Slack 웹훅은 §6에만 필요하다. `agents/troubleshoot-lab/.env`에 둔다.

## 1. 자동 테스트 (Docker·네트워크 불필요)

```bash
uv run pytest
(cd agents/troubleshoot-lab && uv run pytest)
uv run --directory agents/troubleshoot-lab/environment/api pytest
agents/troubleshoot-lab/bin/lab validate
```

기대 결과:
- 모두 통과한다.
- `validate`가 다음을 출력한다.
  - 미션·시나리오 개수(시나리오 23개)와 오류 0
  - plan 21일, 일차별 예상 시간 60~90분

## 2. 실습 환경

```bash
make -C agents/troubleshoot-lab up     # compose(:8080, :8443) + kind(:8081) + toolbox·k6 이미지 + metrics-server
eval "$(agents/troubleshoot-lab/bin/lab env)"
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/healthz                                  # 200
curl -s --cacert agents/troubleshoot-lab/.lab-state/work/nginx/certs/ca.pem https://localhost:8443/healthz  # ok
curl -s -o /dev/null -w '%{http_code}\n' localhost:8081/healthz                                  # 200
```

## 3. 진단 컨테이너와 가드

```bash
agents/troubleshoot-lab/bin/lab exec api -- ss -lntp          # 0.0.0.0:8000 LISTEN (호스트에 ss 없어도 됨)
agents/troubleshoot-lab/bin/lab exec api -- top -b -n 1 | head
agents/troubleshoot-lab/bin/lab exec --env kind api -- ss -lntp
agents/troubleshoot-lab/bin/lab shell api                      # 사용자 터미널용 docker run -it ... 출력
```

가드 확인은 이전 판과 같다. 종료 코드 5(환경 준비 안 됨)와 3(원격 주소 거부)을 확인한다.

## 4. 6단계 흐름 (US1) — Claude Code에서, #3 Connection Refused

1. `/lab-start site-connection-refused`를 실행하면 잠김 상태로 워밍업(socket-check, docker-logs)이 안내된다. 두 워밍업을 완료한다.
2. `/lab-start site-connection-refused`를 다시 실행한다.
   - "1단계: 정상 상태를 측정하세요" 안내가 나오고, 장애는 아직 주입되지 않는다.
   - 이 상태에서 `/lab-inject`를 실행하면 `need_measure`로 거부된다.
3. `/lab-measure`를 실행한다.
   - 정상 상태 측정표가 나온다(오류율 0%, 응답 시간·CPU 실측값).
   - 20~40초 안에 끝난다(SC-006).
4. `/lab-inject`를 실행하면 증상만 안내된다. 이 상태에서 `/lab-check`를 실행하면 `need_measure`가 나온다.
5. `/lab-measure`를 다시 실행한다.
   - 장애 상태 측정이 나온다: 오류율 100%, 응답 시간 "해당 없음".
   - "정상 대비" 열은 "—"다.
6. 증상을 관찰한다. `/lab-exec nginx ss -lntp`는 "대상 서비스가 실행 중이 아니에요"를 안내한다. `docker compose logs nginx`로 원인을 찾는다.
7. 원인을 고친 뒤 `/lab-check`를 실행한다.
   - 해결로 기록되고, 해결 후 측정이 자동으로 실행된다.
   - 해설과 회고 안내가 나오고, push 질문이 뜨면 "아니요"를 고른다.
8. `/lab-report`를 실행한다.
   - `docs/reports/<오늘>-site-connection-refused-1.md`가 만들어진다.
   - 측정표 세 열이 모두 실측값 또는 상태 표기로 채워져 있다. 추정값은 없다(SC-004).
   - 면접 질문 "Connection Refused와 Connection Timeout의 차이는?"이 들어 있다.
9. 보고서를 채우지 않은 채로 `/lab-report --done`을 실행하면 `incomplete`와 빈 섹션 목록이 나온다. 채운 뒤 다시 실행하면 `reviewed`가 나오고 push 질문이 뜬다.
10. `/lab-reset`을 실행한다. 측정 기록과 보고서는 그대로 남아 있다.

## 5. 측정값 규칙

```bash
agents/troubleshoot-lab/bin/lab start <시나리오>
agents/troubleshoot-lab/bin/lab measure --skip "k6 이미지 다운로드 실패"
```

기대 결과: 모든 지표가 "측정 생략(사유)"로 기록되고 inject가 허용된다.

kind 시나리오에서 metrics-server가 준비되기 전에 측정하면 CPU·메모리가 "측정 불가"로 나온다.

## 6. 매일 알림 (US2, US3)

```bash
set -a; . agents/troubleshoot-lab/.env; set +a
L=agents/troubleshoot-lab/bin/lab
$L daily --dry-run --force                         # 1일 차: TCP/IP·OSI, 개념 미션, 예상 60~90분
$L daily --dry-run --force --today 2026-11-01      # 일요일이면 주간 요약도 함께
$L daily --target test --force                     # #agent-test 에 [TEST] 게시
```

`posted.json`을 조작해 다음을 확인한다.
- 마지막 게시가 3일 차면 오늘은 4일 차이고, #1이 주 항목, #4가 "시간이 남으면"이다.
- 밀린 문제가 3개면 따라잡기 날이 된다.
- 21일 차 다음은 심화 1/5다.

모든 경우에 메시지에 힌트·해설·면접 질문·태그가 없다(SC-002).

## 7. 샌드박스 테스트와 GitHub Actions

```bash
make -C agents/troubleshoot-lab test-sandbox
```

기대 결과:
- 시나리오 23개 모두 다음 순서가 통과한다.
  1. baseline 측정
  2. inject
  3. verify 실패
  4. fault 측정
  5. reset ×2
  6. 지문이 같음
- 정상과 장애 측정에서 최소 1개 지표가 다르다(SC-005).
- 미션은 모든 단계가 통과한다.

GitHub Actions 확인은 이전 판 §6과 같다(Secrets `SLACK_WEBHOOK_LAB_URL`, 수동 실행 `target=test post=both`).
