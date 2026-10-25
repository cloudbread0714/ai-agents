## 원인

override가 api에 `LEAK_DB_CONN=1` 과 `DB_POOL_SIZE=3` 을 넣었어요. `/items` 는 쿼리 뒤 연결을 풀에 반납하지 않았고, 3번 만에 풀이 비었어요. 이후 요청은 연결을 2초 기다리다(`pool timeout`) 503을 돌려줬어요. DB에는 api가 붙잡은 idle 연결 3개가 남아 있었어요.

## 해결

1. 응답 본문 `db pool timeout` 과 약 2초의 응답 시간을 확인해요.
2. `pg_stat_activity` 에서 api 연결이 idle 상태로 계속 남아 있는 것을 봐요. DB는 한가해요.
3. `docker compose config api` 에서 `LEAK_DB_CONN`, `DB_POOL_SIZE` 를 찾고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 지운 뒤 `docker compose up -d api`.

## 배운 점

"DB 연결이 모자라다"고 `max_connections` 를 늘리기 전에, 연결이 실제로 일하고 있는지(active) 놀고 있는지(idle)를 보세요. 놀면서 반납되지 않는 연결은 애플리케이션의 누수이고, 한도를 늘리면 DB 메모리만 더 쓰다 같은 장애가 나요.
