# MySQL Mock API — Test Results

Base URL: `http://localhost:8110` (in docker-compose: `http://mysql-api:8110`)

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
| GET    | /api/v1/databases                   | 200                 |
| GET    | /api/v1/tables                      | 200                 |
| GET    | /api/v1/tables/{name}               | 200/404             |
| GET    | /api/v1/tables/{name}/indexes       | 200/404             |
| GET    | /api/v1/variables                   | 200                 |
| GET    | /api/v1/status/counters             | 200                 |
| GET    | /api/v1/processlist                 | 200                 |
| GET    | /api/v1/engines                     | 200                 |
| GET    | /api/v1/replication                 | 200/403             |
| GET    | /api/v1/users                       | 200                 |
| GET    | /api/v1/grants                      | 200/403/404         |

Collection run: **PASS 42 / WARN 18 / FAIL 0 / SKIP 0**. All eighteen WARNs are
intentional error-path requests.

## Real SQL under a MySQL surface

`sql_engine.py` materializes the shared store into an in-memory SQLite database
per request, executes the statement, and syncs writes back — so the store stays
canonical (drift keeps working) while the service gets exact SQL semantics.

### MySQL functions are registered, not rewritten

SQLite is missing several MySQL builtins, so they are registered as real SQL
functions on every connection: `CONCAT`, `CONCAT_WS`, `NOW`, `CURDATE`,
`UNIX_TIMESTAMP`, `DATE_FORMAT` (with MySQL's `%d/%m/%Y`-style tokens), `YEAR`,
`MONTH`, `LOCATE`, `GREATEST`, `LEAST`. A statement written for MySQL runs
unchanged.

Backtick identifiers and `LIMIT offset, count` are already accepted by the
engine, so the rewriter is small: `IF(...)` becomes `IIF(...)` (SQLite treats
`IF` as a keyword) and the null-safe `<=>` becomes `IS`. String literals are
never rewritten.

Because each request gets its own connection, **sessions do not persist** —
`/api/v1/transaction` is the unit of work and is genuinely atomic.

## Schema — `orbit_shop`

| Table | Rows | Notes |
|-------|------|-------|
| `customers` | 6 | `UNIQUE(email)`, `char(2)` country |
| `products` | 8 | `UNIQUE(sku)`, one discontinued |
| `inventory` | 8 | PK is `product_id`, `CHECK (on_hand >= 0)` |
| `orders` | 8 | FK to customers, `CHECK` on status, six statuses represented |
| `order_items` | 12 | `UNIQUE (order_id, product_id)`, cascades from orders |
| `shipments` | 3 | `UNIQUE(tracking_number)`, cascades from orders |

Plus the view `order_totals` and five indexes. `information_schema` reports the
declared MySQL types (`varchar(255)`, `char(2)`, `tinyint`, `datetime`, `text`)
verbatim, and `GET /api/v1/tables` carries the engine, row, length and
`AUTO_INCREMENT` columns.

## Accounts and grants

`X-MySQL-User` (or a bearer token) selects the account; absent or unknown falls
back to `orbit_shop`.

| Account | Host | Privileges |
|---------|------|-----------|
| `root` | `localhost` | ALL, including PROCESS, SUPER and REPLICATION CLIENT |
| `orbit_shop` | `%` | SELECT, INSERT, UPDATE, DELETE (default) |
| `orbit_report` | `10.42.%` | SELECT |
| `orbit_etl` | `10.42.0.44` | SELECT on `customers`, `orders`, `order_items`, `products` only |
| `orbit_legacy` | `%` | **locked** — every statement returns 3118 |

Three behaviours match MySQL:

- A table-level grant list means the account has **no** access to tables outside
  it, so `orbit_etl` reading `shipments` gets 1142.
- `SHOW PROCESSLIST` shows only your own threads without the PROCESS privilege.
- `mysql.user` shows only your own row, and `SHOW GRANTS FOR` another account
  requires SUPER.

## Errors — vendor number plus SQLSTATE

| Condition | errno | Name | SQLSTATE | HTTP |
|-----------|-------|------|----------|------|
| Duplicate key | 1062 | `ER_DUP_ENTRY` | 23000 | 409 |
| Foreign key failure | 1452 | `ER_NO_REFERENCED_ROW_2` | 23000 | 409 |
| Null in NOT NULL column | 1048 | `ER_BAD_NULL_ERROR` | 23000 | 400 |
| Check constraint | 3819 | `ER_CHECK_CONSTRAINT_VIOLATED` | HY000 | 400 |
| Unknown table | 1146 | `ER_NO_SUCH_TABLE` | 42S02 | 404 |
| Unknown column | 1054 | `ER_BAD_FIELD_ERROR` | 42S22 | 400 |
| Parse error | 1064 | `ER_PARSE_ERROR` | 42000 | 400 |
| Table access denied | 1142 | `ER_TABLEACCESS_DENIED_ERROR` | 42000 | 403 |
| Account locked | 3118 | `ER_ACCOUNT_HAS_BEEN_LOCKED` | HY000 | 403 |
| Privilege required | 1227 | `ER_SPECIFIC_ACCESS_DENIED_ERROR` | 42000 | 403 |
| Statement not supported | 1235 | `ER_NOT_SUPPORTED_YET` | 42000 | 403 |

Messages read the way MySQL writes them, e.g.
`Table 'orbit_shop.invoices' doesn't exist` and
`Duplicate entry for key 'products.sku'`.

## Notes

- Results are `{"command", "columns", "rows", "row_count", "affected_rows",
  "insert_id", "warnings", "truncated", "duration_ms", "user"}` — `rows` are
  objects and `columns` carries a MySQL type name per column.
- `POST /api/v1/explain` returns MySQL's traditional column format
  (`id`, `select_type`, `table`, `type`, `possible_keys`, `key`, `key_len`,
  `ref`, `rows`, `filtered`, `Extra`) or `"format": "json"` for the
  `query_block` tree with `cost_info`.
- `/api/v1/transaction` accepts `isolation_level` (`READ UNCOMMITTED`,
  `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`); anything else is 1231.
- `/api/v1/variables` and `/api/v1/status/counters` accept a `like` pattern with
  MySQL wildcards, e.g. `?like=innodb%`.
- `/api/v1/replication` reports `SHOW BINARY LOG STATUS` plus each replica — one
  of which is seeded broken (`Replica_SQL_Running: No`, 1842s behind, with the
  duplicate-key error that stopped it).
- `ATTACH`, `DETACH`, `VACUUM INTO` and dot-commands are rejected with 1235.
- Mutations are held in process memory and reset on container restart.
