## 원인

nginx 에 `/api/items` 전용 location 이 추가되어 있었어요. 이 location 은 api 가 보낸 `Cache-Control: no-store` 를 `proxy_ignore_headers` 로 무시하고 200 응답을 10분 동안 캐시했어요. POST 는 api 까지 가서 저장됐지만, GET 은 캐시된 예전 목록을 돌려줬어요.

## 해결

1. `curl -sI localhost:8080/api/items` 를 두 번 보내 `X-Cache-Status: HIT` 를 확인해요.
2. `docker compose exec nginx nginx -T` 에서 `location = /api/items` 의 `proxy_cache`, `proxy_ignore_headers Cache-Control` 을 찾아요.
3. `agents/troubleshoot-lab/.lab-state/work/nginx/locations/items-cache.conf` 를 지우거나 캐시 관련 줄을 빼고 `docker compose exec nginx nginx -s reload`.

## 배운 점

캐시는 '언제 새 데이터를 볼 수 있는지'를 바꿔요. 서버가 보낸 Cache-Control 을 프록시가 무시하면 이런 '오래된 데이터' 문제가 생겨요. 응답 헤더(X-Cache-Status, Age, Cache-Control)를 보면 데이터가 어디서 왔는지 알 수 있어요.
