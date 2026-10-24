## 원인

nginx 컨테이너의 네트워크 공간에 `iptables -I INPUT -p tcp --dport 80 -j DROP` 규칙이 들어가 있었어요. DROP은 거부 응답(RST)도 보내지 않고 패킷을 버리기 때문에, 클라이언트는 답을 기다리다 시간 초과로 끝나요.

## 해결

1. `curl -v` 에서 연결 단계(`Trying ...`)에서 멈추는 것을 확인해요. 거부라면 즉시 실패했을 거예요.
2. `/lab-exec nginx ss -ltn` 으로 nginx가 `:80` 에서 LISTEN 중인 것을 확인해요. 프로세스 문제가 아니에요.
3. `docker run --rm --cap-add NET_ADMIN --network container:troubleshoot-lab-nginx-1 lab-toolbox:dev iptables -L INPUT -n` 으로 DROP 규칙을 찾아요.
4. `iptables -D INPUT 1` 로 규칙을 지우거나 nginx 컨테이너를 다시 만들어요.

## 배운 점

- Connection refused: 포트에 아무도 LISTEN 하지 않거나 REJECT 규칙이 있어요. 즉시 실패해요.
- Connection timeout: 패킷이 버려지고 있어요(방화벽, 보안 그룹, 라우팅). 한참 기다린 뒤 실패해요.

실패 방식이 원인 위치를 알려 줘요. 클라우드에서는 보안 그룹과 NACL이 같은 역할을 해요.
