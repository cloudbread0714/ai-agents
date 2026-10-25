## 원인

외부 서비스(ext)가 요청의 30%를 5초 늦게 응답했고, api는 `EXT_TIMEOUT_MS=0`(타임아웃 없음)으로 끝까지 기다렸어요. nginx는 3초 뒤 504를 돌려줬고, 그 사이 api 작업 스레드도 붙잡혀 있었어요.

## 해결

1. 실패한 요청이 항상 약 3초(nginx `proxy_read_timeout`)에 504로 끝나는 것을 확인해요.
2. ext에 직접 요청하면 일부가 5초 걸려요. 원인은 외부 의존성의 꼬리 지연이에요.
3. `docker compose config api` 에서 `EXT_TIMEOUT_MS: "0"` 을 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 의 api 항목에서 지운 뒤 `docker compose up -d api`. 기본값 1초 타임아웃이 걸리면 느린 호출은 대체 응답(`queued`)으로 끝나요.

## 배운 점

외부 호출에는 항상 우리 쪽 타임아웃을 두세요. 그 값은 앞단 프록시 타임아웃보다 짧아야 하고, 넘으면 대체 응답·재시도·회로 차단기로 처리해요. "가끔" 생기는 장애는 평균이 아니라 p95·p99와 오류율에서 보여요.
