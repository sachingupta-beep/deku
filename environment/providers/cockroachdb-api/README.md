# cockroachdb-api

A CockroachDB 23.2 cluster served over HTTP — `orbit_fleet`, the multi-region
device registry. Statements run through a **real SQL engine**
(`sql_engine.py`), and CockroachDB speaks the PostgreSQL wire protocol so the
SQLSTATE vocabulary is shared with `postgresql-api`.

What is modelled beyond that is what makes it *distributed*:

- **SERIALIZABLE by default, with real retry errors.** A transaction touching a
  contended row fails its first attempt with 40001
  `TransactionRetryWithProtoRefreshError`. Pass `max_retries` to run the retry
  loop a driver would run; the response reports how many retries it took.
- **`AS OF SYSTEM TIME`.** Historical reads are served from the snapshot taken at
  process start, so a row mutated during a run still reads its original value.
- **Ranges, nodes and regions.** Lease holders, replica localities, five regions,
  and one node deliberately down.

Run it as its own container (build context is the environment root):
```
docker compose up -d cockroachdb-api
curl http://localhost:8112/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir cockroachdb-api --port 8112
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`cockroachdb_api_postman_collection.json` for the runnable collection.
