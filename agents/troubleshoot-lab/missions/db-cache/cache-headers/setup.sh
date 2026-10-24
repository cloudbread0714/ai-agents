#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
t1=$(rand_token)
age=$((100 + 16#${t1:0:2}))
answer_set maxage "$age"
answer_set hit HIT
nginx_location quiz-cache <<EOF
location = /quiz-cache {
    rewrite ^ /items break;
    proxy_pass http://\$api_host;
    proxy_cache lab;
    proxy_cache_valid 200 1m;
    proxy_ignore_headers Cache-Control;
    proxy_hide_header Cache-Control;
    add_header Cache-Control "public, max-age=$age" always;
    add_header X-Cache-Status \$upstream_cache_status always;
}
EOF
wait_http localhost:8080/quiz-cache 200 30
