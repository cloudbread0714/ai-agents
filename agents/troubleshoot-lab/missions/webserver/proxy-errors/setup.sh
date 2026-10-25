#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set bad-gateway 502
answer_set timeout 504
answer_set log 111
dk rm -f lab-hang >/dev/null 2>&1 || true
dk run -d --name lab-hang --network troubleshoot-lab_lab busybox:1.36 \
  sh -c 'while true; do nc -l -p 9000 >/dev/null; done' >/dev/null
nginx_location quiz-proxy <<'EOF'
location = /quiz-502 {
    proxy_pass http://api:8001/;
}
location = /quiz-504 {
    proxy_pass http://lab-hang:9000/;
    proxy_read_timeout 2s;
}
EOF
wait_http localhost:8080/quiz-502 502 30
