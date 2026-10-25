## 원인

새 버전(2.0.0)의 `DATABASE_URL` 비밀번호가 틀렸어요. readiness 검사가 DB를 보지 않는 `/version`만 확인해서 Pod는 모두 Ready가 됐고, 롤링 업데이트가 끝까지 진행되어 기존 정상 Pod가 모두 교체됐어요. 결과적으로 DB를 쓰는 요청이 전부 실패했어요.

## 해결

1. `curl /api/version`은 2.0.0인데 `/api/items`는 실패하는 것을 확인해요.
2. `kubectl -n lab logs deploy/api`에서 DB 인증 오류를, `kubectl -n lab describe deploy api`에서 readiness 경로(`/version`)와 바뀐 환경변수를 찾아요.
3. `kubectl -n lab rollout undo deploy/api`로 직전 리비전으로 되돌리고 `rollout status`로 완료를 확인해요.

## 배운 점

배포 직후 장애는 "원인 분석"보다 "되돌리기"가 먼저예요. 그리고 readiness 검사는 실제 요청 처리에 필요한 의존성(DB 연결 등)을 확인해야 잘못된 버전이 트래픽을 받기 전에 배포를 멈출 수 있어요. 다만 너무 무거운 검사는 의존성 장애 때 모든 Pod를 내려 버릴 수 있으니 균형이 필요해요.
