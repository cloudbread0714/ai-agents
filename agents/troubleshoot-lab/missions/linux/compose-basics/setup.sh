#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
t1=$(rand_token)
answer_set ps 4
answer_set logs "$t1"
answer_set nginx-started "$(dk inspect -f '{{.State.StartedAt}}' troubleshoot-lab-nginx-1)"
wait_http "http://localhost:8080/api/items?mark=$t1" 200 30
