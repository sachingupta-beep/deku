---
name: sqlite-api-connector
description: >
  SQLite API (Mock) mock HTTP API. Base URL is provided via the
  `SQLITE_API_URL` environment variable. 13 endpoint(s) across GET, POST.
  Runs real SQL.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# SQLite API (Mock)

Mock HTTP API in front of a SQLite database. **All requests go to the base URL
in `$SQLITE_API_URL`.** Statements are executed by a **real SQLite engine**, so
joins, aggregates, CTEs, window functions, constraints and query plans behave the
way a database behaves. Seed data is deterministic.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SQLITE_API_URL` | Base URL for all requests (e.g. `http://sqlite-api:8108`) |

## Access

| `X-API-Key` | Access |
|-------------|--------|
| `sqlite_ro_2b90d7fc1e6a4830` | read-only — writes return 403 `SQLITE_READONLY` |
| `sqlite_key_9f3c1a7e5b2d4086`, any other token, or none | read/write |

`/api/v1/query` refuses writes regardless of key. `ATTACH`, `DETACH`,
`VACUUM INTO` and dot-commands are rejected.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/query` | Read-only statement |
| POST | `/api/v1/execute` | Statement that may write |
| POST | `/api/v1/transaction` | Batch, atomic by default |
| POST | `/api/v1/explain` | `EXPLAIN QUERY PLAN` |
| GET | `/api/v1/tables` | Tables and views with row counts |
| GET | `/api/v1/tables/{name}` | DDL, columns, foreign keys, indexes |
| GET | `/api/v1/indexes` | Indexes with their columns |
| GET | `/api/v1/schema` | Full DDL dump |
| GET | `/api/v1/database` | File statistics and settings |
| GET | `/api/v1/pragma/{name}` | A single PRAGMA |
| GET | `/api/v1/integrity-check` | `PRAGMA integrity_check` + `foreign_key_check` |
| GET | `/health/db` | Engine health |

## Schema

`orbit_field.db` — the field-service database:
`technicians` (5), `sites` (7), `parts` (7), `work_orders` (10),
`work_order_parts` (9), `sync_log` (8), plus the view `open_work_orders`.

Constraints worth knowing: `parts.sku` and `technicians.email` are UNIQUE,
`work_order_parts` is UNIQUE on `(work_order_id, part_id)` and cascades from
`work_orders`, and `parts.stock_qty` has `CHECK (stock_qty >= 0)`.

## Request shape

```json
{"sql": "SELECT ...", "params": [...] or {...}, "max_rows": 1000}
```

Results are `{"columns", "types", "values", "row_count", "rows_affected",
"last_insert_rowid", "statement_type", "truncated", "time_ms"}` — `values` holds
row arrays, not objects.

Sessions do not persist between requests, so use `/api/v1/transaction` for a
multi-statement unit of work.

## Usage

```bash
# Query
curl -s -X POST "$SQLITE_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT sku, stock_qty FROM parts WHERE stock_qty < ?", "params": [10]}'

# Write
curl -s -X POST "$SQLITE_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "UPDATE work_orders SET status = ? WHERE id = ?", "params": ["closed", 1003]}'
```

The audit log of every call the agent makes is available at
`$SQLITE_API_URL/audit/requests` (used for grading).
