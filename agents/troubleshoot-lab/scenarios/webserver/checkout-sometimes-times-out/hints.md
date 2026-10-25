## 힌트 1

성공과 실패의 응답 시간을 나눠 보세요. 실패가 항상 같은 시간에 나온다면 누구의 타임아웃일까요?

```
for i in $(seq 10); do curl -s -o /dev/null -w '%{http_code} %{time_total}\n' localhost:8080/api/checkout; done
```

## 힌트 2

`/checkout` 은 외부 결제 서비스(ext)를 호출해요. api를 거치지 않고 ext에 직접 여러 번 물어보면 어떤가요? 외부 서비스가 가끔 느린 건 우리가 바꿀 수 없다고 가정해요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).

```
/lab-exec api sh -c 'for i in 1 2 3 4 5 6; do curl -s -o /dev/null -w "%{time_total}\n" http://ext:8000/ext/work; done'
```

## 힌트 3

api가 ext를 기다리는 시간에 제한이 없어요(`EXT_TIMEOUT_MS=0`). ext가 5초 걸리는 요청은 nginx의 3초 한도에 먼저 걸려 504가 돼요. api에 1초 타임아웃을 두면 대체 응답(`queued`)으로 바로 끝나요. `docker compose config api` 로 확인하고 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 의 api 쪽 `EXT_TIMEOUT_MS` 를 지운 뒤 `docker compose up -d api` 를 실행하세요(ext 쪽 설정은 외부 서비스라 그대로 두세요).
