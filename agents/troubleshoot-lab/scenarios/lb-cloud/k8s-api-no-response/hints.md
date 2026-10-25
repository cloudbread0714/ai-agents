## 힌트 1

트래픽은 nginx → api Service → api Pod 순서로 흘러요. Service가 실제로 Pod을 가리키고 있는지 확인하세요. (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`)

```
kubectl -n lab get endpointslices -l kubernetes.io/service-name=api
```

## 힌트 2

엔드포인트가 비어 있다면, Service가 Pod을 고르는 기준과 Pod의 라벨을 나란히 비교해 보세요.

```
kubectl -n lab describe svc api
kubectl -n lab get pods --show-labels
```

## 힌트 3

Service의 selector 가 실제 Pod 라벨(app=api)과 맞지 않아요. selector를 고치세요.

```
kubectl -n lab patch svc api -p '{"spec":{"selector":{"app":"api"}}}'
```
