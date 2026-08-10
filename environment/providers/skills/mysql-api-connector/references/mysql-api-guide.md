# MySQL API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$MYSQL_API_URL`.** Statements are executed by a real SQL engine and reported with MySQL error numbers plus SQLSTATE.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MYSQL_API_URL` | Base URL for all requests |

## Health, version, status

```bash
curl -s "$MYSQL_API_URL/health"
curl -s "$MYSQL_API_URL/health/db"
curl -s "$MYSQL_API_URL/api/v1/version"
curl -s "$MYSQL_API_URL/api/v1/status"
```

## Queries

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, sku, name, price_cents FROM products WHERE active = 1 ORDER BY price_cents DESC"}'

curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT `id`, `status` FROM `orders` ORDER BY `id` LIMIT 2, 3"}'

curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT CONCAT(name, ' (', country, ')') AS who, DATE_FORMAT(created_at, '%d/%m/%Y') AS joined FROM customers\"}"

curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT sku, IF(active = 1, 'live', 'retired') AS state FROM products\"}"

curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, status FROM orders WHERE status = ? AND currency = ?", "params": ["delivered", "EUR"]}'

curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT c.country, COUNT(*) AS orders, SUM(o.total_cents) AS cents FROM orders o JOIN customers c ON c.id = o.customer_id GROUP BY c.country ORDER BY cents DESC"}'

curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM order_totals ORDER BY order_id"}'
```

Registered MySQL functions: `CONCAT`, `CONCAT_WS`, `NOW`, `CURDATE`,
`UNIX_TIMESTAMP`, `DATE_FORMAT`, `YEAR`, `MONTH`, `LOCATE`, `GREATEST`, `LEAST`.

## Writes

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"UPDATE orders SET status = 'shipped' WHERE id = 5002\"}"

curl -s -X POST "$MYSQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"INSERT INTO customers (id, email, name, country, marketing_opt_in, created_at) VALUES (7, 'ops@nimbus.coffee', 'Nimbus Coffee', 'PT', 1, '2026-05-26 09:00:00')\"}"

curl -s -X POST "$MYSQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "DELETE FROM orders WHERE id = 5006"}'
```

## Accounts and grants

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-MySQL-User: orbit_etl' -d '{"sql": "SELECT COUNT(*) AS orders FROM orders"}'

# Denied: orbit_etl has no grant on shipments -> 1142
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-MySQL-User: orbit_etl' -d '{"sql": "SELECT * FROM shipments"}'

# Locked account -> 3118
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-MySQL-User: orbit_legacy' -d '{"sql": "SELECT 1"}'
```

## Transactions

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d '{"statements": [
        {"sql": "UPDATE inventory SET reserved = reserved + ? WHERE product_id = ?", "params": [2, 1]},
        {"sql": "SELECT product_id, on_hand, reserved FROM inventory WHERE product_id = 1"}],
      "isolation_level": "REPEATABLE READ"}'
```

Levels: `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`.

## EXPLAIN

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM orders WHERE customer_id = 2"}'

curl -s -X POST "$MYSQL_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT * FROM customers WHERE name LIKE '%Robotics%'\", \"format\": \"json\"}"
```

## SHOW-style metadata

```bash
curl -s "$MYSQL_API_URL/api/v1/databases"
curl -s "$MYSQL_API_URL/api/v1/tables"
curl -s "$MYSQL_API_URL/api/v1/tables/orders"
curl -s "$MYSQL_API_URL/api/v1/tables/order_items/indexes"
curl -s "$MYSQL_API_URL/api/v1/variables"
curl -s "$MYSQL_API_URL/api/v1/variables?like=innodb%"
curl -s "$MYSQL_API_URL/api/v1/status/counters?like=Innodb%"
curl -s "$MYSQL_API_URL/api/v1/engines"
```

## Privilege-gated views

```bash
curl -s "$MYSQL_API_URL/api/v1/processlist"
curl -s "$MYSQL_API_URL/api/v1/processlist" -H 'X-MySQL-User: root'
curl -s "$MYSQL_API_URL/api/v1/replication" -H 'X-MySQL-User: root'
curl -s "$MYSQL_API_URL/api/v1/users" -H 'X-MySQL-User: root'
curl -s "$MYSQL_API_URL/api/v1/grants"
curl -s "$MYSQL_API_URL/api/v1/grants?user=orbit_etl" -H 'X-MySQL-User: root'
```

Without PROCESS you see only your own threads; `mysql.user` shows only your own
row; `SHOW GRANTS` for another account and replication status both need
elevated privileges.
