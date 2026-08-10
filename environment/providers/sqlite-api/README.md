# sqlite-api

A SQLite database served over HTTP — the Orbit Labs field-service database that
technician tablets sync against. Statements run through a **real SQLite engine**
(`sql_engine.py`), so joins, aggregates, CTEs, constraints, transactions and
query plans behave the way a database behaves.

The engine materializes the shared store into an in-memory database per request
and syncs writes back, which keeps the admin plane's drift surface working.

SQLite-specific surface: `EXPLAIN QUERY PLAN`, PRAGMAs, `sqlite_master` DDL,
`PRAGMA integrity_check` and the database-file statistics.

Run it as its own container (build context is the environment root):
```
docker compose up -d sqlite-api
curl http://localhost:8108/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir sqlite-api --port 8108
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`sqlite_api_postman_collection.json` for the runnable collection.
