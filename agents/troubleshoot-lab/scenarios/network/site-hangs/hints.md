## 힌트 1

거부(refused)와 시간 초과(timeout)는 다른 신호예요. 연결이 어느 단계에서 멈추는지 보세요.

```
curl -v --max-time 5 -w 'connect=%{time_connect} total=%{time_total}\n' localhost:8080/healthz
```

## 힌트 2

nginx는 80번 포트에서 LISTEN 하고 있고 프로세스도 살아 있어요. 그런데 연결 요청(SYN)에 아무 답이 없다면, 패킷이 중간에서 버려지고 있다는 뜻이에요.

```
/lab-exec nginx ss -ltn
```

## 힌트 3

nginx 컨테이너의 방화벽(iptables)에 80번 포트로 들어오는 패킷을 버리는(DROP) 규칙이 있어요. 규칙을 보거나 지우려면 권한이 필요해요.

```
docker run --rm --cap-add NET_ADMIN --network container:troubleshoot-lab-nginx-1 lab-toolbox:dev iptables -L INPUT -n --line-numbers
```

`iptables -D INPUT 1` 로 지우거나, 컨테이너를 다시 만드세요(`docker compose up -d --force-recreate nginx`) (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).
