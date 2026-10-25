#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
restarts() { dk inspect -f '{{.RestartCount}}' troubleshoot-lab-api-1; }
[[ "$(http_code localhost:8080/api/items)" == 200 ]]
before=$(restarts)
end=$((SECONDS + 15))
while ((SECONDS < end)); do
  http_burst 20 4 http://localhost:8080/api/items >/dev/null
done
sleep 2
[[ "$(restarts)" == "$before" ]]
[[ "$(dk inspect -f '{{.State.Running}}' troubleshoot-lab-api-1)" == true ]]
