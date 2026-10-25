#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
dk network disconnect troubleshoot-lab_lab troubleshoot-lab-redis-1
failing() { [[ "$(http_code localhost:8080/api/counter)" == 500 ]]; }
wait_until 30 failing
