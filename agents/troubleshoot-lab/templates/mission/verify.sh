#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
# verify.sh <step-id> [answer] — 그 단계를 통과하면 0. 실패 이유를 출력하지 마세요.
step=${1:?step id}
answer=${2:-}
case $step in
  look) answer_is look "$answer" ;;
  *) exit 1 ;;
esac
