#!/usr/bin/env bash
set -euo pipefail
source "$LAB_ROOT/lib/common.sh"
need_docker
# Live DB state changes: the next restore recreates postgres with a fresh volume.
touch "$LAB_STATE/dirty-compose"
dc exec -T postgres psql -U lab -d lab -qc 'DROP INDEX IF EXISTS orders_customer_idx'
seq_scan() {
  dc exec -T postgres psql -U lab -d lab -tAc 'EXPLAIN SELECT count(*) FROM orders WHERE customer_id = 42' |
    grep -q 'Seq Scan on orders'
}
wait_until 30 seq_scan
