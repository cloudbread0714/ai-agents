## 힌트 1

nginx 뒤에서 요청을 처리하는 api 컨테이너의 상태를 몇 초 간격으로 여러 번 확인해 보세요. STATUS가 바뀌나요? (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
docker compose ps
```

## 힌트 2

계속 재시작되는 컨테이너는 시작하자마자 종료되고 있어요. 종료 직전에 남긴 말이 로그 끝에 있어요.

```
docker compose logs --tail 20 api
```

## 힌트 3

api가 데이터베이스 주소 환경변수를 받지 못하고 있어요. 실제로 들어간 값은 `docker compose config api` 로 볼 수 있어요. 기본 설정 위에 값을 덮어쓰는 파일은 `agents/troubleshoot-lab/.lab-state/work/compose.override.yaml` 이에요. 고친 뒤 `docker compose up -d api`.
