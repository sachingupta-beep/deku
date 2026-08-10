# MariaDB Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$MARIADB_API_URL`; responses are verbatim (long arrays elided
with `…`).

The `X-MariaDB-User` header selects the account; without it, statements run as
`forum_app`.

## Health and version

```bash
curl -s "$MARIADB_API_URL/health/db"
curl -s "$MARIADB_API_URL/api/v1/version"
```
```json
{"status": "ok", "engine": "mariadb", "version": "10.11.7", "database": "orbit_forum",
 "threads_connected": 22, "gtid_current_pos": "0-1-88412003",
 "max_seconds_behind_master": 4, "latency_ms": 0.187}
{"version": "10.11.7-MariaDB-1:10.11.7+maria~ubu2204", "version_short": "10.11.7",
 "version_comment": "mariadb.org binary distribution",
 "version_compile_os": "debian-linux-gnu", "version_compile_machine": "x86_64"}
```

## Sequences — a MariaDB feature MySQL does not have

```bash
curl -s "$MARIADB_API_URL/api/v1/sequences"
```
```json
{"sequences": [{"name": "thread_number_seq", "start_value": 5000, "increment": 1,
                "minimum_value": 1, "maximum_value": 9223372036854775806,
                "cache_size": 1000, "cycle_option": false,
                "next_not_cached_value": 5008, "last_value": 5007},
               {"name": "kb_version_seq", "next_not_cached_value": 7, "last_value": 6, "…": "…"},
               {"name": "moderation_case_seq", "minimum_value": 100,
                "maximum_value": 999, "cycle_option": true, "…": "…"}],
 "count": 3}
```

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT NEXT VALUE FOR thread_number_seq AS next_thread"}'
```
```json
{"command": "SELECT", "columns": [{"name": "next_thread", "type": "BIGINT"}],
 "rows": [{"next_thread": 5008}], "row_count": 1,
 "sequence_allocations": [{"sequence": "thread_number_seq", "value": 5008,
                           "operation": "nextval"}], "…": "…"}
```

`NEXTVAL()`, `LASTVAL()` and `SETVAL()` work too, and a sequence composes into a
statement — here combined with `RETURNING`:

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"INSERT INTO threads (id, category_id, author_id, title, slug, status, views, reply_count, pinned, created_at, last_post_at) VALUES (NEXT VALUE FOR thread_number_seq, 3, 4, 'Webhook retries after 429', 'webhook-retries-after-429', 'open', 0, 0, 0, '2026-05-26 09:10:00', '2026-05-26 09:10:00') RETURNING id, title\"}"
```
```json
{"command": "INSERT", "rows": [{"id": 5009, "title": "Webhook retries after 429"}],
 "affected_rows": 1,
 "sequence_allocations": [{"sequence": "thread_number_seq", "value": 5009,
                           "operation": "nextval"}], "…": "…"}
```

The same allocation is available over REST:

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/sequences/moderation_case_seq/next"
```
```json
{"sequence": "moderation_case_seq", "value": 104, "next_not_cached_value": 105}
```

A sequence *is* a table in MariaDB, so an unknown one reports 1146:

```json
{"error": "Table 'orbit_forum.ticket_seq' doesn't exist", "errno": 1146,
 "sqlstate": "42S02", "error_name": "ER_NO_SUCH_TABLE"}
```

## RETURNING

Supported on INSERT and DELETE:

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"INSERT INTO categories (id, slug, name, description, sort_order, locked) VALUES (6, 'showcase', 'Showcase', 'Built with Orbit', 5, 0) RETURNING id, slug, name\"}"

curl -s -X POST "$MARIADB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "DELETE FROM page_views WHERE id = 8 RETURNING id, path, views"}'
```
```json
{"command": "INSERT", "rows": [{"id": 6, "slug": "showcase", "name": "Showcase"}],
 "affected_rows": 1, "insert_id": 6, "…": "…"}
{"command": "DELETE", "rows": [{"id": 8, "path": "/kb/api-rate-limits", "views": 812}],
 "affected_rows": 1, "…": "…"}
```

Not on UPDATE — MariaDB does not implement it, and neither does this service:

```json
{"error": "You have an error in your SQL syntax; RETURNING is not supported for UPDATE in MariaDB",
 "errno": 1064, "sqlstate": "42000", "error_name": "ER_PARSE_ERROR",
 "hint": "RETURNING is available on INSERT and DELETE only"}
```

## Aria is not transactional

`page_views` uses the Aria engine, so a write to it survives a rolled-back
transaction. This is reproducible end to end.

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT (SELECT views FROM threads WHERE id = 5001) AS innodb_views, (SELECT views FROM page_views WHERE id = 1) AS aria_views"}'
```
```json
{"rows": [{"innodb_views": 4821, "aria_views": 412}], "…": "…"}
```

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d "{\"statements\": [
        {\"sql\": \"UPDATE threads SET views = views + 100 WHERE id = 5001\"},
        {\"sql\": \"UPDATE page_views SET views = views + 100 WHERE id = 1\"},
        {\"sql\": \"INSERT INTO categories (id, slug, name, sort_order, locked) VALUES (1, 'dup', 'Dup', 1, 0)\"}],
      \"isolation_level\": \"REPEATABLE READ\"}"
```
```json
{"error": "Duplicate entry for key 'PRIMARY'", "errno": 1062, "sqlstate": "23000",
 "error_name": "ER_DUP_ENTRY", "statement_index": 2, "rolled_back": true,
 "non_transactional_writes_kept": [
   {"statement_index": 1,
    "sql": "UPDATE page_views SET views = views + 100 WHERE id = 1",
    "tables": ["page_views"]}],
 "warning": "statements against Aria tables are not transactional and were not rolled back"}
```

Re-reading the same counters shows the asymmetry:

```json
{"rows": [{"innodb_views": 4821, "aria_views": 512}], "…": "…"}
```

InnoDB reverted; Aria kept the increment. `GET /api/v1/tables` reports each
table's `ENGINE` and `TRANSACTIONAL` flag, so this is predictable before you write.

## Queries

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT c.name AS category, COUNT(*) AS threads, SUM(t.views) AS views FROM threads t JOIN categories c ON c.id = t.category_id GROUP BY c.id ORDER BY views DESC"}'
```
```json
{"rows": [{"category": "Announcements", "threads": 1, "views": 18402},
          {"category": "Getting Started", "threads": 1, "views": 9128},
          {"category": "Hardware", "threads": 2, "views": 4825}, "…"], "…": "…"}
```

```bash
# Accepted answers, highest scoring first
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT t.title, u.display_name AS answered_by, p.score FROM posts p JOIN threads t ON t.id = p.thread_id JOIN forum_users u ON u.id = p.author_id WHERE p.accepted = 1 ORDER BY p.score DESC"}'
```

`CONCAT`, `DATE_FORMAT`, backticks and `LIMIT offset, count` all work as written.

## Accounts

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-MariaDB-User: forum_analytics' \
  -d '{"sql": "SELECT viewed_on, SUM(views) AS views FROM page_views GROUP BY viewed_on ORDER BY viewed_on"}'
```
```json
{"rows": [{"viewed_on": "2026-05-25", "views": 2702},
          {"viewed_on": "2026-05-26", "views": 4181}],
 "user": "forum_analytics", "…": "…"}
```

Tables outside the grant list are denied, with MariaDB's backtick-quoted form:

```json
{"error": "SELECT command denied to user 'forum_analytics'@'10.42.0.44' for table `orbit_forum`.`posts`",
 "errno": 1142, "sqlstate": "42000", "error_name": "ER_TABLEACCESS_DENIED_ERROR"}
```

The locked account fails first, with MariaDB's own error number:

```json
{"error": "Access denied, this account is locked", "errno": 4151,
 "sqlstate": "HY000", "error_name": "ER_ACCOUNT_HAS_BEEN_LOCKED"}
```

## EXPLAIN and ANALYZE

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM threads WHERE category_id = 3"}'

curl -s -X POST "$MARIADB_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM posts WHERE thread_id = 5001", "analyze": true}'
```
```json
{"format": "explain", "rows": [{"id": 1, "select_type": "SIMPLE", "table": "threads",
                                "type": "ref", "key": "idx_threads_category",
                                "rows": 1, "Extra": "Using index condition"}]}
{"format": "analyze", "rows": [{"id": 1, "table": "posts", "type": "ref",
                                "key": "idx_posts_thread", "rows": 1,
                                "r_rows": 3, "r_filtered": 100.0, "filtered": 100.0}],
 "r_total_rows": 3}
```

`ANALYZE` adds `r_rows` — the rows actually read — beside the estimate. That
comparison is MariaDB-only.

## Engines and replication

```bash
curl -s "$MARIADB_API_URL/api/v1/engines"
```
```json
{"engines": [{"Engine": "InnoDB", "Support": "DEFAULT", "Transactions": "YES", "…": "…"},
             {"Engine": "Aria", "Support": "YES", "Transactions": "NO",
              "Comment": "Crash-safe tables with MyISAM heritage…"},
             {"Engine": "SEQUENCE", "Support": "YES", "Transactions": "YES", "…": "…"},
             {"Engine": "CONNECT", "…": "…"}],
 "count": 8,
 "non_transactional": ["Aria", "CONNECT", "CSV", "MEMORY", "MRG_MyISAM", "MyISAM"]}
```

```bash
curl -s "$MARIADB_API_URL/api/v1/replication" -H 'X-MariaDB-User: root'
```
```json
{"gtid_binlog_pos": "0-1-88412003", "gtid_current_pos": "0-1-88412003",
 "binlog_file": "mariadb-bin.000318", "binlog_position": 412088993,
 "replicas": [{"Connection_name": "", "Server_id": 2, "Host": "10.42.0.22",
               "Slave_IO_Running": "Yes", "Slave_SQL_Running": "Yes",
               "Seconds_Behind_Master": 0, "Using_Gtid": "Slave_Pos",
               "Gtid_IO_Pos": "0-1-88412003"},
              {"Connection_name": "backup", "Server_id": 3,
               "Seconds_Behind_Master": 4, "Gtid_IO_Pos": "0-1-88411994", "…": "…"}],
 "replica_count": 2}
```

MariaDB's GTID is `domain-server-sequence`, not MySQL's UUID:range, and multi-source
replication gives each connection a name.

## Metadata

```bash
curl -s "$MARIADB_API_URL/api/v1/tables/page_views"
curl -s "$MARIADB_API_URL/api/v1/variables?like=aria%"
curl -s "$MARIADB_API_URL/api/v1/status/counters?like=Aria%"
curl -s "$MARIADB_API_URL/api/v1/accounts" -H 'X-MariaDB-User: root'
curl -s "$MARIADB_API_URL/api/v1/grants?user=forum_analytics" -H 'X-MariaDB-User: root'
```
```json
{"TABLE_NAME": "page_views", "ENGINE": "Aria", "TRANSACTIONAL": "NO",
 "TABLE_ROWS": 8, "DATA_LENGTH": 268435456, "AUTO_INCREMENT": 9,
 "columns": [{"Field": "path", "Type": "varchar(255)", "Key": "UNI", "…": "…"}, "…"],
 "privileges": ["DELETE", "INSERT", "SELECT", "UPDATE"], "…": "…"}

{"variables": [{"Variable_name": "aria_pagecache_buffer_size", "Value": "134217728"},
               {"Variable_name": "aria_group_commit", "Value": "none"}], "count": 2}

{"user": "`forum_analytics`@`10.42.0.44`",
 "grants": ["GRANT SELECT ON orbit_forum.page_views, SELECT ON orbit_forum.threads, SELECT ON orbit_forum.categories TO `forum_analytics`@`10.42.0.44`",
            "GRANT SELECT ON `orbit_forum`.`page_views` TO `forum_analytics`@`10.42.0.44`", "…"],
 "count": 4}
```

Accounts come from `mysql.global_priv`, which is where MariaDB 10.4+ keeps them.
