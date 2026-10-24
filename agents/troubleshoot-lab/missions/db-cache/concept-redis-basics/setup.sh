#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set miss MISS
answer_set hit HIT
answer_set ttl 30000
answer_set speed HIT
answer_set ratio keyspace_misses
tb troubleshoot-lab-redis-1 "redis-cli DEL catalog:7 catalog:8" >/dev/null
