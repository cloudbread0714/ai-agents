## 원인

nginx 가 `/api/profile` 응답을 공유 캐시에 저장했어요. api 는 사용자별 응답이라 `Cache-Control: private` 를 보냈지만, nginx 가 이를 무시했어요(`proxy_ignore_headers Cache-Control Set-Cookie`). 게다가 캐시 키에 쿠키가 없어서, 처음 캐시된 alice 의 응답이 모든 사용자에게 돌아갔어요.

## 해결

1. 쿠키를 바꿔 요청해도 같은 이름과 `X-Cache-Status: HIT` 가 나오는 것을 확인해요.
2. `docker compose exec nginx nginx -T` 에서 `proxy_cache_key "$scheme$host$uri"` 와 `proxy_ignore_headers Cache-Control Set-Cookie` 를 찾아요.
3. `agents/troubleshoot-lab/.lab-state/work/nginx/locations/profile-cache.conf` 를 지우는 게 가장 안전해요(사용자별 응답은 공유 캐시에 넣지 않기). 꼭 캐시해야 한다면 캐시 키에 사용자 식별자를 넣고 private 응답은 캐시하지 않게 해요.
4. `docker compose exec nginx nginx -s reload`.

## 배운 점

공유 캐시(프록시·CDN)에 사용자별 응답이 들어가면 다른 사람의 정보가 노출되는 보안 사고가 돼요. `Cache-Control: private` 는 '공유 캐시에 저장하지 말라'는 뜻이에요. 캐시 키에 무엇이 들어가는지(쿠키, 헤더)도 항상 함께 확인하세요.
