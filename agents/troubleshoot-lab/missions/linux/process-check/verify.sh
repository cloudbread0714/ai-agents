#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}
case $step in
  load | top-cpu) answer_is "$step" "$answer" ;;
  kill) ! tb troubleshoot-lab-api-1 "pgrep -f /tmp/lab" >/dev/null ;;
  *) exit 1 ;;
esac
