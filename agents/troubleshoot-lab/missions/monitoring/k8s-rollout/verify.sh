#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
step=${1:?step id}
answer=${2:-}

version() { k -n lab get deploy api -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="APP_VERSION")].value}'; }
done_rolling() { k -n lab rollout status deploy/api --timeout=10s >/dev/null; }
case $step in
  update) [[ "$(version)" == 2.0.0 ]] && done_rolling ;;
  history) answer_is history "$answer" ;;
  undo) [[ "$(version)" == 1.0.0 ]] && done_rolling ;;
  *) exit 1 ;;
esac
