## 원인

compose override가 api에 `REPORT_DELAY_MS=5000` 을 넣어 `/report` 가 5초 뒤에 응답했어요. nginx는 업스트림 응답을 3초(`proxy_read_timeout 3s`)까지만 기다리고 504를 돌려줬어요.

## 해결

1. `curl -w` 로 504가 항상 약 3초에 나오는 것을 확인해요(nginx 타임아웃).
2. `docker compose logs nginx` 에서 `upstream timed out` 을 찾아요.
3. api에 직접 요청하면 약 5초가 걸려요. 느린 쪽은 api예요.
4. `docker compose config api` 에서 `REPORT_DELAY_MS` 를 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

504는 "프록시가 뒤를 기다리다 포기했다"는 뜻이에요. 타임아웃을 늘리면 오류는 사라지지만 느린 응답은 그대로라 사용자 경험과 연결 점유가 나빠져요. 먼저 왜 느린지 찾고, 타임아웃은 정상 응답 시간보다 조금 길게 두는 게 원칙이에요.
