#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override ext <<'YAML'
environment:
  APP_ROLE: ext
  EXT_SLOW_RATIO: "0.3"
  EXT_SLOW_MS: "5000"
YAML
compose_override api <<'YAML'
environment:
  EXT_TIMEOUT_MS: "0"
YAML
wait_http http://localhost:8080/healthz 200 60
timing_out() { http_burst 20 20 http://localhost:8080/api/checkout | grep -q '^504$'; }
wait_until 60 timing_out
