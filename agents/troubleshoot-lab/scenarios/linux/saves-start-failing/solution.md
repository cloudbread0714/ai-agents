## 원인

override가 api에 `LOG_VERBOSE=1` 을 넣어 요청마다 약 180 KB의 로그를 썼어요. 로그 디렉터리 `/var/log/app` 은 32 MiB로 제한된 tmpfs라 수백 번의 요청 만에 가득 찼고, 이후 로그를 쓰는 모든 요청이 `ENOSPC`(No space left on device)로 500이 됐어요.

## 해결

1. `docker compose logs api` 에서 `No space left on device` 를 찾아요.
2. `docker compose exec -T api df -h` 로 `/var/log/app` 이 100%인 것을 확인해요.
3. `docker compose exec -T api sh -c 'du -sh /var/log/app/*'` 로 `app.log` 가 공간을 다 쓴 것을 확인해요.
4. `docker compose config api` 에서 `LOG_VERBOSE` 를 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

디스크가 차면 "저장 실패", "로그인 실패"처럼 엉뚱한 증상으로 나타나요. `df` 로 어느 파일 시스템이 찼는지, `du` 로 무엇이 차지하는지 보고, 공간만 비우지 말고 계속 채우는 원인(로그 레벨, 로그 로테이션 부재)을 막아야 해요.
