#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
k -n lab rollout status deploy/api --timeout=10s >/dev/null
for _ in 1 2 3 4 5; do
  [[ "$(http_code localhost:8081/api/items)" == 200 ]]
done
