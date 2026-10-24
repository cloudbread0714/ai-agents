#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
k -n lab rollout status deploy/api --timeout=10s >/dev/null
[[ "$(http_code localhost:8081/api/items)" == 200 ]]
