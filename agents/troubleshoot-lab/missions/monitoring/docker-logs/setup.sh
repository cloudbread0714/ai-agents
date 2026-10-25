#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
dk rm -f lab-logger >/dev/null 2>&1 || true
t1=$(rand_token)
t2=$(rand_token)
answer_set logs "$t1"
answer_set stderr "$t2"
dk run -d --name lab-logger busybox:1.36 sh -c "i=0; while true; do i=\$((i+1)); echo \"[info] request \$i ok\"; if [ \$i -eq 3 ]; then echo \"[error] request_id=$t1 failed\"; echo \"[warn] retry code=$t2\" >&2; fi; sleep 1; done" >/dev/null
logger_ready() { dk logs lab-logger 2>&1 | grep -q 'warn'; }
wait_until 20 logger_ready
