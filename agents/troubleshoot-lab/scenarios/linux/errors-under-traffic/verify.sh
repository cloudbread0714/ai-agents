#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
[[ "$(http_code localhost:8080/api/upstream)" == 200 ]]
http_burst_ok 400 40 http://localhost:8080/api/upstream
http_burst_ok 400 40 http://localhost:8080/api/upstream
