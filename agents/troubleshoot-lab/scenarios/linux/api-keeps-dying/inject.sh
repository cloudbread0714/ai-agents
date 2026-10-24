#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override api <<'YAML'
mem_limit: 160m
environment:
  LEAK_MB_PER_REQ: "5"
YAML
wait_http http://localhost:8080/api/items 200 60
restarts() { dk inspect -f '{{.RestartCount}}' troubleshoot-lab-api-1; }
before=$(restarts)
died() {
  http_burst 20 2 http://localhost:8080/api/items >/dev/null
  (($(restarts) > before))
}
wait_until 120 died
wait_http http://localhost:8080/api/items 200 60
