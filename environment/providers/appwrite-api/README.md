# appwrite-api

Mock of a self-hosted Appwrite 1.6 project backing the Orbit Labs mobile app:
Databases (documents with the Query DSL and per-document permissions), Storage,
Functions with execution history, Teams, Users, Account, Locale and the health
probes.

Run it as its own container (build context is the environment root):
```
docker compose up -d appwrite-api
curl http://localhost:8104/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir appwrite-api --port 8104
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`appwrite_api_postman_collection.json` for the runnable collection.
