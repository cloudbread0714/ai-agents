#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
sed_inplace "$LAB_WORK/nginx/default.conf" 's#certs/site\.pem;#certs/wrong.pem;#; s#certs/site\.key;#certs/wrong.key;#'
nginx_reload
tls_broken() { ! curl -sf --max-time 3 --cacert "$LAB_WORK/nginx/certs/ca.pem" https://localhost:8443/healthz >/dev/null; }
wait_until 30 tls_broken
