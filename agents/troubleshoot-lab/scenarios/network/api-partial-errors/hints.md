## 힌트 1

/api/counter 만 쓰는 의존성이 무엇일지 생각해 보세요. api 컨테이너 안에서 그 서비스 이름이 풀리는지 직접 확인할 수 있어요. (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
docker compose exec api python -c "import socket; print(socket.gethostbyname('redis'))"
```

## 힌트 2

컨테이너는 살아 있는데 이름으로 찾을 수 없다면 네트워크를 의심하세요. 어떤 컨테이너가 같은 네트워크에 붙어 있나요?

```
docker network inspect troubleshoot-lab_lab
```

## 힌트 3

redis 컨테이너가 lab 네트워크에서 빠져 있어요. 다시 연결할 때는 서비스 이름(redis)으로 찾을 수 있어야 해요. `docker network connect --alias redis ...` 를 쓰거나, compose로 컨테이너를 다시 만드세요(`docker compose up -d --force-recreate redis`).
