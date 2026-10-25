#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}

case $step in
  ps | logs) answer_is "$step" "$answer" ;;
  restart)
    now=$(dk inspect -f '{{.State.StartedAt}}' troubleshoot-lab-nginx-1)
    [[ -n $now && $now != "$(answer_get nginx-started)" && "$(http_code localhost:8080/healthz)" == 200 ]]
    ;;
  *) exit 1 ;;
esac
