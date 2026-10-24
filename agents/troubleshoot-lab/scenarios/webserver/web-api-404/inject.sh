#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
sed_inplace "$LAB_WORK/nginx/default.conf" 's#location /api/ {#location /apl/ {#'
nginx_reload
broken() { [[ "$(http_code localhost:8080/api/items)" == 404 ]]; }
wait_until 30 broken
