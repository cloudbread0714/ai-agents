#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
# 미션 준비. answer 단계의 기대값은 answer_set 으로 저장하세요(무작위 값은 rand_token).
need_kind   # Docker·웹 미션이면 need_docker
token=$(rand_token)
answer_set look "$token"
