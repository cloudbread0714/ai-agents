#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
sed_inplace "$LAB_WORK/nginx/default.conf" 's/^    listen 80;$/    listen 80/'
dc restart nginx >/dev/null 2>&1 || true
refused() { [[ "$(http_code localhost:8080/healthz)" == 000 ]]; }
wait_until 30 refused
