## 힌트 1

요청을 보내는 동안 api 컨테이너의 CPU가 어떻게 되는지 보세요. 다른 터미널에서 요청을 몇 번 보내면서 확인하면 좋아요.

```
docker stats --no-stream troubleshoot-lab-api-1
/lab-exec api top -b -n 1
```

## 힌트 2

CPU가 한 코어를 꽉 채우고 있어요. 요청 하나가 계산에 시간을 많이 쓰면, 동시에 들어온 요청은 차례를 기다려야 해요. 같은 api의 다른 엔드포인트(`/api/version`)와 응답 시간을 비교해 보세요.

## 힌트 3

`/report` 가 합계를 공식 대신 300만 번 반복문으로 계산하는 방식(`REPORT_ALGO=naive`)으로 바뀌어 있어요. `docker compose config api` 로 확인하고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api` 를 실행하세요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`). 서버를 늘리는 것보다 계산 자체를 줄이는 게 먼저예요.
