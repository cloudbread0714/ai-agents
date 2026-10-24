#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
k -n lab patch svc api -p '{"spec":{"selector":{"app":"api-v2"}}}' >/dev/null
broken() { [[ "$(http_code localhost:8081/api/items)" != 200 ]]; }
wait_until 30 broken
