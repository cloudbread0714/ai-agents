## 원인

override가 api에 `CACHE_LOCK=0`, `CACHE_JITTER=0`, `POPULAR_TTL_MS=300` 을 넣었어요. `/popular` 는 0.3초짜리 비싼 쿼리 결과를 캐시하는데, 0.3초마다 캐시가 만료되면 그 순간 들어온 30개 요청이 모두 MISS가 되어 동시에 DB 쿼리를 실행했어요(cache stampede). 커넥션 풀(10개)도 밀려 응답이 몇 초까지 늘었어요.

## 해결

1. k6 결과에서 p95가 평균보다 훨씬 큰 것(주기적인 튐)을 확인해요.
2. `docker compose logs api | grep 'popular rebuild'` 가 같은 순간에 수십 번 찍히는 것을 봐요.
3. `redis-cli pttl popular` 로 TTL이 0.3초 안팎으로 아주 짧은 것을 확인해요.
4. `docker compose config api` 에서 세 값을 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

캐시가 있어도 만료 순간에 부하가 몰릴 수 있어요. 대책은 세 가지예요.
- 재생성 잠금(한 요청만 DB로 가고 나머지는 기다림)
- TTL jitter(키마다 만료 시각을 흩뜨림)
- 만료 전 백그라운드 갱신

평균만 보면 놓치기 쉬워 p95·p99를 함께 봐야 해요.
