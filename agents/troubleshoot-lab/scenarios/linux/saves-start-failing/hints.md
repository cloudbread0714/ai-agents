## 힌트 1

api 로그 끝에 저장이 실패한 이유가 남아 있어요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).

```
docker compose logs --tail 20 api
```

## 힌트 2

"No space left on device"는 디스크가 꽉 찼다는 뜻이에요. api 컨테이너 안에서 어느 파일 시스템이 찼는지, 무엇이 공간을 차지하는지 보세요.

```
/lab-exec api df -h
/lab-exec api du -sh /proc/1/root/var/log/app/*
```

## 힌트 3

api가 요청마다 로그를 200줄씩 쓰는 디버그 모드(`LOG_VERBOSE=1`)로 떠 있어서 32 MiB짜리 로그 볼륨(`/var/log/app`)이 가득 찼어요. 로그 파일만 지우면 곧 다시 차요. `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 `LOG_VERBOSE` 를 지우고 `docker compose up -d api` 로 다시 만드세요(로그 볼륨도 비워져요).
