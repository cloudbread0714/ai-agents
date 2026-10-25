#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override api <<'YAML'
environment:
  REPORT_ALGO: naive
YAML
wait_http http://localhost:8080/api/report 200 60
slow() {
  local t
  t=$(curl -s -o /dev/null -w '%{time_total}' --max-time 10 localhost:8080/api/report || echo 0)
  awk -v t="$t" 'BEGIN { exit !(t > 0.1) }'
}
wait_until 60 slow
