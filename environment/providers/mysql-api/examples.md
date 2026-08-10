# MySQL Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$MYSQL_API_URL`; responses are verbatim (long arrays elided with
`…`).

The `X-MySQL-User` header selects the account; without it, statements run as
`orbit_shop`.

## Health and version

```bash
curl -s "$MYSQL_API_URL/health/db"
curl -s "$MYSQL_API_URL/api/v1/version"
```
```json
{"status": "ok", "engine": "mysql", "version": "8.0.36", "database": "orbit_shop",
 "threads_connected": 34, "replicas_healthy": 1, "replicas_total": 2,
 "latency_ms": 0.198}
{"version": "8.0.36", "version_comment": "MySQL Community Server - GPL",
 "version_compile_os": "Linux", "version_compile_machine": "x86_64"}
```

One replica is seeded broken, which is why `replicas_healthy` is 1 of 2.

## MySQL syntax that just works

Backtick identifiers and `LIMIT offset, count` are accepted as written:

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT `id`, `status`, `total_cents` FROM `orders` ORDER BY `id` LIMIT 2, 3"}'
```
```json
{"command": "SELECT",
 "columns": [{"name": "id", "type": "BIGINT"}, {"name": "status", "type": "VARCHAR"},
             {"name": "total_cents", "type": "BIGINT"}],
 "rows": [{"id": 5003, "status": "delivered", "total_cents": 105780},
          {"id": 5004, "status": "delivered", "total_cents": 36777},
          {"id": 5005, "status": "processing", "total_cents": 419760}],
 "row_count": 3, "affected_rows": 0, "insert_id": 0, "warnings": 0,
 "truncated": false, "duration_ms": 0.058, "user": "orbit_shop"}
```

`CONCAT` and `DATE_FORMAT` are registered as real SQL functions, with MySQL's
format tokens:

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT CONCAT(name, ' (', country, ')') AS who, DATE_FORMAT(created_at, '%d/%m/%Y') AS joined FROM customers ORDER BY id\"}"
```
```json
{"rows": [{"who": "Aurora Bistro LLC (PT)", "joined": "04/03/2025"},
          {"who": "Helix Robotics Inc (DE)", "joined": "12/09/2024"},
          {"who": "Lumen Design Studio (PT)", "joined": "18/06/2025"}, "…"], "…": "…"}
```

`IF()`, `IFNULL()` and `GREATEST()` all work:

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT sku, IF(active = 1, 'live', 'retired') AS state FROM products ORDER BY id\"}"

curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT id, IFNULL(payment_reference, 'unpaid') AS payment, GREATEST(shipping_cents, tax_cents) AS larger FROM orders ORDER BY id LIMIT 4\"}"
```

## Joins and aggregates

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT c.country, COUNT(*) AS orders, SUM(o.total_cents) AS cents FROM orders o JOIN customers c ON c.id = o.customer_id GROUP BY c.country ORDER BY cents DESC"}'
```
```json
{"rows": [{"country": "DE", "orders": 2, "cents": 1123512},
          {"country": "GB", "orders": 1, "cents": 419760},
          {"country": "PT", "orders": 3, "cents": 199260},
          {"country": "US", "orders": 2, "cents": 155700}],
 "row_count": 4, "…": "…"}
```

```bash
# Stock at or below the reorder point, excluding digital products
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT p.sku, p.name, v.on_hand, v.reserved, v.reorder_point FROM inventory v JOIN products p ON p.id = v.product_id WHERE v.on_hand - v.reserved <= v.reorder_point AND v.warehouse <> 'DIGITAL' ORDER BY v.on_hand\"}"
```
```json
{"rows": [{"sku": "ORB-SNS-V", "name": "Vibration sensor pack (10)",
           "on_hand": 12, "reserved": 12, "reorder_point": 30}],
 "row_count": 1, "…": "…"}
```

## Writes and MySQL errors

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"UPDATE orders SET status = 'shipped' WHERE id = 5002\"}"
```
```json
{"command": "UPDATE", "columns": [], "rows": [], "row_count": 0,
 "affected_rows": 1, "insert_id": 0, "warnings": 0, "truncated": false,
 "duration_ms": 0.061, "user": "orbit_shop"}
```

Failures carry the vendor error number, the symbolic name and SQLSTATE:

```json
{"error": "Duplicate entry for key 'products.sku'", "errno": 1062,
 "sqlstate": "23000", "error_name": "ER_DUP_ENTRY",
 "message": "Duplicate entry for key 'products.sku'"}

{"error": "Cannot add or update a child row: a foreign key constraint fails",
 "errno": 1452, "sqlstate": "23000", "error_name": "ER_NO_REFERENCED_ROW_2"}

{"error": "Table 'orbit_shop.invoices' doesn't exist", "errno": 1146,
 "sqlstate": "42S02", "error_name": "ER_NO_SUCH_TABLE"}

{"error": "Unknown column 'nonexistent' in 'field list'", "errno": 1054,
 "sqlstate": "42S22", "error_name": "ER_BAD_FIELD_ERROR"}
```

`DELETE FROM orders WHERE id = 5006` cascades to `order_items`, because the FK
is declared `ON DELETE CASCADE` and the engine enforces it.

## Accounts and grants

```bash
# orbit_etl holds table grants on customers, orders, order_items and products
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-MySQL-User: orbit_etl' -d '{"sql": "SELECT COUNT(*) AS orders FROM orders"}'
```
```json
{"rows": [{"orders": 8}], "row_count": 1, "user": "orbit_etl", "…": "…"}
```

Any table outside that list is denied — MySQL's table-grant model, not a
database-wide one:

```json
{"error": "SELECT command denied to user 'orbit_etl'@'10.42.0.44' for table 'shipments'",
 "errno": 1142, "sqlstate": "42000", "error_name": "ER_TABLEACCESS_DENIED_ERROR",
 "table": "shipments", "database": "orbit_shop"}
```

The locked account fails before anything runs:

```json
{"error": "Access denied for user 'orbit_legacy'@'%'. Account is locked.",
 "errno": 3118, "sqlstate": "HY000", "error_name": "ER_ACCOUNT_HAS_BEEN_LOCKED"}
```

## Transactions

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d '{"statements": [
        {"sql": "UPDATE inventory SET reserved = reserved + ? WHERE product_id = ?", "params": [2, 1]},
        {"sql": "INSERT INTO order_items (id, order_id, product_id, quantity, unit_price_cents, discount_cents) VALUES (13, 5008, 1, 2, 49900, 0)"},
        {"sql": "SELECT product_id, on_hand, reserved FROM inventory WHERE product_id = 1"}],
      "isolation_level": "REPEATABLE READ"}'
```
```json
{"results": [{"command": "UPDATE", "affected_rows": 1, "statement_index": 0, "…": "…"},
             {"command": "INSERT", "affected_rows": 1, "insert_id": 12, "statement_index": 1, "…": "…"},
             {"command": "SELECT", "rows": [{"product_id": 1, "on_hand": 142, "reserved": 20}],
              "statement_index": 2, "…": "…"}],
 "statement_count": 3, "isolation_level": "REPEATABLE READ",
 "rolled_back": false, "committed": true}
```

A failure rolls the batch back — the preceding `UPDATE inventory SET on_hand = 999`
leaves no trace, and a follow-up query still reports `310`:

```json
{"error": "Duplicate entry for key 'order_items.order_id_product_id'",
 "errno": 1062, "sqlstate": "23000", "error_name": "ER_DUP_ENTRY",
 "statement_index": 1, "rolled_back": true}
```

An unrecognised isolation level is rejected before anything runs (1231).

## EXPLAIN

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM orders WHERE customer_id = 2"}'
```
```json
{"format": "traditional",
 "rows": [{"id": 1, "select_type": "SIMPLE", "table": "orders", "partitions": null,
           "type": "ref", "possible_keys": "idx_orders_customer",
           "key": "idx_orders_customer", "key_len": 4, "ref": "const",
           "rows": 1, "filtered": 100.0, "Extra": "Using index condition"}]}
```

```bash
curl -s -X POST "$MYSQL_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT * FROM customers WHERE name LIKE '%Robotics%'\", \"format\": \"json\"}"
```
```json
{"format": "json", "EXPLAIN": {"query_block": {
  "select_id": 1, "cost_info": {"query_cost": 120.0},
  "table": [{"table_name": "customers", "access_type": "ALL", "key": null,
             "rows_examined_per_scan": 100, "filtered": 100.0,
             "possible_keys": null}]}}}
```

A predicate the indexes cannot serve reports `access_type: "ALL"`.

## SHOW-style metadata

```bash
curl -s "$MYSQL_API_URL/api/v1/tables/orders"
```
```json
{"TABLE_SCHEMA": "orbit_shop", "TABLE_NAME": "orders", "TABLE_TYPE": "BASE TABLE",
 "columns": [{"Field": "id", "Type": "int", "Null": "NO", "Key": "PRI",
              "Default": null, "Extra": ""},
             {"Field": "customer_id", "Type": "int", "Null": "NO", "Key": "MUL", "…": "…"},
             {"Field": "currency", "Type": "char(3)", "Null": "NO", "Key": "", "…": "…"}],
 "foreign_keys": [{"column": "customer_id", "referenced_table": "customers",
                   "referenced_column": "id", "on_delete": "NO ACTION"}],
 "privileges": ["DELETE", "INSERT", "SELECT", "UPDATE"],
 "ENGINE": "InnoDB", "TABLE_ROWS": 8, "DATA_LENGTH": 1073741824,
 "INDEX_LENGTH": 402653184, "AUTO_INCREMENT": 5009,
 "TABLE_COLLATION": "utf8mb4_0900_ai_ci"}
```

```bash
curl -s "$MYSQL_API_URL/api/v1/tables/order_items/indexes"
curl -s "$MYSQL_API_URL/api/v1/variables?like=innodb%"
curl -s "$MYSQL_API_URL/api/v1/status/counters?like=Innodb%"
curl -s "$MYSQL_API_URL/api/v1/engines"
curl -s "$MYSQL_API_URL/api/v1/databases"
```
```json
{"variables": [{"Variable_name": "innodb_buffer_pool_size", "Value": "8589934592"},
               {"Variable_name": "innodb_flush_log_at_trx_commit", "Value": "1"},
               {"Variable_name": "innodb_log_file_size", "Value": "536870912"}],
 "count": 3}
```

## Privilege-gated views

`SHOW PROCESSLIST` shows only your own threads without the PROCESS privilege:

```bash
curl -s "$MYSQL_API_URL/api/v1/processlist"
```
```json
{"processlist": [{"id": 104412, "user": "orbit_shop", "command": "Query",
                  "info": "SELECT * FROM orders WHERE customer_id = ? ORDER BY placed_at DESC"},
                 {"id": 104413, "user": "orbit_shop", "command": "Sleep", "time": 12}],
 "count": 2, "user": "orbit_shop", "full_visibility": false,
 "note": "only your own threads are shown; the PROCESS privilege is required to see all connections"}
```

With `X-MySQL-User: root` all six threads appear, including the ETL query and the
binlog dump.

`mysql.user` behaves the same way — your own row unless you are root:

```json
{"users": [{"user": "orbit_shop", "host": "%", "plugin": "caching_sha2_password",
            "account_locked": 0, "max_connections": 150, "ssl_type": "ANY",
            "grants": "SELECT, INSERT, UPDATE, DELETE ON orbit_shop.*"}],
 "count": 1}
```

`SHOW GRANTS` for another account requires SUPER (1227), and replication status
requires REPLICATION CLIENT:

```bash
curl -s "$MYSQL_API_URL/api/v1/replication" -H 'X-MySQL-User: root'
```
```json
{"source_status": {"File": "binlog.000412", "Position": 884120993,
                   "Executed_Gtid_Set": "9f3c1a7e-…:1-88412003"},
 "replicas": [{"Server_id": 2, "Host": "10.42.0.22", "Replica_IO_Running": "Yes",
               "Replica_SQL_Running": "Yes", "Seconds_Behind_Source": 0},
              {"Server_id": 3, "Host": "10.42.0.23", "Replica_IO_Running": "Yes",
               "Replica_SQL_Running": "No", "Seconds_Behind_Source": 1842,
               "Last_SQL_Error": "Error 'Duplicate entry 5001 for key orders.PRIMARY' on query. Default database: 'orbit_shop'"}],
 "replica_count": 2}
```
