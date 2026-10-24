#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# The leak alone takes too long to hurt in a 20 s measurement; a lower fd limit makes it bite.
compose_override api <<'YAML'
environment:
  LEAK_SOCKETS: "1"
ulimits:
  nofile:
    soft: 1024
    hard: 1024
YAML
wait_http http://localhost:8080/api/upstream 200 60
failing() { ! http_burst_ok 200 5 http://localhost:8080/api/upstream; }
wait_until 180 failing
