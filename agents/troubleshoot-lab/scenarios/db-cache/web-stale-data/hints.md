## 힌트 1

같은 GET 요청을 두 번 보내고 응답 헤더를 비교해 보세요. 실습 nginx 는 X-Cache-Status 헤더로 캐시 사용 여부를 알려 줘요.

```
curl -sI localhost:8080/api/items
```

## 힌트 2

HIT 라면 응답이 api 가 아니라 nginx 캐시에서 나오고 있어요. api 가 원래 보내는 Cache-Control 은 무엇이고, nginx 는 그 헤더를 따르고 있나요? 이 경로에 적용된 설정을 찾아보세요. (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
docker compose exec nginx nginx -T | grep -n -A8 'location = /api/items'
```

## 힌트 3

`/api/items` 전용 location 이 api 의 `Cache-Control: no-store` 를 무시(`proxy_ignore_headers`)하고 10분 동안 캐시해요. `agents/troubleshoot-lab/.lab-state/work/nginx/locations/` 의 해당 설정을 고치거나 지운 뒤 `docker compose exec nginx nginx -s reload`.
