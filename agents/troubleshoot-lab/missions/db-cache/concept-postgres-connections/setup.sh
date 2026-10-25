#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set max 100
answer_set process lab
answer_set states idle
answer_set pool 30
