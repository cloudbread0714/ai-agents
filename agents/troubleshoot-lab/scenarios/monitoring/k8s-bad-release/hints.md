## 힌트 1

배포 자체는 성공했는데 요청이 실패해요. 버전과 실제 요청을 나란히 확인하고, 새 Pod의 로그를 보세요. (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
curl -s localhost:8081/api/version
curl -i localhost:8081/api/items
kubectl -n lab logs deploy/api --tail 20
```

## 힌트 2

Pod가 Ready인데 요청이 실패한다면 "Ready"를 판단하는 기준이 실제 동작을 확인하지 못하는 거예요. 새 버전에서 무엇이 바뀌었는지 비교해 보세요.

```
kubectl -n lab describe deploy api        # Readiness, Environment
kubectl -n lab rollout history deploy/api
```

## 힌트 3

새 버전은 DB 비밀번호가 틀렸고, readiness 검사가 `/version`만 보기 때문에 DB 연결 실패를 잡지 못한 채 끝까지 배포됐어요. 먼저 직전 버전으로 되돌리세요.

```
kubectl -n lab rollout undo deploy/api
```
