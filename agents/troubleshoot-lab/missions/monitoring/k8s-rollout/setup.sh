#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
k -n lab rollout status deploy/api --timeout=120s >/dev/null
rev=$(k -n lab get deploy api -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}')
answer_set history "$((rev + 1))"
