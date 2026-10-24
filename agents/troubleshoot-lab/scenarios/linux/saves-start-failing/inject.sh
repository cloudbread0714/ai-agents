#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override api <<'YAML'
environment:
  LOG_VERBOSE: "1"
YAML
wait_http http://localhost:8080/api/items 200 60
full() {
  http_burst 50 5 http://localhost:8080/api/items >/dev/null
  [[ "$(http_code -X POST -H 'Content-Type: application/json' -d '{"name":"x"}' http://localhost:8080/api/items)" == 500 ]]
}
wait_until 120 full
