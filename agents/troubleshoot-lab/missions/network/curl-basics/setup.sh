#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
t1=$(rand_token)
answer_set body "$t1"
answer_set status 404
answer_set verbose GET
nginx_location quiz-curl <<EOF
location = /quiz {
    default_type text/plain;
    return 200 "hello from nginx, code=lab-$t1";
}
EOF
wait_http localhost:8080/quiz 200 30
