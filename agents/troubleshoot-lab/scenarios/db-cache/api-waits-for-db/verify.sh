#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
http_burst_ok 30 3 http://localhost:8080/api/items
http_burst_ok 30 3 http://localhost:8080/api/items
