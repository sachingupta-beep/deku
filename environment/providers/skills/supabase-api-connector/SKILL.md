---
name: supabase-api-connector
description: >
  Supabase API (Mock) mock HTTP API. Base URL is provided via the
  `SUPABASE_API_URL` environment variable. 21 endpoint(s) across GET, POST, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Supabase API (Mock)

Mock HTTP API. **All requests go to the base URL in `$SUPABASE_API_URL`.** The
`apikey` header selects the Postgres role (any token is accepted; the anon and
service keys have special meaning). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SUPABASE_API_URL` | Base URL for all requests (e.g. `http://supabase-api:8102`) |

## Keys

| Key | Role | Effect |
|-----|------|--------|
| _(none)_ or `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost` | `anon` | Public projects, published documents, public buckets |
| any other token | `authenticated` | Full reads, inserts and updates |
| `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost` | `service_role` | Bypasses RLS; required for deletes |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/rest/v1/` |
| GET | `/rest/v1/{table}` |
| POST | `/rest/v1/{table}` |
| PATCH | `/rest/v1/{table}` |
| DELETE | `/rest/v1/{table}` |
| POST | `/rest/v1/rpc/{fn_name}` |
| GET | `/storage/v1/bucket` |
| GET | `/storage/v1/bucket/{bucket_id}` |
| POST | `/storage/v1/bucket` |
| DELETE | `/storage/v1/bucket/{bucket_id}` |
| POST | `/storage/v1/object/list/{bucket_id}` |
| GET | `/storage/v1/object/info/{bucket_id}/{path}` |
| POST | `/storage/v1/object/sign/{bucket_id}/{path}` |
| DELETE | `/storage/v1/object/{bucket_id}/{path}` |
| GET | `/functions/v1` |
| POST | `/functions/v1/{slug}` |
| GET | `/realtime/v1/channels` |
| POST | `/realtime/v1/api/broadcast` |
| GET | `/v1/projects` |
| GET | `/v1/projects/{ref}` |

Tables exposed through `/rest/v1`: `profiles`, `projects`, `documents`, `comments`.
Functions callable through `/rest/v1/rpc`: `project_stats`, `search_documents`,
`publish_document`.

## Usage

```bash
# GET example
curl -s "$SUPABASE_API_URL/rest/v1/documents?status=eq.published&select=id,title&order=id.asc"

# POST example
curl -s -X POST "$SUPABASE_API_URL/rest/v1/documents" -H 'Content-Type: application/json' \
  -H 'apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost' -d '{}'
```

The audit log of every call the agent makes is available at
`$SUPABASE_API_URL/audit/requests` (used for grading).
