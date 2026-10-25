#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# The DROP rule lives in nginx's network namespace; a new container gets a clean one.
dc up -d --force-recreate nginx >/dev/null 2>&1 || true
"$LAB_ROOT/environment/restore.sh" compose
