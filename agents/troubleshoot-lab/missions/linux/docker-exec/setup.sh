#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
dk rm -f lab-box >/dev/null 2>&1 || true
t1=$(rand_token)
t2=$(rand_token)
answer_set env "$t1"
answer_set file "$t2"
dk run -d --name lab-box -e "LAB_WORD=$t1" busybox:1.36 sleep 3600 >/dev/null
dk exec lab-box sh -c "echo $t2 > /tmp/note.txt"
