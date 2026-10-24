## 원인

override가 api에 `CACHE_TTL_MS=1` 을 넣어 Redis에 저장한 상품이 1ms 뒤 만료됐어요. 캐시는 "있지만 늘 비어 있는" 상태라 적중률이 0%였고, 모든 요청이 DB 쿼리를 실행했어요.

## 해결

1. 연속 요청의 `X-Cache` 헤더가 항상 `MISS` 인 것을 확인해요.
2. `redis-cli --scan --pattern 'catalog:*'` 이 비어 있고 `keyspace_misses` 만 늘어나는 것을 봐요.
3. `docker compose config api` 에서 `CACHE_TTL_MS: "1"` 을 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

캐시는 "적용했다"가 아니라 "적중하고 있다"가 중요해요. 적중률(hits / (hits + misses))을 모니터링하고, TTL은 데이터가 바뀌는 주기와 허용할 수 있는 오래됨 사이에서 정해요.
