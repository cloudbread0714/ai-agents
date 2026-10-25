#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
ip=$(tb troubleshoot-lab-api-1 "dig +short nginx" | head -1)
answer_set dns "$ip"
answer_set tcp 8080
answer_set http HTTP/1.1
answer_set ttfb server
answer_set proxy 8000
answer_set layer 7
