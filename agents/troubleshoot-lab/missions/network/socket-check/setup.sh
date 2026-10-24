#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set listen 8000
answer_set reach succeeded
answer_set closed refused
