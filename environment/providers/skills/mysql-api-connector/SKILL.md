---
name: mysql-api-connector
description: >
  MySQL API (Mock) mock HTTP API. Base URL is provided via the
  `MYSQL_API_URL` environment variable. 19 endpoint(s) across GET, POST.
  Runs real SQL and reports MySQL error numbers.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# MySQL API (Mock)

Mock HTTP API in front of a MySQL 8 database (`orbit_shop`). **All requests go
to the base URL in `$MYSQL_API_URL`.** Statements are executed by a **real SQL
engine**, so joins, aggregates, subqueries, constraints and query plans behave
the way a database behaves. Seed data is deterministic.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MYSQL_API_URL` | Base URL for all requests (e.g. `http://mysql-api:8110`) |

## Accounts

`X-MySQL-User` (or a bearer token) selects the account; absent or unknown falls
back to `orbit_shop`.

| Account | Host | Privileges |
|---------|------|-----------|
| `root` | `localhost` | ALL, including PROCESS, SUPER, REPLICATION CLIENT |
| `orbit_shop` | `%` | SELECT, INSERT, UPDATE, DELETE (default) |
| `orbit_report` | `10.42.%` | SELECT |
| `orbit_etl` | `10.42.0.44` | SELECT on `customers`, `orders`, `order_items`, `products` only |
| `orbit_legacy` | `%` | locked — every statement returns 3118 |

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/query` | Read-only statement |
| POST | `/api/v1/execute` | Statement that may write |
| POST | `/api/v1/transaction` | Batch with an `isolation_level`, atomic |
| POST | `/api/v1/explain` | `EXPLAIN`, `format` traditional or json |
| GET | `/api/v1/databases` | `SHOW DATABASES` |
| GET | `/api/v1/tables` | Tables with engine, rows, lengths, AUTO_INCREMENT |
| GET | `/api/v1/tables/{name}` | `DESCRIBE` + create statement + foreign keys |
| GET | `/api/v1/tables/{name}/indexes` | `SHOW INDEX` |
| GET | `/api/v1/variables` | `SHOW VARIABLES` (`?like=innodb%`) |
| GET | `/api/v1/status/counters` | `SHOW STATUS` (`?like=`) |
| GET | `/api/v1/processlist` | `SHOW PROCESSLIST` (PROCESS-gated) |
| GET | `/api/v1/engines` | `SHOW ENGINES` |
| GET | `/api/v1/replication` | Binary log + replica status (REPLICATION CLIENT) |
| GET | `/api/v1/users` | `mysql.user` (own row unless root) |
| GET | `/api/v1/grants` | `SHOW GRANTS` (`?user=`, SUPER for others) |
| GET | `/api/v1/status` · `/api/v1/version` · `/health/db` | Server facts |

## Schema — `orbit_shop`

`customers` (6), `products` (8), `inventory` (8), `orders` (8), `order_items`
(12), `shipments` (3), plus the view `order_totals`.

Constraints worth knowing: `customers.email`, `products.sku` and
`shipments.tracking_number` are UNIQUE, `order_items` is UNIQUE on
`(order_id, product_id)` and cascades from `orders`, and `inventory.on_hand` has
`CHECK (on_hand >= 0)`.

## Dialect notes

Backtick identifiers and `LIMIT offset, count` work as written. `CONCAT`,
`CONCAT_WS`, `NOW`, `CURDATE`, `UNIX_TIMESTAMP`, `DATE_FORMAT`, `YEAR`, `MONTH`,
`LOCATE`, `GREATEST` and `LEAST` are registered as real SQL functions. `IF()` and
`<=>` are rewritten. Sessions do not persist between requests — use
`/api/v1/transaction` for a unit of work.

## Usage

```bash
# Query
curl -s -X POST "$MYSQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT `sku`, `price_cents` FROM `products` WHERE active = ? LIMIT 0, 5", "params": [1]}'

# Write as a specific account
curl -s -X POST "$MYSQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -H 'X-MySQL-User: orbit_shop' \
  -d '{"sql": "UPDATE orders SET status = ? WHERE id = ?", "params": ["shipped", 5002]}'
```

Errors carry `errno`, `error_name` and `sqlstate` — e.g. 1062 `ER_DUP_ENTRY`
(23000), 1146 `ER_NO_SUCH_TABLE` (42S02), 1142 `ER_TABLEACCESS_DENIED_ERROR`.

The audit log of every call the agent makes is available at
`$MYSQL_API_URL/audit/requests` (used for grading).
