#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
dk rm -f lab-web >/dev/null 2>&1 || true
answer_set curl "Welcome to nginx!"
answer_set ps "8090->80"
