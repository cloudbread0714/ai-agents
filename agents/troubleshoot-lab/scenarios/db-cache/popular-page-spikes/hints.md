## 힌트 1

k6로 30명이 동시에 부를 때 응답 시간이 고르게 느린지, 몇 초마다 튀는지 보세요. 튀는 순간 api 로그에 무엇이 찍히나요? (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
docker compose logs --since 10s api | grep -c 'popular rebuild'
docker compose exec -T postgres psql -U lab -d lab -c "SELECT seq_scan, idx_scan FROM pg_stat_user_tables WHERE relname = 'popular'"
```

## 힌트 2

`popular rebuild` 는 캐시가 비어서 DB에서 다시 만든 횟수예요. 캐시가 만료되는 순간 동시에 들어온 요청이 모두 DB로 가고 있어요. 캐시 키의 남은 수명을 보세요.

```
docker compose exec -T redis redis-cli pttl popular
```

## 힌트 3

만료 시간이 2초로 짧고(`POPULAR_TTL_MS`), "한 요청만 다시 만들고 나머지는 기다리는" 잠금(`CACHE_LOCK=0`)과 만료 시각을 흩뜨리는 jitter(`CACHE_JITTER=0`)가 꺼져 있어요. 그래서 2초마다 cache stampede가 나요. `docker compose config api` 로 확인하고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 세 값을 지운 뒤 `docker compose up -d api` 를 실행하세요.
