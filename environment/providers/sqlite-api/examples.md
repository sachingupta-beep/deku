# SQLite Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$SQLITE_API_URL`; responses are verbatim (long arrays elided with
`…`).

Results use the shape a SQLite HTTP service returns: `columns`, `types` and
`values` — row arrays rather than objects.

## Health

```bash
curl -s "$SQLITE_API_URL/health"
curl -s "$SQLITE_API_URL/health/db"
```
```json
{"status": "ok"}
{"status": "ok", "engine": "sqlite", "sqlite_version": "3.45.3",
 "journal_mode": "wal", "tables": 6, "latency_ms": 0.412}
```

## Queries

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, sku, name, stock_qty FROM parts ORDER BY sku"}'
```
```json
{"columns": ["id", "sku", "name", "stock_qty"],
 "types": ["integer", "text", "text", "integer"],
 "values": [[3, "BLT-045", "Drive belt 45cm", 3],
            [6, "CBL-900", "CAN bus harness", 0],
            [5, "FLT-012", "Air filter cartridge", 120], "…"],
 "row_count": 7, "rows_affected": 0, "last_insert_rowid": null,
 "statement_type": "select", "truncated": false, "time_ms": 0.061}
```

Joins and aggregates:

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT s.customer, COUNT(*) AS work_orders, SUM(w.minutes_spent) AS minutes FROM work_orders w JOIN sites s ON s.id = w.site_id GROUP BY s.customer ORDER BY work_orders DESC, s.customer"}'
```
```json
{"columns": ["customer", "work_orders", "minutes"],
 "types": ["text", "integer", "integer"],
 "values": [["Helix Robotics Inc", 4, 635], ["Aurora Bistro LLC", 3, 175],
            ["Lumen Design Studio", 1, 140], ["Pelagic Freight Co", 1, 0],
            ["Verdant Farms", 1, 260]],
 "row_count": 5, "…": "…"}
```

Window functions and CTEs work because this is a real engine:

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, priority, minutes_spent, RANK() OVER (PARTITION BY priority ORDER BY minutes_spent DESC) AS rank_in_priority FROM work_orders WHERE status = '\''closed'\'' ORDER BY priority, rank_in_priority"}'
```
```json
{"columns": ["id", "priority", "minutes_spent", "rank_in_priority"],
 "types": ["integer", "text", "integer", "integer"],
 "values": [[1001, "P1", 385, 1], [1005, "P2", 260, 1], [1009, "P2", 160, 2],
            [1008, "P3", 140, 1], [1002, "P3", 90, 2]],
 "row_count": 5, "…": "…"}
```

```bash
# CTE: the three work orders with the highest parts cost
curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "WITH part_cost AS (SELECT work_order_id, SUM(quantity * unit_cost_cents) AS cents FROM work_order_parts GROUP BY work_order_id) SELECT w.id, w.summary, part_cost.cents FROM work_orders w JOIN part_cost ON part_cost.work_order_id = w.id ORDER BY part_cost.cents DESC LIMIT 3"}'
```
```json
{"columns": ["id", "summary", "cents"],
 "values": [[1005, "Irrigation controller power supply failure", 32300],
            [1001, "Coolant pump seized on line 2", 25080],
            [1009, "Sensor recalibration after firmware update", 16800]], "…": "…"}
```

## Parameters

Positional (`?` with a JSON array) or named (`:name` with a JSON object):

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, summary FROM work_orders WHERE status = ? AND priority = ?",
       "params": ["closed", "P1"]}'

curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT sku, stock_qty FROM parts WHERE stock_qty < :threshold ORDER BY stock_qty",
       "params": {"threshold": 10}}'
```
```json
{"values": [[1001, "Coolant pump seized on line 2"]], "row_count": 1, "…": "…"}
{"values": [["CBL-900", 0], ["BLT-045", 3], ["PSU-500", 7], ["VLV-777", 9]], "…": "…"}
```

`max_rows` caps a result and flags it:

```json
{"columns": ["id"], "values": [[1001], [1002], [1003]],
 "row_count": 3, "truncated": true, "…": "…"}
```

## Writes

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "INSERT INTO parts (sku, name, category, unit_cost_cents, stock_qty, reorder_level) VALUES (?, ?, ?, ?, ?, ?)",
       "params": ["VLV-777", "Bypass valve", "hydraulic", 5600, 9, 4]}'
```
```json
{"columns": [], "types": [], "values": [], "row_count": 0,
 "rows_affected": 1, "last_insert_rowid": 8,
 "statement_type": "insert", "truncated": false, "time_ms": 0.048}
```

`ON DELETE CASCADE` on `work_order_parts` is real — deleting a work order takes
its parts rows with it.

## Constraint failures

Each carries SQLite's extended result code and C-API errno:

| Statement | Response |
|-----------|----------|
| `INSERT INTO parts … VALUES ('PMP-100', …)` | 400 `{"error": "UNIQUE constraint failed: parts.sku", "code": "SQLITE_CONSTRAINT_UNIQUE", "errno": 2067, "kind": "unique_violation"}` |
| `INSERT INTO work_orders (site_id, …) VALUES (999, …)` | 409 `{"error": "FOREIGN KEY constraint failed", "code": "SQLITE_CONSTRAINT_FOREIGNKEY", "errno": 787}` |
| `UPDATE parts SET stock_qty = -5 …` | 400 `{"error": "CHECK constraint failed: stock_qty >= 0", "code": "SQLITE_CONSTRAINT_CHECK", "errno": 275}` |
| `INSERT INTO sites (name, region) VALUES (…)` | 400 `{"error": "NOT NULL constraint failed: sites.customer", "code": "SQLITE_CONSTRAINT_NOTNULL", "errno": 1299}` |
| `SELECT * FROM invoices` | 400 `{"error": "no such table: invoices", "code": "SQLITE_ERROR", "errno": 1}` |
| `DELETE …` on `/api/v1/query` | 403 `SQLITE_AUTH` |
| Any write with `X-API-Key: sqlite_ro_2b90d7fc1e6a4830` | 403 `SQLITE_READONLY` |
| `ATTACH DATABASE '/etc/passwd' AS leak` | 403 `SQLITE_AUTH` |

## Transactions

Each request gets its own connection, so a bare `BEGIN` does not carry across
requests — `/api/v1/transaction` is the unit of work.

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d '{"statements": [
        {"sql": "UPDATE parts SET stock_qty = stock_qty - ? WHERE sku = ?", "params": [2, "SNS-220"]},
        {"sql": "INSERT INTO work_order_parts (work_order_id, part_id, quantity, unit_cost_cents) VALUES (1004, 2, 2, 4200)"},
        {"sql": "SELECT sku, stock_qty FROM parts WHERE sku = '\''SNS-220'\''"}],
      "atomic": true}'
```
```json
{"results": [{"rows_affected": 1, "statement_type": "update", "statement_index": 0, "…": "…"},
             {"rows_affected": 1, "last_insert_rowid": 10, "statement_type": "insert", "statement_index": 1, "…": "…"},
             {"columns": ["sku", "stock_qty"], "values": [["SNS-220", 46]], "statement_index": 2, "…": "…"}],
 "statement_count": 3, "failed_count": 0, "rolled_back": false}
```

A failure inside an atomic batch rolls the whole thing back:

```json
{"error": "UNIQUE constraint failed: parts.sku", "code": "SQLITE_CONSTRAINT_UNIQUE",
 "errno": 2067, "kind": "unique_violation", "statement_index": 1, "rolled_back": true}
```

The preceding `UPDATE parts SET stock_qty = 999 WHERE sku = 'FLT-012'` left no
trace — a follow-up query still reports `120`.

With `"atomic": false` the batch continues and reports per-statement errors:

```json
{"results": [{"error": "UNIQUE constraint failed: parts.sku",
              "code": "SQLITE_CONSTRAINT_UNIQUE", "errno": 2067,
              "kind": "unique_violation", "statement_index": 0},
             {"columns": ["parts"], "values": [[8]], "statement_index": 1, "…": "…"}],
 "statement_count": 2, "failed_count": 1, "rolled_back": false}
```

## Query plans

```bash
curl -s -X POST "$SQLITE_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM work_orders WHERE site_id = 3"}'
```
```json
{"query": "SELECT * FROM work_orders WHERE site_id = 3",
 "plan": [{"id": 3, "parent": 0, "notused": 61,
           "detail": "SEARCH work_orders USING INDEX idx_work_orders_site (site_id=?)"}],
 "uses_index": true, "scans": []}
```

A predicate the indexes cannot serve falls back to a scan:

```json
{"query": "SELECT * FROM sites WHERE customer LIKE '%Robotics%'",
 "plan": [{"id": 2, "parent": 0, "notused": 216, "detail": "SCAN sites"}],
 "uses_index": false, "scans": ["SCAN sites"]}
```

## Schema introspection

```bash
curl -s "$SQLITE_API_URL/api/v1/tables"
curl -s "$SQLITE_API_URL/api/v1/tables/work_orders"
curl -s "$SQLITE_API_URL/api/v1/indexes"
curl -s "$SQLITE_API_URL/api/v1/schema"
```
```json
{"tables": [{"name": "parts", "type": "table", "sql": "CREATE TABLE parts (…)", "row_count": 7},
            {"name": "work_orders", "type": "table", "…": "…", "row_count": 10},
            {"name": "open_work_orders", "type": "view", "sql": "CREATE VIEW …"}],
 "count": 7}
```

`describe_table` returns the DDL plus `PRAGMA table_info`, `foreign_key_list`
and `index_list` with each index's columns:

```json
{"name": "work_orders", "type": "table", "sql": "CREATE TABLE work_orders (…)",
 "columns": [{"cid": 0, "name": "id", "type": "INTEGER", "notnull": 0,
              "dflt_value": null, "pk": 1}, "…"],
 "foreign_keys": [{"id": 0, "seq": 0, "table": "technicians", "from": "technician_id",
                   "to": "id", "on_update": "NO ACTION", "on_delete": "NO ACTION", "…": "…"}, "…"],
 "indexes": [{"seq": 0, "name": "idx_work_orders_status", "unique": 0,
              "columns": ["status", "priority"], "…": "…"}, "…"],
 "row_count": 10}
```

## Database file and pragmas

```bash
curl -s "$SQLITE_API_URL/api/v1/database"
```
```json
{"name": "orbit_field.db", "path": "/var/lib/orbit/field/orbit_field.db",
 "sqlite_version": "3.45.3", "size_bytes": 2097152, "page_size": 4096,
 "page_count": 512, "freelist_count": 7, "encoding": "UTF-8",
 "journal_mode": "wal", "synchronous": "NORMAL", "auto_vacuum": "INCREMENTAL",
 "foreign_keys": true, "user_version": 14, "application_id": 1198813761,
 "wal": {"checkpoint_mode": "PASSIVE", "autocheckpoint_pages": 1000,
         "wal_size_bytes": 163840},
 "last_backup_at": "2026-05-26T02:00:00Z", "table_count": 6, "total_rows": 46}
```

File-level pragmas come from the database description; live pragmas run against
the database:

```bash
curl -s "$SQLITE_API_URL/api/v1/pragma/journal_mode"
curl -s "$SQLITE_API_URL/api/v1/pragma/table_list"
curl -s "$SQLITE_API_URL/api/v1/integrity-check"
```
```json
{"pragma": "journal_mode", "value": "wal", "source": "database_file"}
{"pragma": "table_list", "rows": [{"schema": "main", "name": "work_orders",
                                   "type": "table", "ncol": 10, "wr": 0, "strict": 0}, "…"],
 "source": "live"}
{"integrity_check": ["ok"], "ok": true, "foreign_key_violations": []}
```
