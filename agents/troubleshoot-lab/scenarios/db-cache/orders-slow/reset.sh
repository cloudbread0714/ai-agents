#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
touch "$LAB_STATE/dirty-compose"
"$LAB_ROOT/environment/restore.sh" compose
