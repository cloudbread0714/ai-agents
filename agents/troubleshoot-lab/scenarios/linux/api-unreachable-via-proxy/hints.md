## 힌트 1

api 컨테이너 안에서 프로세스가 어떤 주소와 포트로 연결을 기다리는지 보세요.

```
/lab-exec api ss -ltnp
```

## 힌트 2

`0.0.0.0:8000` 과 `127.0.0.1:8000` 은 다르게 동작해요. 같은 컨테이너 안에서는 둘 다 응답하지만, nginx는 다른 컨테이너예요. nginx 쪽에서 api로 직접 붙어 보세요.

```
/lab-exec nginx curl -s -m 3 -o /dev/null -w '%{http_code}\n' http://api:8000/healthz
```

## 힌트 3

api가 `127.0.0.1`(자기 자신)에만 바인드되어 있어 다른 컨테이너에서 접속할 수 없어요. 실행 명령은 `docker compose config api` 의 `command` 에서 볼 수 있어요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`). `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 에서 api의 `command` 덮어쓰기를 지우고 `docker compose up -d api` 를 실행하세요.
