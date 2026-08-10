# mariadb-api

A MariaDB 10.11 database served over HTTP — `orbit_forum`, the Orbit Labs
community forum and knowledge base. Statements run through a **real SQL engine**
(`sql_engine.py`), so joins, aggregates, constraints and query plans behave the
way a database behaves.

MySQL-compatible where MariaDB is, and divergent where MariaDB is. The three
divergences modelled here change behaviour, not just strings:

- **Sequences.** `NEXT VALUE FOR`, `NEXTVAL()`, `LASTVAL()` and `SETVAL()` are
  real, with cycling and exhaustion. MySQL has no sequences.
- **RETURNING** on INSERT and DELETE. `UPDATE … RETURNING` is rejected, because
  MariaDB does not implement it either.
- **Non-transactional Aria tables.** `page_views` is Aria, so a write to it
  survives a rolled-back transaction — exactly what a non-transactional engine
  does, and a common source of surprise.

Run it as its own container (build context is the environment root):
```
docker compose up -d mariadb-api
curl http://localhost:8111/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir mariadb-api --port 8111
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`mariadb_api_postman_collection.json` for the runnable collection.
