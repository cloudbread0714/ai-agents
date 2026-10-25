#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
post() { http_code -X POST -H 'Content-Type: application/json' -d '{"name":"verify"}' http://localhost:8080/api/items; }
[[ "$(post)" == 201 ]]
# Normal traffic must not refill the log volume (cleaning it while the flood continues fails here).
http_burst 150 5 http://localhost:8080/api/items >/dev/null
[[ "$(post)" == 201 ]]
used=$(dc exec -T api df -P /var/log/app | awk 'NR == 2 { gsub("%", "", $5); print $5 }')
((used < 80))
