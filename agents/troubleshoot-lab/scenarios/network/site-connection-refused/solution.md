## 원인

nginx 설정의 `listen 80;` 끝 세미콜론이 빠져 있었어요. nginx가 다음 줄까지 한 지시어로 읽다가 `invalid parameter` 오류를 내고 시작하자마자 종료했어요. 컨테이너가 없으니 8080 포트로 들어오는 연결이 바로 거부됐어요.

## 해결

1. `docker compose ps -a` 로 nginx가 Exited 인 것을 확인해요.
2. `docker compose logs nginx` 에서 `[emerg] invalid parameter ... default.conf:줄번호` 를 찾아요.
3. `agents/troubleshoot-lab/.lab-state/work/nginx/default.conf` 의 `listen 80` 뒤에 `;` 를 붙여요.
4. `docker compose up -d nginx` 로 다시 시작하고 `curl -i localhost:8080/healthz` 가 200인지 확인해요.

## 배운 점

연결 거부(connection refused)는 대개 '그 포트에서 듣고 있는 프로세스가 없다'는 뜻이에요. 먼저 컨테이너가 살아 있는지(`ps -a`), 죽었다면 왜 죽었는지(`logs`)를 차례로 보면 대부분 금방 찾을 수 있어요. 설정을 바꾼 뒤에는 `nginx -t` 로 문법을 먼저 확인하는 습관도 좋아요.
