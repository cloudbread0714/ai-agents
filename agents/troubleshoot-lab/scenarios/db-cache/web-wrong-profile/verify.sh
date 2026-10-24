#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
for _ in 1 2; do
  who="u$(rand_token)"
  curl -s --cookie "user=$who" localhost:8080/api/profile | grep -q "\"$who\""
done
