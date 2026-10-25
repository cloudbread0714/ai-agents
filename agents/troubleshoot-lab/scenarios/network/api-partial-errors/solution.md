## 원인

redis 컨테이너가 compose 네트워크(`troubleshoot-lab_lab`)에서 분리돼 있었어요. api는 `redis` 라는 이름을 DNS로 찾을 수 없어 Redis를 쓰는 /api/counter 와 /healthz 에서만 오류를 냈어요. PostgreSQL만 쓰는 /api/items 는 멀쩡했어요.

## 해결

1. api 안에서 `socket.gethostbyname('redis')` 가 실패하는 것을 확인해요.
2. `docker network inspect troubleshoot-lab_lab` 의 Containers 목록에 redis가 없는 것을 찾아요.
3. 둘 중 하나로 고쳐요.
   - `docker network connect --alias redis troubleshoot-lab_lab troubleshoot-lab-redis-1`
   - `docker compose up -d --force-recreate redis`
4. `--alias` 없이 다시 연결하면 컨테이너 이름으로만 찾을 수 있어서 `redis` 라는 이름은 여전히 안 풀려요.

## 배운 점

'일부 기능만 실패'하면 그 기능만 쓰는 의존성을 먼저 의심하세요. 컨테이너가 Up 이어도 네트워크와 DNS 이름(alias)이 맞아야 서로 찾을 수 있어요. compose 서비스 이름은 네트워크 alias로 등록된다는 점을 기억하세요.
