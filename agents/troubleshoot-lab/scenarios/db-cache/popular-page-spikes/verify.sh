#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
wait_http http://localhost:8080/api/popular 200 30
for i in 1 2 3; do
  http_burst_ok 60 30 http://localhost:8080/api/popular --max-time 10
  sleep 2.2
done
(($(dc logs --since 8s api 2>/dev/null | grep -c 'popular rebuild') <= 3))
