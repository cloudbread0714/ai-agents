#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
# 시나리오 전용 정리(필요하면) 후 공통 복원으로 끝내세요. 몇 번을 실행해도 결과가 같아야 해요.
"$LAB_ROOT/environment/restore.sh" compose   # Kubernetes 시나리오면 kind
