#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}
case $step in
  dns | tcp | http | ttfb | proxy | layer) answer_is "$step" "$answer" ;;
  *) exit 1 ;;
esac
