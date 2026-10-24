#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set listen LISTEN
answer_set close-wait 8000
answer_set time-wait TIME-WAIT
dk rm -f lab-closewait >/dev/null 2>&1 || true
# ext answers and closes; this side keeps fd 3 open -> CLOSE-WAIT in the api namespace
dk run -d --name lab-closewait --network container:troubleshoot-lab-api-1 lab-toolbox:dev bash -c \
  'exec 3<>/dev/tcp/ext/8000; printf "GET /ext/ping HTTP/1.1\r\nHost: ext\r\nConnection: close\r\n\r\n" >&3; sleep 3600' >/dev/null
cw() { tb troubleshoot-lab-api-1 "ss -Htan state close-wait" | grep -q :8000; }
wait_until 20 cw
