#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
t1=$(rand_token)
answer_set get "$t1"
answer_set stats keyspace_misses
tb troubleshoot-lab-redis-1 "redis-cli DEL lab:mine >/dev/null; redis-cli SET lab:quiz $t1 EX 3600" >/dev/null
