## 원인

override가 api에 `LEAK_SOCKETS=1` 과 `nofile` 1024 한도를 넣었어요. `/upstream` 은 ext 서비스를 호출한 뒤 소켓을 닫지 않았고, ext가 먼저 끊은 연결이 api 쪽에서 CLOSE_WAIT로 쌓였어요. 소켓마다 파일 디스크립터를 하나씩 차지해 한도에 닿자 `Too many open files` 로 새 연결을 못 만들고 500이 났어요.

## 해결

1. `/lab-exec api ss -tan state close-wait` 로 CLOSE_WAIT가 요청 수만큼 늘어나는 것을 확인해요.
2. `/lab-exec api sh -c 'ls /proc/1/fd | wc -l; prlimit --pid 1 --nofile'` 로 fd가 한도에 가까운 것을 봐요.
3. `docker compose logs api` 에서 `Too many open files` 를 찾아요.
4. `docker compose config api` 에서 `LEAK_SOCKETS` 를 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

CLOSE_WAIT가 계속 늘면 "우리 코드가 close를 안 한다"는 신호예요. 반대로 TIME_WAIT는 먼저 끊은 쪽에 잠시 남는 정상 상태라 많아도 대부분 문제가 아니에요. 재시작하면 좋아지고 시간이 지나면 나빠지는 장애는 누수(메모리, 소켓, 커넥션)를 먼저 의심하세요.
