## 원인

nginx 설정의 `location /api/` 가 `location /apl/` 로 잘못 적혀 있었어요. `/api/...` 요청을 처리할 location 이 없어서 nginx 가 기본 동작으로 404 를 돌려줬어요.

## 해결

1. `curl -i localhost:8080/api/items` 의 `Server: nginx` 와 nginx 기본 404 페이지를 확인해요.
2. `docker compose exec nginx nginx -T` 에서 `location /apl/` 오타를 찾아요.
3. `agents/troubleshoot-lab/.lab-state/work/nginx/default.conf` 를 `location /api/` 로 고치고 `docker compose exec nginx nginx -s reload`.

## 배운 점

같은 404 라도 앱이 만든 것인지 프록시가 만든 것인지에 따라 볼 곳이 달라요. 응답 헤더와 본문으로 '누가 응답했는지'부터 가려내는 습관이 중요해요. `nginx -T` 는 실제로 적용된 설정 전체를 보여 줘요.
