## 원인

`orders(customer_id)` 인덱스(`orders_customer_idx`)가 삭제됐어요. 그래서 고객 한 명의 주문 40건을 찾을 때마다 PostgreSQL이 20만 행 전체를 순차 스캔(Seq Scan)했어요. 오류 없이 느려지기만 해서 알아채기 어려운 장애예요.

## 해결

1. `curl -w` 로 `/api/orders` 만 느린 것을 확인해요.
2. psql에서 같은 쿼리를 `\timing` 으로 재고, `EXPLAIN ANALYZE` 에서 `Seq Scan on orders` 와 `Rows Removed by Filter` 를 봐요.
3. `\d orders` 에서 `customer_id` 인덱스가 없는 것을 확인해요.
4. `CREATE INDEX orders_customer_idx ON orders (customer_id);` 를 실행하고 `EXPLAIN` 이 Index Scan(또는 Bitmap Index Scan)으로 바뀐 것을 확인해요.

## 배운 점

"오류 없이 느리다"면 DB 쿼리 계획부터 보세요. `EXPLAIN ANALYZE` 는 DB가 실제로 몇 행을 읽고 버렸는지 알려 줘요. 운영에서는 슬로 쿼리 로그(`log_min_duration_statement`)나 `pg_stat_statements` 로 느린 쿼리를 먼저 찾아요.
