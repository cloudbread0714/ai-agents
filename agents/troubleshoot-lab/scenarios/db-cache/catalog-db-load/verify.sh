#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
cache_header() { curl -s -o /dev/null -D - --max-time 5 "$1" | tr -d '\r' | awk -F': ' 'tolower($1) == "x-cache" { print $2 }'; }
for id in 7 8; do
  cache_header "http://localhost:8080/api/catalog/$id" >/dev/null
  sleep 1
  [[ "$(cache_header "http://localhost:8080/api/catalog/$id")" == HIT ]]
done
