#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
ip=$(tb troubleshoot-lab-api-1 "dig +short redis" | head -1)
answer_set lookup "$ip"
answer_set nslookup "$(tb troubleshoot-lab-api-1 "dig +short postgres" | head -1)"
answer_set resolver 127.0.0.11
status=$(tb troubleshoot-lab-api-1 "dig no-such-service.invalid" | sed -n 's/.*status: \([A-Z]*\),.*/\1/p' | head -1)
answer_set missing "${status:-NXDOMAIN}"
