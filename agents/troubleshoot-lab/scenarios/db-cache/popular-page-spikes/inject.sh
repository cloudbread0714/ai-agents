#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override api <<'YAML'
environment:
  CACHE_LOCK: "0"
  CACHE_JITTER: "0"
  POPULAR_TTL_MS: "2000"
YAML
wait_http http://localhost:8080/api/popular 200 60
stampede() {
  local i
  for i in 1 2 3; do
    http_burst 60 30 http://localhost:8080/api/popular >/dev/null
    sleep 2.2
  done
  (($(dc logs --since 10s api 2>/dev/null | grep -c 'popular rebuild') >= 5))
}
wait_until 90 stampede
