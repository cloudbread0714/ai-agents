## 원인

override가 api 컨테이너에 `ulimits.nofile: 128` 을 넣었어요. 리눅스에서는 소켓도 파일 디스크립터라, 동시 요청 40개가 nginx·ext·DB·Redis 연결을 함께 열면 한도를 넘었어요. 새 소켓을 만들지 못한 요청이 `Too many open files` 로 실패했어요.

## 해결

1. 동시 요청을 보내 실패를 재현하고 `docker compose logs api` 에서 `Too many open files` 를 찾아요.
2. `/lab-exec api prlimit --pid 1 --nofile` 로 한도가 128인 것을 확인해요.
3. `docker compose config api` 에서 `ulimits` 를 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

"평소엔 괜찮고 몰릴 때만" 실패하면 동시성에 비례하는 자원(파일 디스크립터, 스레드, 커넥션 풀, 포트)을 의심하세요. `ulimit -n` 은 서버 기본값이 낮은 경우가 많아, 운영 서버는 systemd `LimitNOFILE` 이나 컨테이너 `ulimits` 로 명시해요.
