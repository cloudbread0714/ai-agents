## 원인

api Service의 selector가 `app=api-v2` 로 바뀌어 있었어요. 그런 라벨을 가진 Pod이 없어서 Service 뒤에 엔드포인트가 하나도 없었고, nginx가 api로 연결하지 못해 502를 돌려줬어요.

## 해결

1. `kubectl -n lab get endpointslices -l kubernetes.io/service-name=api` 의 ENDPOINTS 가 비어 있는 것을 확인해요.
2. `kubectl -n lab describe svc api` 의 Selector(`app=api-v2`)와 Pod 라벨(`app=api`)이 다른 것을 찾아요.
3. `kubectl -n lab patch svc api -p '{"spec":{"selector":{"app":"api"}}}'` 또는 `kubectl -n lab edit svc api` 로 고쳐요.

## 배운 점

Pod이 건강해도 Service가 그 Pod을 고르지 못하면 트래픽이 가지 않아요. '응답 없음'이 나오면 Pod → Service → 엔드포인트 순서로 연결이 이어지는지 확인하세요. 라벨과 selector는 철자 하나만 달라도 연결이 끊겨요.
