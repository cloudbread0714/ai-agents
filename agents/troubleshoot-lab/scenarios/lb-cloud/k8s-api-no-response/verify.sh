#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_kind
addrs=$(k -n lab get endpointslices -l kubernetes.io/service-name=api -o jsonpath='{.items[*].endpoints[*].addresses[*]}')
[[ -n $addrs ]]
[[ "$(http_code localhost:8081/api/items)" == 200 ]]
