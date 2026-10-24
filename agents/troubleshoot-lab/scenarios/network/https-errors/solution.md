## 원인

nginx 설정 작업 사본의 `ssl_certificate` 가 SAN이 `wrong.example` 인 인증서(`wrong.pem`)를 가리켰어요. CA는 정상이지만 접속한 이름 `localhost` 가 인증서 이름과 달라 클라이언트가 연결을 거부했어요(`no alternative certificate subject name matches`).

## 해결

1. `curl -v --cacert ...` 에서 인증서 이름 불일치 오류를 확인해요.
2. `openssl s_client ... | openssl x509 -noout -subject -ext subjectAltName` 로 nginx가 내미는 인증서의 SAN이 `wrong.example` 인 것을 봐요.
3. `.lab-state/work/nginx/default.conf` 에서 인증서 경로를 `site.pem`/`site.key` 로 바꾸고 `nginx -s reload`.

## 배운 점

인증서 오류는 원인이 몇 가지로 정해져 있어요.
- 이름 불일치(SAN)
- 만료
- 신뢰할 수 없는 발급자(CA·중간 인증서 누락)
- 시계 오차

`openssl s_client` 로 서버가 실제로 내미는 인증서를 직접 보면 대부분 바로 구분돼요.
