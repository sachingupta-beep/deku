# pocketbase-api

Mock of a self-hosted PocketBase instance backing the Orbit Labs status page:
collection metadata, record CRUD with the PocketBase filter/sort/expand grammar,
files, logs, backups, crons, settings and realtime subscribe. The auth endpoints
live in `pocketbase-auth-api`.

Run it as its own container (build context is the environment root):
```
docker compose up -d pocketbase-api
curl http://localhost:8103/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir pocketbase-api --port 8103
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`pocketbase_api_postman_collection.json` for the runnable collection.
