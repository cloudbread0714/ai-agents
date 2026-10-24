## 원인

compose override 파일이 api의 실행 명령을 바꿔 uvicorn이 `--host 127.0.0.1` 로 떠 있었어요. 루프백 주소는 컨테이너 자신만 접근할 수 있어서, 다른 컨테이너인 nginx의 연결은 거부됐고 nginx는 502를 돌려줬어요.

## 해결

1. `/lab-exec api ss -ltnp` 에서 `127.0.0.1:8000` 으로만 LISTEN 중인 것을 확인해요.
2. `/lab-exec nginx curl http://api:8000/healthz` 가 연결 거부(000)인 것을 확인해요.
3. `docker compose config api` 로 `command` 에 `--host 127.0.0.1` 이 들어간 것을 찾아요.
4. `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 api의 `command` 를 지우고 `docker compose up -d api` 를 실행해요.

## 배운 점

"프로세스가 떠 있다"와 "다른 곳에서 접속할 수 있다"는 다른 문제예요. LISTEN 주소가 `0.0.0.0`(모든 인터페이스)인지 `127.0.0.1`(자기 자신)인지 먼저 확인하세요. 컨테이너와 서버 모두 같은 원리예요.
