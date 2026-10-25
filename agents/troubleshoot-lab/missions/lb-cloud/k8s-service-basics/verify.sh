#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}

case $step in
  selector | endpoints) answer_is "$step" "$answer" ;;
  connect)
    addrs=$(k -n lab get endpointslices -l kubernetes.io/service-name=quiz-svc -o jsonpath='{.items[*].endpoints[*].addresses[*]}')
    [[ -n $addrs ]]
    ;;
  *) exit 1 ;;
esac
