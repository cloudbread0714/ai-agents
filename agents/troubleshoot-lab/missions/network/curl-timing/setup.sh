#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
dk rm -f lab-hang >/dev/null 2>&1 || true
answer_set phases total
answer_set refused 7
answer_set timeout 28
# accepts TCP connections and never answers
dk run -d --name lab-hang -p 127.0.0.1:8099:9000 busybox:1.36 \
  sh -c 'while true; do nc -l -p 9000 >/dev/null; done' >/dev/null
