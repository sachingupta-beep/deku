# SQLite Mock API — Test Results

Base URL: `http://localhost:8108` (in docker-compose: `http://sqlite-api:8108`)

## Endpoints covered

| Method | Path                             | Status          |
|--------|----------------------------------|-----------------|
| GET    | /health                          | 200             |
| GET    | /health/db                       | 200             |
| POST   | /api/v1/query                    | 200/400/403     |
| POST   | /api/v1/execute                  | 200/400/403/409 |
| POST   | /api/v1/transaction              | 200/400/403     |
| POST   | /api/v1/explain                  | 200/400         |
| GET    | /api/v1/tables                   | 200             |
| GET    | /api/v1/tables/{name}            | 200/404         |
| GET    | /api/v1/indexes                  | 200             |
| GET    | /api/v1/schema                   | 200             |
| GET    | /api/v1/database                 | 200             |
| GET    | /api/v1/pragma/{name}            | 200/400         |
| GET    | /api/v1/integrity-check          | 200             |

Collection run: **PASS 35 / WARN 13 / FAIL 0 / SKIP 0**. All thirteen WARNs are
intentional error-path requests.

## This service runs real SQL

Python ships with SQLite, so `sql_engine.py` executes genuine statements rather
than pattern-matching them. Joins, aggregates, subqueries, CTEs, window
functions, views, constraints, cascades and query plans all behave the way a
database behaves — including failures nobody hand-coded.

The shared store stays the source of truth, so the admin plane can still drift a
row mid-run:

1. every request materializes a fresh in-memory database from the store,
2. the statement executes against it,
3. a write syncs the resulting rows back into the store.

Because each request gets its own connection, **sessions do not persist** — a
`BEGIN` in one request has no effect on the next. `/api/v1/transaction` is how a
multi-statement unit of work is expressed, and it is genuinely atomic: a failure
rolls the batch back and nothing reaches the store.

## Schema

`orbit_field.db` — the field-service database the technician tablets sync against.

| Table | Rows | Notes |
|-------|------|-------|
| `technicians` | 5 | `UNIQUE(email)`, `CHECK (active IN (0,1))` |
| `sites` | 7 | `REAL` latitude/longitude |
| `parts` | 7 | `UNIQUE(sku)`, `CHECK (stock_qty >= 0)` |
| `work_orders` | 10 | FKs to `sites` and `technicians`; `CHECK` on status and priority |
| `work_order_parts` | 9 | `UNIQUE(work_order_id, part_id)`, `ON DELETE CASCADE` |
| `sync_log` | 8 | Push/pull records with a conflict flag |

Plus the view `open_work_orders`, four indexes, and the full DDL available from
`GET /api/v1/schema`.

Every column is a SQLite scalar (INTEGER, REAL, TEXT). Booleans are stored as
0/1 and blank seed cells become `NULL`, so `NOT NULL` and `IS NULL` behave as
they would in a real database.

## Access control

`X-API-Key` (or a bearer token):

| Key | Access |
|-----|--------|
| `sqlite_ro_2b90d7fc1e6a4830` | read-only — a write returns 403 `SQLITE_READONLY` |
| `sqlite_key_9f3c1a7e5b2d4086`, any other token, or none | read/write |

`/api/v1/query` also refuses writes regardless of key, so a read endpoint can
never mutate.

`ATTACH`, `DETACH`, `VACUUM INTO` and the dot-commands are rejected with 403 —
the in-memory database is otherwise a closed world, so that is the whole guard.

## Errors

Failures carry SQLite's extended result code and its C-API errno:

| Kind | Code | errno | HTTP |
|------|------|-------|------|
| unique violation | `SQLITE_CONSTRAINT_UNIQUE` | 2067 | 400 |
| foreign key violation | `SQLITE_CONSTRAINT_FOREIGNKEY` | 787 | 409 |
| not null violation | `SQLITE_CONSTRAINT_NOTNULL` | 1299 | 400 |
| check violation | `SQLITE_CONSTRAINT_CHECK` | 275 | 400 |
| unknown table / column / syntax | `SQLITE_ERROR` | 1 | 400 |
| write on a read-only endpoint or key | `SQLITE_AUTH` / `SQLITE_READONLY` | 23 | 403 |

A failed atomic transaction adds `rolled_back: true` and `statement_index`. A
non-atomic batch keeps going, and each failing entry appears in `results` with
its own error plus a `failed_count` in the envelope.

## Notes

- Results use the shape a SQLite HTTP service returns: `columns`, `types`,
  `values` (row arrays, not objects), `row_count`, `rows_affected`,
  `last_insert_rowid`, `truncated` and `time_ms`.
- `types` is inferred from the first non-null value per column, which is how
  SQLite's dynamic typing actually presents itself.
- `last_insert_rowid` is only reported for `INSERT`/`REPLACE`.
- `max_rows` (default 1000) caps a result and sets `truncated`.
- Parameters bind positionally (a JSON array with `?`) or by name (a JSON object
  with `:name`).
- `POST /api/v1/explain` runs `EXPLAIN QUERY PLAN` — SQLite's plan format, not a
  cost-based tree — and adds `uses_index` plus the list of full scans, which is
  the practical question a plan is read for.
- `GET /api/v1/pragma/{name}` answers file-level pragmas (`journal_mode`,
  `page_size`, `user_version`, …) from the seeded database description, and live
  pragmas (`integrity_check`, `foreign_key_check`, `table_list`,
  `compile_options`) from the database itself.
- Mutations are held in process memory and reset on container restart.
