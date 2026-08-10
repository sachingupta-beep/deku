# nhost-api

Mock of a self-hosted Nhost project ("Orbit Insights"): Hasura GraphQL over
Postgres at `/v1/graphql`, Hasura Auth at `/v1/auth`, Hasura Storage at
`/v1/storage` and serverless functions at `/v1/functions`.

The GraphQL surface is a real query engine (`graphql_engine.py`) — parser,
boolean expressions, relationship traversal, aggregates and mutations — driven
by the role permissions seeded in `permissions.json`.

Run it as its own container (build context is the environment root):
```
docker compose up -d nhost-api
curl http://localhost:8106/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir nhost-api --port 8106
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`nhost_api_postman_collection.json` for the runnable collection.
