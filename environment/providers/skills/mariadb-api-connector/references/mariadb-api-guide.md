# MariaDB API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$MARIADB_API_URL`.** Statements are executed by a real SQL engine and the seed data is deterministic.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MARIADB_API_URL` | Base URL for all requests |

## Health, version, status

```bash
curl -s "$MARIADB_API_URL/health"
curl -s "$MARIADB_API_URL/health/db"
curl -s "$MARIADB_API_URL/api/v1/version"
curl -s "$MARIADB_API_URL/api/v1/status"
```

## Queries

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, username, role, reputation FROM forum_users WHERE banned = 0 ORDER BY reputation DESC"}'

curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT c.name AS category, COUNT(*) AS threads, SUM(t.views) AS views FROM threads t JOIN categories c ON c.id = t.category_id GROUP BY c.id ORDER BY views DESC"}'

curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT id, title, views FROM threads WHERE status = ? AND views > ?", "params": ["answered", 1000]}'

curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM thread_activity ORDER BY last_post_at DESC"}'
```

`CONCAT`, `CONCAT_WS`, `NOW`, `CURDATE`, `DATE_FORMAT`, `YEAR`, `GREATEST` and
`LEAST` are registered functions. Backticks and `LIMIT offset, count` work as written.

## Sequences

```bash
curl -s "$MARIADB_API_URL/api/v1/sequences"

curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT NEXT VALUE FOR thread_number_seq AS next_thread"}'

curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT NEXTVAL(kb_version_seq) AS allocated, LASTVAL(kb_version_seq) AS last"}'

curl -s -X POST "$MARIADB_API_URL/api/v1/sequences/moderation_case_seq/next"
```

Seeded sequences: `thread_number_seq`, `kb_version_seq`, and
`moderation_case_seq` which cycles between 100 and 999. Every response that
touched a sequence carries `sequence_allocations`.

## RETURNING

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"INSERT INTO categories (id, slug, name, sort_order, locked) VALUES (6, 'showcase', 'Showcase', 5, 0) RETURNING id, slug, name\"}"

curl -s -X POST "$MARIADB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d '{"sql": "DELETE FROM page_views WHERE id = 8 RETURNING id, path, views"}'
```

`UPDATE … RETURNING` is rejected with 1064 — MariaDB does not support it.

## Aria is not transactional

`page_views` is an Aria table, so a write to it survives a rolled-back
transaction. Read the counters, run a failing transaction, read them again:

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT (SELECT views FROM threads WHERE id = 5001) AS innodb_views, (SELECT views FROM page_views WHERE id = 1) AS aria_views"}'

curl -s -X POST "$MARIADB_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d "{\"statements\": [
        {\"sql\": \"UPDATE threads SET views = views + 100 WHERE id = 5001\"},
        {\"sql\": \"UPDATE page_views SET views = views + 100 WHERE id = 1\"},
        {\"sql\": \"INSERT INTO categories (id, slug, name, sort_order, locked) VALUES (1, 'dup', 'Dup', 1, 0)\"}]}"
```

The InnoDB change reverts; the Aria change stays. The failing response lists
`non_transactional_writes_kept`.

## Writes and transactions

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/execute" -H 'Content-Type: application/json' \
  -d "{\"sql\": \"UPDATE threads SET status = 'answered' WHERE id = 5002\"}"

curl -s -X POST "$MARIADB_API_URL/api/v1/transaction" -H 'Content-Type: application/json' \
  -d "{\"statements\": [
        {\"sql\": \"UPDATE kb_articles SET version = NEXT VALUE FOR kb_version_seq WHERE slug = 'api-rate-limits'\"},
        {\"sql\": \"SELECT slug, version FROM kb_articles WHERE slug = 'api-rate-limits'\"}],
      \"isolation_level\": \"SERIALIZABLE\"}"
```

## EXPLAIN and ANALYZE

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM threads WHERE category_id = 3"}'

curl -s -X POST "$MARIADB_API_URL/api/v1/explain" -H 'Content-Type: application/json' \
  -d '{"sql": "SELECT * FROM posts WHERE thread_id = 5001", "analyze": true}'
```

`ANALYZE` adds `r_rows`, the rows actually read.

## Accounts

```bash
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-MariaDB-User: forum_analytics' \
  -d '{"sql": "SELECT viewed_on, SUM(views) AS views FROM page_views GROUP BY viewed_on"}'

# Denied: no grant on posts -> 1142
curl -s -X POST "$MARIADB_API_URL/api/v1/query" -H 'Content-Type: application/json' \
  -H 'X-MariaDB-User: forum_analytics' -d '{"sql": "SELECT * FROM posts"}'
```

## Metadata

```bash
curl -s "$MARIADB_API_URL/api/v1/databases"
curl -s "$MARIADB_API_URL/api/v1/tables"
curl -s "$MARIADB_API_URL/api/v1/tables/page_views"
curl -s "$MARIADB_API_URL/api/v1/tables/article_revisions/indexes"
curl -s "$MARIADB_API_URL/api/v1/variables?like=aria%"
curl -s "$MARIADB_API_URL/api/v1/status/counters?like=Aria%"
curl -s "$MARIADB_API_URL/api/v1/engines"
curl -s "$MARIADB_API_URL/api/v1/replication" -H 'X-MariaDB-User: root'
curl -s "$MARIADB_API_URL/api/v1/accounts" -H 'X-MariaDB-User: root'
curl -s "$MARIADB_API_URL/api/v1/grants?user=forum_analytics" -H 'X-MariaDB-User: root'
```

Replication reports MariaDB's GTID format (`0-1-88412003`) and
`Slave_IO_Running` / `Seconds_Behind_Master` field names, with a named `backup`
replica connection.
