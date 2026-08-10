# Supabase API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$SUPABASE_API_URL`.** The `apikey` header selects the Postgres role (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SUPABASE_API_URL` | Base URL for all requests |

Set the service key once to follow the write examples:

```bash
export SERVICE_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost'
```

## REST (PostgREST)

```bash
curl -s "$SUPABASE_API_URL/rest/v1/"
curl -s "$SUPABASE_API_URL/rest/v1/profiles?select=id,username,role&order=username.asc"
curl -s "$SUPABASE_API_URL/rest/v1/projects?select=id,name,visibility"
curl -s "$SUPABASE_API_URL/rest/v1/projects?visibility=eq.public&star_count=gte.20" \
  -H "apikey: $SERVICE_KEY"
curl -s "$SUPABASE_API_URL/rest/v1/documents?status=eq.published&order=word_count.desc&limit=3"
curl -s "$SUPABASE_API_URL/rest/v1/documents?id=eq.501&select=id,title,profiles(username),comments(id,body)" \
  -H "apikey: $SERVICE_KEY"
curl -s -X POST "$SUPABASE_API_URL/rest/v1/documents" -H 'Content-Type: application/json' \
  -H "apikey: $SERVICE_KEY" -d '{"project_id": 101, "title": "New note", "body": "Body text."}'
curl -s -X PATCH "$SUPABASE_API_URL/rest/v1/documents?id=eq.503" -H 'Content-Type: application/json' \
  -H "apikey: $SERVICE_KEY" -d '{"status": "in_review"}'
curl -s -X DELETE "$SUPABASE_API_URL/rest/v1/comments?id=eq.9007" -H "apikey: $SERVICE_KEY"
```

Filter operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `like`, `ilike`, `in`,
`is`, `cs`, each optionally prefixed with `not.` — e.g. `?status=not.eq.draft`.

## RPC

```bash
curl -s -X POST "$SUPABASE_API_URL/rest/v1/rpc/project_stats" -H 'Content-Type: application/json' \
  -H "apikey: $SERVICE_KEY" -d '{"project_id": 101}'
curl -s -X POST "$SUPABASE_API_URL/rest/v1/rpc/search_documents" -H 'Content-Type: application/json' \
  -d '{"query": "rotation", "limit": 5}'
curl -s -X POST "$SUPABASE_API_URL/rest/v1/rpc/publish_document" -H 'Content-Type: application/json' \
  -H "apikey: $SERVICE_KEY" -d '{"document_id": 505}'
```

## Storage

```bash
curl -s "$SUPABASE_API_URL/storage/v1/bucket"
curl -s "$SUPABASE_API_URL/storage/v1/bucket/avatars"
curl -s -X POST "$SUPABASE_API_URL/storage/v1/bucket" -H 'Content-Type: application/json' \
  -H "apikey: $SERVICE_KEY" -d '{"id": "exports", "public": false}'
curl -s -X DELETE "$SUPABASE_API_URL/storage/v1/bucket/exports" -H "apikey: $SERVICE_KEY"
curl -s -X POST "$SUPABASE_API_URL/storage/v1/object/list/project-assets" -H 'Content-Type: application/json' \
  -H "apikey: $SERVICE_KEY" -d '{"prefix": "auth-service/", "limit": 10}'
curl -s "$SUPABASE_API_URL/storage/v1/object/info/avatars/public/amelia.png"
curl -s -X POST "$SUPABASE_API_URL/storage/v1/object/sign/invoices/2026/05/ORBIT-0042.pdf" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" -d '{"expiresIn": 900}'
curl -s -X DELETE "$SUPABASE_API_URL/storage/v1/object/db-backups/daily/2026-05-26.sql.gz" \
  -H "apikey: $SERVICE_KEY"
```

## Edge Functions

```bash
curl -s "$SUPABASE_API_URL/functions/v1"
curl -s -X POST "$SUPABASE_API_URL/functions/v1/generate-report" -H 'Content-Type: application/json' \
  -H "apikey: $SERVICE_KEY" -d '{"period": "2026-05"}'
```

## Realtime

```bash
curl -s "$SUPABASE_API_URL/realtime/v1/channels"
curl -s -X POST "$SUPABASE_API_URL/realtime/v1/api/broadcast" -H 'Content-Type: application/json' \
  -H "apikey: $SERVICE_KEY" \
  -d '{"messages": [{"topic": "public:documents", "event": "document_published", "payload": {"id": 505}}]}'
```

## Project

```bash
curl -s "$SUPABASE_API_URL/v1/projects"
curl -s "$SUPABASE_API_URL/v1/projects/orbitlabsselfhost01"
```
