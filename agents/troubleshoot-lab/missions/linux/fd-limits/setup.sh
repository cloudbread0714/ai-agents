#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
soft=$(tb troubleshoot-lab-api-1 "prlimit --pid 1 --nofile -o SOFT --noheadings" | tr -d ' ')
answer_set limit "$soft"
answer_set fds socket
answer_set lsof IPv4
