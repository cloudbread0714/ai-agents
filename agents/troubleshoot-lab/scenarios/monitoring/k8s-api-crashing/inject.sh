#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
k -n lab patch deploy api --type=strategic -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null},"template":{"spec":{"containers":[{"name":"api","command":["python","-m","app.server"]}]}}}}' >/dev/null
crashing() {
  local counts
  counts=$(k -n lab get pods -l app=api -o jsonpath='{.items[*].status.containerStatuses[*].restartCount}')
  [[ $counts =~ [1-9] ]] && [[ "$(http_code localhost:8081/api/items)" != 200 ]]
}
wait_until 150 crashing
