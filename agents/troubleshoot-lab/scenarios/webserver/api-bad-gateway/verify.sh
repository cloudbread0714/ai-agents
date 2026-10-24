#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
[[ "$(http_code localhost:8080/api/items)" == 200 ]]
[[ "$(dk inspect -f '{{.State.Restarting}}' troubleshoot-lab-api-1)" == false ]]
