#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set max 100
answer_set activity idle
answer_set explain orders_customer_idx
