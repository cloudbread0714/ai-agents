## 힌트 1

서로 다른 쿠키로 요청하면서 응답 헤더를 비교해 보세요.

```
curl -si --cookie user=bob localhost:8080/api/profile
curl -si --cookie user=carol localhost:8080/api/profile
```

## 힌트 2

응답이 공유 캐시에서 나오고 있어요(X-Cache-Status). api 가 원래 보내는 Cache-Control 은 `private` 인데, 클라이언트가 받는 값은 무엇인가요? 이 경로의 캐시 키와 무시하는 헤더를 확인하세요. (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
docker compose exec nginx nginx -T | grep -n -A12 'location = /api/profile'
```

## 힌트 3

`/api/profile` location 이 api 의 `Cache-Control: private` 를 무시하고, 쿠키가 빠진 캐시 키로 모든 사용자에게 같은 응답을 줘요. `agents/troubleshoot-lab/.lab-state/work/nginx/locations/` 의 해당 설정에서 캐시를 끄는 것이 가장 안전해요. 고친 뒤 `docker compose exec nginx nginx -s reload`.
