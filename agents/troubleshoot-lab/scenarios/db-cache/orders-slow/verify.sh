#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
[[ "$(http_code 'localhost:8080/api/orders?customer=42')" == 200 ]]
! dc exec -T postgres psql -U lab -d lab -tAc 'EXPLAIN SELECT count(*) FROM orders WHERE customer_id = 42' |
  grep -q 'Seq Scan on orders'
