#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# rebuilds_on_expiry: expire the cached list now, send 30 concurrent requests, and count how many
# of them rebuilt it from the database (the api logs one line per rebuild).
rebuilds_on_expiry() {
  local since
  sleep 1
  since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  dc exec -T redis redis-cli DEL popular >/dev/null
  http_burst 30 30 http://localhost:8080/api/popular --max-time 10 >/dev/null
  dc logs --since "$since" api 2>/dev/null | grep -c 'popular rebuild' || true
}
compose_override api <<'YAML'
environment:
  CACHE_LOCK: "0"
  CACHE_JITTER: "0"
  POPULAR_TTL_MS: "2000"
YAML
wait_http http://localhost:8080/api/popular 200 60
stampede() { (($(rebuilds_on_expiry) >= 5)); }
wait_until 90 stampede
