#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
answer_set listen 8000
answer_set reach succeeded
answer_set closed refused
answer_set summary estab
answer_set route "$(tb troubleshoot-lab-api-1 "ip route" | awk '$1 == "default" { print $3; exit }')"
