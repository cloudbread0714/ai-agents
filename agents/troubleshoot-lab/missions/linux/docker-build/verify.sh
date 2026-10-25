#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}

case $step in
  build)
    [[ "$(dk image inspect -f '{{index .Config.Labels "lab.build"}}' lab-hello:practice 2>/dev/null)" == "$(answer_get build-label)" ]]
    ;;
  run)
    code=$(dk run --rm lab-hello:practice 2>/dev/null | sed -n 's/.*lab-//p')
    answer_set run "$code"
    answer_is run "$answer"
    ;;
  *) exit 1 ;;
esac
