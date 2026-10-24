#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
t1=$(rand_token)
mb=$((3 + 16#${t1:0:1} % 5))
answer_set free available
answer_set vmstat id
answer_set df 32M
answer_set du "big-$t1.bin"
dk exec troubleshoot-lab-api-1 sh -c "head -c ${mb}M /dev/zero > /var/log/app/big-$t1.bin"
