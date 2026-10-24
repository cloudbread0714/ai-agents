## 힌트 1

504가 몇 초 만에 나오는지 재 보세요. 매번 같은 시간이라면 누군가의 타임아웃 값이에요.

```
curl -s -o /dev/null -w 'code=%{http_code} total=%{time_total}\n' localhost:8080/api/report
```

## 힌트 2

nginx 오류 로그에 업스트림을 기다리다 포기한 기록이 있어요. 그렇다면 api는 이 요청에 얼마나 걸릴까요? nginx를 거치지 않고 api에 직접 물어보세요.

```
docker compose logs --tail 20 nginx
/lab-exec nginx curl -s -o /dev/null -w 'total=%{time_total}\n' http://api:8000/report
```

## 힌트 3

api가 `/report` 응답 전에 5초를 기다리고 있어요(`REPORT_DELAY_MS`). nginx의 `proxy_read_timeout` 은 3초예요. 타임아웃을 늘리면 사용자가 5초씩 기다리게 될 뿐이에요. `docker compose config api` 로 값을 확인하고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api` 를 실행하세요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).
