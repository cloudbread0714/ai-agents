#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# Slow answers from the external service stay; the api must cope with them.
http_burst_ok 20 20 http://localhost:8080/api/checkout --max-time 4
http_burst_ok 20 20 http://localhost:8080/api/checkout --max-time 4
