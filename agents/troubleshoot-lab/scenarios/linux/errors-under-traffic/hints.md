## 힌트 1

실패한 순간 api가 남긴 로그를 보세요. 동시 요청을 보낸 직후에 확인하면 좋아요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).

```
docker compose logs --tail 30 api
```

## 힌트 2

"Too many open files"는 프로세스가 열 수 있는 파일 디스크립터(소켓 포함) 한도에 닿았다는 뜻이에요. api 프로세스의 한도가 얼마인지 보세요.

```
/lab-exec api prlimit --pid 1 --nofile
```

## 힌트 3

api 컨테이너의 `nofile` 한도가 64로 낮춰져 있어요(`ulimits`). 요청 하나가 nginx 연결, ext 연결, DB·Redis 연결을 함께 쓰기 때문에 동시 요청이 많으면 금방 닿아요. `docker compose config api` 로 확인하고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 `ulimits` 를 지운 뒤 `docker compose up -d api` 를 실행하세요.
