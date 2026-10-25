#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}
case $step in
  lookup | nslookup | resolver | missing) answer_is "$step" "$answer" ;;
  *) exit 1 ;;
esac
