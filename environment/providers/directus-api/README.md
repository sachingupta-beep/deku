# directus-api

Mock of a self-hosted Directus 11 instance running the Orbit Labs marketing site:
the `posts`, `categories` and `job_openings` collections plus the system
collections (users, roles, permissions, files, activity, flows, settings), with
the Directus query language — `filter` JSON, relational `fields`, `sort`,
`search`, `meta` and `aggregate`/`groupBy`.

Run it as its own container (build context is the environment root):
```
docker compose up -d directus-api
curl http://localhost:8105/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir directus-api --port 8105
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`directus_api_postman_collection.json` for the runnable collection.
