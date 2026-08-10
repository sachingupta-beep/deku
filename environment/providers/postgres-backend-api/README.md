# postgres-backend-api

Mock of a plain, hand-rolled REST backend over PostgreSQL — the Orbit Labs
back-office: employees, teams, assets and access requests, with bearer-token
auth, role-based authorization (viewer < manager < admin), offset pagination, an
audit trail, and the operational endpoints a team ships alongside the API
(`/health/db`, `/health/ready`, `/metrics`, migration history, schema
introspection).

No BaaS framework: the conventions are the service's own.

Run it as its own container (build context is the environment root):
```
docker compose up -d postgres-backend-api
curl http://localhost:8107/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir postgres-backend-api --port 8107
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`postgres_backend_api_postman_collection.json` for the runnable collection.
