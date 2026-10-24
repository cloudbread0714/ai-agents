#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
compose_override api <<'YAML'
environment:
  REPORT_DELAY_MS: "5000"
YAML
timing_out() { [[ "$(http_code localhost:8080/api/report)" == 504 ]]; }
wait_until 90 timing_out
