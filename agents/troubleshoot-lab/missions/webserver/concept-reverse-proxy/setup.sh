#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set upstream 8000
answer_set timeout 3s
answer_set rewrite /version
answer_set server nginx
