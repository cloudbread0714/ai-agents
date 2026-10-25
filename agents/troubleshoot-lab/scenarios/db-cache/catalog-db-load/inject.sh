#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override api <<'YAML'
environment:
  CACHE_TTL_MS: "1"
YAML
wait_http http://localhost:8080/api/catalog/1 200 60
cache_header() { curl -s -o /dev/null -D - --max-time 5 "$1" | tr -d '\r' | awk -F': ' 'tolower($1) == "x-cache" { print $2 }'; }
missing() {
  cache_header http://localhost:8080/api/catalog/1 >/dev/null
  [[ "$(cache_header http://localhost:8080/api/catalog/1)" == MISS ]]
}
wait_until 30 missing
