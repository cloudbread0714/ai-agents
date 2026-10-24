## 힌트 1

응답 본문과 걸린 시간을 함께 보세요. 2초는 누구의 기다림일까요?

```
curl -s -w '\ntotal=%{time_total}\n' localhost:8080/api/items
```

## 힌트 2

DB 쪽에서 api가 연결을 몇 개 들고 있고, 그 연결들이 무엇을 하고 있는지 보세요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).

```
docker compose exec -T postgres psql -U lab -d lab -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname = 'lab' GROUP BY state"
```

## 힌트 3

api의 DB 커넥션 풀이 3개로 작고(`DB_POOL_SIZE=3`), `/items` 가 쓴 연결을 풀에 돌려주지 않아요(`LEAK_DB_CONN=1`). 세 번 쓰고 나면 남은 연결이 없어 2초 기다린 뒤 503이 나요. DB의 `max_connections` 나 풀 크기를 늘려도 새는 연결은 결국 다 차요. `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 두 값을 지우고 `docker compose up -d api` 를 실행하세요.
