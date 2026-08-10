---
name: mariadb-api-connector
description: >
  MariaDB API (Mock) mock HTTP API. Base URL is provided via the
  `MARIADB_API_URL` environment variable. 20 endpoint(s) across GET, POST.
  Runs real SQL, with sequences, RETURNING and non-transactional Aria tables.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# MariaDB API (Mock)

Mock HTTP API in front of a MariaDB 10.11 database (`orbit_forum`). **All
requests go to the base URL in `$MARIADB_API_URL`.** Statements are executed by
a **real SQL engine**. Seed data is deterministic.

MySQL-compatible where MariaDB is; the differences that matter are implemented,
not just labelled.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MARIADB_API_URL` | Base URL for all requests (e.g. `http://mariadb-api:8111`) |

## Accounts

`X-MariaDB-User` (or a bearer token) selects the account; absent or unknown
falls back to `forum_app`. Accounts live in `mysql.global_priv`.

| Account | Host | Privileges |
|---------|------|-----------|
| `root` | `localhost` | ALL, including SUPER and REPLICATION CLIENT |
| `forum_app` | `%` | SELECT, INSERT, UPDATE, DELETE (default) |
| `forum_mod` | `10.42.%` | SELECT, UPDATE, DELETE |
| `forum_analytics` | `10.42.0.44` | SELECT on `page_views`, `threads`, `categories` only |
| `forum_import` | `%` | locked — every statement returns 4151 |

## MariaDB-specific behaviour

**Sequences.** `NEXT VALUE FOR seq`, `NEXTVAL(seq)`, `LASTVAL(seq)` and
`SETVAL(seq, n)` are real. Seeded: `thread_number_seq`, `kb_version_seq`,
`moderation_case_seq` (cycles at 999). Responses carry `sequence_allocations`.
An unknown sequence returns 1146, because a sequence is a table.

**RETURNING** works on INSERT and DELETE. `UPDATE … RETURNING` is rejected with
1064 — MariaDB does not implement it.

**Aria is not transactional.** `page_views` is an Aria table, so a write to it
**survives a rolled-back transaction**. The failing response lists
`non_transactional_writes_kept`. `GET /api/v1/tables` reports each table's
`ENGINE` and `TRANSACTIONAL` flag.

**ANALYZE.** `POST /api/v1/explain` with `"analyze": true` adds `r_rows` — rows
actually read — beside the estimate.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/query` | Read-only statement |
| POST | `/api/v1/execute` | Statement that may write |
| POST | `/api/v1/transaction` | Batch with an `isolation_level` |
| POST | `/api/v1/explain` | `EXPLAIN`, or `ANALYZE` with `"analyze": true` |
| GET | `/api/v1/sequences` | Sequence definitions and current values |
| POST | `/api/v1/sequences/{name}/next` | Allocate the next value |
| GET | `/api/v1/databases` · `/tables` · `/tables/{name}` · `/tables/{name}/indexes` | Schema |
| GET | `/api/v1/variables` · `/status/counters` | `SHOW VARIABLES` / `SHOW STATUS`, `?like=` |
| GET | `/api/v1/engines` | Engines, with the non-transactional ones called out |
| GET | `/api/v1/replication` | GTID, binlog and replicas (REPLICATION CLIENT) |
| GET | `/api/v1/accounts` · `/grants` | `mysql.global_priv` and grants |
| GET | `/api/v1/status` · `/api/v1/version` · `/health/db` | Server facts |

## Schema — `orbit_forum`

`forum_users` (7), `categories` (5), `threads` (7), `posts` (10),
`kb_articles` (5), `article_revisions` (9) on InnoDB, plus `page_views` (8) on
**Aria**. View: `thread_activity`.

## Usage

```bash
# Sequence + RETURNING in one statement
curl -s -X POST "$MARIADB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"INSERT INTO categories (id, slug, name, sort_order, locked) VALUES (NEXT VALUE FOR moderation_case_seq, 'x', 'X', 9, 0) RETURNING id, slug\"}"

# Query
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM thread_activity ORDER BY last_post_at DESC"}'
```

Errors carry `errno`, `error_name` and `sqlstate`. MariaDB numbers its own
errors from 4000 up: 4025 `ER_CONSTRAINT_FAILED`, 4084 `ER_SEQUENCE_RUN_OUT`,
4151 `ER_ACCOUNT_HAS_BEEN_LOCKED`.

The audit log of every call the agent makes is available at
`$MARIADB_API_URL/audit/requests` (used for grading).
