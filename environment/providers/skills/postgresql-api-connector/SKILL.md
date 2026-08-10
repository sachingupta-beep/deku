---
name: postgresql-api-connector
description: >
  PostgreSQL API (Mock) mock HTTP API. Base URL is provided via the
  `POSTGRESQL_API_URL` environment variable. 20 endpoint(s) across GET, POST.
  Runs real SQL and reports PostgreSQL SQLSTATE errors.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# PostgreSQL API (Mock)

Mock HTTP API in front of a PostgreSQL database (`orbit_core`). **All requests
go to the base URL in `$POSTGRESQL_API_URL`.** Statements are executed by a
**real SQL engine**, so joins, aggregates, CTEs, window functions, constraints
and query plans behave the way a database behaves. Seed data is deterministic.

## Base URL

| Variable | Purpose |
|----------|---------|
| `POSTGRESQL_API_URL` | Base URL for all requests (e.g. `http://postgresql-api:8109`) |

## Roles

`X-DB-Role` (or a bearer token) selects the cluster role; absent or unknown
falls back to `orbit_app`. Table GRANTs are enforced per statement.

| Role | Access |
|------|--------|
| `postgres` | superuser — bypasses GRANTs, unmasked `pg_stat_activity` |
| `orbit_app` | default — read/write, SELECT only on `endpoints` |
| `orbit_readonly` | SELECT on everything |
| `orbit_analytics` | SELECT on `organizations`, `endpoints`, `request_stats` only |

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/query` | Read-only statement |
| POST | `/api/v1/execute` | Statement that may write |
| POST | `/api/v1/transaction` | Batch with an `isolation_level`, atomic |
| POST | `/api/v1/explain` | `EXPLAIN` with `analyze`, `buffers`, `format` |
| GET | `/api/v1/schemas` | Schemas |
| GET | `/api/v1/tables` | Tables with sizes and the caller's privileges |
| GET | `/api/v1/tables/{name}` | Columns, foreign keys, indexes, DDL |
| GET | `/api/v1/indexes` | Indexes with `indexdef` |
| GET | `/api/v1/catalog/pg_stat_activity` | Sessions (query text masked for non-superusers) |
| GET | `/api/v1/catalog/pg_stat_statements` | Statement statistics |
| GET | `/api/v1/catalog/pg_stat_user_tables` | Per-table scan/tuple/vacuum stats |
| GET | `/api/v1/catalog/pg_stat_replication` | Standbys and replay lag |
| GET | `/api/v1/catalog/pg_settings` | Server settings (`?name=` for one) |
| GET | `/api/v1/catalog/pg_extension` | Installed extensions |
| GET | `/api/v1/catalog/pg_roles` | Cluster roles |
| GET | `/api/v1/catalog/grants` | Table grants (`?role=`) |
| GET | `/api/v1/database` | Cluster and database facts |
| GET | `/api/v1/version` · `/health/db` | Version and health |

## Schema — `orbit_core`

`organizations` (6, uuid PK + jsonb settings), `api_keys` (8), `api_key_scopes`
(13), `endpoints` (7), `request_stats` (12), `webhooks` (5),
`webhook_deliveries` (10, jsonb payload), plus the view `active_api_keys`.

## Dialect notes

`$1` placeholders, `ILIKE`, `::` casts and `NOW()` are rewritten before
execution; `->` and `->>` JSON access work natively. Constructs outside that set
surface as `42601 syntax_error` rather than being mistranslated. Sessions do not
persist between requests — use `/api/v1/transaction` for a unit of work.

## Usage

```bash
# Query
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT slug, seats FROM organizations WHERE plan = $1", "params": ["enterprise"]}'

# Write as a specific role
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -H 'X-DB-Role: orbit_app' \
  -d '{"sql": "UPDATE webhooks SET active = false WHERE id = 5"}'
```

Errors carry `severity`, `code`/`sqlstate`, `condition`, and where applicable
`detail`, `hint`, `constraint`, `table`, `column`.

The audit log of every call the agent makes is available at
`$POSTGRESQL_API_URL/audit/requests` (used for grading).
