#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}

running() { dk inspect -f '{{.State.Running}}' lab-web 2>/dev/null; }
case $step in
  run) [[ "$(running)" == true ]] ;;
  curl | ps) answer_is "$step" "$answer" ;;
  stop) [[ "$(running)" == false ]] ;;
  *) exit 1 ;;
esac
