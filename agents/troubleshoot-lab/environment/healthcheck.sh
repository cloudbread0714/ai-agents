#!/usr/bin/env bash
# Base-state health check. Usage: healthcheck.sh [all|compose|kind]
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"

mode=${1:-all}

if [[ $mode == all || $mode == compose ]]; then
  need_docker
  wait_http http://localhost:8080/healthz 200 90
  wait_http http://localhost:8080/api/items 200 30
  ext_ok() { [[ "$(dk inspect -f '{{.State.Running}}' troubleshoot-lab-ext-1 2>/dev/null)" == true ]]; }
  wait_until 30 ext_ok
  if [[ -f $LAB_WORK/nginx/certs/ca.pem ]]; then
    tls_ok() { curl -sf --max-time 3 --cacert "$LAB_WORK/nginx/certs/ca.pem" https://localhost:8443/healthz >/dev/null; }
    wait_until 30 tls_ok
  fi
fi

if [[ $mode == all || $mode == kind ]]; then
  for d in postgres redis ext api nginx; do
    k -n lab rollout status "deploy/$d" --timeout=180s >/dev/null
  done
  wait_http http://localhost:8081/healthz 200 90
fi
