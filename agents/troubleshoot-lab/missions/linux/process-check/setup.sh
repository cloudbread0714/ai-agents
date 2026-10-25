#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
t1=$(rand_token)
answer_set load 3
answer_set top-cpu "lab$t1"
# a CPU hog under a random name, inside the api container
dk exec -d troubleshoot-lab-api-1 sh -c "cp /usr/bin/yes /tmp/lab$t1 && exec /tmp/lab$t1 >/dev/null"
running() { tb troubleshoot-lab-api-1 "pgrep -f ^/tmp/lab$t1" >/dev/null; }
wait_until 15 running
