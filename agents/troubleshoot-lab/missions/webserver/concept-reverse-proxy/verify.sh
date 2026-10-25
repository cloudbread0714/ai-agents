#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}
case $step in
  upstream | timeout | rewrite | server) answer_is "$step" "$answer" ;;
  location) wait_http localhost:8080/hello 200 10 ;;  # reload is graceful; give it a moment
  *) exit 1 ;;
esac
