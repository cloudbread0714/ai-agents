#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set rps rps
answer_set p95 95
answer_set errors 100.00%
nginx_location quiz-k6 <<'EOF'
location = /quiz-k6-error {
    return 503;
}
EOF
wait_http localhost:8080/quiz-k6-error 503 30
