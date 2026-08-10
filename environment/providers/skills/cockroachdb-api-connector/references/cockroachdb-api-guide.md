# CockroachDB API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$COCKROACHDB_API_URL`.** Statements are executed by a real SQL engine and the seed data is deterministic.

## Base URL

| Variable | Purpose |
|----------|---------|
| `COCKROACHDB_API_URL` | Base URL for all requests |

## Health and cluster

```bash
curl -s "$COCKROACHDB_API_URL/health"
curl -s "$COCKROACHDB_API_URL/health/db"
curl -s "$COCKROACHDB_API_URL/api/v1/version"
curl -s "$COCKROACHDB_API_URL/api/v1/cluster/status"
```

`/health/db` reports `degraded` because node 6 (`ap-southeast-1`) is seeded down.

## Queries

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT crdb_region, count(*) AS devices FROM devices GROUP BY crdb_region ORDER BY devices DESC"}'

curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT serial, status FROM devices WHERE crdb_region = $1 AND status = $2", "params": ["eu-central-1", "online"]}'

curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT serial, battery_pct FROM devices WHERE customer ILIKE '%farms%' AND battery_pct::int < 70\"}"

curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM fleet_by_region ORDER BY crdb_region"}'
```

`$n` placeholders, `::` casts, `ILIKE` and `now()` are rewritten before
execution; `gen_random_uuid()` and `unique_rowid()` are registered functions.

## Serializable transactions and retries

Transactions are SERIALIZABLE. A batch touching the contended device row
(`3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901`) fails its first attempt with 40001.

```bash
# Fails with SQLSTATE 40001, "retryable": true
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d "{\"statements\": [{\"sql\": \"UPDATE devices SET status = 'degraded' WHERE id = '3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901'\"}]}"

# Succeeds, reporting "retries": 1
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d "{\"statements\": [{\"sql\": \"UPDATE devices SET status = 'degraded' WHERE id = '3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901'\"}], \"max_retries\": 3}"
```

Priorities: `LOW`, `NORMAL`, `HIGH`. A failing batch rolls back entirely.

## AS OF SYSTEM TIME

Historical reads come from the snapshot taken at process start, so after a write
they differ from a live read.

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT serial, status FROM devices", "as_of_system_time": "-10s"}'

curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT serial, status FROM devices AS OF SYSTEM TIME '-1h'\"}"

curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT count(*) AS devices FROM devices AS OF SYSTEM TIME follower_read_timestamp()"}'
```

On a write it is rejected with `0A000`.

## Writes

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"INSERT INTO device_events (id, device_id, kind, severity, detail, occurred_at) VALUES (11, '3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901', 'heartbeat_gap', 'warning', 'Gap of 71s', '2026-05-26T09:05:00Z')\"}"

curl -s -X POST "$COCKROACHDB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"DELETE FROM devices WHERE serial = 'OGW-US-001205'\"}"
```

Deleting a device cascades to its events.

## EXPLAIN

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT * FROM devices WHERE crdb_region = 'eu-west-1'\"}"

curl -s -X POST "$COCKROACHDB_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT * FROM device_events WHERE severity = 'error'\", \"analyze\": true, \"verbose\": true}"
```

Reports `distribution` (`local` or `full`), `vectorized`, planning time, and
under `analyze` the actual rows, KV rows/bytes read and memory used. A full scan
is flagged with `"warning": "full scan"`.

## Topology

```bash
curl -s "$COCKROACHDB_API_URL/api/v1/tables/devices/ranges"
curl -s "$COCKROACHDB_API_URL/api/v1/ranges"
curl -s "$COCKROACHDB_API_URL/api/v1/nodes"
curl -s "$COCKROACHDB_API_URL/api/v1/regions"
```

`devices` is `REGIONAL BY ROW` and split into four ranges keyed by
`crdb_region`, each with its own lease holder and replica localities.

## Cluster surface

```bash
curl -s "$COCKROACHDB_API_URL/api/v1/jobs"
curl -s "$COCKROACHDB_API_URL/api/v1/jobs?status=running"
curl -s "$COCKROACHDB_API_URL/api/v1/jobs?job_type=BACKUP"
curl -s "$COCKROACHDB_API_URL/api/v1/cluster/settings"
curl -s "$COCKROACHDB_API_URL/api/v1/cluster/settings?name=kv.rangefeed.enabled"
curl -s "$COCKROACHDB_API_URL/api/v1/statements?order_by=retries&limit=5"
curl -s "$COCKROACHDB_API_URL/api/v1/users"
curl -s "$COCKROACHDB_API_URL/api/v1/grants?user=orbit_readonly"
```

## Schema

```bash
curl -s "$COCKROACHDB_API_URL/api/v1/databases"
curl -s "$COCKROACHDB_API_URL/api/v1/tables"
curl -s "$COCKROACHDB_API_URL/api/v1/tables/devices"
```

Tables: `devices` (`REGIONAL BY ROW`), `device_events`, `firmware_releases`
(`GLOBAL`), `rollouts`, plus the view `fleet_by_region`.

## Users

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -H 'X-CRDB-User: orbit_readonly' -d '{"sql": "DELETE FROM devices WHERE serial = '\''OGW-AP-000077'\''"}'

curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-CRDB-User: orbit_changefeed' -d '{"sql": "SELECT 1"}'
```

`orbit_readonly` is refused with 42501; `orbit_changefeed` is NOLOGIN and
refused with 28000.
