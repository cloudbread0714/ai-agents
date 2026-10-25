#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# 64 keeps idle health checks passing (~15 fds); 40 concurrent requests need ~90 (nginx + ext sockets).
compose_override api <<'YAML'
ulimits:
  nofile:
    soft: 64
    hard: 64
YAML
wait_http http://localhost:8080/api/upstream 200 60
failing() { ! http_burst_ok 400 40 http://localhost:8080/api/upstream; }
wait_until 90 failing
