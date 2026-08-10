# postgresql-api

A PostgreSQL database served over HTTP — `orbit_core`, the API-platform database
behind the Orbit Labs product. Statements run through a **real SQL engine**
(`sql_engine.py`), so joins, aggregates, CTEs, window functions, constraints and
query plans behave the way a database behaves.

Everything above the engine is PostgreSQL: SQLSTATE error reports with
severity/detail/hint/constraint fields, `information_schema` and `pg_catalog`
views, `EXPLAIN (ANALYZE, BUFFERS)` node trees, role GRANTs, extensions,
settings and replication state.

A dialect rewriter translates the PostgreSQL-only syntax an agent is likely to
send — `::` casts, `ILIKE`, `$1` placeholders, `NOW()` — into the engine's SQL.

Run it as its own container (build context is the environment root):
```
docker compose up -d postgresql-api
curl http://localhost:8109/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir postgresql-api --port 8109
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`postgresql_api_postman_collection.json` for the runnable collection.
