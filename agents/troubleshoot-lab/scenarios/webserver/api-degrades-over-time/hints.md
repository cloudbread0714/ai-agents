## 힌트 1

api 컨테이너의 TCP 연결 상태를 세어 보세요. 요청을 보낸 뒤 다시 세면 무엇이 늘어나나요?

```
/lab-exec api ss -tan state close-wait
/lab-exec api sh -c 'ss -tan | awk "{print \$1}" | sort | uniq -c'
```

## 힌트 2

CLOSE_WAIT는 상대(외부 서비스)가 먼저 연결을 끊었는데 우리 쪽 프로그램이 소켓을 닫지 않은 상태예요. 이 소켓은 파일 디스크립터를 계속 차지해요. api 프로세스의 한도와 사용량을 비교해 보세요.

```
/lab-exec api sh -c 'ls /proc/1/fd | wc -l; prlimit --pid 1 --nofile'
```

## 힌트 3

`/upstream` 이 외부 서비스(ext) 호출 뒤 소켓을 닫지 않는 모드(`LEAK_SOCKETS=1`)로 떠 있어요. 1024개 한도를 다 쓰면 새 연결을 만들 수 없어 500이 나요. 한도를 올려도 결국 다시 차요. `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 `LEAK_SOCKETS` 를 지우고 `docker compose up -d api` 를 실행하세요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).
