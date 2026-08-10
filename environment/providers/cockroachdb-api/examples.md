# CockroachDB Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$COCKROACHDB_API_URL`; responses are verbatim (long arrays elided
with `…`).

The `X-CRDB-User` header selects the SQL user; without it, statements run as
`orbit_app`.

## Cluster health

```bash
curl -s "$COCKROACHDB_API_URL/health/db"
curl -s "$COCKROACHDB_API_URL/api/v1/cluster/status"
```
```json
{"status": "degraded", "engine": "cockroachdb", "server_version": "23.2.5",
 "database": "orbit_fleet", "nodes_live": 5, "nodes_total": 6,
 "dead_nodes": [6], "survival_goal": "REGION FAILURE", "latency_ms": 0.196}
```

The cluster reports `degraded` because node 6 (`ap-southeast-1`) is seeded down.

```json
{"cluster_id": "9f3c1a7e-5b2d-4086-af51-c7e93b0d6248", "cluster_name": "orbit-fleet",
 "version": "CockroachDB CCL v23.2.5 (x86_64-pc-linux-gnu, built 2026/03/18 …)",
 "license_type": "Enterprise", "database": "orbit_fleet",
 "primary_region": "eu-central-1", "survival_goal": "REGION FAILURE",
 "regions": 5, "nodes": 6, "live_nodes": 5, "ranges": 8,
 "total_range_size_mb": 1221.1, "default_isolation_level": "SERIALIZABLE"}
```

## Serializable retries — the behaviour clients must handle

Transactions are SERIALIZABLE. A batch touching the seeded contended device row
loses its first attempt:

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/transaction" \
  -H 'Content-Type: application/json' \
  -d '{"statements": [{"sql": "UPDATE devices SET status = '\''degraded'\'' WHERE id = '\''3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901'\''"}]}'
```
```json
{"error": "restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)",
 "severity": "ERROR", "code": "40001", "sqlstate": "40001",
 "condition": "serialization_failure",
 "hint": "The transaction must be retried by the client. Re-send it with max_retries set, or implement a retry loop keyed on SQLSTATE 40001.",
 "detail": {"attempt": 1,
            "contended_rows": [{"table": "devices", "key": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901"}],
            "isolation_level": "SERIALIZABLE"},
 "retryable": true}
```

The same batch with a retry budget runs the loop and commits:

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/transaction" \
  -H 'Content-Type: application/json' \
  -d '{"statements": [
        {"sql": "UPDATE devices SET status = '\''degraded'\'' WHERE id = '\''3f1c9b52-…'\''"},
        {"sql": "SELECT serial, status FROM devices WHERE id = '\''3f1c9b52-…'\''"}],
      "max_retries": 3}'
```
```json
{"results": [{"command": "UPDATE", "rows_affected": 1, "statement_index": 0, "…": "…"},
             {"command": "SELECT",
              "rows": [{"serial": "OGW-EU-000412", "status": "degraded"}],
              "statement_index": 1, "…": "…"}],
 "statement_count": 2, "isolation_level": "SERIALIZABLE", "priority": "NORMAL",
 "retries": 1,
 "contended_rows": [{"table": "devices", "key": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901"}],
 "rolled_back": false, "committed": true}
```

An uncontended transaction commits on the first attempt with `"retries": 0`.
A failing batch rolls back entirely — a following read shows the write reverted.
An unrecognised `priority` is rejected before anything runs (valid: `LOW`,
`NORMAL`, `HIGH`).

## AS OF SYSTEM TIME

Historical reads come from the snapshot taken at process start, so after the
transaction above the two reads disagree:

```bash
# live
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT serial, status FROM devices WHERE id = '\''3f1c9b52-…'\''"}'

# historical, via the request field
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT serial, status FROM devices WHERE id = '\''3f1c9b52-…'\''",
       "as_of_system_time": "-10s"}'

# historical, inline
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT serial, status FROM devices AS OF SYSTEM TIME '\''-1h'\'' WHERE id = '\''3f1c9b52-…'\''"}'
```
```json
{"rows": [{"serial": "OGW-EU-000412", "status": "degraded"}], "…": "…"}
{"rows": [{"serial": "OGW-EU-000412", "status": "online"}],
 "as_of_system_time": "-10s", "read_type": "historical",
 "note": "historical reads are served from the snapshot taken when the process started"}
{"rows": [{"serial": "OGW-EU-000412", "status": "online"}],
 "as_of_system_time": "-1h", "read_type": "historical", "…": "…"}
```

`follower_read_timestamp()` is accepted too. On a write, `AS OF SYSTEM TIME` is
rejected:

```json
{"error": "AS OF SYSTEM TIME is only supported for reads", "code": "0A000",
 "condition": "feature_not_supported"}
```

## Queries

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT crdb_region, count(*) AS devices FROM devices GROUP BY crdb_region ORDER BY devices DESC, crdb_region"}'
```
```json
{"command": "SELECT",
 "columns": [{"name": "crdb_region", "type": "STRING"}, {"name": "devices", "type": "INT8"}],
 "rows": [{"crdb_region": "eu-central-1", "devices": 2},
          {"crdb_region": "eu-west-1", "devices": 2},
          {"crdb_region": "us-west-2", "devices": 2},
          {"crdb_region": "ap-southeast-1", "devices": 1},
          {"crdb_region": "us-east-1", "devices": 1}],
 "row_count": 5, "user": "orbit_app", "…": "…"}
```

`$n` placeholders, `::` casts, `ILIKE` and `now()` are rewritten before
execution; `gen_random_uuid()` and `unique_rowid()` are registered functions.

```bash
# Devices still on a stale stable release
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT d.serial, d.firmware_version, f.channel FROM devices d JOIN firmware_releases f ON f.version = d.firmware_version WHERE f.version <> '4.8.1' AND f.channel = 'stable' ORDER BY d.serial\"}"
```

## Ranges, nodes and regions

```bash
curl -s "$COCKROACHDB_API_URL/api/v1/tables/devices/ranges"
```
```json
{"ranges": [{"range_id": 412, "table_name": "devices",
             "start_key": "/Table/106/1", "end_key": "/Table/106/1/\"eu-central-1\"",
             "replicas": [1, 2, 3],
             "replica_localities": ["eu-central-1", "eu-central-1", "eu-west-1"],
             "lease_holder": 1, "lease_holder_locality": "region=eu-central-1,az=a",
             "range_size_mb": 128.4, "voting_replicas": [1, 2, 3],
             "non_voting_replicas": []},
            {"range_id": 413, "end_key": "/Table/106/1/\"eu-west-1\"",
             "lease_holder": 2, "non_voting_replicas": [4], "…": "…"}, "…"],
 "count": 4, "total_size_mb": 417.4}
```

`devices` is split on `crdb_region` — the shape a `REGIONAL BY ROW` table takes.

```bash
curl -s "$COCKROACHDB_API_URL/api/v1/nodes"
curl -s "$COCKROACHDB_API_URL/api/v1/regions"
```
```json
{"nodes": [{"node_id": 1, "address": "10.42.1.11:26257",
            "locality": "region=eu-central-1,az=a", "is_live": true,
            "ranges": 412, "leases": 138, "build_tag": "v23.2.5",
            "cpu_percent": 0.34, "used_bytes": 18253611008, "…": "…"}, "…"],
 "count": 6, "live_count": 5, "dead_nodes": [6]}

{"regions": [{"region": "eu-central-1", "zones": ["a", "b"], "nodes": 2,
              "primary": true, "live_nodes": 2, "node_ids": [1, 2]},
             {"region": "ap-southeast-1", "zones": ["a"], "nodes": 1,
              "primary": false, "live_nodes": 0, "node_ids": [6]}, "…"],
 "primary_region": "eu-central-1", "survival_goal": "REGION FAILURE", "count": 5}
```

## EXPLAIN

```bash
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"SELECT * FROM device_events WHERE severity = 'error'\", \"analyze\": true, \"verbose\": true}"
```
```json
{"plan": [{"operator": "scan", "table": "device_events", "spans": "1 span",
           "index": "idx_events_severity", "estimated_row_count": 2,
           "actual_row_count": 2, "execution_time_ms": 0.412,
           "kv_rows_read": 2, "kv_bytes_read": 256,
           "columns": "all", "ordering": "+id"}],
 "distribution": "local", "vectorized": true, "planning_time_ms": 0.184,
 "execution_time_ms": 0.412, "max_memory_used_kb": 20, "network_bytes_sent": 0}
```

A predicate the indexes cannot serve reports `"spans": "FULL SCAN"`,
`"warning": "full scan"` and `"distribution": "full"`.

## Jobs, settings and statement statistics

```bash
curl -s "$COCKROACHDB_API_URL/api/v1/jobs?status=running"
curl -s "$COCKROACHDB_API_URL/api/v1/cluster/settings?name=kv.rangefeed.enabled"
curl -s "$COCKROACHDB_API_URL/api/v1/statements?order_by=retries&limit=3"
```
```json
{"jobs": [{"job_id": "984127553012891653", "job_type": "ROW LEVEL TTL",
           "description": "ttl for orbit_fleet.public.device_events",
           "status": "running", "running_status": "deleting rows",
           "fraction_completed": 0.61, "…": "…"},
          {"job_id": "984127553012891649", "job_type": "CHANGEFEED",
           "description": "CREATE CHANGEFEED FOR TABLE device_events INTO 'kafka://…'",
           "high_water_timestamp": "2026-05-26T08:30:58Z", "…": "…"}],
 "count": 2}

{"variable": "kv.rangefeed.enabled", "value": "true", "type": "b",
 "description": "if set, rangefeed registration is enabled"}

{"statements": [{"fingerprint_id": "a41f7c885be942d7",
                 "query": "UPDATE devices SET last_seen_at = now(), status = $1 WHERE id = $2",
                 "count": 18204881, "retries": 8412,
                 "service_lat_p99_ms": 88.12, "full_scan": false,
                 "distributed": false, "implicit_txn": false}, "…"],
 "count": 5, "order_by": "retries"}
```

The statement with the most retries is the one updating a device row — the same
contention the transaction endpoint reproduces.

## Users

```bash
curl -s "$COCKROACHDB_API_URL/api/v1/users"
curl -s -X POST "$COCKROACHDB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-CRDB-User: orbit_changefeed' -d '{"sql": "SELECT 1"}'
```
```json
{"users": [{"username": "root", "options": "CREATEROLE", "member_of": "admin", "login": true},
           {"username": "orbit_changefeed", "options": "NOLOGIN", "login": false}, "…"],
 "count": 5}

{"error": "user orbit_changefeed does not have login privilege",
 "code": "28000", "condition": "invalid_authorization_specification"}
```
