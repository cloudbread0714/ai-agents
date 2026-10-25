## 원인

override가 api에 `REPORT_ALGO=naive` 를 넣어, `/report` 가 제곱합을 공식 대신 Python 반복문 300만 번으로 계산했어요. 요청마다 CPU를 수백 ms 쓰고, Python은 한 프로세스에서 한 번에 한 계산만 하기 때문에 동시 요청이 줄을 섰어요.

## 해결

1. `docker stats` 와 `/lab-exec api top -b -n 1` 에서 api의 CPU가 100% 근처인 것을 확인해요.
2. `/api/version` 은 빠르고 `/api/report` 만 느려요. 특정 코드 경로 문제예요.
3. `docker compose config api` 에서 `REPORT_ALGO: naive` 를 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

CPU 100%일 때는 "어떤 프로세스가, 어떤 요청에서" 쓰는지부터 좁혀요. 서버를 늘리면 잠시 버티지만 비용이 계속 들어요. 비효율적인 계산을 고치거나 결과를 캐시하는 게 근본 해결이에요. Load Average는 CPU를 기다리는 작업 수까지 포함하므로, CPU 사용률과 함께 보면 "줄이 얼마나 긴지" 알 수 있어요.
