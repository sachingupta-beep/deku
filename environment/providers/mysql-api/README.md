# mysql-api

A MySQL 8 database served over HTTP — `orbit_shop`, the storefront behind the
Orbit Labs self-serve shop. Statements run through a **real SQL engine**
(`sql_engine.py`), so joins, aggregates, subqueries, constraints and query plans
behave the way a database behaves.

Everything above the engine is MySQL: vendor error numbers alongside SQLSTATE,
`SHOW`-style metadata (tables, columns, indexes, variables, status, processlist,
engines, replica status), `information_schema.TABLES` columns, `EXPLAIN` in the
traditional column format or as JSON, and `'user'@'host'` accounts with
per-table grants.

MySQL functions SQLite lacks — `CONCAT`, `DATE_FORMAT`, `UNIX_TIMESTAMP`,
`GREATEST` and friends — are registered on every connection rather than
rewritten, so a statement written for MySQL runs unchanged.

Run it as its own container (build context is the environment root):
```
docker compose up -d mysql-api
curl http://localhost:8110/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir mysql-api --port 8110
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`mysql_api_postman_collection.json` for the runnable collection.
