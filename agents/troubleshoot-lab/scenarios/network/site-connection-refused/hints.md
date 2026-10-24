## 힌트 1

요청을 받아야 할 컨테이너가 지금 살아 있는지부터 보세요. (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
docker compose ps -a
```

## 힌트 2

nginx 컨테이너가 Exited 상태예요. 컨테이너가 왜 종료됐는지는 그 컨테이너의 로그 마지막 줄에 남아 있어요.

```
docker compose logs nginx
```

## 힌트 3

로그의 `[emerg]` 줄이 설정 파일과 줄 번호를 알려 줘요. 이 환경의 nginx 설정 작업 사본은 `agents/troubleshoot-lab/.lab-state/work/nginx/default.conf` 예요. 그 줄 근처에서 지시어를 끝맺는 문자가 빠진 곳을 고친 뒤 nginx를 다시 띄우세요.

```
docker compose up -d nginx
```
