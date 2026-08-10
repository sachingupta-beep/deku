# CockroachDB Mock API — Test Results

Base URL: `http://localhost:8112` (in docker-compose: `http://cockroachdb-api:8112`)

## Endpoints covered

| Method | Path                              | Status              |
|--------|-----------------------------------|---------------------|
| GET    | /health                           | 200                 |
| GET    | /health/db                        | 200                 |
| GET    | /api/v1/version                   | 200                 |
| POST   | /api/v1/query                     | 200/400/403/404     |
| POST   | /api/v1/execute                   | 200/400/403/404/409 |
| POST   | /api/v1/transaction               | 200/400/403/409     |
| POST   | /api/v1/explain                   | 200/400/403/404     |
| GET    | /api/v1/databases                 | 200                 |
| GET    | /api/v1/tables                    | 200                 |
| GET    | /api/v1/tables/{name}             | 200/404             |
| GET    | /api/v1/tables/{name}/ranges      | 200/404             |
| GET    | /api/v1/ranges                    | 200                 |
| GET    | /api/v1/nodes                     | 200                 |
| GET    | /api/v1/regions                   | 200                 |
| GET    | /api/v1/jobs                      | 200                 |
| GET    | /api/v1/cluster/settings          | 200/404             |
| GET    | /api/v1/cluster/status            | 200                 |
| GET    | /api/v1/statements                | 200/400             |
| GET    | /api/v1/users                     | 200                 |
| GET    | /api/v1/grants                    | 200/404             |

Collection run: **PASS 40 / WARN 18 / FAIL 0 / SKIP 0**. All eighteen WARNs are
intentional error-path requests.

## What makes this CockroachDB rather than PostgreSQL

CockroachDB speaks the PostgreSQL wire protocol, so SQLSTATE codes, `$n`
placeholders, `::` casts and `ILIKE` behave exactly as in `postgresql-api`. The
service earns its own entry by modelling what is *distributed*, and each of
these changes behaviour rather than adding a decorative field.

### SERIALIZABLE by default, with real retry errors

Transactions are SERIALIZABLE — CockroachDB has no weaker default. A transaction
touching a **contended row** loses its first attempt:

```json
{"code": "40001", "condition": "serialization_failure",
 "error": "restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)",
 "hint": "The transaction must be retried by the client. Re-send it with max_retries set, or implement a retry loop keyed on SQLSTATE 40001.",
 "detail": {"attempt": 1, "contended_rows": [{"table": "devices", "key": "3f1c9b52-…"}],
            "isolation_level": "SERIALIZABLE"},
 "retryable": true}
```

Sending the same batch with `"max_retries": 3` runs the loop a driver would run
and succeeds, reporting `"retries": 1`. This is the behaviour CockroachDB clients
must implement, so an agent that ignores 40001 will visibly fail here.

The contended row is seeded in `cluster.json` under `contention`, so it is
deterministic rather than random.

### AS OF SYSTEM TIME

Historical reads are served from a snapshot captured at process start, before any
request can mutate the store. The collection demonstrates the difference:

| Read | `devices.status` for `OGW-EU-000412` |
|------|--------------------------------------|
| Before the transaction | `online` |
| After the transaction commits | `degraded` |
| `AS OF SYSTEM TIME '-10s'` | **`online`** |
| `AS OF SYSTEM TIME '-1h'` | **`online`** |

Accepted both as a request field (`as_of_system_time`) and inline in the
statement, including `follower_read_timestamp()`. Any timestamp resolves to the
same snapshot — the mock keeps exactly one historical version, which is stated in
the response `note`. `AS OF SYSTEM TIME` on a write is rejected with `0A000`,
as CockroachDB rejects it.

### Ranges, nodes and regions

- `SHOW RANGES` with `start_key`/`end_key`, replica sets, replica localities,
  lease holder and lease-holder locality, and non-voting replicas
- `devices` is split into four ranges keyed by `crdb_region` — the shape a
  `REGIONAL BY ROW` table actually takes
- Six nodes across five regions, **one deliberately down** (`node 6`,
  `ap-southeast-1`), which is why `/health/db` reports `degraded`
- `SHOW REGIONS` reports zones, node ids and live counts per region, plus the
  primary region and `REGION FAILURE` survival goal
- Per-table localities: `REGIONAL BY ROW`, `REGIONAL BY TABLE IN PRIMARY REGION`,
  `GLOBAL`

### Cluster surface

`SHOW JOBS` (changefeed, schema change, backup, restore, row-level TTL — with one
failed and one canceled), `SHOW CLUSTER SETTINGS`, `crdb_internal` statement
statistics including per-fingerprint `retries` and `full_scan` flags, `SHOW USERS`
and `SHOW GRANTS`.

## Schema — `orbit_fleet`

| Table | Rows | Locality | Notes |
|-------|------|----------|-------|
| `devices` | 8 | `REGIONAL BY ROW` | `uuid` PK, `UNIQUE(serial)`, FK to firmware |
| `device_events` | 10 | `REGIONAL BY TABLE` | Cascades from devices |
| `firmware_releases` | 6 | `GLOBAL` | PK is `version`; one yanked |
| `rollouts` | 6 | `REGIONAL BY TABLE` | `UNIQUE (firmware_version, crdb_region)` |

Plus the view `fleet_by_region` and four indexes. CockroachDB type names
(`uuid`, `string`, `int8`, `timestamptz`, `bool`) are reported verbatim by the
schema endpoints, and result columns are typed `STRING` / `INT8` / `DECIMAL`.

## Users

`X-CRDB-User` (or a bearer token); absent or unknown falls back to `orbit_app`.

| User | Privileges |
|------|-----------|
| `root` | ALL |
| `orbit_app` | SELECT, INSERT, UPDATE, DELETE (default) |
| `orbit_readonly` | SELECT |
| `orbit_fleet_admin` | ALL, member of `admin` |
| `orbit_changefeed` | **NOLOGIN** — every statement returns 28000 |

## Errors

| Condition | SQLSTATE | HTTP |
|-----------|----------|------|
| `serialization_failure` (retryable) | **40001** | 409 |
| `unique_violation` | 23505 | 409 |
| `foreign_key_violation` | 23503 | 409 |
| `check_violation` | 23514 | 400 |
| `undefined_table` | 42P01 | 404 |
| `undefined_column` | 42703 | 400 |
| `syntax_error` | 42601 | 400 |
| `insufficient_privilege` | 42501 | 403 |
| `invalid_authorization_specification` (NOLOGIN) | 28000 | 403 |
| `feature_not_supported` | 0A000 | 400/403 |
| `undefined_object` | 42704 | 404 |

## Notes

- Results are `{"command", "columns", "rows", "row_count", "rows_affected",
  "truncated", "duration_ms", "user"}`; a historical read adds
  `as_of_system_time`, `read_type` and `note`.
- `POST /api/v1/explain` accepts `analyze` and `verbose`, and reports
  `distribution` (`local` or `full`), `vectorized`, planning time, and — under
  `analyze` — actual rows, KV rows/bytes read and memory used. A full scan is
  flagged with `"warning": "full scan"`.
- `gen_random_uuid()` and `unique_rowid()` are registered as real SQL functions.
- Sessions do not persist between requests; `/api/v1/transaction` is the unit of work.
- Mutations are held in process memory and reset on container restart.
