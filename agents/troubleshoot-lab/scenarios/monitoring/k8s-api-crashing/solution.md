## 원인

api Deployment에 잘못된 `command: [python, -m, app.server]` 가 들어간 채로 배포됐어요. 컨테이너가 `ModuleNotFoundError` 로 바로 종료되어 CrashLoopBackOff 가 됐어요. 배포 전략도 Recreate 라서 기존 Pod이 먼저 모두 내려가 서비스가 멈췄어요.

## 해결

1. `kubectl -n lab get pods -l app=api` 에서 CrashLoopBackOff 와 늘어나는 RESTARTS 를 확인해요.
2. `kubectl -n lab logs deploy/api --previous` 에서 `No module named app.server` 를 찾아요.
3. `kubectl -n lab rollout undo deploy/api` 로 되돌리거나, `kubectl -n lab edit deploy api` 에서 command 를 지워요.
4. `kubectl -n lab rollout status deploy/api` 가 끝나고 `curl localhost:8081/api/items` 가 200인지 확인해요.

## 배운 점

CrashLoopBackOff 는 '컨테이너가 시작했다가 곧 죽는 것을 반복한다'는 뜻이에요. 원인은 대부분 직전 실행 로그(`logs --previous`)에 있어요. 배포 직후에 생긴 문제라면 `rollout undo` 로 먼저 서비스를 살리고 원인을 고치는 것도 좋은 선택이에요.
