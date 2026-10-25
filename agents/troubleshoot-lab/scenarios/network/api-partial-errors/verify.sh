#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
[[ "$(http_code localhost:8080/api/counter)" == 200 ]]
[[ "$(http_code localhost:8080/healthz)" == 200 ]]
