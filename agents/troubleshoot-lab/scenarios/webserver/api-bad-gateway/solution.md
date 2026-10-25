## 원인

compose override 파일이 api의 `DATABASE_URL` 을 빈 값으로 덮어쓰고 있었어요. api는 시작할 때 이 값이 없으면 종료하고, `restart: unless-stopped` 때문에 계속 재시작했어요. 그 사이 nginx는 연결할 api가 없어 502를 돌려줬어요.

## 해결

1. `docker compose ps` 를 여러 번 실행하면 api가 Restarting 과 Up 을 오가요.
2. `docker compose logs --tail 20 api` 에서 `DATABASE_URL is not set` 을 찾아요.
3. `docker compose config api` 로 합쳐진 설정에서 `DATABASE_URL: ""` 를 확인해요.
4. `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 해당 항목을 지우고(`services: {}` 만 남겨도 돼요) `docker compose up -d api` 를 실행해요.

## 배운 점

502는 '프록시는 살아 있는데 그 뒤가 응답하지 않는다'는 신호예요. 재시작을 반복하는 컨테이너는 로그 끝부분에 원인을 남기는 경우가 많아요. compose는 여러 파일을 합쳐서 최종 설정을 만들기 때문에, `docker compose config` 로 실제로 적용된 값을 확인하는 게 중요해요.
