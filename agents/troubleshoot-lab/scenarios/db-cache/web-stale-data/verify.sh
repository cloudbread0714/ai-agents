#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
name="check-$(rand_token)"
[[ "$(http_code -X POST -H 'Content-Type: application/json' -d "{\"name\":\"$name\"}" localhost:8080/api/items)" == 201 ]]
curl -s localhost:8080/api/items | grep -q "$name"
