# PostgreSQL Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$POSTGRESQL_API_URL`; responses are verbatim (long arrays elided
with `…`).

The `X-DB-Role` header selects the cluster role; without it, statements run as
`orbit_app`.

## Health and version

```bash
curl -s "$POSTGRESQL_API_URL/health/db"
curl -s "$POSTGRESQL_API_URL/api/v1/version"
```
```json
{"status": "ok", "engine": "postgresql", "server_version": "15.6",
 "database": "orbit_core",
 "connections": {"active": 7, "idle": 24, "idle_in_transaction": 1, "total": 32},
 "max_replication_lag_ms": 1870, "latency_ms": 0.214}
{"version": "PostgreSQL 15.6 on x86_64-pc-linux-gnu, compiled by gcc 12.2.0, 64-bit",
 "server_version": "15.6", "server_version_num": 150006}
```

## Queries

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT slug, plan, seats, mrr_cents FROM organizations ORDER BY mrr_cents DESC"}'
```
```json
{"command": "SELECT",
 "fields": [{"name": "slug", "type": "text"}, {"name": "plan", "type": "text"},
            {"name": "seats", "type": "int8"}, {"name": "mrr_cents", "type": "int8"}],
 "rows": [{"slug": "helix-robotics", "plan": "enterprise", "seats": 50, "mrr_cents": 249900},
          {"slug": "quanta-analytics", "plan": "enterprise", "seats": 40, "mrr_cents": 199900},
          "…"],
 "row_count": 6, "rows_affected": 0, "truncated": false,
 "duration_ms": 0.061, "role": "orbit_app"}
```

Rows are objects and `fields` carries a PostgreSQL type per column.

## PostgreSQL syntax that gets rewritten

`$n` placeholders, `ILIKE` and `::` casts are translated before execution:

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT slug, seats FROM organizations WHERE plan = $1 AND seats >= $2 ORDER BY slug",
       "params": ["enterprise", 10]}'

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT name, plan FROM organizations WHERE name ILIKE '%robotics%' AND seats::int > 10\"}"
```
```json
{"rows": [{"slug": "helix-robotics", "seats": 50}, {"slug": "quanta-analytics", "seats": 40}], "…": "…"}
{"rows": [{"name": "Helix Robotics Inc", "plan": "enterprise"}], "…": "…"}
```

`->` and `->>` JSON access needs no translation:

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT slug, settings ->> 'retention_days' AS retention_days, settings ->> 'sso' AS sso FROM organizations ORDER BY slug\"}"
```
```json
{"rows": [{"slug": "aurora-bistro", "retention_days": 30, "sso": "false"},
          {"slug": "helix-robotics", "retention_days": 365, "sso": "true"},
          {"slug": "lumen-design", "retention_days": 90, "sso": "false"}, "…"], "…": "…"}
```

String literals are never rewritten — the rewriter splits on quotes first, so a
value containing `::` or `ILIKE` passes through untouched.

## Joins, window functions and CTEs

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT e.path, r.requests, r.errors, ROUND(100.0 * r.errors / NULLIF(r.requests, 0), 3) AS error_pct, RANK() OVER (ORDER BY r.errors DESC) AS worst FROM request_stats r JOIN endpoints e ON e.id = r.endpoint_id WHERE r.day = '2026-05-26' ORDER BY worst LIMIT 5\"}"
```
```json
{"rows": [{"path": "/v0/metrics", "requests": 1904, "errors": 1904, "error_pct": 100.0, "worst": 1},
          {"path": "/v1/telemetry/batch", "requests": 91044, "errors": 1877, "error_pct": 2.062, "worst": 2},
          {"path": "/v1/telemetry", "requests": 482119, "errors": 412, "error_pct": 0.085, "worst": 3}, "…"],
 "row_count": 5, "…": "…"}
```

The deprecated `/v0/metrics` endpoint failing 100% of requests is real data in
the seed, not a special case.

```bash
# CTE: webhooks with failing deliveries
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"WITH failing AS (SELECT webhook_id, COUNT(*) AS failures FROM webhook_deliveries WHERE status IN ('failed', 'retrying') GROUP BY webhook_id) SELECT w.url, w.active, failing.failures FROM webhooks w JOIN failing ON failing.webhook_id = w.id ORDER BY failing.failures DESC\"}"
```

## Writes and SQLSTATE errors

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"UPDATE webhook_deliveries SET status = 'delivered', attempts = attempts + 1, response_code = 200 WHERE id = 5\"}"
```
```json
{"command": "UPDATE", "fields": [], "rows": [], "row_count": 0,
 "rows_affected": 1, "truncated": false, "duration_ms": 0.058, "role": "orbit_app"}
```

Failures come back as a full PostgreSQL error report:

```json
{"error": "duplicate key value violates unique constraint \"organizations_slug_key\"",
 "severity": "ERROR", "code": "23505", "sqlstate": "23505",
 "condition": "unique_violation",
 "message": "duplicate key value violates unique constraint \"organizations_slug_key\"",
 "detail": "Key (slug) already exists.", "constraint": "organizations_slug_key",
 "table": "organizations", "schema": "public", "statement": "INSERT INTO organizations …"}
```

```json
{"error": "null value in column \"day\" of relation \"request_stats\" violates not-null constraint",
 "severity": "ERROR", "code": "23502", "sqlstate": "23502",
 "condition": "not_null_violation", "table": "request_stats", "column": "day",
 "schema": "public"}
```

```json
{"error": "relation \"invoices\" does not exist", "code": "42P01",
 "condition": "undefined_table", "table": "invoices", "schema": "public"}
```

| Statement | SQLSTATE | HTTP |
|-----------|----------|------|
| Duplicate `slug` | 23505 | 409 |
| `api_keys.org_id` pointing at a missing org | 23503 | 409 |
| `plan = 'platinum'` (CHECK) | 23514 | 400 |
| `INSERT` omitting a NOT NULL column | 23502 | 400 |
| `SELECT * FROM invoices` | 42P01 | 404 |
| `SELECT nonexistent FROM organizations` | 42703 | 400 |
| `SELEC * FROM …` | 42601 | 400 |
| `DELETE` on `/api/v1/query` | 0A000 | 403 |
| `ATTACH DATABASE …` | 0A000 | 403 |

## Roles and GRANTs

```bash
# orbit_analytics has SELECT on request_stats
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-DB-Role: orbit_analytics' \
  -d '{"sql": "SELECT day, SUM(requests) AS requests FROM request_stats GROUP BY day ORDER BY day"}'
```
```json
{"rows": [{"day": "2026-05-25", "requests": 523890},
          {"day": "2026-05-26", "requests": 800458}],
 "row_count": 2, "role": "orbit_analytics", "…": "…"}
```

The same role has no grant on `webhooks`:

```json
{"error": "permission denied for table webhooks", "severity": "ERROR",
 "code": "42501", "sqlstate": "42501", "condition": "insufficient_privilege",
 "table": "webhooks", "schema": "public",
 "detail": "Role \"orbit_analytics\" lacks SELECT on public.webhooks."}
```

**Privilege checks run before constraint validation**, matching PostgreSQL. An
`INSERT INTO endpoints` as `orbit_app` — which holds only SELECT there — returns
`42501`, not the NOT NULL error the row would also have triggered:

```json
{"error": "permission denied for table endpoints", "code": "42501",
 "detail": "Role \"orbit_app\" lacks INSERT on public.endpoints."}
```

## Transactions

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d '{"statements": [
        {"sql": "UPDATE organizations SET seats = seats + 5 WHERE slug = $1", "params": ["lumen-design"]},
        {"sql": "INSERT INTO api_key_scopes (id, api_key_id, scope) VALUES (14, 5, '\''admin'\'')"},
        {"sql": "SELECT slug, seats FROM organizations WHERE slug = '\''lumen-design'\''"}],
      "isolation_level": "serializable"}'
```
```json
{"results": [{"command": "UPDATE", "rows_affected": 1, "statement_index": 0, "…": "…"},
             {"command": "INSERT", "rows_affected": 1, "statement_index": 1, "…": "…"},
             {"command": "SELECT", "rows": [{"slug": "lumen-design", "seats": 17}],
              "statement_index": 2, "…": "…"}],
 "statement_count": 3, "isolation_level": "serializable",
 "rolled_back": false, "committed": true}
```

A failure rolls the batch back and reports the failing statement:

```json
{"error": "duplicate key value violates unique constraint \"api_key_scopes_api_key_id_scope_key\"",
 "code": "23505", "condition": "unique_violation", "statement_index": 1,
 "rolled_back": true, "in_failed_transaction": true}
```

The preceding `UPDATE … SET seats = 999` left no trace — a follow-up query still
reports `9` for `verdant-farms`.

An unrecognised isolation level is rejected before anything runs:

```json
{"error": "invalid value for parameter \"transaction_isolation\": \"snapshot\"",
 "code": "0A000", "condition": "feature_not_supported",
 "hint": "Available values: read committed, repeatable read, serializable, read uncommitted"}
```

## EXPLAIN

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT o.name, SUM(r.requests) FROM request_stats r JOIN organizations o ON o.id = r.org_id GROUP BY o.name\", \"analyze\": true, \"buffers\": true}"
```
```json
{"format": "json",
 "plan": [{"Node Type": "Nested Loop", "Join Type": "Inner",
           "Startup Cost": 0.0, "Total Cost": 37.78, "Plan Rows": 5, "Plan Width": 64,
           "Plans": [{"Node Type": "Seq Scan", "Relation Name": "r",
                      "Total Cost": 3.22, "Actual Startup Time": 0.012,
                      "Actual Total Time": 2.674, "Actual Rows": 5, "Actual Loops": 1,
                      "Shared Hit Blocks": 12, "Shared Read Blocks": 0}, "…"]}],
 "planning_time_ms": 0.184, "execution_time_ms": 2.674}
```

`"format": "text"` returns the familiar indented plan:

```
Index Scan on webhook_deliveries using idx_deliveries_status  (cost=0.00..26.90 rows=1 width=64)
```

## information_schema and pg_catalog

```bash
curl -s "$POSTGRESQL_API_URL/api/v1/tables/request_stats"
```
```json
{"table_schema": "public", "table_name": "request_stats", "table_type": "BASE TABLE",
 "definition": "CREATE TABLE request_stats (…)",
 "columns": [{"ordinal_position": 1, "column_name": "id", "data_type": "integer",
              "is_nullable": "NO", "column_default": null, "is_primary_key": true},
             {"ordinal_position": 2, "column_name": "org_id", "data_type": "uuid",
              "is_nullable": "NO", "…": "…"},
             {"ordinal_position": 7, "column_name": "p95_ms", "data_type": "numeric(10,2)", "…": "…"}],
 "foreign_keys": [{"column": "org_id", "references_table": "organizations",
                   "references_column": "id", "on_delete": "CASCADE"}, "…"],
 "indexes": [{"indexname": "idx_request_stats_org_day", "is_unique": false,
              "columns": ["org_id", "day"]}, "…"],
 "privileges": ["INSERT", "SELECT"]}
```

The declared PostgreSQL types (`uuid`, `jsonb`, `numeric(10,2)`, `timestamptz`)
are reported verbatim.

`pg_stat_activity` masks other roles' query text unless the caller is a
superuser — exactly what PostgreSQL does:

```bash
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_activity"
```
```json
{"rows": [{"pid": 41207, "usename": "orbit_app", "state": "active",
           "query": "SELECT * FROM request_stats WHERE org_id = $1 AND day >= $2"},
          {"pid": 41244, "usename": "orbit_readonly", "state": "active",
           "query": "<insufficient privilege>"}, "…"],
 "count": 6, "role": "orbit_app",
 "note": "query text of other roles' sessions is masked without superuser"}
```

With `X-DB-Role: postgres` every query is visible and `note` is `null`.

```bash
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_statements?order_by=mean_exec_time&limit=3"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_user_tables"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_replication"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_settings?name=work_mem"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_extension"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_roles"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/grants?role=orbit_analytics"
```
```json
{"role": "primary", "wal_lsn": "3F/8A21C440",
 "standbys": [{"application_name": "orbit-replica-1", "client_addr": "10.42.0.21",
               "state": "streaming", "sync_state": "sync",
               "replay_lag_bytes": 8192, "replay_lag_ms": 41},
              {"application_name": "orbit-replica-2", "sync_state": "async",
               "replay_lag_ms": 1870}],
 "count": 2}
{"name": "work_mem", "setting": "16384", "unit": "kB",
 "category": "Resource Usage / Memory", "context": "user", "source": "configuration file"}
```

## Database

```bash
curl -s "$POSTGRESQL_API_URL/api/v1/database"
```
```json
{"version": "PostgreSQL 15.6 on x86_64-pc-linux-gnu, compiled by gcc 12.2.0, 64-bit",
 "database": "orbit_core", "schema": "public", "search_path": "\"$user\", public",
 "encoding": "UTF8", "collate": "en_US.utf8", "size_bytes": 8438452224,
 "uptime_seconds": 1231913, "max_connections": 200,
 "connections": {"active": 7, "idle": 24, "idle_in_transaction": 1, "total": 32},
 "replication_role": "primary", "table_count": 7, "total_rows": 61}
```
