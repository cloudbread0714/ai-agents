#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# 200 and fast: making nginx wait longer for a 5 s answer does not count as fixed.
for _ in 1 2 3 4 5; do
  out=$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 5 localhost:8080/api/report || true)
  [[ ${out%% *} == 200 ]]
  awk -v t="${out#* }" 'BEGIN { exit !(t < 1.0) }'
done
