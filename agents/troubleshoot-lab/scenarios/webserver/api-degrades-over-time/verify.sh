#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
close_wait() {
  dc exec -T api sh -c 'cat /proc/net/tcp /proc/net/tcp6 2>/dev/null' | awk '$4 == "08"' | wc -l | tr -d ' '
}
[[ "$(http_code localhost:8080/api/upstream)" == 200 ]]
end=$((SECONDS + 10))
while ((SECONDS < end)); do
  http_burst_ok 50 5 http://localhost:8080/api/upstream
done
(($(close_wait) < 5))
