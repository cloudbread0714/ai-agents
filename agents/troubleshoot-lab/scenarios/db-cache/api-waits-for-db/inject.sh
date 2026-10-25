#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override api <<'YAML'
environment:
  LEAK_DB_CONN: "1"
  DB_POOL_SIZE: "3"
YAML
wait_http http://localhost:8080/healthz 200 60
exhausted() {
  http_code http://localhost:8080/api/items >/dev/null
  [[ "$(http_code http://localhost:8080/api/items)" == 503 ]]
}
wait_until 60 exhausted
