# Supabase Self-Host Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$SUPABASE_API_URL`; responses are verbatim (long arrays elided
with `…`). Write examples assume:

```bash
export SERVICE_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost'
```

## Health

```bash
curl -s "$SUPABASE_API_URL/health"
```
```json
{"status": "ok"}
```

## PostgREST root

```bash
curl -s "$SUPABASE_API_URL/rest/v1/"
```
```json
{
  "swagger": "2.0",
  "info": {
    "title": "standard public schema",
    "description": "PostgREST API mock for the self-hosted Supabase project orbitlabsselfhost01",
    "version": "v12.2.0"
  },
  "host": "supabase-db",
  "basePath": "/rest/v1",
  "schemes": ["http"],
  "definitions": {"profiles": {"type": "array"}, "projects": {"type": "array"},
                  "documents": {"type": "array"}, "comments": {"type": "array"}},
  "paths": {"/profiles": {}, "/projects": {}, "/documents": {}, "/comments": {}}
}
```

## Row-level security: the same query under two roles

```bash
curl -s "$SUPABASE_API_URL/rest/v1/projects?select=id,name,visibility"
```
```json
[{"id": 103, "name": "Web App", "visibility": "public"},
 {"id": 104, "name": "Engineering Docs", "visibility": "public"}]
```

```bash
curl -s "$SUPABASE_API_URL/rest/v1/projects?select=id,name,visibility,status&order=id.asc" \
  -H "apikey: $SERVICE_KEY"
```
```json
[{"id": 101, "name": "Auth Service", "visibility": "private", "status": "active"},
 {"id": 102, "name": "Billing Platform", "visibility": "private", "status": "active"},
 {"id": 103, "name": "Web App", "visibility": "public", "status": "active"},
 {"id": 104, "name": "Engineering Docs", "visibility": "public", "status": "active"},
 {"id": 105, "name": "Legacy Importer", "visibility": "private", "status": "archived"}]
```

Response header on every list read: `Content-Range: 0-4/5`.

## Filtering and ordering

```bash
curl -s "$SUPABASE_API_URL/rest/v1/projects?visibility=eq.public&star_count=gte.20&select=id,name,star_count" \
  -H "apikey: $SERVICE_KEY"
```
```json
[{"id": 104, "name": "Engineering Docs", "star_count": 310}]
```

```bash
curl -s "$SUPABASE_API_URL/rest/v1/documents?status=eq.published&select=id,title,word_count&order=word_count.desc&limit=3"
```
```json
[{"id": 507, "title": "Row level security cookbook", "word_count": 2640},
 {"id": 502, "title": "Session store benchmark: Redis vs Postgres", "word_count": 2310},
 {"id": 501, "title": "Refresh token rotation design", "word_count": 1840}]
```

```bash
curl -s "$SUPABASE_API_URL/rest/v1/documents?tags=cs.{security}&select=id,title,tags" \
  -H "apikey: $SERVICE_KEY"
```
```json
[{"id": 501, "title": "Refresh token rotation design", "tags": ["auth", "design", "security"]},
 {"id": 507, "title": "Row level security cookbook", "tags": ["postgres", "rls", "security"]}]
```

```bash
curl -s "$SUPABASE_API_URL/rest/v1/comments?body=ilike.*rollback*&select=id,document_id,body" \
  -H "apikey: $SERVICE_KEY"
```
```json
[{"id": 9004, "document_id": 503,
  "body": "Rollback trigger needs an owner. Assigning to Helena until the runbook is published."}]
```

## Resource embedding

```bash
curl -s "$SUPABASE_API_URL/rest/v1/projects?id=eq.101&select=id,name,documents(id,title,status)" \
  -H "apikey: $SERVICE_KEY"
```
```json
[{"id": 101, "name": "Auth Service",
  "documents": [
    {"id": 501, "title": "Refresh token rotation design", "status": "published"},
    {"id": 502, "title": "Session store benchmark: Redis vs Postgres", "status": "published"},
    {"id": 503, "title": "Dual-writer cutover runbook", "status": "draft"}]}]
```

The join key is read before projection, so a many-to-one embed resolves even
when its foreign key is not selected:

```bash
curl -s "$SUPABASE_API_URL/rest/v1/documents?id=eq.501&select=id,title,profiles(username,full_name),comments(id,body,resolved)" \
  -H "apikey: $SERVICE_KEY"
```
```json
[{"id": 501, "title": "Refresh token rotation design",
  "profiles": {"username": "helena", "full_name": "Helena Park"},
  "comments": [
    {"id": 9001, "body": "Call out the reuse-detection window explicitly - 60 seconds is not obvious from the diagram.", "resolved": true},
    {"id": 9002, "body": "Family invalidation should log the parent token id so support can trace it.", "resolved": false}]}]
```

## Insert, update, delete

```bash
curl -s -X POST "$SUPABASE_API_URL/rest/v1/documents" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -H 'Prefer: return=representation' \
  -d '{"project_id": 101, "author_id": "a41f7c88-5be9-42d7-9c03-77e2f8b41d16",
       "title": "Token family revocation audit",
       "body": "Audit trail for every revoked refresh-token family, retained for 90 days.",
       "status": "draft", "tags": ["auth", "audit"]}'
```
```json
[{"id": 509, "project_id": 101, "author_id": "a41f7c88-5be9-42d7-9c03-77e2f8b41d16",
  "title": "Token family revocation audit", "slug": "token-family-revocation-audit",
  "body": "Audit trail for every revoked refresh-token family, retained for 90 days.",
  "status": "draft", "word_count": 11, "tags": ["auth", "audit"], "published_at": null}]
```

`Prefer: return=minimal` returns `[]` instead of the representation.

```bash
curl -s -X PATCH "$SUPABASE_API_URL/rest/v1/documents?id=eq.503" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -d '{"status": "in_review", "word_count": 1010}'
```
```json
[{"id": 503, "title": "Dual-writer cutover runbook", "status": "in_review", "word_count": 1010, "…": "…"}]
```

```bash
curl -s -X DELETE "$SUPABASE_API_URL/rest/v1/comments?id=eq.9007" -H "apikey: $SERVICE_KEY"
```
```json
[{"id": 9007, "document_id": 507, "author_id": "a41f7c88-5be9-42d7-9c03-77e2f8b41d16",
  "body": "Added the service_role bypass warning to the top of the page.",
  "resolved": true, "created_at": "2026-05-09T16:20:00+00:00"}]
```

## Error paths

| Request | Status | Body |
|---------|--------|------|
| `GET /rest/v1/orders` | 404 | `{"error": "relation \"public.orders\" does not exist", "code": "42P01", …}` |
| `POST /rest/v1/documents` with `project_id: 999` | 409 | `{"error": "insert or update on table \"documents\" violates foreign key constraint \"documents_project_id_fkey\"", "code": "23503", "details": "Key (project_id)=(999) is not present in table \"projects\".", …}` |
| `POST /rest/v1/documents` with no apikey | 401 | `{"error": "new row violates row-level security policy for table \"documents\"", "code": "42501", "hint": "Send an apikey header with a writable role.", …}` |
| `DELETE /rest/v1/documents` with no filter | 400 | `{"error": "delete requires at least one filter", "code": "PGRST109", …}` |
| `POST /rest/v1/rpc/archive_project` | 404 | `{"error": "Could not find the function public.archive_project in the schema cache", "code": "PGRST202", …}` |

## RPC

```bash
curl -s -X POST "$SUPABASE_API_URL/rest/v1/rpc/project_stats" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" -d '{"project_id": 101}'
```
```json
{"project_id": 101, "name": "Auth Service", "document_count": 3, "published_count": 2,
 "comment_count": 4, "unresolved_comment_count": 3, "total_words": 5110}
```

```bash
curl -s -X POST "$SUPABASE_API_URL/rest/v1/rpc/search_documents" \
  -H 'Content-Type: application/json' -d '{"query": "rotation", "limit": 5}'
```
```json
[{"id": 501, "project_id": 101, "title": "Refresh token rotation design",
  "slug": "refresh-token-rotation-design", "status": "published", "rank": 0.0625}]
```

```bash
curl -s -X POST "$SUPABASE_API_URL/rest/v1/rpc/publish_document" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" -d '{"document_id": 505}'
```
```json
{"id": 505, "title": "Dunning retry schedule", "status": "published",
 "published_at": "2026-05-26T09:14:22+00:00", "…": "…"}
```

Re-publishing an already-published document returns 400 with code `P0001`.

## Storage

```bash
curl -s "$SUPABASE_API_URL/storage/v1/bucket"
```
```json
[{"id": "avatars", "name": "avatars", "owner_id": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901",
  "public": true, "file_size_limit": 2097152,
  "allowed_mime_types": ["image/png", "image/jpeg", "image/webp"],
  "created_at": "2024-04-12T10:05:00+00:00", "updated_at": "2026-05-20T09:00:00+00:00"}]
```

Sending the service key returns all four buckets.

```bash
curl -s -X POST "$SUPABASE_API_URL/storage/v1/object/list/project-assets" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -d '{"prefix": "auth-service/", "limit": 10, "offset": 0}'
```
```json
[{"id": "obj_d4f0e6", "bucket_id": "project-assets", "name": "auth-service/architecture.svg",
  "size": 84210, "mime_type": "image/svg+xml", "etag": "\"b58e1f70c3aa\"", "…": "…"},
 {"id": "obj_e5b3c8", "bucket_id": "project-assets", "name": "auth-service/rotation-sequence.png",
  "size": 251904, "mime_type": "image/png", "etag": "\"2f9c47a0be15\"", "…": "…"}]
```

```bash
curl -s -X POST "$SUPABASE_API_URL/storage/v1/object/sign/invoices/2026/05/ORBIT-0042.pdf" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" -d '{"expiresIn": 900}'
```
```json
{"signedURL": "/storage/v1/object/sign/invoices/2026/05/ORBIT-0042.pdf?token=106907211dbf4613b51f91b5f5f33ee6"}
```

```bash
curl -s -X POST "$SUPABASE_API_URL/storage/v1/bucket" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -d '{"id": "exports", "name": "exports", "public": false, "file_size_limit": 10485760,
       "allowed_mime_types": ["text/csv"]}'
```
```json
{"name": "exports"}
```

Deleting a bucket that still holds objects returns 409
(`The bucket you tried to delete is not empty`).

## Edge Functions

```bash
curl -s -X POST "$SUPABASE_API_URL/functions/v1/generate-report" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" -d '{"period": "2026-05"}'
```
```json
{"invocation_id": "inv_06fefd80ae12", "slug": "generate-report", "version": 4,
 "data": {"report_id": "rep_b58782ded803", "period": "2026-05",
          "documents": 8, "published": 5, "total_words": 11610}}
```

`resize-avatar` is seeded as `THROTTLED` and always answers 429; functions with
`verify_jwt: true` answer 401 when called without an apikey.

## Realtime

```bash
curl -s "$SUPABASE_API_URL/realtime/v1/channels"
```
```json
[{"id": "ch_documents", "name": "public:documents", "topic": "realtime:public:documents",
  "schema_table": "public.documents", "event_filter": ["INSERT", "UPDATE", "DELETE"],
  "subscriber_count": 14, "is_private": false, "inserted_at": "2026-03-01T14:00:00+00:00"},
 {"id": "ch_project_101", "name": "project:101", "…": "…", "is_private": true},
 {"id": "ch_presence_web", "name": "presence:web-app", "…": "…"}]
```

```bash
curl -s -X POST "$SUPABASE_API_URL/realtime/v1/api/broadcast" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -d '{"messages": [{"topic": "public:documents", "event": "document_published", "payload": {"id": 505}}]}'
```
```json
{"message": "ok", "accepted": 1}
```

Broadcasting to `project:101` (a private channel) without a key returns 401.

## Project

```bash
curl -s "$SUPABASE_API_URL/v1/projects/orbitlabsselfhost01"
```
```json
{"ref": "orbitlabsselfhost01", "name": "orbit-labs-selfhost", "organization": "Orbit Labs",
 "region": "self-hosted", "status": "ACTIVE_HEALTHY", "self_hosted": true,
 "db": {"host": "supabase-db", "port": 5432, "name": "postgres", "version": "15.6",
        "schemas": ["public", "storage", "auth", "realtime"]},
 "services": {"rest": {"name": "postgrest", "version": "v12.2.0", "healthy": true}, "…": "…"},
 "api": {"url": "http://localhost:8102",
         "anon_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost",
         "service_role_key": "eyJhbGciOiJI...lfhost", "default_schema": "public", "max_rows": 1000}}
```
