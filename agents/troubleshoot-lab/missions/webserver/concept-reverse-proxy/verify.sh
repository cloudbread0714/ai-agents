#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}
case $step in
  upstream | timeout | rewrite | server) answer_is "$step" "$answer" ;;
  location) [[ "$(http_code localhost:8080/hello)" == 200 ]] ;;
  *) exit 1 ;;
esac
