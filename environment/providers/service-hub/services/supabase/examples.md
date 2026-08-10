# Supabase — worked examples

Captured from a running container (`service-hub:v1`, `docker run -p 8099:8080`). Every
response below is real output, including the error bodies.

Throughout:

```bash
HUB=http://localhost:8080
SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost
```

Get the keys yourself with `curl $HUB/supabase/v1/projects/orbitlabsselfhost01`.

---

## Health

```bash
curl $HUB/supabase/health
```

```json
{
  "service": "supabase",
  "status": "ok",
  "checks": {
    "project_ref": "orbitlabsselfhost01",
    "rows": {"profiles": 6, "projects": 5, "documents": 8, "comments": 7},
    "buckets": 4,
    "functions": 4
  }
}
```

---

## Row-level security

The same request, twice, differing only in the credential. This is the clearest way to see
that RLS is enforced rather than decorative.

**As `anon`** — no header:

```bash
curl $HUB/supabase/rest/v1/projects
```

```json
[
  {
    "id": 103,
    "owner_id": "a41f7c88-5be9-42d7-9c03-77e2f8b41d16",
    "name": "Web App",
    "slug": "web-app",
    "description": "Customer-facing Next.js application.",
    "visibility": "public",
    "status": "active",
    "star_count": 18,
    "created_at": "2024-03-20T10:00:00+00:00",
    "updated_at": "2026-05-26T08:00:00+00:00"
  },
  {
    "id": 104,
    "name": "Engineering Docs",
    "visibility": "public",
    "star_count": 310
  }
]
```

Two of five rows. **As `service_role`** — five of five:

```bash
curl $HUB/supabase/rest/v1/projects -H "apikey: $SERVICE_KEY"
```

---

## Filtering, ordering, projection

```bash
curl -i "$HUB/supabase/rest/v1/projects?order=star_count.desc&limit=2&select=id,name,star_count" \
  -H "apikey: $SERVICE_KEY"
```

```http
HTTP/1.1 200 OK
content-range: 0-1/5
```
```json
[{"id": 104, "name": "Engineering Docs", "star_count": 310},
 {"id": 101, "name": "Auth Service", "star_count": 42}]
```

`Content-Range` reports `0-1/5` — the window returned, and the total *before* the limit.

More filters:

```bash
?status=eq.published            # equality
?status=not.eq.draft            # negation
?star_count=gt.100              # numeric, coerced to the column type
?title=ilike.*rotation*         # case-insensitive pattern
?id=in.(101,103)                # set membership
?published_at=is.null           # null check
?tags=cs.{security}             # array contains
```

A parameter with no operator is a `PGRST100`, as upstream:

```bash
curl "$HUB/supabase/rest/v1/documents?status=published"     # missing "eq."
```
```json
{"code": "PGRST100",
 "message": "unexpected \"published\" expecting \"eq\", \"gt\", \"gte\", \"lt\", \"lte\", \"neq\", \"like\", \"ilike\", \"in\", \"is\", \"cs\" or \"not\"",
 "details": "filter on column 'status'"}
```

---

## Resource embedding

```bash
curl "$HUB/supabase/rest/v1/projects?id=eq.101&select=id,name,documents(id,title,status)" \
  -H "apikey: $SERVICE_KEY"
```

```json
[
  {
    "id": 101,
    "name": "Auth Service",
    "documents": [
      {"id": 501, "title": "Refresh token rotation design", "status": "published"},
      {"id": 502, "title": "Session store benchmark: Redis vs Postgres", "status": "published"},
      {"id": 503, "title": "Dual-writer cutover runbook", "status": "draft"}
    ]
  }
]
```

The same call **as `anon`** returns only the two published documents — an embed is filtered by
RLS, not a back door around it. (Project 101 is private, so anon cannot reach it at all;
try `id=eq.103` to see the effect.)

Parent embeds work too, and the join key does not need to be selected:

```bash
curl "$HUB/supabase/rest/v1/documents?id=eq.501&select=id,profiles(username)" \
  -H "apikey: $SERVICE_KEY"
```
```json
[{"id": 501, "profiles": {"username": "amelia"}}]
```

`author_id` was projected away, and the join still resolved.

---

## Writes

**Insert** — 201, with the row echoed back:

```bash
curl -X POST $HUB/supabase/rest/v1/projects \
  -H "apikey: $SERVICE_KEY" -H 'content-type: application/json' \
  -d '{"name": "Realtime Gateway", "visibility": "public"}'
```
```json
[{"id": 106, "name": "Realtime Gateway", "slug": "realtime-gateway",
  "visibility": "public", "status": "active", "star_count": 0,
  "created_at": "2026-08-07T10:22:41+00:00", "updated_at": "2026-08-07T10:22:41+00:00"}]
```

The id is the next serial, and the slug was derived. `Prefer: return=minimal` gives `201` with
`[]`.

**Update** — the filter selects the rows:

```bash
curl -X PATCH "$HUB/supabase/rest/v1/projects?id=eq.101" \
  -H "apikey: $SERVICE_KEY" -H 'content-type: application/json' \
  -d '{"description": "Rewritten."}'
```

**Delete** — `service_role` only, and never unfiltered:

```bash
curl -X DELETE "$HUB/supabase/rest/v1/comments?id=eq.9001" -H "apikey: $SERVICE_KEY"
```

---

## Error paths

Each of these has seed data behind it, so all are reachable.

**RLS denial on write** — anon insert, `42501` → 401:

```bash
curl -X POST $HUB/supabase/rest/v1/projects -H 'content-type: application/json' -d '{"name":"x"}'
```
```json
{
  "error": "new row violates row-level security policy for table \"projects\"",
  "code": "42501",
  "details": null,
  "hint": "Send an apikey header with a writable role.",
  "message": "new row violates row-level security policy for table \"projects\""
}
```

**Foreign-key violation** — `23503` → 409, with the constraint named:

```bash
curl -X POST $HUB/supabase/rest/v1/documents -H "apikey: $SERVICE_KEY" \
  -H 'content-type: application/json' -d '{"title": "Orphan", "project_id": 999}'
```
```json
{
  "error": "insert or update on table \"documents\" violates foreign key constraint \"documents_project_id_fkey\"",
  "code": "23503",
  "details": "Key (project_id)=(999) is not present in table \"projects\".",
  "hint": null
}
```

**Unknown table** — `42P01` → 404:

```bash
curl $HUB/supabase/rest/v1/orders
```
```json
{
  "error": "relation \"public.orders\" does not exist",
  "code": "42P01",
  "hint": "Verify the table name and the exposed schema."
}
```

**Unfiltered delete** — `PGRST109` → 400. A deliberate deviation from upstream, which would
empty the table:

```bash
curl -X DELETE $HUB/supabase/rest/v1/comments -H "apikey: $SERVICE_KEY"
```
```json
{"error": "delete requires at least one filter", "code": "PGRST109",
 "hint": "Add a filter such as ?id=eq.101."}
```

---

## RPC

**`project_stats`** — aggregates across three tables:

```bash
curl -X POST $HUB/supabase/rest/v1/rpc/project_stats \
  -H "apikey: $SERVICE_KEY" -H 'content-type: application/json' -d '{"project_id": 101}'
```
```json
{
  "project_id": 101,
  "name": "Auth Service",
  "document_count": 3,
  "published_count": 2,
  "comment_count": 4,
  "unresolved_comment_count": 3,
  "total_words": 5110
}
```

The same call as `anon` is a **404 `PGRST116`**, not an empty result — project 101 is private,
so to anon it does not exist.

**`search_documents`** — ranked full-text-ish search:

```bash
curl -X POST $HUB/supabase/rest/v1/rpc/search_documents \
  -H "apikey: $SERVICE_KEY" -H 'content-type: application/json' \
  -d '{"query": "rotation", "limit": 3}'
```
```json
[{"id": 501, "project_id": 101, "title": "Refresh token rotation design",
  "slug": "refresh-token-rotation-design", "status": "published", "rank": 0.0625}]
```

**`publish_document`** — mutates and returns the row; calling it twice is `P0001` → 400.

---

## Storage

**Buckets as `anon`** — public only:

```bash
curl $HUB/supabase/storage/v1/bucket
```
```json
[{"id": "avatars", "name": "avatars", "public": true,
  "file_size_limit": 2097152,
  "allowed_mime_types": ["image/png", "image/jpeg", "image/webp"],
  "created_at": "2024-04-12T10:05:00+00:00", "updated_at": "2026-05-20T09:00:00+00:00"}]
```

A private bucket is **404** to anon, not 403 — it should not confirm its own existence:

```bash
curl -o /dev/null -w '%{http_code}\n' $HUB/supabase/storage/v1/bucket/invoices    # 404
```

**Object listing** (POST, as upstream):

```bash
curl -X POST $HUB/supabase/storage/v1/object/list/avatars \
  -H "apikey: $SERVICE_KEY" -H 'content-type: application/json' -d '{"prefix": "public/"}'
```

**Signed URL**:

```bash
curl -X POST $HUB/supabase/storage/v1/object/sign/avatars/public/amelia.png \
  -H "apikey: $SERVICE_KEY" -H 'content-type: application/json' -d '{"expiresIn": 600}'
```
```json
{"signedURL": "/storage/v1/object/sign/avatars/public/amelia.png?token=f5e3def6d1ab41dcba1dc94c352fec5c"}
```

**Deleting a non-empty bucket** is a 409:

```json
{"error": "The bucket you tried to delete is not empty", "code": "409"}
```

---

## Edge Functions

```bash
curl -X POST $HUB/supabase/functions/v1/billing-webhook \
  -H 'content-type: application/json' -d '{"type": "invoice.paid"}'
```
```json
{"invocation_id": "inv_3a7c91e40b2d", "slug": "billing-webhook", "version": 4,
 "data": {"received": true, "event": "invoice.paid",
          "processed_at": "2026-08-07T10:24:03+00:00"}}
```

`send-welcome-email` sets `verify_jwt`, so anon gets **401**. `resize-avatar` is `THROTTLED`
and always **429**s:

```json
{"error": "Function resize-avatar is throttled; retry after the cooldown", "code": "429"}
```

---

## Realtime

```bash
curl -X POST $HUB/supabase/realtime/v1/api/broadcast \
  -H 'content-type: application/json' \
  -d '{"messages": [{"topic": "public:documents", "payload": {"id": 501}}]}'
```
```json
{"message": "ok", "accepted": 1}
```

Status is **202**. Broadcasting to `project:101` — a private channel — as anon is a 401.

---

## Project settings

```bash
curl $HUB/supabase/v1/projects/orbitlabsselfhost01
```
```json
{
  "ref": "orbitlabsselfhost01",
  "name": "orbit-labs-selfhost",
  "organization": "Orbit Labs",
  "region": "self-hosted",
  "status": "ACTIVE_HEALTHY",
  "api": {
    "url": "http://service-hub:8080/supabase",
    "anon_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost",
    "service_role_key": "eyJhbGciOiJI...lfhost",
    "default_schema": "public",
    "max_rows": 1000
  }
}
```

The anon key is public and comes back in full; the service key is masked, as the dashboard
shows it.

---

## Hub interaction

Loading is implicit — but visible:

```bash
curl -s $HUB/hub/metrics | jq '{loaded, supabase: .services.supabase}'
```
```json
{"loaded": 0, "supabase": {"state": "discovered", "load_ms": null, "request_count": 0}}
```

```bash
curl -s $HUB/supabase/rest/v1/projects > /dev/null
curl -s $HUB/hub/metrics | jq '{loaded, supabase: .services.supabase}'
```
```json
{"loaded": 1, "supabase": {"state": "ready", "load_ms": 89.28, "request_count": 1}}
```

Between benchmark tasks, rewind the data without re-importing:

```bash
curl -X POST $HUB/hub/services/supabase/reset
```
```json
{"service": "supabase", "reset": "baseline", "state": "ready"}
```
