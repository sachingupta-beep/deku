# supabase-api

Mock of the self-hosted Supabase data plane: PostgREST (`/rest/v1`), Storage
(`/storage/v1`), Edge Functions (`/functions/v1`), Realtime (`/realtime/v1`) and
the project read model (`/v1/projects`). GoTrue lives in `supabase-auth-api`.

Run it as its own container (build context is the environment root):
```
docker compose up -d supabase-api
curl http://localhost:8102/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir supabase-api --port 8102
```

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`supabase_api_postman_collection.json` for the runnable collection.
