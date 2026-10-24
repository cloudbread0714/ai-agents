## 힌트 1

404를 누가 만들었는지부터 확인하세요. 응답의 `Server` 헤더와 본문을 보면 api가 아니라 앞단에서 만든 응답인지 알 수 있어요.

```
curl -i localhost:8080/api/items
```

## 힌트 2

nginx 가 직접 404를 돌려줬다면, 이 경로를 처리할 location 이 없다는 뜻이에요. 지금 적용 중인 설정 전체를 보세요. (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
docker compose exec nginx nginx -T
```

## 힌트 3

`/api/` 를 처리해야 할 location 경로에 오타가 있어요. 작업 사본 `agents/troubleshoot-lab/.lab-state/work/nginx/default.conf` 를 고친 뒤 nginx 에 다시 읽게 하세요.

```
docker compose exec nginx nginx -s reload
```
