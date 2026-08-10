# MariaDB Mock API — Test Results

Base URL: `http://localhost:8111` (in docker-compose: `http://mariadb-api:8111`)

## Endpoints covered

| Method | Path                                | Status              |
|--------|-------------------------------------|---------------------|
| GET    | /health                             | 200                 |
| GET    | /health/db                          | 200                 |
| GET    | /api/v1/version                     | 200                 |
| GET    | /api/v1/status                      | 200                 |
| POST   | /api/v1/query                       | 200/400/403/404     |
| POST   | /api/v1/execute                     | 200/400/403/404/409 |
| POST   | /api/v1/transaction                 | 200/400/403/409     |
| POST   | /api/v1/explain                     | 200/400/403/404     |
| GET    | /api/v1/sequences                   | 200                 |
| POST   | /api/v1/sequences/{name}/next       | 200/400/404         |
| GET    | /api/v1/databases                   | 200                 |
| GET    | /api/v1/tables                      | 200                 |
| GET    | /api/v1/tables/{name}               | 200/404             |
| GET    | /api/v1/tables/{name}/indexes       | 200/404             |
| GET    | /api/v1/variables                   | 200                 |
| GET    | /api/v1/status/counters             | 200                 |
| GET    | /api/v1/engines                     | 200                 |
| GET    | /api/v1/replication                 | 200/403             |
| GET    | /api/v1/accounts                    | 200                 |
| GET    | /api/v1/grants                      | 200/403/404         |

Collection run: **PASS 42 / WARN 17 / FAIL 0 / SKIP 0**. All seventeen WARNs are
intentional error-path requests.

## What makes this MariaDB rather than MySQL

The wire format and most error numbers are shared, so the interesting part is
where MariaDB actually behaves differently. Three divergences are modelled here,
and all three change behaviour rather than just strings.

### 1. Sequences

MySQL has none. Here they are real, backed by `sequences` rows:

- `NEXT VALUE FOR seq` and `NEXTVAL(seq)` allocate and advance
- `LASTVAL(seq)` reads the last allocated value
- `SETVAL(seq, n)` repositions, validating against the bounds
- `moderation_case_seq` has `cycle_option` set and a maximum of 999, so it wraps
- Exhausting a non-cycling sequence returns 4084 `ER_SEQUENCE_RUN_OUT`
- Referencing an unknown sequence returns 1146, because a MariaDB sequence *is*
  a table

Every response that touched a sequence carries a `sequence_allocations` array,
and a rolled-back transaction reports that its allocations are **not** returned —
which is how sequences behave in a real server.

`POST /api/v1/sequences/{name}/next` exposes the same allocation over REST.

### 2. RETURNING

Supported on `INSERT` and `DELETE`:

```sql
DELETE FROM page_views WHERE id = 8 RETURNING id, path, views
```

`UPDATE ... RETURNING` is **rejected** with 1064 and the hint
`RETURNING is available on INSERT and DELETE only` — because MariaDB does not
implement it for UPDATE either.

### 3. Non-transactional Aria tables

`page_views` is an Aria table. Aria is not transactional, so a write to it
survives a rolled-back transaction. The collection demonstrates it directly:

| Step | `threads.views` (InnoDB) | `page_views.views` (Aria) |
|------|--------------------------|---------------------------|
| Before the transaction | 4821 | 412 |
| Transaction adds 100 to each, then fails on a duplicate key | rolled back | kept |
| After | **4821** | **512** |

The failing response carries `non_transactional_writes_kept` listing exactly
which statements survived, plus a warning explaining why.

## Schema — `orbit_forum`

| Table | Rows | Engine | Notes |
|-------|------|--------|-------|
| `forum_users` | 7 | InnoDB | `UNIQUE(username)`, `UNIQUE(email)`, one banned |
| `categories` | 5 | InnoDB | `UNIQUE(slug)`, two locked |
| `threads` | 7 | InnoDB | FKs to categories and users, `UNIQUE(slug)` |
| `posts` | 10 | InnoDB | Cascades from threads, `accepted` flag |
| `kb_articles` | 5 | InnoDB | draft / published / archived |
| `article_revisions` | 9 | InnoDB | `UNIQUE (article_id, version)`, cascades |
| `page_views` | 8 | **Aria** | `UNIQUE (path, viewed_on)` — non-transactional |

Plus the view `thread_activity`, five indexes and three sequences.

`GET /api/v1/tables` reports each table's `ENGINE` and a `TRANSACTIONAL` flag, so
the Aria table is identifiable before you write to it.

## Accounts

`X-MariaDB-User` (or a bearer token) selects the account; absent or unknown falls
back to `forum_app`. Accounts come from `mysql.global_priv`, which is where
MariaDB 10.4+ keeps them.

| Account | Host | Privileges |
|---------|------|-----------|
| `root` | `localhost` | ALL, including SUPER and REPLICATION CLIENT |
| `forum_app` | `%` | SELECT, INSERT, UPDATE, DELETE (default) |
| `forum_mod` | `10.42.%` | SELECT, UPDATE, DELETE |
| `forum_analytics` | `10.42.0.44` | SELECT on `page_views`, `threads`, `categories` only |
| `forum_import` | `%` | **locked** — every statement returns 4151 |

## Errors

| Condition | errno | Name | SQLSTATE | HTTP |
|-----------|-------|------|----------|------|
| Duplicate key | 1062 | `ER_DUP_ENTRY` | 23000 | 409 |
| Foreign key failure | 1452 | `ER_NO_REFERENCED_ROW_2` | 23000 | 409 |
| Null in NOT NULL column | 1048 | `ER_BAD_NULL_ERROR` | 23000 | 400 |
| Check constraint | 4025 | `ER_CONSTRAINT_FAILED` | 23000 | 400 |
| Unknown table or sequence | 1146 | `ER_NO_SUCH_TABLE` | 42S02 | 404 |
| Unknown column | 1054 | `ER_BAD_FIELD_ERROR` | 42S22 | 400 |
| Parse error | 1064 | `ER_PARSE_ERROR` | 42000 | 400 |
| Table access denied | 1142 | `ER_TABLEACCESS_DENIED_ERROR` | 42000 | 403 |
| Account locked | 4151 | `ER_ACCOUNT_HAS_BEEN_LOCKED` | HY000 | 403 |
| Sequence exhausted | 4084 | `ER_SEQUENCE_RUN_OUT` | HY000 | 400 |
| Sequence value conflict | 4086 | `ER_SEQUENCE_INVALID_DATA` | HY000 | 400 |

Note `ER_CONSTRAINT_FAILED` (4025) rather than MySQL's 3819, and
`ER_ACCOUNT_HAS_BEEN_LOCKED` at 4151 rather than 3118 — MariaDB numbers its own
errors from 4000 upward.

## Notes

- `POST /api/v1/explain` with `"analyze": true` returns MariaDB's `ANALYZE`
  output, adding `r_rows` (rows actually read) beside the estimate — a
  MariaDB-only feature.
- `SHOW ENGINES` lists MariaDB's set including Aria, SEQUENCE and CONNECT, and
  the response calls out which engines are non-transactional.
- Replication uses MariaDB's GTID format (`0-1-88412003`, domain-server-sequence)
  and `Slave_IO_Running` / `Seconds_Behind_Master` field names, with a named
  `backup` replica connection.
- MariaDB builtins are registered as real SQL functions: `CONCAT`, `CONCAT_WS`,
  `NOW`, `CURDATE`, `DATE_FORMAT`, `YEAR`, `GREATEST`, `LEAST`. Backticks and
  `LIMIT offset, count` are accepted as written.
- Sessions do not persist between requests; `/api/v1/transaction` is the unit of work.
- Mutations are held in process memory and reset on container restart.
