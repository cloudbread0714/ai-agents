#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# 128 keeps idle health checks passing; only many concurrent requests run out of fds.
compose_override api <<'YAML'
ulimits:
  nofile:
    soft: 128
    hard: 128
YAML
wait_http http://localhost:8080/api/upstream 200 60
failing() { ! http_burst_ok 400 40 http://localhost:8080/api/upstream; }
wait_until 90 failing
