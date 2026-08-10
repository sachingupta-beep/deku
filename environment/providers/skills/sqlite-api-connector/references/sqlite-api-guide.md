# SQLite API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$SQLITE_API_URL`.** Statements are executed by a real SQLite engine and the seed data is deterministic.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SQLITE_API_URL` | Base URL for all requests |

## Health

```bash
curl -s "$SQLITE_API_URL/health"
curl -s "$SQLITE_API_URL/health/db"
```

## Queries

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, sku, name, stock_qty FROM parts ORDER BY sku"}'

curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT s.customer, COUNT(*) AS work_orders, SUM(w.minutes_spent) AS minutes FROM work_orders w JOIN sites s ON s.id = w.site_id GROUP BY s.customer ORDER BY work_orders DESC"}'

curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, summary FROM work_orders WHERE status = ? AND priority = ?", "params": ["closed", "P1"]}'

curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT sku, stock_qty FROM parts WHERE stock_qty < :threshold", "params": {"threshold": 10}}'

curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM open_work_orders ORDER BY priority"}'

curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id FROM work_orders ORDER BY id", "max_rows": 3}'
```

CTEs, window functions, subqueries and views all work — this is a real engine.

## Writes

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "INSERT INTO parts (sku, name, category, unit_cost_cents, stock_qty, reorder_level) VALUES (?, ?, ?, ?, ?, ?)", "params": ["VLV-777", "Bypass valve", "hydraulic", 5600, 9, 4]}'

curl -s -X POST "$SQLITE_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "UPDATE work_orders SET status = ?, closed_at = ? WHERE id = ?", "params": ["closed", "2026-05-26T09:30:00Z", 1003]}'

curl -s -X POST "$SQLITE_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "DELETE FROM work_orders WHERE id = 1006"}'
```

Writes with `-H 'X-API-Key: sqlite_ro_2b90d7fc1e6a4830'` return 403.

## Transactions

Sessions do not persist between requests, so a multi-statement unit of work goes
through this endpoint. Atomic by default: any failure rolls the batch back.

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d '{"statements": [
        {"sql": "UPDATE parts SET stock_qty = stock_qty - ? WHERE sku = ?", "params": [2, "SNS-220"]},
        {"sql": "INSERT INTO work_order_parts (work_order_id, part_id, quantity, unit_cost_cents) VALUES (1004, 2, 2, 4200)"},
        {"sql": "SELECT sku, stock_qty FROM parts WHERE sku = '\''SNS-220'\''"}],
      "atomic": true}'
```

Pass `"atomic": false` to keep going after a failure and collect per-statement errors.

## Query plans

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM work_orders WHERE site_id = 3"}'
```

The response adds `uses_index` and the list of full `scans`.

## Schema introspection

```bash
curl -s "$SQLITE_API_URL/api/v1/tables"
curl -s "$SQLITE_API_URL/api/v1/tables?include_views=false"
curl -s "$SQLITE_API_URL/api/v1/tables/work_orders"
curl -s "$SQLITE_API_URL/api/v1/indexes"
curl -s "$SQLITE_API_URL/api/v1/schema"
```

## Database file and pragmas

```bash
curl -s "$SQLITE_API_URL/api/v1/database"
curl -s "$SQLITE_API_URL/api/v1/pragma/journal_mode"
curl -s "$SQLITE_API_URL/api/v1/pragma/page_size"
curl -s "$SQLITE_API_URL/api/v1/pragma/user_version"
curl -s "$SQLITE_API_URL/api/v1/pragma/foreign_key_check"
curl -s "$SQLITE_API_URL/api/v1/pragma/table_list"
curl -s "$SQLITE_API_URL/api/v1/integrity-check"
```

File-level pragmas (`journal_mode`, `page_size`, `page_count`, `freelist_count`,
`synchronous`, `auto_vacuum`, `busy_timeout`, `cache_size`, `temp_store`,
`user_version`, `application_id`, `encoding`, `foreign_keys`) report the database
file's settings. Live pragmas (`integrity_check`, `quick_check`,
`foreign_key_check`, `table_list`, `compile_options`, `database_list`) run
against the database.
