## 힌트 1

curl이 어떤 단계에서 왜 연결을 끊는지 자세히 보세요. 실습용 CA를 믿도록 `--cacert` 를 꼭 붙이세요.

```
curl -v --cacert agents/troubleshoot-lab/.lab-state/work/nginx/certs/ca.pem https://localhost:8443/healthz
```

## 힌트 2

인증서는 믿을 수 있는 CA가 발급했지만, 접속한 이름과 인증서에 적힌 이름이 같아야 해요. nginx가 실제로 내미는 인증서의 이름(SAN)을 보세요.

```
/lab-exec nginx sh -c 'openssl s_client -connect 127.0.0.1:443 -servername localhost </dev/null 2>/dev/null | openssl x509 -noout -subject -ext subjectAltName'
```

## 힌트 3

nginx가 `localhost` 용 인증서 대신 `wrong.example` 용 인증서(`wrong.pem`)를 쓰고 있어요. `agents/troubleshoot-lab/.lab-state/work/nginx/default.conf` 의 `ssl_certificate`·`ssl_certificate_key` 를 `site.pem`·`site.key` 로 바꾸고 `docker compose exec nginx nginx -s reload` 를 실행하세요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).
