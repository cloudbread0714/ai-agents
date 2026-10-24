## 힌트 1

같은 상품을 연속으로 불러 응답 헤더를 비교해 보세요. 두 번째는 캐시에서 나와야 해요.

```
curl -s -o /dev/null -D - localhost:8080/api/catalog/1 | grep -i x-cache
```

## 힌트 2

api는 조회 결과를 Redis에 저장해요. 방금 조회한 상품의 키가 Redis에 남아 있는지, 남아 있다면 얼마 뒤 사라지는지 보세요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).

```
docker compose exec -T redis redis-cli --scan --pattern 'catalog:*'
docker compose exec -T redis redis-cli info stats | grep keyspace
```

## 힌트 3

캐시 만료 시간(`CACHE_TTL_MS`)이 1ms로 바뀌어 있어서, 저장하자마자 사라져 적중률이 0%예요. 모든 요청이 DB로 가요. `docker compose config api` 로 확인하고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api` 를 실행하세요.
