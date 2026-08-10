---
name: cockroachdb-api-connector
description: >
  CockroachDB API (Mock) mock HTTP API. Base URL is provided via the
  `COCKROACHDB_API_URL` environment variable. 20 endpoint(s) across GET, POST.
  Runs real SQL with serializable retries and AS OF SYSTEM TIME.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# CockroachDB API (Mock)

Mock HTTP API in front of a CockroachDB 23.2 cluster (`orbit_fleet`). **All
requests go to the base URL in `$COCKROACHDB_API_URL`.** Statements are executed
by a **real SQL engine**; CockroachDB speaks the PostgreSQL wire protocol, so
SQLSTATE codes, `$n` placeholders, `::` casts and `ILIKE` behave as in Postgres.
Seed data is deterministic.

## Base URL

| Variable | Purpose |
|----------|---------|
| `COCKROACHDB_API_URL` | Base URL for all requests (e.g. `http://cockroachdb-api:8112`) |

## Distributed behaviour you must handle

**Transactions are SERIALIZABLE.** A batch touching the seeded contended device
row (`3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901`) fails its first attempt with
**SQLSTATE 40001** `TransactionRetryWithProtoRefreshError` and `"retryable": true`.
Send the same batch with `"max_retries": 3` — the response then reports
`"retries": 1`. Ignoring 40001 will fail against this service, exactly as it
would against a real cluster.

**`AS OF SYSTEM TIME`** reads the snapshot taken at process start, so after a
write the historical read still returns the original value. Pass it as the
`as_of_system_time` request field or inline in the statement
(`follower_read_timestamp()` works). On a write it is rejected with `0A000`.

## Users

`X-CRDB-User` (or a bearer token); absent or unknown falls back to `orbit_app`.

| User | Privileges |
|------|-----------|
| `root`, `orbit_fleet_admin` | ALL |
| `orbit_app` | SELECT, INSERT, UPDATE, DELETE (default) |
| `orbit_readonly` | SELECT |
| `orbit_changefeed` | NOLOGIN — every statement returns 28000 |

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/query` | Read-only; accepts `as_of_system_time` |
| POST | `/api/v1/execute` | Statement that may write |
| POST | `/api/v1/transaction` | Serializable batch; `priority`, `max_retries` |
| POST | `/api/v1/explain` | `analyze`, `verbose`; reports distribution |
| GET | `/api/v1/databases` · `/tables` · `/tables/{name}` | Schema |
| GET | `/api/v1/tables/{name}/ranges` · `/ranges` | `SHOW RANGES` |
| GET | `/api/v1/nodes` · `/regions` | Topology |
| GET | `/api/v1/jobs` | `SHOW JOBS` (`?status=`, `?job_type=`) |
| GET | `/api/v1/cluster/settings` · `/cluster/status` | Cluster facts |
| GET | `/api/v1/statements` | Statement statistics (`?order_by=retries`) |
| GET | `/api/v1/users` · `/grants` | SQL users and grants |
| GET | `/api/v1/version` · `/health/db` | Version and health |

## Schema — `orbit_fleet`

`devices` (8, `REGIONAL BY ROW`), `device_events` (10), `firmware_releases`
(6, `GLOBAL`), `rollouts` (6), plus the view `fleet_by_region`. Six nodes across
five regions, one down.

## Usage

```bash
# Retryable transaction, handled properly
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d '{"statements": [{"sql": "UPDATE devices SET status = $1 WHERE serial = $2", "params": ["online", "OGW-EU-000412"]}], "max_retries": 3}'

# Historical read
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT serial, status FROM devices", "as_of_system_time": "-10s"}'
```

The audit log of every call the agent makes is available at
`$COCKROACHDB_API_URL/audit/requests` (used for grading).
