# PostgreSQL API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$POSTGRESQL_API_URL`.** Statements are executed by a real SQL engine and reported with PostgreSQL SQLSTATE codes.

## Base URL

| Variable | Purpose |
|----------|---------|
| `POSTGRESQL_API_URL` | Base URL for all requests |

## Health and version

```bash
curl -s "$POSTGRESQL_API_URL/health"
curl -s "$POSTGRESQL_API_URL/health/db"
curl -s "$POSTGRESQL_API_URL/api/v1/version"
```

## Queries

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT slug, plan, seats FROM organizations ORDER BY mrr_cents DESC"}'

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT slug, seats FROM organizations WHERE plan = $1 AND seats >= $2", "params": ["enterprise", 10]}'

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT name FROM organizations WHERE name ILIKE '%robotics%' AND seats::int > 10\"}"

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT slug, settings ->> 'retention_days' AS retention FROM organizations\"}"

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT o.name, SUM(r.requests) AS requests FROM request_stats r JOIN organizations o ON o.id = r.org_id GROUP BY o.name ORDER BY requests DESC"}'

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM active_api_keys ORDER BY id"}'
```

`$n` placeholders, `ILIKE`, `::` casts and `NOW()` are rewritten before
execution. `->`/`->>` JSON access works natively. CTEs, window functions and
views all work.

## Writes

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"UPDATE webhook_deliveries SET status = 'delivered', attempts = attempts + 1 WHERE id = 5\"}"

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "DELETE FROM webhooks WHERE id = 2"}'
```

## Roles and GRANTs

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-DB-Role: orbit_analytics' \
  -d '{"sql": "SELECT day, SUM(requests) FROM request_stats GROUP BY day"}'

# Denied: orbit_analytics has no grant on webhooks -> 42501
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-DB-Role: orbit_analytics' -d '{"sql": "SELECT * FROM webhooks"}'

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-DB-Role: postgres' -d '{"sql": "SELECT id, url FROM webhooks"}'
```

Privilege checks run before constraint validation, matching PostgreSQL.

## Transactions

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d '{"statements": [
        {"sql": "UPDATE organizations SET seats = seats + 5 WHERE slug = $1", "params": ["lumen-design"]},
        {"sql": "SELECT slug, seats FROM organizations WHERE slug = '\''lumen-design'\''"}],
      "isolation_level": "serializable"}'
```

Valid isolation levels: `read committed`, `repeatable read`, `serializable`,
`read uncommitted`. A failure rolls the whole batch back.

## EXPLAIN

```bash
curl -s -X POST "$POSTGRESQL_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM request_stats WHERE org_id = $1"}'

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT o.name, SUM(r.requests) FROM request_stats r JOIN organizations o ON o.id = r.org_id GROUP BY o.name", "analyze": true, "buffers": true}'

curl -s -X POST "$POSTGRESQL_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT * FROM webhook_deliveries WHERE status = 'failed'\", \"format\": \"text\"}"
```

## Schema introspection

```bash
curl -s "$POSTGRESQL_API_URL/api/v1/schemas"
curl -s "$POSTGRESQL_API_URL/api/v1/tables"
curl -s "$POSTGRESQL_API_URL/api/v1/tables/request_stats"
curl -s "$POSTGRESQL_API_URL/api/v1/indexes"
```

## pg_catalog

```bash
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_activity"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_activity" -H 'X-DB-Role: postgres'
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_statements?order_by=mean_exec_time&limit=5"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_user_tables"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_stat_replication"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_settings"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_settings?name=work_mem"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_extension"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/pg_roles"
curl -s "$POSTGRESQL_API_URL/api/v1/catalog/grants?role=orbit_analytics"
curl -s "$POSTGRESQL_API_URL/api/v1/database"
```

`pg_stat_activity` masks other roles' query text unless the caller is a
superuser. `pg_stat_statements` requires `orbit_app` or a superuser.
