#!/bin/sh
# Generate the practice TLS material (local only, not a secret): a lab CA, a certificate
# for localhost/nginx, and one for a different name (used by the HTTPS scenario).
# Runs inside the toolbox image: `make up` mounts the output directory at /certs.
set -eu
cd /certs
[ -f ca.pem ] && exit 0
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=troubleshoot-lab CA" \
  -keyout ca.key -out ca.pem 2>/dev/null
issue() {
  name=$1 san=$2
  openssl req -newkey rsa:2048 -nodes -subj "/CN=$name" -keyout "$name.key" -out "$name.csr" 2>/dev/null
  printf 'subjectAltName=%s\n' "$san" >"$name.ext"
  openssl x509 -req -in "$name.csr" -CA ca.pem -CAkey ca.key -CAcreateserial -days 825 \
    -extfile "$name.ext" -out "$name.pem" 2>/dev/null
  rm -f "$name.csr" "$name.ext"
}
issue site "DNS:localhost,DNS:nginx,IP:127.0.0.1"
issue wrong "DNS:wrong.example"
rm -f ca.key ca.srl
