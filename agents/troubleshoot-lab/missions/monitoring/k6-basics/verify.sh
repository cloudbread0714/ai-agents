#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}
case $step in
  rps | p95 | errors) answer_is "$step" "$answer" ;;
  *) exit 1 ;;
esac
