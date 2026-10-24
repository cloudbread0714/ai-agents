## 힌트 1

컨테이너가 다시 시작됐는지, 왜 끝났는지는 docker가 기록해 둬요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).

```
docker inspect -f 'restarts={{.RestartCount}} oom={{.State.OOMKilled}} exit={{.State.ExitCode}}' troubleshoot-lab-api-1
```

## 힌트 2

종료 코드 137은 강제 종료(SIGKILL)예요. 요청을 보내면서 메모리 사용량이 어떻게 변하는지 지켜보세요. 한도(LIMIT)에 닿으면 무슨 일이 생길까요?

```
docker stats --no-stream troubleshoot-lab-api-1
/lab-exec api free -m
```

## 힌트 3

api가 요청마다 5 MiB를 해제하지 않고 쌓아요(`LEAK_MB_PER_REQ`). 메모리 한도 160 MiB(`mem_limit`)에 닿으면 커널이 OOM으로 죽이고, docker가 다시 시작해요. 한도를 올리면 죽는 시점만 늦춰져요. `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 `LEAK_MB_PER_REQ` 를 지우고 `docker compose up -d api` 를 실행하세요.
