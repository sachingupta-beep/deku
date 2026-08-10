# PostgreSQL Mock API — Test Results

Base URL: `http://localhost:8109` (in docker-compose: `http://postgresql-api:8109`)

## Endpoints covered

| Method | Path                                        | Status              |
|--------|---------------------------------------------|---------------------|
| GET    | /health                                     | 200                 |
| GET    | /health/db                                  | 200                 |
| GET    | /api/v1/version                             | 200                 |
| POST   | /api/v1/query                               | 200/400/403/404     |
| POST   | /api/v1/execute                             | 200/400/403/404/409 |
| POST   | /api/v1/transaction                         | 200/400/403/409     |
| POST   | /api/v1/explain                             | 200/400/403/404     |
| GET    | /api/v1/schemas                             | 200                 |
| GET    | /api/v1/tables                              | 200                 |
| GET    | /api/v1/tables/{name}                       | 200/404             |
| GET    | /api/v1/indexes                             | 200                 |
| GET    | /api/v1/catalog/pg_stat_activity            | 200                 |
| GET    | /api/v1/catalog/pg_stat_statements          | 200/400/403         |
| GET    | /api/v1/catalog/pg_stat_user_tables         | 200                 |
| GET    | /api/v1/catalog/pg_stat_replication         | 200                 |
| GET    | /api/v1/catalog/pg_settings                 | 200/404             |
| GET    | /api/v1/catalog/pg_extension                | 200                 |
| GET    | /api/v1/catalog/pg_roles                    | 200                 |
| GET    | /api/v1/catalog/grants                      | 200                 |
| GET    | /api/v1/database                            | 200                 |

Collection run: **PASS 41 / WARN 18 / FAIL 0 / SKIP 0**. All eighteen WARNs are
intentional error-path requests.

## Real SQL under a PostgreSQL surface

`sql_engine.py` materializes the shared store into an in-memory SQLite database
per request, executes the statement, and syncs writes back — so the store stays
canonical (drift keeps working) while the service gets exact SQL semantics.
Joins, aggregates, CTEs, window functions, views, constraints and cascades all
work because a database is doing the work.

Everything above the engine is PostgreSQL. Because SQLite records declared types
verbatim, `information_schema` genuinely reports `uuid`, `jsonb`,
`numeric(10,2)`, `timestamptz` and `bigint`.

### Dialect rewriting

A rewriter translates the PostgreSQL-only syntax an agent is likely to send:

| Written | Executed |
|---------|----------|
| `$1`, `$2` | `?` positional parameters |
| `ILIKE` | `LIKE` (already case-insensitive for ASCII) |
| `value::int`, `count(*)::numeric` | `CAST(value AS INTEGER)` |
| `NOW()`, `CURRENT_TIMESTAMP` | `datetime('now')` |

String literals are never rewritten — the rewriter splits on quotes first.
`->` and `->>` JSON access needs no translation; it is supported natively.

Constructs outside that set (`ANY(array)`, `DISTINCT ON`, `RETURNING` with
complex expressions, procedural blocks) are passed through and surface as an
honest `42601 syntax_error` rather than being silently mistranslated.

Because each request gets its own connection, **sessions do not persist** — a
bare `BEGIN` has no effect on the next request. `/api/v1/transaction` is the
unit of work and is genuinely atomic.

## Schema — `orbit_core`

| Table | Rows | Notes |
|-------|------|-------|
| `organizations` | 6 | `uuid` PK, `jsonb` settings, `CHECK` on plan, one suspended |
| `api_keys` | 8 | FK to organizations `ON DELETE CASCADE`, two revoked |
| `api_key_scopes` | 13 | `UNIQUE (api_key_id, scope)` |
| `endpoints` | 7 | `UNIQUE (method, path)`, one deprecated |
| `request_stats` | 12 | `UNIQUE (org_id, endpoint_id, day)`, `numeric(10,2)` p95 |
| `webhooks` | 5 | FK to organizations, one inactive |
| `webhook_deliveries` | 10 | `jsonb` payload, `CHECK` on status, cascades from webhooks |

Plus the view `active_api_keys` and five indexes.

## Roles and GRANTs

`X-DB-Role` (or a bearer token) selects the cluster role; an unknown or absent
value falls back to `orbit_app`.

| Role | Access |
|------|--------|
| `postgres` | superuser — bypasses GRANTs, sees unmasked `pg_stat_activity` |
| `orbit_app` | default — read/write on most tables, SELECT only on `endpoints` |
| `orbit_readonly` | SELECT on everything |
| `orbit_analytics` | SELECT on `organizations`, `endpoints`, `request_stats` only |

GRANTs are seeded in `grants.json` and enforced per statement by extracting the
tables it references. Two behaviours worth noting, both matching PostgreSQL:

- **Privilege checks run before constraint validation.** An `INSERT` into a table
  the role cannot write returns `42501` even when the row would also have failed
  a NOT NULL check.
- **`pg_stat_activity` masks other roles' query text** unless the caller is a
  superuser, reporting `<insufficient privilege>` — exactly what PostgreSQL does.

## Errors — SQLSTATE

Failures are rendered as a PostgreSQL error report with the fields a driver
exposes: `severity`, `code`/`sqlstate`, `condition`, `message`, and where
applicable `detail`, `hint`, `constraint`, `table`, `column`, `schema`.

| Condition | SQLSTATE | HTTP |
|-----------|----------|------|
| `unique_violation` | 23505 | 409 |
| `foreign_key_violation` | 23503 | 409 |
| `not_null_violation` | 23502 | 400 |
| `check_violation` | 23514 | 400 |
| `undefined_table` | 42P01 | 404 |
| `undefined_column` | 42703 | 400 |
| `syntax_error` | 42601 | 400 |
| `insufficient_privilege` | 42501 | 403 |
| `feature_not_supported` | 0A000 | 403 |
| `undefined_object` | 42704 | 404 |

A unique violation reconstructs the constraint name and key, e.g.
`duplicate key value violates unique constraint "organizations_slug_key"` with
`detail: "Key (slug) already exists."`

## Notes

- Results are `{"command", "fields", "rows", "row_count", "rows_affected",
  "truncated", "duration_ms", "role"}`. `rows` are objects (not arrays), and
  `fields` carries a PostgreSQL type name per column.
- `POST /api/v1/explain` accepts `analyze`, `buffers` and `format`
  (`json` or `text`), and returns a node tree with `Node Type`, `Relation Name`,
  `Index Name`, costs, and — with `analyze` — actual times, rows and loops.
- `/api/v1/transaction` takes an `isolation_level`; an unrecognised value is
  rejected with `0A000` and the list of valid levels.
- `pg_stat_statements` requires the app role or a superuser; ordering by an
  unknown column returns `42703` with the available columns.
- `ATTACH`, `DETACH`, `VACUUM INTO` and dot-commands are rejected with `0A000`.
- Mutations are held in process memory and reset on container restart.
