## 힌트 1

Pod 목록에서 STATUS 와 RESTARTS 칸을 보세요. (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
kubectl -n lab get pods -l app=api
```

## 힌트 2

계속 재시작되는 컨테이너가 마지막으로 남긴 말은 '이전 실행'의 로그에 있어요.

```
kubectl -n lab logs deploy/api --previous
```

## 힌트 3

컨테이너 시작 명령(command)이 존재하지 않는 모듈을 실행하고 있어요. 바로 전에 배포된 설정이 문제이니 직전 리비전으로 되돌리세요.

```
kubectl -n lab rollout undo deploy/api
```
