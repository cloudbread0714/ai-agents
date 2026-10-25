#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# rebuilds_on_expiry: expire the cached list now, send 30 concurrent requests, and count how many
# of them rebuilt it, i.e. how many times PostgreSQL read the popular table.
popular_scans() {
  dc exec -T postgres psql -U lab -d lab -tAc \
    "SELECT seq_scan + coalesce(idx_scan, 0) FROM pg_stat_user_tables WHERE relname = 'popular'"
}
rebuilds_on_expiry() {
  local before
  sleep 11 # idle backends flush their table stats within 10 s (PostgreSQL 15+)
  before=$(popular_scans)
  dc exec -T redis redis-cli DEL popular >/dev/null
  http_burst 30 30 http://localhost:8080/api/popular --max-time 10 >/dev/null
  sleep 11
  echo $(($(popular_scans) - before))
}
compose_override api <<'YAML'
environment:
  CACHE_LOCK: "0"
  CACHE_JITTER: "0"
  POPULAR_TTL_MS: "2000"
YAML
wait_http http://localhost:8080/api/popular 200 60
stampede() { (($(rebuilds_on_expiry) >= 5)); }
wait_until 120 stampede
