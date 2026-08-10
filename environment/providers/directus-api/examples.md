# Directus Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$DIRECTUS_API_URL`; responses are verbatim (long arrays elided
with `…`). The examples assume:

```bash
export DR_ADMIN='dr_static_admin_4f81c6a930b7e254'
export DR_EDITOR='dr_static_editor_2b90d7fc1e6a4830'
```

## Server and auth

```bash
curl -s "$DIRECTUS_API_URL/health"
curl -s "$DIRECTUS_API_URL/server/ping"
curl -s "$DIRECTUS_API_URL/server/health"
```
```json
{"status": "ok"}
pong
{"status": "ok", "releaseId": "11.1.1", "serviceId": "8f2c1b40-5e93-4a17-9d26-71c0e84b3f52",
 "checks": {"pg:responseTime": [{"status": "ok", "componentType": "datastore",
                                 "observedValue": 3.1, "observedUnit": "ms"}], "…": "…"}}
```

```bash
curl -s -X POST "$DIRECTUS_API_URL/auth/login" -H 'Content-Type: application/json' \
  -d '{"email": "noor.aziz@orbit-labs.com", "password": "OrbitContent2026!"}'
```
```json
{"data": {"access_token": "dr_session_f51077ef972144a9", "expires": 900000,
          "refresh_token": "dr_refresh_1e5db36e552f42efa929f1ef"}}
```

A wrong password returns 401 `{"errors": [{"message": "Invalid user credentials.",
"extensions": {"code": "INVALID_CREDENTIALS"}}]}`.

## Permissions: the same query under two roles

The Public role's `posts` permission filters on `status = published`, so an
unauthenticated read never sees drafts.

```bash
curl -s "$DIRECTUS_API_URL/items/posts?fields=id,status,title&sort=-publish_date"
```
```json
{"data": [{"id": 16, "status": "published", "title": "We are hiring a platform engineer"},
          {"id": 12, "status": "published", "title": "Offline-first field reports in Orbit 4.8"},
          {"id": 11, "status": "published", "title": "How we cut sign-in latency by 84%"},
          {"id": 18, "status": "published", "title": "Advisory: refresh-token reuse detection"},
          {"id": 13, "status": "published", "title": "Row level security, the practical version"}]}
```

```bash
curl -s "$DIRECTUS_API_URL/items/posts?fields=id,status,title&sort=id" \
  -H "Authorization: Bearer $DR_EDITOR"
# -> 8 rows, including the two drafts and the archived post
```

`job_openings` behaves the same way: 2 rows as Public (`status = open`), 4 as Editor.

## Filters

```bash
curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"hits":{"_gt":3000},"category":{"_in":[1,4]}}' \
  --data-urlencode 'fields=id,title,hits,category' -H "Authorization: Bearer $DR_ADMIN"
```
```json
{"data": [{"id": 11, "title": "How we cut sign-in latency by 84%", "hits": 4821, "category": 1},
          {"id": 13, "title": "Row level security, the practical version", "hits": 8107, "category": 4},
          {"id": 18, "title": "Advisory: refresh-token reuse detection", "hits": 3310, "category": 4}]}
```

```bash
curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"_or":[{"status":{"_eq":"draft"}},{"hits":{"_gte":8000}}]}' \
  --data-urlencode 'fields=id,status,title,hits' --data-urlencode 'sort=id' \
  -H "Authorization: Bearer $DR_ADMIN"
```
```json
{"data": [{"id": 13, "status": "published", "title": "Row level security, the practical version", "hits": 8107},
          {"id": 14, "status": "draft", "title": "Dual-writer cutover: what we would do differently", "hits": 0},
          {"id": 15, "status": "draft", "title": "Passkeys are coming to Orbit", "hits": 0}]}
```

Relational filters nest one level deep:

```bash
curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"category":{"slug":{"_eq":"security"}}}' \
  --data-urlencode 'fields=id,title,category.name' -H "Authorization: Bearer $DR_ADMIN"
```
```json
{"data": [{"id": 13, "title": "Row level security, the practical version", "category": {"name": "Security"}},
          {"id": 18, "title": "Advisory: refresh-token reuse detection", "category": {"name": "Security"}}]}
```

`_contains` also works against CSV fields:

```bash
curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"tags":{"_contains":"auth"}}' \
  --data-urlencode 'fields=id,title,tags' -H "Authorization: Bearer $DR_ADMIN"
# -> 4 rows: 11, 14, 15, 18
```

## Relational fields

```bash
curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"id":{"_eq":11}}' \
  --data-urlencode 'fields=id,title,category.name,category.color,author.first_name,author.last_name,image.filename_download' \
  -H "Authorization: Bearer $DR_ADMIN"
```
```json
{"data": [{"id": 11, "title": "How we cut sign-in latency by 84%",
           "category": {"name": "Engineering", "color": "#2E7DFF"},
           "author": {"first_name": "Amelia", "last_name": "Ortega"},
           "image": {"filename_download": "sign-in-latency-chart.png"}}]}
```

`fields=*.*` expands every relation one level:

```bash
curl -s "$DIRECTUS_API_URL/items/posts/13?fields=*.*" -H "Authorization: Bearer $DR_ADMIN"
```
```json
{"data": {"id": 13, "status": "published", "title": "Row level security, the practical version",
          "slug": "row-level-security-practical", "tags": ["postgres", "security", "rls"],
          "hits": 8107,
          "category": {"id": 4, "name": "Security", "slug": "security", "color": "#D64545", "…": "…"},
          "author": {"id": "1d9f4a02-…", "first_name": "Amelia", "last_name": "Ortega", "…": "…"},
          "image": null}}
```

## Meta, search and aggregation

```bash
curl -s "$DIRECTUS_API_URL/items/posts?meta=*&limit=3&fields=id,title" \
  -H "Authorization: Bearer $DR_ADMIN"
```
```json
{"data": [{"id": 11, "title": "How we cut sign-in latency by 84%"},
          {"id": 12, "title": "Offline-first field reports in Orbit 4.8"},
          {"id": 13, "title": "Row level security, the practical version"}],
 "meta": {"total_count": 8, "filter_count": 8}}
```

```bash
curl -s "$DIRECTUS_API_URL/items/posts?search=passkey&fields=id,status,title" \
  -H "Authorization: Bearer $DR_ADMIN"
# -> {"data": [{"id": 15, "status": "draft", "title": "Passkeys are coming to Orbit"}]}

curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'aggregate={"count":"*","sum":"hits"}' --data-urlencode 'groupBy=status' \
  -H "Authorization: Bearer $DR_ADMIN"
```
```json
{"data": [{"status": "published", "count": 5, "sum": 20734},
          {"status": "draft", "count": 2, "sum": 0},
          {"status": "archived", "count": 1, "sum": 742}]}
```

## Create, update, delete

```bash
curl -s -X POST "$DIRECTUS_API_URL/items/posts" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $DR_EDITOR" \
  -d '{"status": "draft", "title": "Rolling out passkeys to the web app",
       "slug": "rolling-out-passkeys-web", "summary": "WebAuthn lands in the browser next.",
       "category": 2, "author": "5c07e83b-1f42-4d69-b3a8-07e5d91c264f",
       "reading_minutes": 6, "tags": ["auth", "roadmap"]}'
```
```json
{"data": {"id": 19, "status": "draft", "title": "Rolling out passkeys to the web app",
          "slug": "rolling-out-passkeys-web", "category": 2, "reading_minutes": 6,
          "tags": ["auth", "roadmap"], "hits": null,
          "date_created": "…", "date_updated": "…",
          "user_created": "5c07e83b-1f42-4d69-b3a8-07e5d91c264f"}}
```

```bash
curl -s -X PATCH "$DIRECTUS_API_URL/items/posts/15" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $DR_EDITOR" \
  -d '{"status": "published", "publish_date": "2026-05-27"}'

curl -s -o /dev/null -w '%{http_code}\n' -X DELETE "$DIRECTUS_API_URL/items/posts/17" \
  -H "Authorization: Bearer $DR_ADMIN"
# -> 204
```

## Error paths

Directus answers **403 for anything the caller may not see, including rows that
do not exist** — deliberately, so the API never leaks record existence.

| Request | Status | Body |
|---------|--------|------|
| `GET /items/posts/14` as Public (a draft) | 403 | `{"errors": [{"message": "You don't have permission to access this.", "extensions": {"code": "FORBIDDEN"}}]}` |
| `GET /items/posts/999` as Administrator | 403 | same FORBIDDEN body |
| `GET /items/invoices` (unknown collection) | 403 | same FORBIDDEN body |
| `POST /items/posts` as Public | 403 | same FORBIDDEN body |
| `PATCH /items/posts/17` as Editor (archived) | 403 | the Editor update permission filters `status != archived` |
| `DELETE /items/posts/17` as Editor | 403 | the Editor role has no delete permission |
| `POST /items/posts` without `slug` | 400 | `{"errors": [{"message": "Value for field \"slug\" in collection \"posts\" can't be null.", "extensions": {"code": "FAILED_VALIDATION"}}]}` |
| `PATCH /items/posts/12` with `subtitle` | 400 | `{"extensions": {"code": "INVALID_PAYLOAD"}}` |
| `GET /users` as Editor | 403 | system collections require `admin_access` |
| `GET /users/me` as Public | 401 | `{"extensions": {"code": "INVALID_CREDENTIALS"}}` |

## Schema and system collections

```bash
curl -s "$DIRECTUS_API_URL/collections/posts" -H "Authorization: Bearer $DR_ADMIN"
```
```json
{"data": {"collection": "posts",
          "meta": {"icon": "article", "note": "Marketing blog posts",
                   "display_template": "{{title}}", "hidden": false, "singleton": false,
                   "sort_field": "publish_date", "archive_field": "status",
                   "archive_value": "archived", "accountability": "all", "group": "content"},
          "schema": {"name": "posts"}}}
```

```bash
curl -s "$DIRECTUS_API_URL/fields/job_openings" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/permissions" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/roles" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/flows" -H "Authorization: Bearer $DR_ADMIN"
curl -s --get "$DIRECTUS_API_URL/activity" \
  --data-urlencode 'filter={"collection":{"_eq":"posts"}}' --data-urlencode 'limit=5' \
  -H "Authorization: Bearer $DR_ADMIN"
```

The token can also travel as a query parameter, which is how Directus asset
links work:

```bash
curl -s --get "$DIRECTUS_API_URL/files" \
  --data-urlencode "access_token=$DR_EDITOR" \
  --data-urlencode 'filter={"type":{"_eq":"image/png"}}'
```
```json
{"data": [{"id": "3a7f92c1-6b04-4e58-9c31-8d70f2a5b6e9", "storage": "local",
           "filename_download": "sign-in-latency-chart.png", "title": "Sign-in latency chart",
           "type": "image/png", "filesize": 184320, "width": 1600, "height": 900, "…": "…"}, "…"]}
```

```bash
curl -s "$DIRECTUS_API_URL/users/me" -H "Authorization: Bearer $DR_EDITOR"
```
```json
{"data": {"id": "5c07e83b-1f42-4d69-b3a8-07e5d91c264f", "first_name": "Noor",
          "last_name": "Aziz", "email": "noor.aziz@orbit-labs.com",
          "role": "c41d7a68-2b95-4e30-8f71-6a2d9c05e713", "status": "active",
          "title": "Content Lead", "location": "Amman", "…": "…"}}
```
