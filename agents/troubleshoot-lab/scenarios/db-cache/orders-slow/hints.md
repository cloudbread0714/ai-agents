## 힌트 1

느린 API가 어떤 쿼리를 쓰는지 생각해 보고, DB에서 그 쿼리를 직접 실행해 시간을 재 보세요 (이 쉘에서 처음이면 먼저 `eval "$(agents/troubleshoot-lab/bin/lab env)"`).

```
docker compose exec -T postgres psql -U lab -d lab -c '\timing on' -c 'SELECT count(*) FROM orders WHERE customer_id = 42'
```

## 힌트 2

쿼리 계획을 보면 DB가 행을 어떻게 찾는지 알 수 있어요. 20만 행 중 40행을 찾으려고 무엇을 하고 있나요?

```
docker compose exec -T postgres psql -U lab -d lab -c 'EXPLAIN ANALYZE SELECT count(*) FROM orders WHERE customer_id = 42'
```

## 힌트 3

`orders.customer_id` 의 인덱스가 사라져 매번 테이블 전체를 읽어요(Seq Scan). `\d orders` 로 인덱스 목록을 확인하고 `CREATE INDEX orders_customer_idx ON orders (customer_id);` 로 다시 만드세요.
