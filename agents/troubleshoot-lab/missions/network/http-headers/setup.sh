#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
t1=$(rand_token)
t2=$(rand_token)
answer_set response "$t1"
answer_set request "$t2"
answer_set type text/plain
nginx_location quiz-headers <<EOF
location = /quiz-headers {
    add_header X-Lab-Quiz "$t1" always;
    default_type text/plain;
    return 200 "look at the headers";
}
location = /quiz-echo {
    default_type text/plain;
    if (\$http_x_lab_ask != "hello") {
        return 400 "send the header X-Lab-Ask: hello";
    }
    return 200 "code=$t2";
}
EOF
wait_http localhost:8080/quiz-headers 200 30
