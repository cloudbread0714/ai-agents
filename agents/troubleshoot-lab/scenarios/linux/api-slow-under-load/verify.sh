#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
for _ in 1 2 3 4 5; do
  out=$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 5 localhost:8080/api/report || true)
  [[ ${out%% *} == 200 ]]
  awk -v t="${out#* }" 'BEGIN { exit !(t < 0.1) }'
done
