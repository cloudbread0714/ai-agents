#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
curl -sf --max-time 5 --cacert "$LAB_WORK/nginx/certs/ca.pem" https://localhost:8443/healthz >/dev/null
[[ "$(http_code localhost:8080/healthz)" == 200 ]]
