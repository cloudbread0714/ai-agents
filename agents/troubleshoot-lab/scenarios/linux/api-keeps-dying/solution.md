## 원인

override가 api에 `LEAK_MB_PER_REQ=5`(요청마다 메모리 5 MiB를 붙잡아 둠)와 `mem_limit: 160m` 을 넣었어요. 요청이 30번쯤 쌓이면 한도를 넘어 커널 OOM killer가 프로세스를 죽였고(종료 코드 137, `OOMKilled=true`), `restart: unless-stopped` 가 다시 띄우는 동안 nginx는 502를 돌려줬어요.

## 해결

1. `docker inspect` 로 `RestartCount` 증가와 `OOMKilled=true` 를 확인해요.
2. `docker stats` 로 요청할 때마다 메모리가 계단식으로 오르는 것을 봐요. 줄지 않으면 누수예요.
3. `docker compose config api` 에서 `LEAK_MB_PER_REQ` 를 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

"가끔 죽는다"는 보통 자원 고갈이에요. 종료 코드 137과 OOMKilled가 메모리 문제를 가리켜요. 메모리 한도를 올리거나 재시작 주기를 짧게 하는 건 임시 처방이고, 요청이 끝나도 메모리가 줄지 않는 원인(누수)을 고쳐야 해요.
