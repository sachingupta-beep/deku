# Mock API Services Documentation

Backend/BaaS, relational-database, authentication, email and payment mock
services. Each service is an independent FastAPI app in `<name>-api/`, runnable
on its own via Docker, exposing a `/health` endpoint and the shared audit plane.

## Table of Contents

- [Service Overview](#service-overview)
- [Shared Tracking/Audit Endpoints](#shared-trackingaudit-endpoints)
- [1. Supabase API (self-host)](#1-supabase-api-self-host)
- [2. PocketBase API](#2-pocketbase-api)
- [3. Appwrite API](#3-appwrite-api)
- [4. Directus API](#4-directus-api)
- [5. Nhost API](#5-nhost-api)
- [6. Plain PostgreSQL Backend](#6-plain-postgresql-backend)
- [7. SQLite API](#7-sqlite-api)
- [8. PostgreSQL API](#8-postgresql-api)
- [9. MySQL API](#9-mysql-api)
- [10. MariaDB API](#10-mariadb-api)
- [11. CockroachDB API](#11-cockroachdb-api)
- [12. Supabase Auth API (GoTrue)](#12-supabase-auth-api-gotrue)
- [13. PocketBase Auth API](#13-pocketbase-auth-api)
- [14. SuperTokens Core API](#14-supertokens-core-api)
- [15. Logto API](#15-logto-api)
- [16. Keycloak API](#16-keycloak-api)
- [17. Zitadel API](#17-zitadel-api)
- [18. Ory Kratos API](#18-ory-kratos-api)
- [19. Dex API](#19-dex-api)
- [20. MailHog API](#20-mailhog-api)
- [21. Mailpit API](#21-mailpit-api)
- [22. Inbucket API](#22-inbucket-api)
- [23. smtp4dev API](#23-smtp4dev-api)
- [24. MailCatcher API](#24-mailcatcher-api)
- [25. Orbit Payments API (in-house)](#25-orbit-payments-api-in-house)
- [26. Lago API](#26-lago-api)
- [27. Kill Bill API](#27-kill-bill-api)

## Service Overview

| Service | Port | Env Var | App Title | Version | Group |
|---------|------|---------|-----------|---------|-------|
| supabase-api | 8102 | `SUPABASE_API_URL` | Supabase API (Mock) | v1 | Backend / BaaS |
| pocketbase-api | 8103 | `POCKETBASE_API_URL` | PocketBase API (Mock) | v0.24.4 | Backend / BaaS |
| appwrite-api | 8104 | `APPWRITE_API_URL` | Appwrite API (Mock) | 1.6.0 | Backend / BaaS |
| directus-api | 8105 | `DIRECTUS_API_URL` | Directus API (Mock) | 11.1.1 | Backend / BaaS |
| nhost-api | 8106 | `NHOST_API_URL` | Nhost API (Mock) | v2.42.0 | Backend / BaaS |
| postgres-backend-api | 8107 | `POSTGRES_BACKEND_API_URL` | Orbit Back-office API (Mock) | 2.7.3 | Backend / BaaS |
| sqlite-api | 8108 | `SQLITE_API_URL` | SQLite API (Mock) | 3.45.3 | Relational database |
| postgresql-api | 8109 | `POSTGRESQL_API_URL` | PostgreSQL API (Mock) | 15.6 | Relational database |
| mysql-api | 8110 | `MYSQL_API_URL` | MySQL API (Mock) | 8.0.36 | Relational database |
| mariadb-api | 8111 | `MARIADB_API_URL` | MariaDB API (Mock) | 10.11.7 | Relational database |
| cockroachdb-api | 8112 | `COCKROACHDB_API_URL` | CockroachDB API (Mock) | 23.2.5 | Relational database |
| supabase-auth-api | 8113 | `SUPABASE_AUTH_API_URL` | Supabase Auth API (Mock) | v2.158.1 | Authentication |
| pocketbase-auth-api | 8114 | `POCKETBASE_AUTH_API_URL` | PocketBase Auth API (Mock) | v0.24.4 | Authentication |
| supertokens-api | 8115 | `SUPERTOKENS_API_URL` | SuperTokens Core API (Mock) | 9.2.2 | Authentication |
| logto-api | 8116 | `LOGTO_API_URL` | Logto API (Mock) | 1.23.0 | Authentication |
| keycloak-api | 8117 | `KEYCLOAK_API_URL` | Keycloak API (Mock) | 26.0.5 | Authentication |
| zitadel-api | 8118 | `ZITADEL_API_URL` | Zitadel API (Mock) | 2.65.1 | Authentication |
| ory-kratos-api | 8119 | `ORY_KRATOS_API_URL` | Ory Kratos API (Mock) | v1.3.1 | Authentication |
| dex-api | 8120 | `DEX_API_URL` | Dex API (Mock) | v2.41.1 | Authentication |
| mailhog-api | 8121 | `MAILHOG_API_URL` | MailHog API (Mock) | v1.0.1 | Email |
| mailpit-api | 8122 | `MAILPIT_API_URL` | Mailpit API (Mock) | v1.21.3 | Email |
| inbucket-api | 8123 | `INBUCKET_API_URL` | Inbucket API (Mock) | 3.1.0 | Email |
| smtp4dev-api | 8124 | `SMTP4DEV_API_URL` | smtp4dev API (Mock) | 3.8.6 | Email |
| mailcatcher-api | 8125 | `MAILCATCHER_API_URL` | MailCatcher API (Mock) | 0.10.0 | Email |
| inhouse-payments-api | 8126 | `INHOUSE_PAYMENTS_API_URL` | Orbit Payments API (Mock) | 2026-04-01 | Payments |
| lago-api | 8127 | `LAGO_API_URL` | Lago API (Mock) | 1.17.0 | Payments |
| killbill-api | 8128 | `KILLBILL_API_URL` | Kill Bill API (Mock) | 0.24.10 | Payments |

Ports 8000–8101 belong to the upstream fleet and are never reused. This fleet
allocates 8102 upward: 8102–8107 Backend/BaaS, 8108–8112 relational databases,
8113–8120 authentication, 8121–8125 email, 8126–8128 payments.

## Shared Tracking/Audit Endpoints

Every service installs the tracking middleware and exposes these endpoints:

#### `GET /health`
Health check.

**Response:** `200`
```json
{"status": "ok"}
```

#### `GET /audit/requests`
Returns full audit log of all requests.

**Response:** `200`
```json
{"total": 42, "requests": [...]}
```

#### `GET /audit/requests/clear`
Clears the audit log.

**Response:** `200`
```json
{"cleared": 42}
```

#### `GET /audit/summary`
Aggregated request summary by endpoint.

**Response:** `200`
```json
{"total_requests": 42, "endpoints": {"GET /some/path": {"count": 10, "statuses": {"200": 8, "404": 2}}}}
```

Each value in `endpoints` is a dict with `count` (integer) and `statuses` (map of status code → count).

**Audit Log Entry Format:**
```json
{
  "timestamp": 1234567890.123,
  "timestamp_iso": "2026-05-26T10:30:00",
  "method": "GET",
  "path": "/some/path",
  "query_params": {"key": "value"},
  "request_body": "...",
  "status_code": 200,
  "response_body": "...",
  "duration_ms": 12.34
}
```

Every service also serves its generated OpenAPI schema at `GET /openapi.json`,
committed alongside the service as `<name>-api/openapi.json`.

---

## 1. Supabase API (self-host)

**Service**: `supabase-api` · **Port**: 8102 · **Env**: `SUPABASE_API_URL`

Mock service mirroring the data plane of a self-hosted Supabase stack: PostgREST,
Storage, Edge Functions, Realtime and the project read model. GoTrue is served
separately by `supabase-auth-api`. See
`supabase-api/supabase_api_postman_collection.json` for the runnable request
collection and `supabase-api/examples.md` for captured request/response pairs.

### Authentication

The `apikey` header (or `Authorization: Bearer <token>`) selects the Postgres
role the request is evaluated as:

| Key | Role | Capability |
|-----|------|------------|
| absent, or `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost` | `anon` | Reads public projects, published documents and public buckets |
| any other non-empty token | `authenticated` | Full reads, inserts and updates |
| `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost` | `service_role` | Bypasses RLS; required for deletes |

### Schema

`public` schema tables exposed through `/rest/v1`:

| Table | PK | Rows | Notes |
|-------|----|------|-------|
| `profiles` | `id` (uuid) | 6 | 5 people + 1 service bot |
| `projects` | `id` (bigint) | 5 | 2 public, 3 private, 1 archived |
| `documents` | `id` (bigint) | 8 | published / draft / archived; `tags` is a text array |
| `comments` | `id` (bigint) | 7 | FK to `documents` |

Storage: 4 buckets, 9 objects. Edge Functions: 4. Realtime channels: 3.

### Endpoints

- `GET {{baseUrl}}/health` — health
- `GET {{baseUrl}}/rest/v1/` — rest root schema
- `GET {{baseUrl}}/rest/v1/profiles?select=id,username,full_name,role&order=username.asc` — list profiles
- `GET {{baseUrl}}/rest/v1/projects?select=id,name,visibility` — list projects as anon (RLS hides private rows)
- `GET {{baseUrl}}/rest/v1/projects?select=id,name,visibility,status&order=id.asc` — list projects as service_role
- `GET {{baseUrl}}/rest/v1/projects?visibility=eq.public&star_count=gte.20&select=id,name,star_count` — filter projects (gte + eq)
- `GET {{baseUrl}}/rest/v1/projects?id=eq.101&select=id,name,documents(id,title,status)` — embed documents into project
- `GET {{baseUrl}}/rest/v1/documents?status=eq.published&select=id,title,word_count&order=word_count.desc&limit=3` — list published documents
- `GET {{baseUrl}}/rest/v1/documents?id=eq.501&select=id,title,profiles(username,full_name),comments(id,body,resolved)` — document with author and comments
- `GET {{baseUrl}}/rest/v1/documents?tags=cs.{security}&select=id,title,tags` — search documents by tag (cs)
- `GET {{baseUrl}}/rest/v1/comments?body=ilike.*rollback*&select=id,document_id,body` — list comments (ilike)
- `GET {{baseUrl}}/rest/v1/orders?select=*` — unknown relation (404 expected)
- `POST {{baseUrl}}/rest/v1/documents` — insert document
- `PATCH {{baseUrl}}/rest/v1/documents?id=eq.503` — update document status
- `DELETE {{baseUrl}}/rest/v1/comments?id=eq.9007` — delete comment
- `POST {{baseUrl}}/rest/v1/rpc/project_stats` — rpc project_stats
- `POST {{baseUrl}}/rest/v1/rpc/search_documents` — rpc search_documents
- `POST {{baseUrl}}/rest/v1/rpc/publish_document` — rpc publish_document
- `GET {{baseUrl}}/storage/v1/bucket` — list buckets
- `GET {{baseUrl}}/storage/v1/bucket/avatars` — get bucket
- `POST {{baseUrl}}/storage/v1/bucket` — create bucket
- `DELETE {{baseUrl}}/storage/v1/bucket/avatars` — delete bucket (409 when non-empty)
- `POST {{baseUrl}}/storage/v1/object/list/project-assets` — list objects in bucket
- `GET {{baseUrl}}/storage/v1/object/info/avatars/public/amelia.png` — get object info
- `POST {{baseUrl}}/storage/v1/object/sign/invoices/2026/05/ORBIT-0042.pdf` — create signed url
- `DELETE {{baseUrl}}/storage/v1/object/db-backups/daily/2026-05-26.sql.gz` — delete object
- `GET {{baseUrl}}/functions/v1` — list edge functions
- `POST {{baseUrl}}/functions/v1/generate-report` — invoke edge function
- `GET {{baseUrl}}/realtime/v1/channels` — list realtime channels
- `POST {{baseUrl}}/realtime/v1/api/broadcast` — broadcast realtime message
- `GET {{baseUrl}}/v1/projects` — list projects (management)
- `GET {{baseUrl}}/v1/projects/orbitlabsselfhost01` — get project settings

### PostgREST query grammar

Filters are `?column=[not.]op.operand` with `op` in `eq`, `neq`, `gt`, `gte`,
`lt`, `lte`, `like`, `ilike`, `in`, `is`, `cs`. `select` supports column
projection and one level of resource embedding. `order=col.desc`, `limit`
(≤ 1000) and `offset` complete the grammar. List reads return a bare JSON array
plus a `Content-Range` response header (`0-4/5`, or `*/0` when empty).

### Error codes

| Code | HTTP | Meaning |
|------|------|---------|
| `42P01` | 404 | Relation does not exist |
| `PGRST202` | 404 | Function not in the schema cache |
| `PGRST116` | 404 | Row not found |
| `42501` | 401 | Row-level security / permission denied |
| `23503` | 409 | Foreign-key violation |
| `PGRST100` / `PGRST102` / `PGRST109` | 400 | Malformed filter, body or unfiltered delete |
| `P0001` | 400 | `raise_exception` from a Postgres function |
| `429` | 429 | Edge function throttled |

---

## 2. PocketBase API

**Service**: `pocketbase-api` · **Port**: 8103 · **Env**: `POCKETBASE_API_URL`

Mock service mirroring a self-hosted PocketBase instance backing the Orbit Labs
status page: collection metadata, record CRUD, files, logs, backups, crons,
settings and realtime subscribe. The auth endpoints are served by
`pocketbase-auth-api`. See
`pocketbase-api/pocketbase_api_postman_collection.json` for the runnable request
collection and `pocketbase-api/examples.md` for captured request/response pairs.

### Authentication

`Authorization: <token>` (the `Bearer` prefix is optional):

| Token | Identity | Capability |
|-------|----------|------------|
| absent | guest | Public collections: `services`, `incidents`, `incident_updates`; may create `subscribers` |
| `eyJhbGciOiJIUzI1NiJ9.users_amelia.orbit-labs-status`, or any other token | user `usramelia000001` | Adds the `users` collection and file tokens |
| `eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status` | superuser | Bypasses every collection rule |

### Collections

| Collection | Type | Records | list / view | create | update | delete |
|------------|------|---------|-------------|--------|--------|--------|
| `users` | auth | 6 | authenticated | public | owner | superuser |
| `services` | base | 5 | public | superuser | superuser | superuser |
| `incidents` | base | 6 | public | superuser | superuser | superuser |
| `incident_updates` | base | 8 | public | superuser | superuser | superuser |
| `subscribers` | base | 5 | superuser | public | superuser | superuser |

Relations: `incidents.service` → `services`, `incidents.assignee` → `users`,
`incident_updates.incident` → `incidents`, `incident_updates.author` → `users`,
`subscribers.services` → `services` (multi).

### Endpoints

- `GET {{baseUrl}}/health` — health
- `GET {{baseUrl}}/api/health` — api health
- `GET {{baseUrl}}/api/collections?perPage=10` — list collections
- `GET {{baseUrl}}/api/collections/incidents` — get collection
- `GET {{baseUrl}}/api/collections/services/records?sort=sort_order` — list services (public rule)
- `GET {{baseUrl}}/api/collections/incidents/records?filter=status!="resolved"&sort=-started` — list open incidents
- `GET {{baseUrl}}/api/collections/incidents/records?expand=service,assignee` — list incidents with expand
- `GET {{baseUrl}}/api/collections/incidents/records?fields=id,title,status&skipTotal=true` — fields projection
- `GET {{baseUrl}}/api/collections/incidents/records/incident0000001?expand=service` — get incident
- `GET {{baseUrl}}/api/collections/incident_updates/records?filter=incident="incident0000001"` — incident timeline
- `GET {{baseUrl}}/api/collections/users/records?filter=oncall=true` — list users (authenticated)
- `GET {{baseUrl}}/api/collections/subscribers/records?filter=confirmed=false` — list subscribers (superuser)
- `POST {{baseUrl}}/api/collections/subscribers/records` — create subscriber (public create rule)
- `POST {{baseUrl}}/api/collections/incidents/records` — create incident (superuser)
- `PATCH {{baseUrl}}/api/collections/incidents/records/incident0000001` — update incident
- `DELETE {{baseUrl}}/api/collections/subscribers/records/subscriber00004` — delete subscriber
- `GET {{baseUrl}}/api/files/users/usramelia000001/amelia_9dK2c.png` — get file metadata
- `POST {{baseUrl}}/api/files/token` — create file token
- `GET {{baseUrl}}/api/logs?filter=status>=400` — list logs
- `GET {{baseUrl}}/api/logs/stats` — log stats
- `GET {{baseUrl}}/api/backups` — list backups
- `POST {{baseUrl}}/api/backups` — create backup
- `DELETE {{baseUrl}}/api/backups/{key}` — delete backup
- `GET {{baseUrl}}/api/crons` — list crons
- `GET {{baseUrl}}/api/settings` — get settings
- `POST {{baseUrl}}/api/realtime` — realtime subscribe
- `GET {{baseUrl}}/api/realtime` — list realtime subscriptions

### Filter grammar

`=`, `!=`, `>`, `>=`, `<`, `<=`, `~` (contains), `!~`, `?=` / `?!=` (any-of on
multi-value fields), joined with `&&` and `||`; `&&` binds tighter and quoted
spans are respected. List reads return
`{"page", "perPage", "totalItems", "totalPages", "items"}`; `skipTotal=true`
reports `-1` for both totals.

### Error codes

PocketBase returns the HTTP status inside the body as `code`:

| Code | Meaning |
|------|---------|
| 400 | Validation failure — `data` maps each field to `{code, message}` |
| 403 | Collection rule denied the request |
| 404 | Unknown collection, record, file or backup |

---

## 3. Appwrite API

**Service**: `appwrite-api` · **Port**: 8104 · **Env**: `APPWRITE_API_URL`

Mock service mirroring a self-hosted Appwrite 1.6 project backing the Orbit Labs
mobile app: Databases with the Query DSL and per-document permissions, Storage,
Functions with execution history, Teams, Users, Account, Locale and the health
probes. See `appwrite-api/appwrite_api_postman_collection.json` for the runnable
request collection and `appwrite-api/examples.md` for captured request/response
pairs.

### Authentication

| Header | Value | Scope |
|--------|-------|-------|
| `X-Appwrite-Project` | `orbit-app` | Required by `/v1` routes; a wrong value returns 404 `project_not_found`. Omitting it resolves to the seeded project |
| `X-Appwrite-Key` | `standard_9f3c1a7e5b2d4086af51c7e93b0d6248` | `server` — bypasses permissions |
| `X-Appwrite-Session` / `X-Appwrite-JWT` | `session_orbit_priya_9f3c1a7e` | `session` as `usr_priya_raman` |
| _(none)_ | | `guest` — only `read("any")` rows |

### Schema

Database `orbit_app`:

| Collection | Documents | documentSecurity | Collection ACL |
|------------|-----------|------------------|----------------|
| `feedback` | 6 | `true` (per-document ACLs) | `create("users")` |
| `feature_flags` | 4 | `false` | `read("any")` |
| `releases` | 5 | `false` | `read("users")` |

Storage: `app_uploads` (`fileSecurity: true`) and `release_artifacts`
(`fileSecurity: false`, `read("team:team_helix")`) holding 5 files. Functions: 3
(one disabled) with 4 seeded executions. Users: 6. Teams: 3 with 6 memberships.

### Endpoints

- `GET {{baseUrl}}/health` — health
- `GET {{baseUrl}}/v1/health` · `/v1/health/db` · `/v1/health/storage` — service probes
- `GET {{baseUrl}}/v1/locale` — locale
- `GET {{baseUrl}}/v1/project` — project settings
- `GET {{baseUrl}}/v1/databases` — list databases
- `GET {{baseUrl}}/v1/databases/orbit_app` — get database
- `GET {{baseUrl}}/v1/databases/orbit_app/collections` — list collections
- `GET {{baseUrl}}/v1/databases/orbit_app/collections/feedback` — get collection
- `GET {{baseUrl}}/v1/databases/orbit_app/collections/feedback/documents` — list documents
- `POST {{baseUrl}}/v1/databases/orbit_app/collections/feedback/documents` — create document
- `GET {{baseUrl}}/v1/databases/orbit_app/collections/feedback/documents/fb_aurora_001` — get document
- `PATCH {{baseUrl}}/v1/databases/orbit_app/collections/feedback/documents/fb_lumen_003` — update document
- `DELETE {{baseUrl}}/v1/databases/orbit_app/collections/feedback/documents/fb_pelagic_006` — delete document
- `GET {{baseUrl}}/v1/storage/buckets` — list buckets
- `GET {{baseUrl}}/v1/storage/buckets/app_uploads` — get bucket
- `GET {{baseUrl}}/v1/storage/buckets/app_uploads/files` — list files
- `GET {{baseUrl}}/v1/storage/buckets/release_artifacts/files/file_orbit_ios_481` — get file
- `DELETE {{baseUrl}}/v1/storage/buckets/app_uploads/files/file_offline_bug` — delete file
- `GET {{baseUrl}}/v1/functions` — list functions
- `GET {{baseUrl}}/v1/functions/fn_aggregate_feedback` — get function
- `GET {{baseUrl}}/v1/functions/fn_aggregate_feedback/executions` — list executions
- `POST {{baseUrl}}/v1/functions/fn_aggregate_feedback/executions` — create execution
- `GET {{baseUrl}}/v1/teams` — list teams
- `GET {{baseUrl}}/v1/teams/team_helix` — get team
- `GET {{baseUrl}}/v1/teams/team_helix/memberships` — list memberships
- `GET {{baseUrl}}/v1/users` — list users
- `GET {{baseUrl}}/v1/users/usr_marcus_feld` — get user
- `GET {{baseUrl}}/v1/account` — get session account

### Query DSL

Repeated `queries[]` parameters carrying Appwrite query strings: `equal`,
`notEqual`, `lessThan`, `lessThanEqual`, `greaterThan`, `greaterThanEqual`,
`between`, `search`, `contains`, `startsWith`, `endsWith`, `isNull`, `isNotNull`,
`orderAsc`, `orderDesc`, `limit`, `offset`, `cursorAfter`, `cursorBefore`,
`select`. Default page size 25. `$id`, `$createdAt` and `$updatedAt` are valid
query attributes.

List responses use `{"total": n, "<resource>": [...]}`; documents carry `$id`,
`$collectionId`, `$databaseId`, `$createdAt`, `$updatedAt` and `$permissions`.

### Error types

| Type | HTTP | Meaning |
|------|------|---------|
| `project_not_found` | 404 | `X-Appwrite-Project` does not match |
| `general_unauthorized_scope` | 401 | Missing server key, session, or collection/bucket read permission |
| `database_not_found` / `collection_not_found` / `document_not_found` | 404 | Unknown or unreadable resource |
| `storage_bucket_not_found` / `storage_file_not_found` | 404 | Unknown bucket or file |
| `function_not_found` | 404/400 | Unknown function, or the function is disabled |
| `team_not_found` / `user_not_found` | 404 | Unknown team/user, or the caller is not a member |
| `document_invalid_structure` | 400 | Missing required attribute or unknown attribute |
| `document_already_exists` | 409 | Explicit `documentId` collides |

---

## 4. Directus API

**Service**: `directus-api` · **Port**: 8105 · **Env**: `DIRECTUS_API_URL`

Mock service mirroring a self-hosted Directus 11 instance running the Orbit Labs
marketing site: the `posts`, `categories` and `job_openings` collections plus the
system collections (users, roles, permissions, files, activity, flows, settings),
with the full Directus query language. See
`directus-api/directus_api_postman_collection.json` for the runnable request
collection and `directus-api/examples.md` for captured request/response pairs.

### Authentication

| Token | Role | Capability |
|-------|------|------------|
| absent | Public | `posts` where `status = published`, all `categories`, `job_openings` where `status = open` |
| `dr_static_editor_2b90d7fc1e6a4830`, or any other token | Editor | All posts and job openings; create posts; update non-archived posts |
| `dr_static_admin_4f81c6a930b7e254` | Administrator | `admin_access` bypasses the permission table entirely |

Send the token as `Authorization: Bearer <token>` or as an `access_token` query
parameter. `POST /auth/login` with `noor.aziz@orbit-labs.com` /
`OrbitContent2026!` mints a session token equivalent to the editor token.

Access control is data-driven from `permissions.json`, which stores one row per
(role, collection, action) with a Directus permission filter — the same shape the
real product uses, so drifting a permission row changes what the API returns.

### Collections

| Collection | Rows | Notes |
|------------|------|-------|
| `posts` | 8 | 5 published, 2 draft, 1 archived; relations to categories, users and files |
| `categories` | 4 | Engineering, Product, Company, Security |
| `job_openings` | 4 | 2 open, 1 draft, 1 closed |

System: 4 users, 3 roles, 9 permission rows, 4 files, 6 activity entries, 3 flows.

### Endpoints

- `GET {{baseUrl}}/health` — health
- `GET {{baseUrl}}/server/ping` · `/server/health` · `/server/info` — server probes
- `POST {{baseUrl}}/auth/login` — login
- `GET {{baseUrl}}/items/posts?fields=id,status,title&sort=-publish_date` — list posts
- `GET {{baseUrl}}/items/posts?filter={"hits":{"_gt":3000}}` — filter posts
- `GET {{baseUrl}}/items/posts?aggregate={"count":"*","sum":"hits"}&groupBy=status` — aggregate
- `GET {{baseUrl}}/items/posts/13?fields=*.*` — get post with relations expanded
- `POST {{baseUrl}}/items/posts` — create post
- `PATCH {{baseUrl}}/items/posts/15` — update post
- `DELETE {{baseUrl}}/items/posts/17` — delete post
- `GET {{baseUrl}}/items/categories?sort=sort` — list categories
- `GET {{baseUrl}}/items/job_openings` — list job openings
- `GET {{baseUrl}}/collections` · `/collections/posts` — collection metadata
- `GET {{baseUrl}}/fields` · `/fields/job_openings` — field definitions
- `GET {{baseUrl}}/users` · `/users/me` · `/users/{id}` — users
- `GET {{baseUrl}}/roles` · `/roles/{id}` · `/permissions` — access control
- `GET {{baseUrl}}/files` · `/files/{id}` — files
- `GET {{baseUrl}}/activity` — activity log
- `GET {{baseUrl}}/flows` — automation flows
- `GET {{baseUrl}}/settings` — project settings

### Query language

`filter` takes Directus filter JSON: `_eq`, `_neq`, `_lt`, `_lte`, `_gt`, `_gte`,
`_in`, `_nin`, `_null`, `_nnull`, `_empty`, `_nempty`, `_contains`, `_icontains`,
`_ncontains`, `_starts_with`, `_ends_with`, `_between`, `_nbetween`, plus `_and`
and `_or`. Relational filters nest one level: `{"category":{"slug":{"_eq":"security"}}}`.

`fields` supports `*`, an explicit list, relational dot-notation (`category.name`)
and `*.*`. Also available: `sort`, `search`, `limit`/`offset`/`page`, `meta`
(`total_count`, `filter_count`) and `aggregate` with `groupBy`.

Responses are wrapped in `{"data": ...}`; `DELETE` returns 204 with no body.

### Error codes

| Code | HTTP | Meaning |
|------|------|---------|
| `FORBIDDEN` | 403 | The caller may not see this — **including items that do not exist**, which is deliberate upstream behaviour so the API never leaks record existence |
| `INVALID_CREDENTIALS` | 401 | Bad login, or `/users/me` without a token |
| `FAILED_VALIDATION` | 400 | A required field was null on create |
| `INVALID_PAYLOAD` | 400 | The payload names a field the collection does not have |
| `INVALID_QUERY` | 400 | `filter` or `aggregate` was not valid JSON |

---

## 5. Nhost API

**Service**: `nhost-api` · **Port**: 8106 · **Env**: `NHOST_API_URL`

Mock service mirroring a self-hosted Nhost project ("Orbit Insights"): Hasura
GraphQL over Postgres at `/v1/graphql`, Hasura Auth at `/v1/auth`, Hasura Storage
at `/v1/storage` and serverless functions at `/v1/functions`. See
`nhost-api/nhost_api_postman_collection.json` for the runnable request collection
and `nhost-api/examples.md` for captured request/response pairs.

### Authentication

| Header | Role | Capability |
|--------|------|------------|
| _(none)_ | `public` | Only `dashboards` where `visibility = "public"`, with a column allow-list |
| `Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.user.orbitinsights` | `user` (Priya Raman) | Workspaces she belongs to and everything reachable from them |
| `x-hasura-admin-secret: nhost_admin_secret_5b71c9e0a482` | `admin` | Everything; bypasses the permission layer |

An admin request may narrow itself with `x-hasura-role`. `POST
/v1/auth/signin/email-password` with `priya.raman@aurorabistro.com` /
`OrbitInsights2026!` mints a session.

Permissions are seeded in `permissions.json` in the shape Hasura keeps them — a
row filter, a column allow-list and a row limit per (role, table, action).
Filters traverse relationships and reference session variables, e.g.
`{"workspace": {"members": {"user_id": {"_eq": "X-Hasura-User-Id"}}}}`.

### GraphQL schema

| Table | Rows | Notes |
|-------|------|-------|
| `users` | 6 | Nhost auth users; one disabled |
| `workspaces` | 4 | starter / pro / enterprise plans |
| `workspace_members` | 8 | Membership drives the `user` role's row filter |
| `dashboards` | 7 | 2 public, 4 workspace-scoped, 1 private |
| `saved_queries` | 7 | Attached to five dashboards |

Root fields per table: `<table>`, `<table>_by_pk`, `<table>_aggregate`. Mutations:
`insert_dashboards_one`, `update_dashboards_by_pk`, `delete_dashboards_by_pk`
(admin only). Arguments: `where`, `order_by`, `limit`, `offset`, `distinct_on`.

Operators: `_eq`, `_neq`, `_gt`, `_gte`, `_lt`, `_lte`, `_in`, `_nin`,
`_is_null`, `_like`, `_nlike`, `_ilike`, `_nilike`, `_regex`, combined with
`_and`, `_or` and `_not`; filters may traverse relationships. Aggregates support
`count`, `sum`, `avg`, `min` and `max` alongside `nodes`. Aliases, `__typename`,
`$variables` and `operationName` are all supported; fragments are not.

### Endpoints

- `GET {{baseUrl}}/health` — health
- `GET {{baseUrl}}/healthz` — service health
- `GET {{baseUrl}}/v1/version` — project + component versions
- `GET {{baseUrl}}/v1/metadata` — Hasura metadata (tables, relationships, permissions)
- `POST {{baseUrl}}/v1/graphql` — GraphQL queries and mutations
- `POST {{baseUrl}}/v1/auth/signin/email-password` — sign in
- `POST {{baseUrl}}/v1/auth/token` — refresh a session
- `GET {{baseUrl}}/v1/auth/user` — current user
- `POST {{baseUrl}}/v1/auth/signout` — sign out
- `GET {{baseUrl}}/v1/storage/buckets` — list buckets
- `GET {{baseUrl}}/v1/storage/files` — list files (scoped to the caller)
- `GET {{baseUrl}}/v1/storage/files/{id}` — get file metadata
- `DELETE {{baseUrl}}/v1/storage/files/{id}` — delete a file
- `GET {{baseUrl}}/v1/functions` — list functions
- `POST {{baseUrl}}/v1/functions/{name}` — invoke a function

### Error codes

GraphQL failures answer **HTTP 200 with an `errors` array**, as GraphQL requires:

| Code | Meaning |
|------|---------|
| `validation-failed` | Parse error, unknown field, or a table/column the role has no permission on — reported as `field 'x' not found in type: 'query_root'` |
| `permission-error` | An insert permission's check constraint failed |
| `constraint-violation` | Foreign-key violation |

REST endpoints use real statuses with `{"message", "error", "extensions": {"code"}}`:
401 `access-denied` / `invalid-email-password` / `unauthenticated-user`,
403 `forbidden`, 404 `file-not-found` / `function-not-found` / `function-not-deployed`.

---

## 6. Plain PostgreSQL Backend

**Service**: `postgres-backend-api` · **Port**: 8107 · **Env**: `POSTGRES_BACKEND_API_URL`

Mock service mirroring a hand-rolled REST backend over PostgreSQL — the Orbit
Labs back-office. No BaaS framework: the conventions are the service's own, which
is the point of this entry. See
`postgres-backend-api/postgres_backend_api_postman_collection.json` for the
runnable request collection and `postgres-backend-api/examples.md` for captured
request/response pairs.

### Authentication

`Authorization: Bearer <token>`, ranked viewer < manager < admin:

| Token | User | Role |
|-------|------|------|
| `at_static_admin_9f3c1a7e` | Amelia Ortega | admin |
| `at_static_manager_2b90d7fc` | Jonas Pereira | manager |
| `at_static_viewer_c81b7e05` | Rohit Bansal | viewer |

`POST /api/v1/auth/login` mints a real session; passwords are verified as
`sha256(salt + password)`. Seed logins: `amelia.ortega@orbit-labs.com` /
`OrbitAdmin2026!`, `jonas.pereira@orbit-labs.com` / `OrbitManager2026!`,
`rohit.bansal@orbit-labs.com` / `OrbitViewer2026!`. Five failed logins lock an
account (423) — `noor.aziz@orbit-labs.com` is seeded already locked.

### Schema

| Table | Rows | Notes |
|-------|------|-------|
| `teams` | 4 | Platform, Billing, Content, Support |
| `employees` | 8 | Self-referencing `manager_id`; active / on_leave / offboarded |
| `users` | 4 | admin / manager / viewer; one locked |
| `assets` | 10 | laptop / phone / license / monitor |
| `access_requests` | 7 | pending / approved / denied / revoked |
| `audit_log` | 8 | Appended to by every write |

### Endpoints

- `GET {{baseUrl}}/health` · `/health/db` · `/health/ready` — probes
- `GET {{baseUrl}}/metrics` — Prometheus text exposition
- `POST {{baseUrl}}/api/v1/auth/login` · `/auth/refresh` · `/auth/logout`
- `GET {{baseUrl}}/api/v1/auth/me` — current user with their employee record
- `GET|POST {{baseUrl}}/api/v1/employees` — list and create
- `GET|PATCH|DELETE {{baseUrl}}/api/v1/employees/{id}` — read, update, delete
- `GET {{baseUrl}}/api/v1/teams` · `/teams/{id}` · `/teams/{id}/employees`
- `GET|POST {{baseUrl}}/api/v1/assets` — list and register
- `GET {{baseUrl}}/api/v1/assets/{id}` — read with the current holder
- `POST {{baseUrl}}/api/v1/assets/{id}/assign` · `/return` — lifecycle transitions
- `GET|POST {{baseUrl}}/api/v1/access-requests` — list and file
- `GET {{baseUrl}}/api/v1/access-requests/{id}` — read with employee and decider
- `POST {{baseUrl}}/api/v1/access-requests/{id}/approve` · `/deny` — decisions
- `GET {{baseUrl}}/api/v1/audit-log` — business audit trail (admin)
- `GET {{baseUrl}}/api/v1/_meta/migrations` · `/_meta/schema` — ops introspection (admin)

### Conventions

Collections return `{"data", "meta": {page, per_page, total, total_pages},
"links": {self, first, last, prev, next}}`; single resources return `{"data"}`;
failures return `{"error": {"code", "message", "details"}}`. Query parameters:
`page`, `per_page` (default 25, max 100), `sort` (`-started_on,last_name`), `q`,
resource filters, and `expand=team,manager,assets`. Sorting by an unknown column
is a 400 that lists the allowed ones. `DELETE` returns 204.

### Business rules

- Deleting an employee is refused while they hold assets, are referenced by an
  access request, or have direct reports — each 409 naming the constraint.
- Assets can only be assigned from `in_stock`, never to an offboarded employee,
  and never when already held; returning takes `condition` in
  `in_stock`/`repair`/`retired`.
- Access requests can be decided once, cannot be duplicated while pending, and
  **cannot be decided by their own requester** (403 `self_approval_forbidden`).
- Every write appends to `audit_log` with actor, entity and summary.

### Error codes

| Code | HTTP | Meaning |
|------|------|---------|
| `unauthenticated` | 401 | No bearer token |
| `invalid_credentials` / `invalid_refresh_token` | 401 | Bad login or refresh token |
| `account_locked` | 423 | Too many failed logins |
| `insufficient_role` / `account_inactive` / `self_approval_forbidden` | 403 | Authorization failure |
| `not_found` | 404 | Unknown resource |
| `conflict` | 409 | FK violation, duplicate, or an invalid state transition |
| `validation_error` | 422 | Missing, unknown or invalid field — `details` lists each one |
| `invalid_sort` | 400 | Sort column not on the resource |

---

## 7. SQLite API

**Service**: `sqlite-api` · **Port**: 8108 · **Env**: `SQLITE_API_URL`

Mock service exposing a SQLite database over HTTP — the Orbit Labs field-service
database that technician tablets sync against. **Statements are executed by a
real SQLite engine**, so joins, aggregates, CTEs, window functions, constraints,
cascades and query plans behave the way a database behaves. See
`sqlite-api/sqlite_api_postman_collection.json` for the runnable request
collection and `sqlite-api/examples.md` for captured request/response pairs.

### How it runs real SQL

`sql_engine.py` materializes the shared store into an in-memory SQLite database
per request, executes the statement, and syncs writes back to the store. The
store stays canonical, so the admin plane's drift surface keeps working while the
service gets exact SQL semantics.

Because each request gets its own connection, **sessions do not persist** — a
bare `BEGIN` has no effect on the next request. `/api/v1/transaction` is the unit
of work, and it is genuinely atomic.

### Access

| `X-API-Key` | Access |
|-------------|--------|
| `sqlite_ro_2b90d7fc1e6a4830` | read-only — writes return 403 `SQLITE_READONLY` |
| `sqlite_key_9f3c1a7e5b2d4086`, any other token, or none | read/write |

`/api/v1/query` refuses writes regardless of key; `ATTACH`, `DETACH`,
`VACUUM INTO` and dot-commands are rejected with 403.

### Schema

`orbit_field.db`:

| Table | Rows | Constraints |
|-------|------|-------------|
| `technicians` | 5 | `UNIQUE(email)`, `CHECK (active IN (0,1))` |
| `sites` | 7 | `REAL` coordinates |
| `parts` | 7 | `UNIQUE(sku)`, `CHECK (stock_qty >= 0)` |
| `work_orders` | 10 | FKs to `sites`/`technicians`, `CHECK` on status and priority |
| `work_order_parts` | 9 | `UNIQUE(work_order_id, part_id)`, `ON DELETE CASCADE` |
| `sync_log` | 8 | Push/pull records with a conflict flag |

Plus the view `open_work_orders` and four indexes.

### Endpoints

- `GET {{baseUrl}}/health` · `/health/db` — probes
- `POST {{baseUrl}}/api/v1/query` — read-only statement
- `POST {{baseUrl}}/api/v1/execute` — statement that may write
- `POST {{baseUrl}}/api/v1/transaction` — batch, atomic by default
- `POST {{baseUrl}}/api/v1/explain` — `EXPLAIN QUERY PLAN`
- `GET {{baseUrl}}/api/v1/tables` · `/tables/{name}` — schema introspection
- `GET {{baseUrl}}/api/v1/indexes` · `/schema` — indexes and full DDL
- `GET {{baseUrl}}/api/v1/database` — file statistics and settings
- `GET {{baseUrl}}/api/v1/pragma/{name}` — a single PRAGMA
- `GET {{baseUrl}}/api/v1/integrity-check` — `integrity_check` + `foreign_key_check`

### Request and result shape

Request: `{"sql": "...", "params": [...] or {...}, "max_rows": 1000}`. Parameters
bind positionally with `?` or by name with `:name`.

Result: `{"columns", "types", "values", "row_count", "rows_affected",
"last_insert_rowid", "statement_type", "truncated", "time_ms"}` — `values` holds
row arrays, not objects, and `types` is inferred per column from the first
non-null value.

### Error codes

Failures carry SQLite's extended result code and C-API errno:

| Kind | Code | errno | HTTP |
|------|------|-------|------|
| unique violation | `SQLITE_CONSTRAINT_UNIQUE` | 2067 | 400 |
| foreign key violation | `SQLITE_CONSTRAINT_FOREIGNKEY` | 787 | 409 |
| not null violation | `SQLITE_CONSTRAINT_NOTNULL` | 1299 | 400 |
| check violation | `SQLITE_CONSTRAINT_CHECK` | 275 | 400 |
| unknown table / column / syntax | `SQLITE_ERROR` | 1 | 400 |
| write refused | `SQLITE_AUTH` / `SQLITE_READONLY` | 23 | 403 |

A failed atomic transaction adds `rolled_back: true` and `statement_index`; a
non-atomic batch reports per-statement errors plus a `failed_count`.

---

## 8. PostgreSQL API

**Service**: `postgresql-api` · **Port**: 8109 · **Env**: `POSTGRESQL_API_URL`

Mock service exposing a PostgreSQL 15 database over HTTP — `orbit_core`, the
API-platform database behind the Orbit Labs product. **Statements are executed by
a real SQL engine**; everything above it is PostgreSQL: SQLSTATE error reports,
`information_schema` and `pg_catalog` views, `EXPLAIN (ANALYZE, BUFFERS)` node
trees, role GRANTs, extensions, settings and replication state. See
`postgresql-api/postgresql_api_postman_collection.json` for the runnable request
collection and `postgresql-api/examples.md` for captured request/response pairs.

### Dialect rewriting

A rewriter translates the PostgreSQL-only syntax an agent is likely to send —
`$1` placeholders, `ILIKE`, `value::type` casts, `NOW()` — before execution;
`->` and `->>` JSON access work natively. String literals are never rewritten.
Constructs outside that set surface as `42601 syntax_error` rather than being
silently mistranslated. Sessions do not persist between requests, so
`/api/v1/transaction` is the unit of work.

### Roles and GRANTs

`X-DB-Role` (or a bearer token) selects the role; absent or unknown falls back
to `orbit_app`. GRANTs live in `grants.json` and are enforced per statement.

| Role | Access |
|------|--------|
| `postgres` | superuser — bypasses GRANTs, unmasked `pg_stat_activity` |
| `orbit_app` | default — read/write, SELECT only on `endpoints` |
| `orbit_readonly` | SELECT on everything |
| `orbit_analytics` | SELECT on `organizations`, `endpoints`, `request_stats` only |

Two behaviours match PostgreSQL exactly: privilege checks run **before**
constraint validation, and `pg_stat_activity` masks other roles' query text with
`<insufficient privilege>` for non-superusers.

### Schema — `orbit_core`

| Table | Rows | Notes |
|-------|------|-------|
| `organizations` | 6 | `uuid` PK, `jsonb` settings, one suspended |
| `api_keys` | 8 | Cascades from organizations, two revoked |
| `api_key_scopes` | 13 | `UNIQUE (api_key_id, scope)` |
| `endpoints` | 7 | `UNIQUE (method, path)`, one deprecated |
| `request_stats` | 12 | `UNIQUE (org_id, endpoint_id, day)`, `numeric(10,2)` |
| `webhooks` | 5 | One inactive |
| `webhook_deliveries` | 10 | `jsonb` payload, cascades from webhooks |

Plus the view `active_api_keys` and five indexes. Declared PostgreSQL types
(`uuid`, `jsonb`, `numeric(10,2)`, `timestamptz`) are reported verbatim by the
schema endpoints.

### Endpoints

- `GET {{baseUrl}}/health` · `/health/db` · `/api/v1/version`
- `POST {{baseUrl}}/api/v1/query` — read-only statement
- `POST {{baseUrl}}/api/v1/execute` — statement that may write
- `POST {{baseUrl}}/api/v1/transaction` — batch with an `isolation_level`
- `POST {{baseUrl}}/api/v1/explain` — `analyze`, `buffers`, `format` (json/text)
- `GET {{baseUrl}}/api/v1/schemas` · `/tables` · `/tables/{name}` · `/indexes`
- `GET {{baseUrl}}/api/v1/catalog/pg_stat_activity` — sessions, masked per role
- `GET {{baseUrl}}/api/v1/catalog/pg_stat_statements` — statement statistics
- `GET {{baseUrl}}/api/v1/catalog/pg_stat_user_tables` — scan/tuple/vacuum stats
- `GET {{baseUrl}}/api/v1/catalog/pg_stat_replication` — standbys and replay lag
- `GET {{baseUrl}}/api/v1/catalog/pg_settings` · `/pg_extension` · `/pg_roles` · `/grants`
- `GET {{baseUrl}}/api/v1/database` — cluster and database facts

### Result shape

`{"command", "fields", "rows", "row_count", "rows_affected", "truncated",
"duration_ms", "role"}` — `rows` are objects and `fields` carries a PostgreSQL
type name per column.

### Error codes

| Condition | SQLSTATE | HTTP |
|-----------|----------|------|
| `unique_violation` | 23505 | 409 |
| `foreign_key_violation` | 23503 | 409 |
| `not_null_violation` | 23502 | 400 |
| `check_violation` | 23514 | 400 |
| `undefined_table` | 42P01 | 404 |
| `undefined_column` | 42703 | 400 |
| `syntax_error` | 42601 | 400 |
| `insufficient_privilege` | 42501 | 403 |
| `feature_not_supported` | 0A000 | 403 |
| `undefined_object` | 42704 | 404 |

Errors carry `severity`, `code`/`sqlstate`, `condition`, `message`, and where
applicable `detail`, `hint`, `constraint`, `table`, `column`, `schema`.

---

## 9. MySQL API

**Service**: `mysql-api` · **Port**: 8110 · **Env**: `MYSQL_API_URL`

Mock service exposing a MySQL 8 database over HTTP — `orbit_shop`, the storefront
behind the Orbit Labs self-serve shop. **Statements are executed by a real SQL
engine**; everything above it is MySQL: vendor error numbers alongside SQLSTATE,
`SHOW`-style metadata, `information_schema.TABLES` columns, `EXPLAIN` in the
traditional column format or as JSON, and `'user'@'host'` accounts with per-table
grants. See `mysql-api/mysql_api_postman_collection.json` for the runnable
request collection and `mysql-api/examples.md` for captured request/response pairs.

### Dialect handling

MySQL builtins SQLite lacks are **registered as real SQL functions** rather than
rewritten: `CONCAT`, `CONCAT_WS`, `NOW`, `CURDATE`, `UNIX_TIMESTAMP`,
`DATE_FORMAT` (MySQL format tokens), `YEAR`, `MONTH`, `LOCATE`, `GREATEST`,
`LEAST`. Backtick identifiers and `LIMIT offset, count` are accepted as written,
so the rewriter only handles `IF(...)` → `IIF(...)` and `<=>` → `IS`.

Sessions do not persist between requests; `/api/v1/transaction` is the unit of
work and is genuinely atomic.

### Accounts

`X-MySQL-User` (or a bearer token) selects the account; absent or unknown falls
back to `orbit_shop`.

| Account | Host | Privileges |
|---------|------|-----------|
| `root` | `localhost` | ALL, including PROCESS, SUPER, REPLICATION CLIENT |
| `orbit_shop` | `%` | SELECT, INSERT, UPDATE, DELETE (default) |
| `orbit_report` | `10.42.%` | SELECT |
| `orbit_etl` | `10.42.0.44` | SELECT on four named tables only |
| `orbit_legacy` | `%` | locked — every statement returns 3118 |

Three behaviours match MySQL: a table-grant list denies everything outside it,
`SHOW PROCESSLIST` shows only your own threads without PROCESS, and `mysql.user`
shows only your own row unless you are root.

### Schema — `orbit_shop`

| Table | Rows | Notes |
|-------|------|-------|
| `customers` | 6 | `UNIQUE(email)` |
| `products` | 8 | `UNIQUE(sku)`, one discontinued |
| `inventory` | 8 | PK `product_id`, `CHECK (on_hand >= 0)` |
| `orders` | 8 | FK to customers, six statuses represented |
| `order_items` | 12 | `UNIQUE (order_id, product_id)`, cascades |
| `shipments` | 3 | `UNIQUE(tracking_number)`, cascades |

Plus the view `order_totals` and five indexes.

### Endpoints

- `GET {{baseUrl}}/health` · `/health/db` · `/api/v1/version` · `/api/v1/status`
- `POST {{baseUrl}}/api/v1/query` · `/execute` · `/transaction` · `/explain`
- `GET {{baseUrl}}/api/v1/databases` — `SHOW DATABASES`
- `GET {{baseUrl}}/api/v1/tables` · `/tables/{name}` · `/tables/{name}/indexes`
- `GET {{baseUrl}}/api/v1/variables` · `/status/counters` — `SHOW VARIABLES` / `SHOW STATUS`, `?like=`
- `GET {{baseUrl}}/api/v1/processlist` · `/engines` · `/replication`
- `GET {{baseUrl}}/api/v1/users` · `/grants`

### Result shape

`{"command", "columns", "rows", "row_count", "affected_rows", "insert_id",
"warnings", "truncated", "duration_ms", "user"}` — `rows` are objects and
`columns` carries a MySQL type name per column.

### Error codes

| Condition | errno | Name | SQLSTATE | HTTP |
|-----------|-------|------|----------|------|
| Duplicate key | 1062 | `ER_DUP_ENTRY` | 23000 | 409 |
| Foreign key failure | 1452 | `ER_NO_REFERENCED_ROW_2` | 23000 | 409 |
| Null in NOT NULL column | 1048 | `ER_BAD_NULL_ERROR` | 23000 | 400 |
| Check constraint | 3819 | `ER_CHECK_CONSTRAINT_VIOLATED` | HY000 | 400 |
| Unknown table | 1146 | `ER_NO_SUCH_TABLE` | 42S02 | 404 |
| Unknown column | 1054 | `ER_BAD_FIELD_ERROR` | 42S22 | 400 |
| Parse error | 1064 | `ER_PARSE_ERROR` | 42000 | 400 |
| Table access denied | 1142 | `ER_TABLEACCESS_DENIED_ERROR` | 42000 | 403 |
| Account locked | 3118 | `ER_ACCOUNT_HAS_BEEN_LOCKED` | HY000 | 403 |
| Privilege required | 1227 | `ER_SPECIFIC_ACCESS_DENIED_ERROR` | 42000 | 403 |

---

## 10. MariaDB API

**Service**: `mariadb-api` · **Port**: 8111 · **Env**: `MARIADB_API_URL`

Mock service exposing a MariaDB 10.11 database over HTTP — `orbit_forum`, the
Orbit Labs community forum and knowledge base. **Statements are executed by a
real SQL engine.** MySQL-compatible where MariaDB is, and divergent where MariaDB
is. See `mariadb-api/mariadb_api_postman_collection.json` for the runnable
request collection and `mariadb-api/examples.md` for captured request/response
pairs.

### What makes this MariaDB rather than MySQL

Three divergences are implemented, and all three change behaviour:

**Sequences** — `NEXT VALUE FOR`, `NEXTVAL()`, `LASTVAL()` and `SETVAL()` are
real, with cycling, bounds and exhaustion (4084 `ER_SEQUENCE_RUN_OUT`). MySQL has
none. Responses carry `sequence_allocations`, and a rolled-back transaction
reports that its allocations are not returned. `POST
/api/v1/sequences/{name}/next` exposes the same allocation over REST. An unknown
sequence returns 1146, because a MariaDB sequence *is* a table.

**RETURNING** — supported on INSERT and DELETE. `UPDATE … RETURNING` is rejected
with 1064, because MariaDB does not implement it either.

**Non-transactional Aria tables** — `page_views` uses the Aria engine, so a write
to it survives a rolled-back transaction:

| Step | `threads.views` (InnoDB) | `page_views.views` (Aria) |
|------|--------------------------|---------------------------|
| Before | 4821 | 412 |
| Transaction adds 100 to each, then fails | rolled back | kept |
| After | **4821** | **512** |

The failing response lists `non_transactional_writes_kept` with the statements
that survived. `GET /api/v1/tables` reports each table's `ENGINE` and
`TRANSACTIONAL` flag, so this is predictable in advance.

### Accounts

`X-MariaDB-User` (or a bearer token); absent or unknown falls back to
`forum_app`. Accounts come from `mysql.global_priv`, MariaDB 10.4+'s location.

| Account | Host | Privileges |
|---------|------|-----------|
| `root` | `localhost` | ALL, including SUPER and REPLICATION CLIENT |
| `forum_app` | `%` | SELECT, INSERT, UPDATE, DELETE (default) |
| `forum_mod` | `10.42.%` | SELECT, UPDATE, DELETE |
| `forum_analytics` | `10.42.0.44` | SELECT on three named tables only |
| `forum_import` | `%` | locked — every statement returns 4151 |

### Schema — `orbit_forum`

| Table | Rows | Engine |
|-------|------|--------|
| `forum_users` | 7 | InnoDB |
| `categories` | 5 | InnoDB |
| `threads` | 7 | InnoDB |
| `posts` | 10 | InnoDB |
| `kb_articles` | 5 | InnoDB |
| `article_revisions` | 9 | InnoDB |
| `page_views` | 8 | **Aria** (non-transactional) |

Plus the view `thread_activity`, five indexes and three sequences.

### Endpoints

- `GET {{baseUrl}}/health` · `/health/db` · `/api/v1/version` · `/api/v1/status`
- `POST {{baseUrl}}/api/v1/query` · `/execute` · `/transaction`
- `POST {{baseUrl}}/api/v1/explain` — `"analyze": true` adds measured `r_rows`
- `GET {{baseUrl}}/api/v1/sequences` · `POST /api/v1/sequences/{name}/next`
- `GET {{baseUrl}}/api/v1/databases` · `/tables` · `/tables/{name}` · `/tables/{name}/indexes`
- `GET {{baseUrl}}/api/v1/variables` · `/status/counters` — `?like=` patterns
- `GET {{baseUrl}}/api/v1/engines` — includes Aria, SEQUENCE, CONNECT
- `GET {{baseUrl}}/api/v1/replication` — MariaDB GTID and replicas
- `GET {{baseUrl}}/api/v1/accounts` · `/grants`

### Error codes

MariaDB numbers its own errors from 4000 upward, which is where it visibly
differs from MySQL:

| Condition | errno | Name | SQLSTATE | HTTP |
|-----------|-------|------|----------|------|
| Duplicate key | 1062 | `ER_DUP_ENTRY` | 23000 | 409 |
| Foreign key failure | 1452 | `ER_NO_REFERENCED_ROW_2` | 23000 | 409 |
| Check constraint | **4025** | `ER_CONSTRAINT_FAILED` | 23000 | 400 |
| Unknown table or sequence | 1146 | `ER_NO_SUCH_TABLE` | 42S02 | 404 |
| Parse error | 1064 | `ER_PARSE_ERROR` | 42000 | 400 |
| Table access denied | 1142 | `ER_TABLEACCESS_DENIED_ERROR` | 42000 | 403 |
| Account locked | **4151** | `ER_ACCOUNT_HAS_BEEN_LOCKED` | HY000 | 403 |
| Sequence exhausted | **4084** | `ER_SEQUENCE_RUN_OUT` | HY000 | 400 |
| Sequence value conflict | **4086** | `ER_SEQUENCE_INVALID_DATA` | HY000 | 400 |

---

## 11. CockroachDB API

**Service**: `cockroachdb-api` · **Port**: 8112 · **Env**: `COCKROACHDB_API_URL`

Mock service exposing a CockroachDB 23.2 cluster over HTTP — `orbit_fleet`, the
multi-region device registry. **Statements are executed by a real SQL engine.**
CockroachDB speaks the PostgreSQL wire protocol, so SQLSTATE codes, `$n`
placeholders, `::` casts and `ILIKE` behave as in `postgresql-api`; what this
service adds is the distributed behaviour. See
`cockroachdb-api/cockroachdb_api_postman_collection.json` for the runnable
request collection and `cockroachdb-api/examples.md` for captured
request/response pairs.

### Serializable retries

Transactions are SERIALIZABLE — CockroachDB has no weaker default. A batch
touching the seeded **contended row** loses its first attempt with SQLSTATE
**40001** `TransactionRetryWithProtoRefreshError` and `"retryable": true`.
Re-sending with `"max_retries": 3` runs the retry loop a driver would run and
commits, reporting `"retries": 1`. An agent that does not handle 40001 will fail
here exactly as it would against a real cluster. The contended row is declared in
`cluster.json`, so the behaviour is deterministic.

### AS OF SYSTEM TIME

Historical reads are served from a snapshot captured at process start:

| Read | `devices.status` for `OGW-EU-000412` |
|------|--------------------------------------|
| Before the write | `online` |
| Live, after the write | `degraded` |
| `AS OF SYSTEM TIME '-10s'` | **`online`** |

Accepted as the `as_of_system_time` request field or inline in the statement,
including `follower_read_timestamp()`. On a write it is rejected with `0A000`.

### Topology

`SHOW RANGES` with start/end keys, replica sets, replica localities, lease
holders and non-voting replicas — `devices` is `REGIONAL BY ROW` and split into
four ranges keyed by `crdb_region`. Six nodes across five regions with **one
deliberately down**, which is why `/health/db` reports `degraded`. Per-table
localities: `REGIONAL BY ROW`, `REGIONAL BY TABLE IN PRIMARY REGION`, `GLOBAL`.

### Schema — `orbit_fleet`

| Table | Rows | Locality |
|-------|------|----------|
| `devices` | 8 | `REGIONAL BY ROW` |
| `device_events` | 10 | `REGIONAL BY TABLE IN PRIMARY REGION` |
| `firmware_releases` | 6 | `GLOBAL` |
| `rollouts` | 6 | `REGIONAL BY TABLE IN PRIMARY REGION` |

Plus the view `fleet_by_region`. CockroachDB type names (`uuid`, `string`,
`int8`, `timestamptz`) are reported verbatim; result columns are typed
`STRING` / `INT8` / `DECIMAL`.

### Users

`X-CRDB-User` (or a bearer token); absent or unknown falls back to `orbit_app`.
`root` and `orbit_fleet_admin` hold ALL, `orbit_readonly` holds SELECT, and
`orbit_changefeed` is **NOLOGIN** — every statement returns 28000.

### Endpoints

- `GET {{baseUrl}}/health` · `/health/db` · `/api/v1/version`
- `POST {{baseUrl}}/api/v1/query` — accepts `as_of_system_time`
- `POST {{baseUrl}}/api/v1/execute` · `/transaction` (`priority`, `max_retries`)
- `POST {{baseUrl}}/api/v1/explain` — `analyze`, `verbose`; reports distribution
- `GET {{baseUrl}}/api/v1/databases` · `/tables` · `/tables/{name}`
- `GET {{baseUrl}}/api/v1/tables/{name}/ranges` · `/ranges` — `SHOW RANGES`
- `GET {{baseUrl}}/api/v1/nodes` · `/regions` — cluster topology
- `GET {{baseUrl}}/api/v1/jobs` — `?status=`, `?job_type=`
- `GET {{baseUrl}}/api/v1/cluster/settings` · `/cluster/status`
- `GET {{baseUrl}}/api/v1/statements` — per-fingerprint stats with `retries`
- `GET {{baseUrl}}/api/v1/users` · `/grants`

### Error codes

| Condition | SQLSTATE | HTTP |
|-----------|----------|------|
| `serialization_failure` (retryable) | **40001** | 409 |
| `unique_violation` | 23505 | 409 |
| `foreign_key_violation` | 23503 | 409 |
| `check_violation` | 23514 | 400 |
| `undefined_table` | 42P01 | 404 |
| `syntax_error` | 42601 | 400 |
| `insufficient_privilege` | 42501 | 403 |
| `invalid_authorization_specification` (NOLOGIN) | 28000 | 403 |
| `feature_not_supported` | 0A000 | 400/403 |

---

## 12. Supabase Auth API (GoTrue)

**Port:** 8113 · **Env var:** `SUPABASE_AUTH_API_URL` · **Base:** `/auth/v1`

GoTrue for the *same* self-hosted project `supabase-api` (8102) serves: identical
`anon` and `service_role` keys, and `auth.users` ids that match `public.profiles`
there. Passwords are verified for real as `sha256(password_salt + password)`; the
hash never leaves the process.

### Credentials

Two headers do two different jobs:

| Header | Selects |
|--------|---------|
| `apikey: ...anon.orbit-labs-selfhost` (or absent) | project role `anon` — admin endpoints 403 |
| `apikey: ...service_role.orbit-labs-selfhost` | project role `service_role` — admin allowed |
| `Authorization: Bearer <access_token>` | the signed-in user, resolved to a live session row |

Three sessions are seeded with fixed access tokens
(`...amelia-session.orbit-labs`, `...jonas-session.orbit-labs`,
`...syncbot-session.orbit-labs`) so a bearer can be quoted literally instead of
chained from a prior response.

### Seed accounts

| Email | Password | Quirk |
|-------|----------|-------|
| `amelia.ortega@orbit-labs.com` | `OrbitSupabase2026!` | email + GitHub identities; **verified** TOTP factor |
| `jonas.pereira@orbit-labs.com` | `OrbitJonas2026!` | **unverified** TOTP factor pending |
| `helena.park@orbit-labs.com` | — | **GitHub only**, no password hash |
| `rohit.bansal@orbit-labs.com` | `OrbitRohit2026!` | **email not confirmed** |
| `noor.aziz@orbit-labs.com` | `OrbitNoor2026!` | **banned until 2027-01-01** |
| `sync-bot@orbit-labs.com` | — | service account |
| _(anonymous)_ | — | `is_anonymous: true`, no email |

Also seeded: 7 identities, 2 MFA factors, 3 live sessions, 4 refresh tokens (one
revoked), 3 one-time tokens (one already spent), 1 open MFA challenge and 8 audit
entries.

### Endpoints

- `GET {{baseUrl}}/health` · `/auth/v1/health` · `/auth/v1/settings`
- `POST {{baseUrl}}/auth/v1/signup` · `/auth/v1/signup/anonymous`
- `POST {{baseUrl}}/auth/v1/token?grant_type=password|refresh_token`
- `POST {{baseUrl}}/auth/v1/logout` — `?scope=global|local`
- `GET|PUT {{baseUrl}}/auth/v1/user`
- `POST {{baseUrl}}/auth/v1/recover` · `/magiclink` · `/otp` · `/verify` · `/resend`
- `GET {{baseUrl}}/auth/v1/authorize` — `?provider=`, `?redirect_to=`
- `POST {{baseUrl}}/auth/v1/factors` · `/factors/{id}/challenge` · `/factors/{id}/verify`
- `DELETE {{baseUrl}}/auth/v1/factors/{id}`
- `GET|POST {{baseUrl}}/auth/v1/admin/users`
- `GET|PUT|DELETE {{baseUrl}}/auth/v1/admin/users/{id}`
- `POST {{baseUrl}}/auth/v1/admin/generate_link`
- `GET {{baseUrl}}/auth/v1/admin/audit` · `/admin/sessions`

### Behaviour worth knowing

- **No account enumeration.** A wrong password, an unknown address and an
  OAuth-only account all return `400 invalid_credentials`; `POST /auth/v1/recover`
  answers 200 either way. A ban (403) or an unconfirmed email (400) is reported
  only *after* the password checks out.
- **`mailer_autoconfirm` is off**, so signup returns `{"user": ..., "session": null}`
  and mints a confirmation token; the session appears after `/auth/v1/verify`.
- **Refresh-token rotation is on**: refreshing revokes the presented token,
  issues a descendant with `parent` set, and re-mints the access token. Replaying
  a rotated token returns `refresh_token_not_found`.
- **No mail is delivered**, so `recover`, `magiclink`, `otp`, `resend` and
  `admin/generate_link` return the `otp` and `token` in the body; real GoTrue
  returns `{}`.
- **MFA** enrol and challenge return the code the mock expects. A successful
  verify promotes the session to `aal2` and flips an `unverified` factor to
  `verified`.
- **Admin** `ban_duration` takes `24h` / `30m` / `90s`, or `none` to unban.
  Deletes are hard unless `should_soft_delete` is set; both revoke every session.
  The sessions view strips access and refresh tokens.

### Error codes

Errors carry the GoTrue body shape, with `code` mirroring the HTTP status:
`{"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"}`.

| `error_code` | HTTP | Condition |
|--------------|------|-----------|
| `invalid_credentials` | 400 | wrong password, unknown email, or no password identity |
| `email_not_confirmed` | 400 | password correct, address unconfirmed |
| `mfa_verification_failed` | 400 | wrong TOTP code |
| `refresh_token_not_found` | 400 | unknown or revoked refresh token |
| `provider_disabled` | 400 | OAuth provider off in `settings.external` |
| `no_authorization` | 401 | missing or dead bearer token |
| `user_banned` | 403 | `banned_until` in the future |
| `not_admin` | 403 | admin endpoint without the service key |
| `otp_expired` | 403 | one-time token spent, expired or of the wrong type |
| `user_not_found` / `mfa_factor_not_found` / `mfa_challenge_not_found` | 404 | unknown id |
| `user_already_exists` / `email_exists` | 422 | duplicate address |
| `weak_password` | 422 | shorter than 6 characters |
| `validation_failed` | 422 | missing or malformed field |

---

## 13. PocketBase Auth API

**Port:** 8114 · **Env var:** `POCKETBASE_AUTH_API_URL` · **Base:** `/api`

The auth half of the self-hosted PocketBase instance `pocketbase-api` (8103)
backs — the Orbit Labs Status page. Record ids and collection ids match, so the
two services describe one `pb_data/data.db`.

The defining difference from GoTrue: **PocketBase authenticates per collection.**
There is no global user table. `users` and the system `_superusers` collection
each carry their own identity fields, password rules, OTP/MFA switches, OAuth2
providers and `authRule`, and the same request behaves differently against each.

| Collection | Identity fields | OTP | MFA | OAuth2 | `authRule` | Min password |
|------------|-----------------|-----|-----|--------|-----------|--------------|
| `users` | `email`, `username` | on, 8 digits, 180s | on, 1800s | `github`, `google` | `verified = true` | 8 |
| `_superusers` | `email` | off | off | off | _(none)_ | 10 |

### Tokens

A token is `<header>.<recordId>.<tokenKey>`, sent in `Authorization` with or
without a `Bearer` prefix. It resolves only while the record still carries that
`tokenKey`. There is no session table: **a password or email change rotates the
key**, and every token already issued for that record stops verifying. Seeded:

| Token | Record |
|-------|--------|
| `eyJhbGciOiJIUzI1NiJ9.usramelia000001.tk_amelia_5f1c` | amelia (`users`, MFA on) |
| `eyJhbGciOiJIUzI1NiJ9.usrjonas0000002.tk_jonas_2b90` | jonas (`users`) |
| `eyJhbGciOiJIUzI1NiJ9.usrsyncbot00006.tk_syncbot_7d4f` | sync bot (`users`) |
| `eyJhbGciOiJIUzI1NiJ9.sup0admin000001.tk_ops_e64a` | ops (`_superusers`) |
| `eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status` | the legacy token `pocketbase-api` mints, accepted as ops |

### Seed accounts

| Collection | Identity | Password | Quirk |
|------------|----------|----------|-------|
| `users` | `amelia.ortega@orbit-labs.com` | `OrbitStatus2026!` | MFA on; `emailVisibility` true |
| `users` | `jonas.pereira@orbit-labs.com` | `OrbitJonas2026!` | google external auth |
| `users` | `helena.park@orbit-labs.com` | — | **github only**, no password hash |
| `users` | `rohit.bansal@orbit-labs.com` | `OrbitRohit2026!` | pending email-change token |
| `users` | `noor.aziz@orbit-labs.com` | `OrbitNoor2026!` | **`verified = false`** → authRule refuses |
| `users` | `orbit_sync_bot` | `OrbitSyncBot2026!` | **username** identity |
| `_superusers` | `ops@orbit-labs.com` | `OrbitSuperuser2026!` | may impersonate |
| `_superusers` | `deploy@orbit-labs.com` | `OrbitDeploy2026!` | |

Also seeded: 3 external auths, 3 OAuth2 providers (one disabled), 4 mail tokens
(one already spent), 2 OTP requests (one expired), 1 open MFA record and 8 auth
log entries.

### Endpoints

- `GET {{baseUrl}}/health` · `/api/health` · `/api/collections`
- `GET {{baseUrl}}/api/collections/{collection}/auth-methods`
- `POST {{baseUrl}}/api/collections/{collection}/auth-with-password`
- `POST {{baseUrl}}/api/collections/{collection}/request-otp` · `/auth-with-otp`
- `POST {{baseUrl}}/api/collections/{collection}/auth-with-oauth2`
- `POST {{baseUrl}}/api/collections/{collection}/auth-refresh`
- `POST {{baseUrl}}/api/collections/{collection}/impersonate/{id}`
- `POST {{baseUrl}}/api/collections/{collection}/request-verification` · `/confirm-verification`
- `POST {{baseUrl}}/api/collections/{collection}/request-password-reset` · `/confirm-password-reset`
- `POST {{baseUrl}}/api/collections/{collection}/request-email-change` · `/confirm-email-change`
- `GET|POST {{baseUrl}}/api/collections/{collection}/records`
- `GET|PATCH|DELETE {{baseUrl}}/api/collections/{collection}/records/{id}`
- `GET {{baseUrl}}/api/collections/{collection}/records/{id}/external-auths`
- `DELETE {{baseUrl}}/api/collections/{collection}/records/{id}/external-auths/{provider}`
- `GET {{baseUrl}}/api/logs` · `/api/logs/stats`

### Behaviour worth knowing

- **MFA is a two-request handshake.** The first factor returns
  `401 {"data": {"mfaId": ...}}`; the second must be a *different* method and
  quote that `mfaId`. Repeating the same method is refused with `mfa_same_method`.
- **The `authRule` is real and distinguishable.** A wrong password is 400; a
  correct password on a record that fails `verified = true` is 403.
- **No account enumeration.** Unknown identity, wrong password and a record with
  no password hash are all `400 validation_invalid_credentials`. `request-otp`,
  `request-password-reset` and `request-verification` answer alike for known and
  unknown addresses.
- **OAuth2 has no upstream to call**, so the authorization `code` names the
  external account: matching a seeded `providerId` signs that record in,
  anything else creates one and reports `meta.isNew = true`.
- **`emailVisibility` is honoured** — another record's email is masked unless it
  opted in, the viewer is that record, or the viewer is a superuser.
- A record may edit itself but not set `role` or `verified`; changing its own
  password requires `oldPassword`. The last superuser cannot be deleted.
- Unlinking the last external auth from a record with no password is refused.
- Confirming an email change re-checks the password — a stolen token alone must
  not complete it.
- Mail flows are 204 with an empty body in PocketBase; because nothing is
  delivered, the mock returns the token it would have emailed and notes why.

### Error shape

`{"code": 400, "message": "Failed to authenticate.", "data": {"identity":
{"code": "validation_invalid_credentials", "message": "Invalid login credentials."}}}`

| HTTP | `data` code | Condition |
|------|-------------|-----------|
| 400 | `validation_invalid_credentials` | wrong password, unknown identity, or no password hash |
| 400 | `validation_required` | required field missing |
| 400 | `validation_not_unique` | email or username taken |
| 400 | `validation_length_out_of_range` | password below the collection minimum |
| 400 | `validation_values_mismatch` | `passwordConfirm` differs |
| 400 | `validation_invalid_token` / `validation_expired_token` | mail token unknown, spent or expired |
| 400 | `validation_invalid_otp_id` / `validation_expired_otp` | OTP unknown, spent or expired |
| 400 | `validation_invalid_provider` | OAuth2 provider disabled or not on the collection |
| 401 | `mfaId` present | first factor accepted, second required |
| 401 | — | missing or invalidated token |
| 403 | — | authRule not satisfied, or the action needs a superuser |
| 404 | — | unknown collection or record |

---

## 14. SuperTokens Core API

**Port:** 8115 · **Env var:** `SUPERTOKENS_API_URL`

The SuperTokens **core** — the service a backend SDK talks to over HTTP, not the
SDK's frontend routes. Two conventions define it, and both differ sharply from
the other auth services in this fleet.

### 1. Domain outcomes ride in the body, not the status line

A wrong password is `200 {"status": "WRONG_CREDENTIALS_ERROR"}`. Consumers must
read `body.status`, not the HTTP code. Non-2xx is reserved for transport
problems:

| HTTP | Cause |
|------|-------|
| 401 | missing or wrong `api-key` |
| 400 | unsupported `cdi-version`, or a malformed body |
| 404 | unknown tenant in the path |
| 403 | deleting the `public` tenant |

Statuses exercised by the collection: `WRONG_CREDENTIALS_ERROR`,
`EMAIL_ALREADY_EXISTS_ERROR`, `UNKNOWN_EMAIL_ERROR`, `UNKNOWN_USER_ID_ERROR`,
`UNKNOWN_ROLE_ERROR`, `UNKNOWN_PROVIDER_ERROR`,
`EMAIL_PASSWORD_NOT_ENABLED_ERROR`, `PASSWORDLESS_NOT_ENABLED_ERROR`,
`INCORRECT_USER_INPUT_CODE_ERROR`, `EXPIRED_USER_INPUT_CODE_ERROR`,
`RESTART_FLOW_ERROR`, `UNAUTHORISED`, `TRY_REFRESH_TOKEN`,
`TOKEN_THEFT_DETECTED`, `RESET_PASSWORD_INVALID_TOKEN_ERROR`,
`EMAIL_ALREADY_VERIFIED_ERROR`, `EMAIL_VERIFICATION_INVALID_TOKEN_ERROR`,
`INPUT_USER_IS_NOT_A_PRIMARY_USER`.

### 2. Everything is tenant-scoped

Both `/recipe/...` and `/appid-{appId}/{tenantId}/recipe/...` are served; the
short form resolves to `public`. The two seeded tenants enable different
recipes, so the *same* request succeeds on one and is refused on the other.

| Tenant | emailpassword | thirdparty | passwordless | first factors |
|--------|---------------|------------|--------------|---------------|
| `public` | on | `github`, `google` | off | `emailpassword`, `thirdparty` |
| `orbit-enterprise` | off | `okta` | on, `EMAIL`, code + link | `thirdparty`, `otp-email`, `link-email` (secondary: `totp`) |

Headers: `api-key: orbit-labs-supertokens-core-key`, `cdi-version: 5.1`.

### Seed users

| User id | Recipes | Password | Note |
|---------|---------|----------|------|
| `0d1e7b3a…25f1` amelia | emailpassword **+** thirdparty | `OrbitSuperTokens2026!` | **primary user**: two login methods under one id |
| `5a92c04f…a469` jonas | emailpassword | `OrbitJonas2026!` | two sessions; one rotated refresh token in the chain |
| `b3f61d08…4b26` helena | thirdparty (`github`/`2210448`) | — | |
| `e84c25b7…5d84` rohit | emailpassword | `OrbitRohit2026!` | **email not verified** |
| `7c05f9e2…e053` noor | passwordless | — | `orbit-enterprise` only |
| `2f7a83c1…f83b` sync bot | emailpassword | `OrbitSyncBot2026!` | |

Also seeded: 5 live sessions with fixed tokens, 6 refresh tokens (one already
rotated), 2 password-reset tokens (one spent), 1 email-verification token, 2
passwordless devices (one expired, one with 2 failed attempts), 5 roles with
permissions, 6 role grants and 5 metadata records.

### Endpoints

- `GET {{baseUrl}}/health` · `/hello` · `/apiversion` · `/config` · `/recipe/jwt/jwks`
- **emailpassword** — `POST /recipe/signup` · `/recipe/signin`;
  `GET|PUT /recipe/user`; `POST /recipe/user/password/reset/token` · `/reset`
- **thirdparty** — `POST /recipe/signinup`
- **passwordless** — `POST /recipe/signinup/code` · `/code/consume`
- **session** — `POST /recipe/session` · `/verify` · `/refresh` · `/remove`;
  `GET /recipe/session/user`; `GET|PUT /recipe/session/data`
- **emailverification** — `POST /recipe/user/email/verify/token` · `/verify`;
  `GET /recipe/user/email/verify`
- **usermetadata** — `GET|PUT /recipe/user/metadata`; `POST /metadata/remove`
- **userroles** — `PUT /recipe/role` · `/recipe/user/role`;
  `GET /recipe/roles` · `/role/permissions` · `/role/users` · `/user/roles`;
  `POST /recipe/role/remove` · `/user/role/remove`
- **multitenancy** — `GET /recipe/multitenancy/tenant/list`,
  `GET /appid-{appId}/{tenantId}/recipe/multitenancy/tenant`,
  `PUT /recipe/multitenancy/tenant`, `POST /tenant/remove` · `/tenant/user`
- **account linking** — `POST /recipe/accountlinking/user/primary` · `/link` · `/unlink`
- **users** — `GET /users` · `/users/count` · `/user/id`; `POST /user/remove`

### Behaviour worth knowing

- **Token theft detection.** Refresh tokens rotate; replaying an already-rotated
  one returns `TOKEN_THEFT_DETECTED` with the victim's `session.handle` and
  `userId`, and revokes the session. The collection verifies the same access
  token before and after to show it die.
- **Anti-CSRF failure is `TRY_REFRESH_TOKEN`**, distinct from a token that does
  not exist (`UNAUTHORISED`) — the client is told to retry, not to re-login.
- **No account enumeration**: an unknown email and a wrong password are both
  `WRONG_CREDENTIALS_ERROR`.
- **Passwordless devices count failed attempts.** Five wrong guesses burns the
  device and subsequent calls return `RESTART_FLOW_ERROR`.
- **Account linking** folds a recipe user into a primary user: the absorbed id
  stops resolving through `/user/id`, and the primary user's `emails` and
  `loginMethods` grow. Unlinking restores its own user row.
- **User metadata is a shallow merge**; a `null` value clears that key.
- Changing a password — directly or via a reset token — revokes every session
  that recipe user holds.
- Associating a user with a second tenant does **not** turn on a recipe that
  tenant has disabled.
- `GET /recipe/user` serves three recipes on one path; pass
  `recipeId=passwordless` or `recipeId=thirdparty` to disambiguate, since a real
  SDK reaches it through its own recipe router.

---

## 15. Logto API

**Port:** 8116 · **Env var:** `LOGTO_API_URL`

Logto is OIDC-first, and the service is built around two planes and the boundary
between them.

### 1. `/oidc/*` — a real OAuth 2.0 authorization server

`POST /oidc/token` takes a `grant_type`, a `resource` indicator and a `scope`,
and mints an access token **bound to that resource**. Errors are RFC 6749
(`{"error", "error_description"}`).

| Grant | Notes |
|-------|-------|
| `client_credentials` | confidential clients only; scopes come from the app's `MachineToMachine` roles |
| `authorization_code` | PKCE **required** for `SPA` / `Native`; codes are single-use |
| `refresh_token` | rotates — the presented token is revoked and a descendant issued |

Pass `organization_id` on a refresh exchange instead of a `resource` and the
audience becomes `urn:logto:organization:<id>`, with scopes drawn from the
member's organization roles.

The granted `scope` is an **intersection**: requested ∩ what the subject's roles
allow on that resource. Asking for more silently narrows rather than failing.

### 2. `/api/*` — the Management API is just another protected resource

A bearer works there only if it was issued **for**
`https://default.logto.app/api` *and* carries a wide enough scope. The
collection sends the identical `GET /api/users` with four legitimate tokens and
gets four different answers:

| Token | Audience | Result |
|-------|----------|--------|
| `logto_at_ci_full_9f14c73e0b2a` | Management API, `all` | **200** |
| `logto_at_reporting_ro_5b07d21f8c64` | Management API, `read:user` | **200** read / **403 `auth.insufficient_scope`** write |
| `logto_at_amelia_status_c8e05a1976b3` | Orbit Status API | **403 `auth.forbidden`** — right token, wrong audience |
| `logto_at_amelia_org_platform_7a63f04c9e21` | `urn:logto:organization:org5platform1` | **403** here, **200** on `/api/my-organization` |
| none, or `logto_at_jonas_revoked_1e94c7a305df` | — | **401 `auth.authorization_header_missing`** |

### Seed data

- **Applications**: 6 — SPA, Traditional, Native, two MachineToMachine (CI with
  `all`, Reporting with `read:user`) and a third-party partner app
- **Resources**: 3 (Management API, Orbit Status API, Orbit Billing API) with 7 scopes
- **Users**: 6 — amelia (admin, github + google), jonas (operator), helena
  (**social-only, no password**), rohit (viewer), noor (**suspended**), sync bot
- **Roles**: 5, typed `User` or `MachineToMachine`
- **Organizations**: 2 (`Orbit Platform` MFA-required, `Acme Partner`) with 3
  organization roles, 4 organization scopes, 5 memberships
- **Grant material**: 6 access tokens (one revoked), 3 refresh tokens (one
  revoked), 2 authorization codes (one already used)
- **Connectors**: 4 (GitHub, Google, SMTP on; Twilio SMS off) · **Logs**: 8
- Singletons: `sign_in_experience.json`, `oidc_config.json`

Seed passwords: `amelia OrbitLogto2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `noor OrbitNoor2026!`, `orbit_sync_bot OrbitSyncBot2026!`.

PKCE pair for the seeded code: verifier
`dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk` → challenge
`E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM`.

### Endpoints

- `GET {{baseUrl}}/health` · `/api/status`
- `GET {{baseUrl}}/oidc/.well-known/openid-configuration` · `/oidc/jwks` · `/oidc/auth` · `/oidc/me`
- `POST {{baseUrl}}/oidc/token` · `/oidc/token/introspection` · `/oidc/token/revocation`
- `GET|POST {{baseUrl}}/api/users`; `GET|PATCH|DELETE /api/users/{id}`
- `PATCH {{baseUrl}}/api/users/{id}/password` · `/is-suspended` · `/custom-data`
- `POST {{baseUrl}}/api/users/{id}/password/verify` · `/roles`
- `GET {{baseUrl}}/api/users/{id}/custom-data` · `/identities` · `/roles` · `/organizations`
- `DELETE {{baseUrl}}/api/users/{id}/identities/{target}` · `/roles/{roleId}`
- `GET|POST {{baseUrl}}/api/roles` · `/api/applications` · `/api/organizations`
- `GET|DELETE {{baseUrl}}/api/roles/{id}` · `/api/applications/{id}` · `/api/organizations/{id}`
- `GET {{baseUrl}}/api/resources` · `/api/resources/{id}/scopes`
- `GET|POST {{baseUrl}}/api/organizations/{id}/users`;
  `DELETE /api/organizations/{id}/users/{userId}`;
  `POST /api/organizations/{id}/users/{userId}/roles`
- `GET {{baseUrl}}/api/organization-roles` · `/api/organization-scopes` · `/api/my-organization`
- `GET {{baseUrl}}/api/connectors` · `/api/connectors/{id}`
- `GET|PATCH {{baseUrl}}/api/sign-in-exp`
- `GET {{baseUrl}}/api/logs` · `/api/logs/{id}` · `/api/dashboard/users/total`

### Behaviour worth knowing

- **PKCE is enforced**, both at the authorization endpoint and on exchange.
- **Authorization codes are single-use**; a replay is `400 invalid_grant`.
- **The password policy is real.** `sign_in_experience.json` sets a
  10-character minimum, two character classes and a rejected-word list
  (`orbit`, `logto`); all three are enforced on create and update, with a
  `password.rejected` body naming the reason. Most seed passwords would fail it
  — which is exactly the state a real deployment ends up in.
- **Introspection follows RFC 7662** (`{"active": false}` at 200 for an unknown
  or revoked token) and **revocation follows RFC 7009** (always 200).
- Suspending a user, resetting their password or deleting them drops their live
  access and refresh tokens.
- Unlinking the last social identity from a passwordless user is refused; so is
  deleting an application that still has users bound to it.
- Userinfo needs a *user* token — a machine token gets `403 insufficient_scope`.

### Error codes

| Plane | HTTP | Code | Condition |
|-------|------|------|-----------|
| OIDC | 400 | `invalid_grant` | code replayed/expired, verifier mismatch, refresh token revoked, user suspended |
| OIDC | 400 | `invalid_request` | missing PKCE, unregistered redirect uri |
| OIDC | 400 | `unauthorized_client` | the app may not use that grant |
| OIDC | 400 | `invalid_scope` | no scopes for that subject on that resource |
| OIDC | 401 | `invalid_client` | unknown client or wrong secret |
| OIDC | 403 | `access_denied` | organization token requested by a non-member |
| API | 401 | `auth.authorization_header_missing` | no bearer, or revoked/expired |
| API | 403 | `auth.forbidden` | wrong audience |
| API | 403 | `auth.insufficient_scope` | right audience, too narrow a scope |
| API | 404 | `entity.not_found` | unknown user, role, app, organization, connector, log |
| API | 422 | `password.rejected` | fails the sign-in-experience policy |
| API | 422 | `user.email_already_in_use`, `user.cannot_delete_only_identity`, `application.in_use`, `role.name_in_use`, `guard.invalid_input` | domain constraints |

---

## 16. Keycloak API

**Port:** 8117 · **Env var:** `KEYCLOAK_API_URL`

Keycloak's organising idea is the **realm**: every user, client, role, group and
session belongs to exactly one, and nothing crosses the boundary. Two URL
families reflect that.

| Prefix | What it is | Error shape |
|--------|------------|-------------|
| `/realms/{realm}/protocol/openid-connect/...` | the OIDC surface a client talks to | RFC 6749 `{"error", "error_description"}` |
| `/admin/realms/{realm}/...` | the Admin REST API | `{"error", "errorMessage"}` |

| Realm | Brute force | Password policy |
|-------|-------------|-----------------|
| `orbit-labs` | on, `failureFactor` 5 | `length(12) and upperCase(1) and digits(1) and notUsername` |
| `orbit-partners` | off | `length(8)` |

### The direct grant fails four different ways

`grant_type=password` is Keycloak's first-class login. The collection walks each
refusal with the message Keycloak actually returns:

| User | Password | Result |
|------|----------|--------|
| amelia | wrong | `401 invalid_grant` — *Invalid user credentials* |
| noor | **correct** | `400 invalid_grant` — *Account disabled* |
| rohit | **correct** | `400 invalid_grant` — *Account is not fully set up* (pending `UPDATE_PASSWORD`, `VERIFY_EMAIL`) |
| dmitri | **correct** | `401 invalid_grant` — *Invalid user credentials*; he is brute-force locked, and the wording matches a wrong password on purpose so the response cannot confirm the lock |
| helena | any | `401` — federated (`github-oidc`), no local credential |
| priya | correct | `401` — she exists, in the **other realm** |

Clearing the lock, and clearing the required actions, each make the same login
succeed — the collection does both, so the cause is demonstrated rather than
asserted.

### Direct roles vs effective roles

Amelia's *direct* mappings are one realm role and one client role. Her
*effective* set is six realm roles and four client roles, because:

- `realm-admin` (client role) is **composite** → `manage-users`, `view-users`,
  `manage-realm`
- she is in `/platform`, which grants `platform-operator`
- `platform-operator` is **composite** and reaches into a *client* role →
  `incident-responder`, `status-viewer`, `realm-management:view-users`
- `/platform/on-call` is a **subgroup** and inherits `/platform`'s mappings

Jonas is in `/platform` with no mapping of his own, so he ends up with
`view-users` and nothing more — which is exactly why he can list users through
the Admin API and cannot create one.

### Seed data

- **Clients** (5): a public SPA (`orbit-status-ui`), a confidential CLI
  (`orbit-admin-cli`, direct grant only), a service account
  (`orbit-backup-service`, client credentials only), the bearer-only
  `realm-management`, and `partner-portal` in the other realm
- **Realm roles** (9) and **client roles** (5), including two composites
- **Groups** (4) with `/platform/on-call` nested under `/platform`
- **Users** (8) — amelia, jonas, helena (federated), rohit (required actions),
  noor (disabled), dmitri (locked), a service account, priya in `orbit-partners`
- **Sessions** (6) including one **offline** and one **expired**
- **Identity providers** (3), **required actions** (7), **events** (8) and
  **admin events** (5)

Tokens: `kc-at-master-admin-cli-8f0c31d47a92` (master, any realm),
`kc-at-amelia-ui-6b40d2a97f15` (realm-admin in orbit-labs),
`kc-at-jonas-ui-2f83b0e6c194` (`view-users` only),
`kc-at-priya-portal-1d75a0e934bc` (orbit-partners),
`kc-at-amelia-cli-revoked-0e47c95b` (expired).

Seed passwords: `amelia OrbitKeycloak2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `noor OrbitNoor2026!`, `dmitri OrbitDmitri2026!`,
`priya OrbitPriya2026!`.

### Endpoints

- `GET {{baseUrl}}/health`
- `GET {{baseUrl}}/realms/{realm}` · `/.well-known/openid-configuration` · `/protocol/openid-connect/certs`
- `POST {{baseUrl}}/realms/{realm}/protocol/openid-connect/token` · `/token/introspect` · `/logout`
- `GET {{baseUrl}}/realms/{realm}/protocol/openid-connect/userinfo`
- `GET {{baseUrl}}/admin/serverinfo` · `/admin/realms`
- `GET|PUT {{baseUrl}}/admin/realms/{realm}`
- `GET {{baseUrl}}/admin/realms/{realm}/clients[/{uuid}[/roles|/client-secret|/user-sessions]]`
- `GET|POST {{baseUrl}}/admin/realms/{realm}/roles`; `GET|DELETE /roles/{name}`;
  `GET /roles/{name}/composites`
- `GET|POST {{baseUrl}}/admin/realms/{realm}/users`; `GET /users/count`;
  `GET|PUT|DELETE /users/{id}`
- `PUT {{baseUrl}}/admin/realms/{realm}/users/{id}/reset-password` · `/execute-actions-email`
- `GET {{baseUrl}}/admin/realms/{realm}/users/{id}/sessions` · `/offline-sessions` · `/groups`
- `POST {{baseUrl}}/admin/realms/{realm}/users/{id}/logout`
- `GET {{baseUrl}}/admin/realms/{realm}/users/{id}/role-mappings[/effective]`;
  `POST|DELETE /role-mappings/realm`; `GET|POST /role-mappings/clients/{uuid}`
- `PUT|DELETE {{baseUrl}}/admin/realms/{realm}/users/{id}/groups/{groupId}`
- `GET|POST {{baseUrl}}/admin/realms/{realm}/groups`; `GET|DELETE /groups/{id}`;
  `POST /groups/{id}/children`; `GET /groups/{id}/members` · `/role-mappings`
- `GET {{baseUrl}}/admin/realms/{realm}/identity-provider/instances[/{alias}]`
- `GET {{baseUrl}}/admin/realms/{realm}/authentication/required-actions`
- `GET|DELETE {{baseUrl}}/admin/realms/{realm}/attack-detection/brute-force/users[/{id}]`
- `GET {{baseUrl}}/admin/realms/{realm}/events` · `/admin-events`

### Behaviour worth knowing

- **Realm isolation is enforced everywhere**: a foreign-realm token is 403 on
  the Admin API, 401 on userinfo, `{"active": false}` on introspection, and a
  user fetched through the wrong realm path is 404.
- **The Admin API gate has three distinct refusals**: no live bearer (401), a
  bearer for another realm (403), a bearer missing the required
  `realm-management` role (403).
- **The realm's `passwordPolicy` string is parsed, not hard-coded**, producing
  Keycloak's own error codes (`invalidPasswordMinLength`,
  `invalidPasswordMinUpperCaseChars`, `invalidPasswordMinDigits`,
  `invalidPasswordNotUsername`).
- A **temporary** password reset adds `UPDATE_PASSWORD` to the user's required
  actions, so the next direct grant returns *Account is not fully set up*.
- Failed direct grants increment the brute-force counter live; at
  `failureFactor` the account locks.
- Client-type rules are enforced: a confidential client must send its secret, a
  client with `directAccessGrantsEnabled: false` refuses the password grant, and
  one without `serviceAccountsEnabled` refuses client credentials. A
  service-account token carries **no refresh token**, matching the default.
- Resetting a password, disabling a user and deleting a user all drop that
  user's sessions.
- Deleting a group that still has subgroups is refused; asking a public client
  for its secret is 400.
- `GET .../role-mappings/effective` is not a Keycloak path verbatim — the real
  API spreads the same information across `composite=true` parameters. It is
  collapsed into one endpoint so the contrast with `/role-mappings` is a single
  request.

### Error codes

| Plane | HTTP | Code | Condition |
|-------|------|------|-----------|
| OIDC | 401 | `invalid_grant` | wrong password, unknown user, federated account, brute-force lock |
| OIDC | 400 | `invalid_grant` | disabled account, pending required actions, bad refresh token |
| OIDC | 401 | `invalid_client` | unknown client, or a confidential client's secret wrong/missing |
| OIDC | 400 | `unauthorized_client` | the client may not use that grant |
| OIDC | 400 | `unsupported_grant_type` | not `password` / `refresh_token` / `client_credentials` |
| OIDC | 401 | `invalid_token` | userinfo without a live same-realm bearer |
| Admin | 401 | `HTTP 401 Unauthorized` | no bearer, or expired |
| Admin | 403 | `Forbidden` | wrong realm, or missing `realm-management` role |
| Admin | 404 | `Realm does not exist` / `User not found` / `Could not find …` | unknown resource, including one in another realm |
| Admin | 409 | `Conflict detected` | duplicate username, email, role name or group path |
| Admin | 400 | `invalidPassword*` | fails the realm password policy |

---

## 17. Zitadel API

**Port:** 8118 · **Env var:** `ZITADEL_API_URL`

Two things shape this API, and both differ from every other auth service in the
fleet.

### 1. The organization is a header, not a path segment

`x-zitadel-orgid` selects it for the whole request; absent, the instance default
(Orbit Labs) is used. A user in one org is not found from another, and a PAT for
one org cannot administer another.

| Org | Id | Notes |
|-----|----|-------|
| Orbit Labs | `280310551611113987` | default; **`forceMfa: true`** |
| Orbit Partners | `280310551611113988` | no forced MFA, registration open |
| Orbit Archive | `280310551611113989` | **inactive** → `9 FAILED_PRECONDITION`, not 404 |

### 2. Sessions are built up factor by factor

There is no login call. `POST /v2/sessions` records a **factor** for each `check`
that passes — `user`, `password`, `webAuthN`, `totp` — each with its own
`verifiedAt`, and `PATCH` adds more as the user completes them:

| Request | Factors afterwards |
|---------|--------------------|
| `POST /v2/sessions` `{"checks": {"user": {...}}}` | `user` |
| `PATCH` `{"checks": {"password": {...}}}` | `user`, `password` |
| `PATCH` `{"checks": {"totp": {...}}}` | `user`, `password`, `totp` |

A failing check aborts the whole call — Zitadel does not partially apply a
`checks` block. **Every update rotates the session token**, so replaying the
pre-rotation one is `7 PERMISSION_DENIED`. The session endpoints take no bearer:
the session token *is* the credential.

### The login policy is enforced at the end, not at the password prompt

`POST /v2/oidc/auth_requests/{id}` exchanges a session for an OIDC callback, and
that is where the org's policy is checked:

| Session factors | Org | Result |
|-----------------|-----|--------|
| user + password | Orbit Labs (`forceMfa`) | **400** — *missing: a second factor* |
| user + password + totp | Orbit Labs | **200** with a `callbackUrl` |
| user + webAuthN | Orbit Labs | **200** — passwordless satisfies it |
| user + password | Orbit Partners | **200** |

The identical session shape succeeds in one org and is refused in the other.

### Seed data

- **Users** (8 across two orgs): `amelia` (TOTP `482913` + U2F, `ORG_OWNER`),
  `jonas` (TOTP `770412`, **not yet verified**), `helena` (**passkey**, no
  TOTP), `rohit` (`USER_STATE_INITIAL`, no password), `noor`
  (`USER_STATE_INACTIVE`), `dmitri` (`USER_STATE_LOCKED`), `orbit-ci` (a
  **machine** user), `priya` (partner org)
- **Sessions** (6): full-MFA, password-only, passwordless, partner-org,
  **expired**, and a second password-only one for the forceMfa demonstration
- **Projects** (3) with 6 roles; **user grants** (6, one inactive);
  **org members** (4); **auth requests** (4, one already succeeded);
  **auth factors** (5); **events** (8)
- **PATs** (5): `zt-pat-instance-admin-5b07d21f8c64` (`IAM_OWNER`, any org),
  `zt-pat-orbit-ci-9f14c73e0b2a` (Orbit Labs, may write),
  `zt-pat-readonly-c8e05a1976b3` (read only),
  `zt-pat-partners-2d47b9e01f5c` (partner org),
  `zt-pat-revoked-1e94c7a305df` (revoked)

Seed passwords: `amelia OrbitZitadel2026!`, `jonas OrbitJonas2026!`,
`helena OrbitHelena2026!`, `noor OrbitNoor2026!`, `dmitri OrbitDmitri2026!`,
`priya OrbitPriya2026!`.

### Endpoints

- `GET {{baseUrl}}/health` · `/debug/healthz`
- `GET {{baseUrl}}/admin/v1/instance`;
  `POST /admin/v1/orgs/_search` · `/admin/v1/events/_search`
- `GET {{baseUrl}}/management/v1/orgs/me` · `/management/v1/policies/login`
- `POST {{baseUrl}}/v2/users/human` · `/v2/users/_search`;
  `GET|DELETE /v2/users/{id}`; `PUT /v2/users/human/{id}`
- `POST {{baseUrl}}/v2/users/{id}/email` · `/email/_verify` · `/password` · `/password_reset`
- `POST {{baseUrl}}/v2/users/{id}/deactivate` · `/reactivate` · `/lock` · `/unlock`
- `GET {{baseUrl}}/v2/users/{id}/authentication_factors`;
  `POST /v2/users/{id}/totp` · `/totp/_verify`;
  `DELETE /v2/users/{id}/authentication_factors/{factorId}`
- `POST {{baseUrl}}/v2/sessions` · `/v2/sessions/_search`;
  `GET|PATCH|DELETE /v2/sessions/{id}`
- `GET|POST {{baseUrl}}/v2/oidc/auth_requests/{id}`
- `POST {{baseUrl}}/management/v1/projects` · `/projects/_search` ·
  `/projects/{id}/roles` · `/projects/{id}/roles/_search`;
  `GET /management/v1/projects/{id}`
- `POST {{baseUrl}}/management/v1/users/grants/_search` · `/users/{id}/grants`;
  `PUT|DELETE /management/v1/users/{id}/grants/{grantId}`
- `POST {{baseUrl}}/management/v1/orgs/me/members` · `/members/_search`;
  `DELETE /management/v1/orgs/me/members/{userId}`

### Behaviour worth knowing

- **Three distinct authorization refusals**: no usable token (`16`), a token for
  another org (`7`, naming both orgs), a read-only token attempting a write
  (`7`, naming the role).
- **Instance endpoints need `IAM_OWNER`**, not merely an org role.
- Setting the first password on a `USER_STATE_INITIAL` user activates the
  account. Changing a password drops every session that authenticated with one;
  deactivating or locking a user drops all of theirs.
- Password complexity (8 characters, upper case, digit, symbol) is enforced on
  create and reset, each violation naming its own Zitadel error id.
- Grants are validated against the project's declared roles.
- An org must keep at least one `ORG_OWNER`.
- Because no mail is delivered, `set email` and `password_reset` return the code
  when the caller passes `returnCode`, and say so otherwise.
- **Every write returns `details.sequence`** from the same monotonic counter the
  event log uses, so a write's sequence and its event line up.

### Error codes

Errors carry a gRPC status code in the body alongside the HTTP status.

| gRPC | HTTP | Condition |
|------|------|-----------|
| 3 INVALID_ARGUMENT | 400 | password complexity, wrong code, unknown role, malformed body |
| 5 NOT_FOUND | 404 | unknown org, user, session, project, grant, member or auth request — including one in another org |
| 6 ALREADY_EXISTS | 409 | duplicate username, email, project name, project role, grant, member, TOTP |
| 7 PERMISSION_DENIED | 403 | token for another org, read-only token writing, missing `IAM_OWNER`, wrong session token |
| 9 FAILED_PRECONDITION | 400 | inactive org, deactivated/locked user, wrong lifecycle state, expired session, session missing a required factor, auth request already completed, last org owner |
| 16 UNAUTHENTICATED | 401 | missing or revoked token |

---

## 18. Ory Kratos API

**Port:** 8119 · **Env var:** `ORY_KRATOS_API_URL`

**There is no login endpoint.** Kratos has *self-service flows*, and they are
first-class resources:

```
GET  /self-service/login/api          -> a flow object carrying a renderable `ui`
POST /self-service/login?flow=<id>    -> submit against that flow
```

The `ui` is a form description — `action`, `method`, and `nodes` each with their
own attributes and messages. **A failed submission is not an error body**: it is
400 with the whole flow re-rendered and messages attached to the offending
nodes, because that is what a client draws. Numbered ids carry the meaning:

| id | meaning | id | meaning |
|----|---------|----|---------|
| 4000001 | property required | 4000007 | identifier exists |
| 4000002 | value too short | 4000032 | password too short |
| 4000003 | invalid format | 4000038 | not in the enum |
| 4000006 | invalid credentials | 4000040 | trait not allowed by the schema |
| 4060006 | code invalid or used | | |

### Traits are validated against the identity's JSON Schema

| Schema | Required | Constraints |
|--------|----------|-------------|
| `default` | `email`, `name.first`, `name.last` | `role` enum (`owner`/`engineer`/`support`/`service`), `seat_id` pattern `^SEAT-[0-9]{3}$` |
| `partner` | `email`, `company` | |

Both forbid extra properties. The collection registers the *same* payload
against each and shows it succeed on `default` and fail on `partner`, plus one
request per rule — missing property, malformed email, value outside the enum,
value failing the pattern, unlisted trait — each landing on its own node.

### `continue_with` says what happens next

| After | `continue_with` |
|-------|-----------------|
| registration | `set_ory_session_token`, then `show_verification_ui` with the new flow |
| recovery code accepted | `set_ory_session_token`, then `show_settings_ui` — Kratos forces a password change |
| settings changing the email | `show_verification_ui` for the new address |
| login where the identity has TOTP | `set_ory_session_token` (aal1) plus `redirect_browser_to` the aal2 flow |

### Seed data

- **Identity schemas**: 2 · **Identities**: 7
  - `amelia` — password **+ totp + lookup_secret**, aal2 session
  - `jonas` — password only, two sessions
  - `helena` — **oidc only** (`github:2210448`), no password
  - `rohit` — **email unverified**, with an open verification flow and code
  - `noor` — **state `inactive`**: a correct password is still refused
  - `sync-bot`, `priya` (on the `partner` schema)
- **Credentials**: 8 across `password`, `oidc`, `totp`, `lookup_secret`
- **Flows**: 9 — api and browser logins, an aal2 step-up, an **expired** one, a
  registration, a recovery, a verification and two settings flows
- **Sessions**: 6 (one revoked, one at aal2) · **Codes**: 3 (one spent)
- **Courier messages**: 5 across `sent`, `queued`, `abandoned`

Seed passwords: `amelia OrbitKratos2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `noor OrbitNoor2026!`, `priya OrbitPriya2026!`.
TOTP `482913`; lookup secrets `91cd2f7a`, `4b60e18d`, `7fa3c052`.

Session tokens (`X-Session-Token`): `ory_st_amelia_4c19f7e0b83d` (aal2),
`ory_st_jonas_91e5c7d40a26`, `ory_st_helena_d502a8f371c6`,
`ory_st_priya_1d75a0e934bc`, `ory_st_amelia_revoked_3a6d80e5` (revoked).

### Endpoints

- `GET {{baseUrl}}/health` · `/health/alive` · `/health/ready` · `/version`
- `GET {{baseUrl}}/schemas` · `/schemas/{id}`
- `GET {{baseUrl}}/self-service/{login|registration|recovery|verification|settings}/{api|browser}`
- `GET {{baseUrl}}/self-service/{type}/flows?id=`
- `POST {{baseUrl}}/self-service/login` · `/registration` · `/recovery` ·
  `/verification` · `/settings` (each `?flow=`)
- `DELETE {{baseUrl}}/self-service/logout/api`
- `GET {{baseUrl}}/sessions/whoami` · `/sessions`;
  `DELETE /sessions` · `/sessions/{id}`
- `GET|POST {{baseUrl}}/admin/identities`;
  `GET|PUT|PATCH|DELETE /admin/identities/{id}`
- `GET|DELETE {{baseUrl}}/admin/identities/{id}/sessions`;
  `DELETE /admin/identities/{id}/credentials/{type}`
- `POST {{baseUrl}}/admin/recovery/code` · `/admin/recovery/link`
- `GET {{baseUrl}}/admin/sessions` · `/admin/sessions/{id}`;
  `PATCH /admin/sessions/{id}/extend`; `DELETE /admin/sessions/{id}`
- `GET {{baseUrl}}/admin/courier/messages` · `/messages/{id}`

### Behaviour worth knowing

- **Flow lifecycle is enforced.** An unknown flow is 404
  `self_service_flow_not_found`; an **expired** one is **410
  `self_service_flow_expired`** with `details.expired_at`; a flow fetched under
  the wrong type is 404.
- **Browser flows carry an anti-CSRF token; API flows do not.** Submitting a
  browser flow without echoing `csrf_token` is 403 `security_csrf_violation`.
- **No account enumeration.** An unknown identifier, a wrong password and an
  identity with no password credential all produce the same `4000006`. Recovery
  sends mail either way — the seed contains the `recovery_invalid` message
  Kratos sends to an address it does not know.
- **aal2 is a second flow, not a second field.** Logging in as an identity with
  TOTP yields an aal1 session plus a pointer to the aal2 flow; submitting that
  with `totp` or `lookup_secret` yields aal2. A consumed lookup secret is
  removed from the credential.
- **Settings flows are bound to their identity** — another session is 403
  `session_refresh_required`, none is 401. Changing an email marks it unverified
  and returns a verification flow; changing a password revokes every other
  session.
- **`PATCH /admin/identities/{id}` is JSON Patch (RFC 6902).** Only a fixed set
  of paths is writable; an unsupported path or op is rejected *with the
  supported list*, not ignored. Patching `/state` to `inactive` revokes sessions.
- Deleting the `password` credential through the admin API is refused — Kratos
  requires a settings flow.
- Because no mail is delivered, recovery, verification and registration return
  the code and say so; the **courier log** records what would have been sent.

### Error ids

| HTTP | `error.id` | Condition |
|------|-----------|-----------|
| 401 | `session_inactive` | missing, revoked or expired session token |
| 403 | `security_csrf_violation` | browser flow without `csrf_token` |
| 403 | `session_refresh_required` | settings flow with another identity's session |
| 404 | `self_service_flow_not_found` | unknown flow, or one of the wrong type |
| 404 | `not_found` | unknown identity, session, schema or courier message |
| 409 | `identity_conflict` | admin create with an existing identifier |
| 410 | `self_service_flow_expired` | the flow's lifetime elapsed |
| 400 | `identity_schema_validation_failed` | admin create/update failing the schema |
| 400 | `patch_path_invalid` / `patch_op_invalid` | unsupported JSON Patch path or op |
| 400 | `identity_state_invalid` | a state other than `active`/`inactive` |
| 400 | `credential_type_not_removable` | removing `password` via the admin API |

---

## 19. Dex API

**Port:** 8120 · **Env var:** `DEX_API_URL`

**Dex is a federator, not an identity provider.** It has no user database: real
identities live behind *connectors*, and the only thing Dex stores locally is
the `local` connector's static passwords. Everything else it knows about a
person exists only because a refresh token remembers it — which is why
`/api/v2/refresh/{user_id}` and `/api/v2/offline-sessions` are the closest thing
this API has to a user list.

### 1. Connectors decide what is possible

| Connector | Type | Password grant | Asking anyway |
|-----------|------|----------------|---------------|
| `local` | static passwords | **yes** | tokens |
| `ldap` | directory | **yes** | tokens, `sub` keyed by the DN |
| `github` | social | **no** | 400 *use the browser flow* |
| `orbit-saml` | SAML | — | 400 *connector is disabled* |

The same username and password through `local` and `ldap` produce **different
subjects**, because Dex's `sub` encodes the connector — ids are only unique
within one.

### 2. The device authorization grant is first-class

RFC 8628 in full, with a seeded device request per state so each error can be
exercised without setting up:

| Device code | State | Polling returns |
|-------------|-------|-----------------|
| `dex-device-pending-9f14c73e0b2a` (`BDWD-HQMK`) | pending | `authorization_pending`, then `slow_down` from the fourth poll |
| `dex-device-approved-5b07d21f8c64` | approved | tokens |
| `dex-device-denied-c8e05a1976b3` | denied | `access_denied` |
| `dex-device-expired-2d47b9e01f5c` | expired | `expired_token` |
| `dex-device-redeemed-7a63f04c9e21` | redeemed | `invalid_grant` |

### 3. Cross-client audiences need a trusted peer

A client may request `audience:server:client_id:<other>` only if it appears on
that other client's `trustedPeers`. `orbit-kubectl` is on grafana's list and
succeeds; `orbit-status-web` is not and gets `invalid_scope` naming the fix.

### The gRPC API answers with flags, not status codes

`/api/v2` mirrors Dex's gRPC surface, including its envelopes: creating a client
that exists is **200** with `already_exists: true`, and deleting one that does
not is **200** with `not_found: true`. Only `GET /api/v2/clients/{id}` uses a
real 404. Worth knowing before writing a client that switches on the status.

### Seed data

- **Connectors** (4): `local`, `ldap`, `github`, a **disabled** `orbit-saml`
- **Clients** (4): `orbit-status-web` (confidential, allowed the password
  grant), `orbit-cli` (**public**, allowed the device grant), `orbit-grafana`
  (trusts `orbit-kubectl`), `orbit-kubectl`
- **Passwords** (4): the entire local identity store — amelia, jonas, rohit,
  the sync bot
- **Refresh tokens** (5) across three connectors, one carrying an
  `obsoleteToken` from a previous rotation, one carrying a cross-client audience
- **Authorization codes** (3): unused with PKCE, **used**, **expired**
- **Authorization requests** (3), one **expired** · **Device requests** (5)

Client secrets: `dex-secret-status-web-9f14c73e0b2a`,
`dex-secret-grafana-5b07d21f8c64`, `dex-secret-kubectl-1c84f065`;
`orbit-cli` is public and carries none.

Seed passwords: `amelia OrbitDex2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `orbit_sync_bot OrbitSyncBot2026!`. Helena exists only
as a GitHub refresh token and Noor only as an LDAP one — neither has a local
password, which is the point.

PKCE pair: verifier `dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk` → challenge
`E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM`.

### Endpoints

- `GET {{baseUrl}}/health` · `/healthz`
- `GET {{baseUrl}}/dex/.well-known/openid-configuration` · `/dex/keys` · `/dex/connectors`
- `GET {{baseUrl}}/dex/auth` · `/dex/auth/{connector_id}`
- `POST {{baseUrl}}/dex/approval` · `/dex/token` · `/dex/token/introspect`
- `GET {{baseUrl}}/dex/userinfo`
- `POST {{baseUrl}}/dex/device/code` · `/dex/device/auth/verify` · `/dex/device/token`;
  `GET /dex/device?user_code=`
- `GET {{baseUrl}}/api/v2/version`
- `GET|POST {{baseUrl}}/api/v2/clients`; `GET|PUT|DELETE /api/v2/clients/{id}`
- `GET|POST {{baseUrl}}/api/v2/passwords`; `PUT|DELETE /api/v2/passwords/{email}`;
  `POST /api/v2/passwords/verify`
- `GET {{baseUrl}}/api/v2/refresh/{user_id}`; `POST /api/v2/refresh/revoke`
- `GET {{baseUrl}}/api/v2/offline-sessions`

### Behaviour worth knowing

- **Client authentication follows client type**: a confidential client must
  present its secret (401), a public one carries none; a grant a client does not
  declare is `unauthorized_client`.
- **Authorization codes are single-use**; PKCE is verified when the code carries
  a challenge (`S256` and `plain`).
- **Refresh tokens rotate and Dex keeps exactly one previous generation**, so a
  client that crashed mid-rotation can recover; a token two generations old gets
  its own message.
- **A refresh may narrow scopes but never widen them** — a scope outside the
  original grant is `invalid_scope` naming the offender.
- Changing a password through `/api/v2` drops every offline session it anchored.
- Deleting a client also removes its refresh tokens and device requests.
- `/api/v2/refresh/{user_id}` takes a path parameter that accepts slashes and
  equals signs, because an LDAP identity id is a full DN.

### Error codes

| Surface | HTTP | `error` | Condition |
|---------|------|---------|-----------|
| `/dex/*` | 400 | `invalid_grant` | code unknown/used/expired, refresh token unknown or too old, device code redeemed |
| `/dex/*` | 400 | `invalid_request` | unregistered redirect uri, unknown or disabled connector, connector without password support |
| `/dex/*` | 400 | `unauthorized_client` | the client may not use that grant |
| `/dex/*` | 400 | `invalid_scope` | audience without a trusted peer, refresh widening scopes |
| `/dex/*` | 400 | `authorization_pending` · `slow_down` · `expired_token` · `access_denied` | device flow states |
| `/dex/*` | 401 | `invalid_client` | unknown client or wrong secret |
| `/dex/*` | 401 | `access_denied` | wrong username or password |
| `/dex/*` | 401 | `invalid_token` | userinfo without a live token |
| `/dex/*` | 404 | `invalid_request` | unknown user code |
| `/api/v2/*` | 200 | `already_exists` / `not_found` **flags** | duplicate create, or absent update/delete/revoke |
| `/api/v2/*` | 400 | `error` | password create with no email or no password |
| `/api/v2/*` | 404 | `error` | `GET /api/v2/clients/{id}` for an unknown client |

---

## 20. MailHog API

**Port:** 8121 · **Env var:** `MAILHOG_API_URL`

**MailHog captures mail; it does not deliver it.** Everything the API exposes
follows from that: the messages are what an SMTP server actually received, so
they are reported as envelopes rather than as rendered mail, and the only way a
message leaves is by being *released* to a real relay on purpose.

### 1. Addresses are `Path` objects, not strings

```json
"From": {"Relays": null, "Mailbox": "auth", "Domain": "orbit-labs.com", "Params": ""}
```

`To` is a list of those, and it carries the `Cc` **and the `Bcc`** — the
envelope recipients, not the header ones. A `Bcc` invisible in the rendered mail
is plainly there in the API, which is exactly why capture tools are used.

### 2. v1 and v2 are the same inbox in two shapes

| | Shape |
|---|-------|
| `GET /api/v1/messages` | bare array |
| `GET /api/v2/messages` | `{total, count, start, items}` |

Both are served because clients in the wild use both. Messages come back
newest-first, as MailHog's UI shows them.

### 3. Jim, the chaos monkey, answers 404 until switched on

`GET`, `PUT` and `DELETE /api/v2/jim` are **404 `Jim is not enabled`** — that is
how a client discovers chaos is off, not an error. `POST` enables him;
enabling twice is 400.

Once on, his chances apply to the release endpoint, and the roll is **seeded
from the recipient address**, so the outcome is deterministic per address rather
than random:

| Recipient | Roll | At `RejectRecipientChance: 0.4` |
|-----------|------|--------------------------------|
| `oncall@orbit-labs.com` | 0.114 | rejected |
| `status@orbit-labs.com` | 0.282 | rejected |
| `subscribers@orbit-labs.com` | 0.302 | rejected |
| `rohit.bansal@orbit-labs.com` | 0.420 | released |
| `amelia.ortega@orbit-labs.com` | 0.749 | released |

Raising `DisconnectChance` changes *which* refusal the same address gets.

**One deliberate deviation.** Real MailHog reports a refused release as 500;
this mock returns **400** with the reason in the body, because the fleet harness
reads any 5xx as a broken service and an injected refusal is a chosen outcome,
not a fault.

### MIME parts are addressable individually

`GET /api/v1/messages/{id}/mime/part/{n}/download` serves one part with its own
content type and a `Content-Disposition` filename — how a single attachment is
pulled out of a captured multipart message.

| Message | Part 0 | Part 1 |
|---------|--------|--------|
| incident notification | `text/plain` | `text/html` |
| weekly digest | `text/plain` | `text/csv` — `uptime-2026-w21.csv` |
| invoice | `text/plain` | `application/pdf` — `INV-2026-0417.pdf` |
| bounce | `text/plain` | `message/delivery-status` |

An index out of range is 404 naming the part count, a non-multipart message is
404 `Message has no MIME parts`, and a non-numeric index is 400.

### Seed data

- **Messages** (8), chosen to span the shapes a real inbox sees: two plain-text
  codes, an HTML partner welcome, a plain-text security alert with a **Bcc**, a
  `multipart/alternative` incident notice, a `multipart/mixed` digest with a
  **CSV**, a `multipart/mixed` invoice with a **PDF** and a **Cc**, and a
  `multipart/report` **bounce**
- **MIME parts** (8) across the four multipart messages, keyed
  `{messageId}#{partIndex}`
- **Outgoing SMTP servers** (2): `orbit-relay` (`smtp.orbit-labs.com:587`,
  PLAIN) and `acme-partner` (`smtp.acme-partner.com:465`, CRAM-MD5)
- **Jim**: seeded **disabled**, carrying MailHog's default chances

The captured mail is the mail the rest of this fleet would have sent — the
verification code `482913` matches Kratos's seed, the recovery code `770412`
matches the authentication services, and the bounce is addressed to the
deactivated account.

Message ids: `3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example` (verification),
`9tQrKcVmXwLpZbN2eHjD4A@mailhog.example` (recovery),
`Kf7bVpQnRtLmYcXwEjH0Zg@mailhog.example` (incident),
`Wq3ZmNbXcVpLkJhGfDsA2Q@mailhog.example` (digest + CSV),
`Bn5XcTgYuIoPlKjHgFdSa1@mailhog.example` (invoice + PDF),
`Mj8LkQwErTyUiOpAsDfGh3@mailhog.example` (security, has a Bcc),
`Zx4CvBnMqWeRtYuIoPaSd6@mailhog.example` (welcome),
`Hg2FdSaPoIuYtReWq9MnBv@mailhog.example` (bounce).

### Endpoints

- `GET {{baseUrl}}/health` · `/api/v1/info` · `/api/v1/events`
- `GET|DELETE {{baseUrl}}/api/v1/messages`
- `GET|DELETE {{baseUrl}}/api/v1/messages/{id}`
- `GET {{baseUrl}}/api/v1/messages/{id}/download`
- `GET {{baseUrl}}/api/v1/messages/{id}/mime/part/{n}/download`
- `POST {{baseUrl}}/api/v1/messages/{id}/release` · `GET /api/v1/releases`
- `GET {{baseUrl}}/api/v2/messages?start=&limit=`
- `GET {{baseUrl}}/api/v2/search?kind=from|to|containing&query=`
- `GET|POST|PUT|DELETE {{baseUrl}}/api/v2/jim`
- `GET {{baseUrl}}/api/v2/outgoing-smtp`

### Behaviour worth knowing

- **Search `containing` reads the subject and the rebuilt body**, so it matches
  text inside a multipart message that no single stored part holds verbatim.
  `kind=to` matches the `Cc` and `Bcc` too. Any other `kind`, or a missing
  `query`, is 400.
- **Release takes credentials inline or by name**: `Host`/`Port`/`Email` plus an
  optional `Username`/`Password`/`Mechanism`, or `Name` naming a server from
  `/api/v2/outgoing-smtp`. Only `PLAIN` and `CRAM-MD5` are supported.
- **Deleting a message removes its MIME parts too**; deleting it again is 404.
  `DELETE /api/v1/messages` empties the capture and reports the count.
- Mutations are held in process memory and reset on container restart.

**Two additions to the real API**, both marked in their responses:
`/api/v1/releases` records what was released so a release can be verified, and
`/api/v1/events` returns a snapshot rather than holding open an SSE stream,
which a mock cannot usefully do.

### Error codes

| HTTP | Condition |
|------|-----------|
| 400 | unsupported search `kind`, missing `query`, non-numeric part index, a Jim chance outside `0..1` or non-numeric, `LinkSpeedMin > LinkSpeedMax`, enabling Jim twice, release missing `Host`/`Port` or `Email`, unknown named server, unsupported mechanism, mechanism with no `Username`, a Jim-injected refusal |
| 404 | unknown message, part index out of range, a part requested from a non-multipart message, any Jim read/update/delete while chaos is disabled |

---

## 21. Mailpit API

**Port:** 8122 · **Env var:** `MAILPIT_API_URL`

Mailpit is MailHog's successor, and this service is deliberately **not** a
reskin of §20. Four things differ, and all four are modelled.

Note the singular/plural split in the paths — it is Mailpit's, not a typo.
`/api/v1/messages` is the **list**; `/api/v1/message/{id}` is the **read**. The
list gives a `Snippet` and an attachment *count*; the read gives `Text`, `HTML`
and the attachment *list*. Addresses are `{Name, Address}` in both.

### 1. Search is a real query language

MailHog takes `kind=from|to|containing`. Mailpit takes a query:

```
query=from:billing is:unread -tag:receipt "order total"
```

| Form | Terms |
|------|-------|
| prefixes | `from:` `to:` `cc:` `bcc:` `reply-to:` `addressed:` `subject:` `message-id:` `tag:` `before:` `after:` |
| flags | `is:read` `is:unread` `is:tagged` `is:untagged` `has:attachment` |
| other | `"quoted phrase"`, bare words, negation with `-` or `!` |

`addressed:` spans from, to, cc and bcc at once; `has:attachment` ignores inline
images. Terms are ANDed. `GET` and `DELETE /api/v1/search` share the parser, so
a delete removes exactly what the same query would have listed. An unknown
prefix or flag value is a 400 that **lists the valid ones**.

### 2. A message has state, and reading changes it

`GET /api/v1/message/{id}` marks the message read as a side effect, so
`is:unread` counts move as a client browses. `PUT /api/v1/messages` sets the
flag in bulk, and an empty `IDs` applies to every message. Tags are
first-class: settable in bulk, renameable across every message carrying them,
deletable, and searchable the moment they are set.

### 3. Mailpit analyses what it captured

| Endpoint | Returns |
|----------|---------|
| `html-check` | a score against eight email clients, plus one warning per unsupported feature |
| `link-check` | what every link in the message answered |
| `sa-check` | SpamAssassin rule hits, a total, and an `IsSpam` verdict at 5.0 |

The partner welcome fails four html-check tests (`display: flex`, `gap`,
`border-radius`, `linear-gradient()`) for 75% supported; the order confirmation
is clean at 100%; a text-only message is 400. Two of the newsletter's four links
fail — a `404` and a DNS failure, which has no HTTP status and so comes back as
`StatusCode 0` with the resolver error. `follow=true` resolves a redirect, so
the welcome mail's `301` becomes a `200` at a different URL. The promo blast
scores **6.839** and is spam; the digest scores **-1.089** and is not.

### 4. Chaos is error codes, not behaviours

MailHog's Jim rolls against behavioural chances as floats. Mailpit's Chaos gives
each trigger an **SMTP error code** and a **whole percentage**:

```json
{"Sender":         {"ErrorCode": 451, "Probability": 0},
 "Recipient":      {"ErrorCode": 451, "Probability": 0},
 "Authentication": {"ErrorCode": 535, "Probability": 0}}
```

It bites on `POST /api/v1/send`, and the roll is seeded from the address, so the
outcome is deterministic per address rather than random:

| Address | Roll | At `Probability: 50` |
|---------|------|----------------------|
| `priya.raman@orbit-labs.com` | 2 | refused |
| `rohit.bansal@orbit-labs.com` | 16 | refused |
| `jonas.pereira@orbit-labs.com` | 41 | refused |
| `oncall@orbit-labs.com` | 44 | refused |
| `dmitri.volkov@orbit-labs.com` | 53 | accepted |
| `amelia.ortega@orbit-labs.com` | 59 | accepted |
| `helena.park@orbit-labs.com` | 68 | accepted |
| `noor.aziz@orbit-labs.com` | 75 | accepted |

An SMTP code is not an HTTP status, so it travels in the body and the request
fails with 400: `{"error": "chaos: sender ... rejected", "smtpErrorCode": 550}`.
A probability outside `0..100`, a fractional probability, an error code outside
`400..599` and an unknown trigger are each 400 naming the offender.

### Sending and releasing

`POST /api/v1/send` creates a real message in the mailbox — Mailpit accepts mail
over HTTP as well as SMTP, which MailHog does not. The new id is derived from
the sender, subject and recipients, so the same payload always yields the same
id.

`POST /api/v1/message/{id}/release` takes `{"To": [...]}` and is checked against
the relay rules reported by `/api/v1/webui`:

```
AllowedRecipients: @(orbit-labs\.com|acme-partner\.example)$
BlockedRecipients: ^(audit|no-reply)@
```

So `audit@orbit-labs.com` is blocked and `someone@elsewhere.example` is not
permitted — each 400 naming which rule refused it.

### Seed data

- **Messages** (9): 4 unread / 5 read, 7 tagged / 2 untagged, 3 with parts
  (PDF, CSV, an inline PNG); one with a hidden `Bcc`, one with two `Cc`s, one
  carrying a `List-Unsubscribe` header
- **Attachments** (3) · **SpamAssassin rules** (18) across 4 messages ·
  **Links** (7) across 4 messages · **HTML warnings** (7) across 3 messages
- **Chaos**: all three triggers at 0% · **Relay**: enabled, with the rules above

Message ids: `iAfZuC9x4Pq2wKvNhLmRtY` (order + PDF),
`Rn7KdWpXsE3zQjBvUyTaHc` (password reset, code `770412`),
`Lm4TgVhNpZxCwQdRsFuKb8` (May digest, failing links),
`Yb9PxJqWnMkTvRzHcAeDs2` (promo, spam), `Ct5NrXbGmVpLdWyQzKfJh7` (incident),
`Da3ZkFpQwSxEvRtYuIoLm1` (invoice + CSV + `Bcc`),
`Ek6MbNcVxZaSdFgHjKlPq4` (partner welcome), `Gp8WqErTyUiOpAsDfGhZx5` (bounce),
`Hs2JnBvCxZlKmQwErTyUi9` (deploy notice).

The mail matches the rest of the fleet: the recovery code `770412` is the
authentication services', `INC-4417` is MailHog's incident, and the bounce is
addressed to the deactivated account.

### Endpoints

- `GET {{baseUrl}}/health` · `/livez` · `/readyz` · `/api/v1/info` · `/api/v1/webui`
- `GET|PUT|DELETE {{baseUrl}}/api/v1/messages`
- `GET|DELETE {{baseUrl}}/api/v1/search?query=`
- `GET|PUT {{baseUrl}}/api/v1/tags`; `PUT|DELETE /api/v1/tags/{tag}`
- `GET {{baseUrl}}/api/v1/message/{id}` · `/raw` · `/headers`
- `GET {{baseUrl}}/api/v1/message/{id}/part/{partId}` · `/thumbnail`
- `GET {{baseUrl}}/api/v1/message/{id}/html-check` · `/link-check` · `/sa-check`
- `POST {{baseUrl}}/api/v1/message/{id}/release` · `/api/v1/send`
- `GET|PUT {{baseUrl}}/api/v1/chaos`

### Behaviour worth knowing

- **Nothing was invented.** Sends, releases, chaos refusals and deletes are
  recorded in `RuntimeStats` on `/api/v1/info` — `SMTPAccepted`,
  `SMTPAcceptedSize`, `SMTPRejected`, `MessagesDeleted` — which is where Mailpit
  already reports them, so no extra endpoint was needed to verify a mutation.
- An **inline image is not an attachment**: excluded from the summary count and
  from `has:attachment`, and listed under `Inline` on the read.
- `thumbnail` refuses a non-image part with a 400 naming its content type.
- Deleting a message takes its attachments, rules, links and warnings with it.
- Mutations are held in process memory and reset on container restart.

### Error codes

| HTTP | Condition |
|------|-----------|
| 400 | unknown search prefix or flag, a `before:`/`after:` that is not `YYYY-MM-DD`, an empty query, a missing or non-boolean `Read`, `Tags` with no `IDs`, an invalid tag, a rename with no `Name`, html-check on a text-only message, thumbnail of a non-image part, a send with no sender or recipient or a malformed address, a chaos setting out of range or an unknown trigger, a chaos-injected refusal, a release with no recipients or one the relay rules refuse |
| 404 | unknown message id, unknown part id, unknown tag |

---

## 22. Inbucket API

**Port:** 8123 · **Env var:** `INBUCKET_API_URL`

Inbucket is a third capture model, and it differs from §20 and §21
**structurally**, not cosmetically.

### 1. There is no global inbox

Every read names a mailbox. No endpoint lists all captured mail, and none lists
the mailboxes either — a client is expected to know the address it sent to.
That absence is the design, not an omission; the monitor is the only
cross-mailbox view.

### 2. The mailbox is derived from the address, not stored

Under the `local` policy the mailbox is the local part, lowercased, with any
`+subaddress` stripped. All of these read the **same** mailbox:

| `{name}` | Resolves to |
|----------|-------------|
| `amelia.ortega` | `amelia.ortega` |
| `Amelia.Ortega@orbit-labs.com` | `amelia.ortega` |
| `amelia.ortega+billing@orbit-labs.com` | `amelia.ortega` |
| `AMELIA.ORTEGA@acme-partner.example` | `amelia.ortega` |
| `Amelia Ortega <amelia.ortega@orbit-labs.com>` | `amelia.ortega` |

Three addresses, two domains, one mailbox. The policy applies to every route
that takes a `{name}` — read, patch, delete and purge alike — and `/status`
reports the configuration driving it.

### 3. Every mailbox exists

An unknown mailbox is **`200 []`**, never a 404. There is nothing to create, so
there is nothing to be missing — the opposite of how MailHog and Mailpit answer
for an unknown message. The 404s in this API are all about *messages*: an
unknown id, or a real id read through the wrong mailbox.

### 4. A message to two recipients is two messages

The seeded incident notice went to `oncall@orbit-labs.com` and
`helena.park@orbit-labs.com`, so there are two copies:

```
oncall       20260526T142208-0006
helena.park  20260526T142208-0007
```

Same subject, same body, own ids, independent `seen` flags. Asking for helena's
id inside `oncall` is a 404; marking oncall's copy seen leaves hers unseen; and
purging `oncall` leaves hers standing.

### 5. Deletion is per-mailbox

`DELETE /api/v1/mailbox/{name}` purges one mailbox and reports the count.
Nothing empties the server. Purging an empty or never-used mailbox reports `0`
rather than failing — consistent with every mailbox existing. Deleting a
*message* twice **is** a 404.

### Smaller things that are Inbucket's

- Keys are hyphenated: `posix-millis`, `content-type`, `download-link`.
- Mailboxes list **oldest first** — arrival order — where MailHog and Mailpit
  list newest first.
- The attachment filename is part of its URL **and is checked**: a mismatch is a
  404 reporting the real name.
- Each attachment carries a genuine MD5 of its bytes.
- A **per-mailbox message cap** evicts the oldest message once exceeded.
  Inbucket defaults to 500; this instance is set to **5** so the eviction is
  observable, and the delivery response names what went in `evicted`.

### Seed data

- **Messages** (10) across **6 mailboxes**: `amelia.ortega` 3, `jonas.pereira`
  2, `oncall` 2, `helena.park` 1, `billing` 1, `support` 1
- **Attachments** (3), keyed `{messageId}#{index}` — a PDF (90 B,
  `4ccc1752…`), a CSV (156 B, `ff85013f…`) and a PNG (70 B, `2cd8bde4…`)
- **Config**: `local` naming, case-insensitive, subaddress stripping on, cap 5,
  72h retention · **Counters**: seeded expvar totals the run then moves

The mail matches the rest of the fleet: the recovery code `770412` is the
authentication services', and `INC-4417` is the incident MailHog and Mailpit
also captured.

### Endpoints

- `GET {{baseUrl}}/health` · `/status` · `/debug/vars`
- `GET|POST|DELETE {{baseUrl}}/api/v1/mailbox/{name}` — list, deliver, purge
- `GET|PATCH|DELETE {{baseUrl}}/api/v1/mailbox/{name}/{id}`
- `GET {{baseUrl}}/api/v1/mailbox/{name}/{id}/source`
- `GET {{baseUrl}}/api/v1/mailbox/{name}/{id}/attach/{index}/{filename}`
- `GET {{baseUrl}}/api/v1/monitor/messages` · `/api/v1/monitor/mailbox/{name}`

### Two mock additions, both marked in their responses

- `POST /api/v1/mailbox/{name}` — Inbucket only accepts mail over SMTP, which a
  mock cannot offer. This stands in for that delivery and answers **201** with
  the mailbox the address resolved to, which doubles as the shortest
  demonstration of the naming policy.
- The monitor endpoints return a **snapshot** rather than an SSE stream, and say
  so.

### Behaviour worth knowing

- `PATCH /api/v1/mailbox/{name}/{id}` with `{"seen": true|false}` is the only
  mutation on a message.
- `Delivered-To` keeps the address as it was written, even though the mailbox it
  resolved to is normalised.
- `download-link` is a relative API path — the mock has no reliable notion of
  its own external host.
- Delivered ids are the arrival timestamp plus a sequence, so they differ per
  run; verify a delivery by listing the mailbox, not by quoting the id back.
- Mutations are held in process memory and reset on container restart.

### Error codes

| HTTP | Condition |
|------|-----------|
| 400 | a non-numeric attachment index, a missing or non-boolean `seen`, a delivery with no `from` or a malformed `from`, a `{name}` that is a half-written address |
| 404 | an unknown message id, a real id read through the wrong mailbox, an attachment index out of range, an attachment filename that does not match, a message with no attachments |

There is no 404 on the mailbox routes themselves.

---

## 23. smtp4dev API

**Port:** 8124 · **Env var:** `SMTP4DEV_API_URL`

smtp4dev is a .NET application and every contract shows it. Five differences
from §20–§22, all modelled rather than smoothed into a common shape.

### 1. Pages, not offsets

Every list is a `PagedResult`:

```json
{"results": [ … ], "firstRowOnPage": 4, "lastRowOnPage": 6,
 "currentPage": 2, "pageCount": 3, "pageSize": 3, "rowCount": 8}
```

`page` is **1-based**, and a page past the end is an empty `results` with
`firstRowOnPage: 0` — not a 404. Sorting is `sortColumn` + `sortIsDescending`:

| Resource | Sortable columns |
|----------|------------------|
| messages | `receivedDate` (default), `from`, `to`, `subject`, `attachmentCount`, `isUnread`, `mailbox` |
| sessions | `startDate` (default), `endDate`, `clientAddress`, `numberOfMessages`, `terminatedWithError` |

Anything else is a 400 that **lists the ones that work**. `searchTerms` matches
the sender, recipients, Cc, subject and both bodies, and composes with
`mailboxName`.

### 2. Sessions are peers of messages, not a view of them

A session is the SMTP *conversation*, kept with its full transcript. Two of the
seven seeded sessions produced **no message at all**:

| Session | `sessionErrorType` | What happened |
|---------|--------------------|---------------|
| `7e30825b…` | `UnexpectedException` | three failed `AUTH LOGIN`, then `421 4.7.0` |
| `8f41936c…` | `ClientDisconnected` | both `RCPT TO` got `550 5.1.1`, client hung up before `DATA` |

The transcripts are real conversations — `220`/`EHLO`/`STARTTLS`/`AUTH`/`MAIL
FROM`/`RCPT TO`/`DATA`/`QUIT` — readable whole at `/api/Sessions/{id}/log`.
Deleting **every message** leaves every session standing, now reporting
`numberOfMessages: 0`. Nothing else in this fleet keeps the conversation.

### 3. Mailboxes route, they do not derive

| Mailbox | Rule |
|---------|------|
| `Billing` | `billing@orbit-labs.com`, `invoices@orbit-labs.com`, `finance@*` |
| `Alerts` | `oncall@orbit-labs.com`, `alerts@*`, `sre@*` |
| `Default` | `*` — checked **last**, so it never steals from a named mailbox |

Inbucket *derives* a mailbox from the address; smtp4dev *routes* to one by
matching patterns. And filtering by a mailbox that does not exist **is a 404**
here — the deliberate opposite of §22.

### 4. MIME parts are a tree

```
1        multipart/mixed
1.1      multipart/alternative
1.1.1    text/plain
1.1.2    text/html
1.2      application/pdf   receipt-ORD-2026-4417.pdf
```

Each node carries `childParts`, `headers`, `size`, `isAttachment`, `fileName`
and `warnings`. Three distinguishable errors: asking a **container** for content
is 400 naming the container, an unknown section number is 404 **and lists the
real ones**, an unknown message is 404. `/part/{id}/source` renders the subtree
with its own boundary.

### 5. The server settings are writable

`POST /api/Server` is the Settings dialog. It takes a partial object, validates
every key, and returns the whole settings as they now stand. Writable: the
ports, the host name, `secureConnectionMode`, the booleans, the retention
counts, and all of `relayOptions`.

**Retention trims on the spot.** Lowering `numberOfMessagesToKeep` to 4 deletes
immediately and reports `"trimmed": {"messages": 7, "sessions": 0}`; only the
four newest survive. `numberOfSessionsToKeep` does the same to the
conversations. That immediacy is smtp4dev's behaviour, not a shortcut.

### Two error fields that are not the same thing

| Field | Means |
|-------|-------|
| `mimeParseError` | smtp4dev could not parse what arrived — the nightly archive has an unclosed boundary, and its attachment part carries two `warnings` |
| `relayError` | the relay attempt failed — the ingest-lag alert has `451 4.7.1 Greylisted, try again in 300 seconds` |

Both are seeded so a client can tell them apart.

### Seed data

- **Messages** (8) across 3 mailboxes — `Default` 4, `Billing` 2, `Alerts` 2;
  four unread, one already relayed, one with a failed relay, one with a MIME
  parse error
- **Parts** (18), keyed `{messageId}#{partId}` — one tree three levels deep, two
  two-level trees, five single-part messages
- **Sessions** (7), two of which produced no message
- **Mailboxes** (3) with their recipient rules · **Settings**: relay enabled to
  `smtp.orbit-labs.com:587` over StartTls, retention 100/100

The mail matches the rest of the fleet: the recovery code `770412` is the
authentication services', and `INC-4417` is the incident §20–§22 also captured.

Message ids: `a1f3c7d9…` (order + PDF), `b2e4d8ea…` (invoice + CSV),
`c3f5e9fb…` (incident), `d4a6fa0c…` (password reset), `e5b70b1d…` (welcome,
relayed), `f6c81c2e…` (alert, relay failed), `07d92d3f…` (archive, parse error),
`18ea3e40…` (payout).

### Endpoints

- `GET {{baseUrl}}/health` · `/api/Version` · `/api/Mailboxes`
- `GET|POST {{baseUrl}}/api/Server`
- `GET|POST {{baseUrl}}/api/Messages` — paged list, deliver
- `DELETE {{baseUrl}}/api/Messages/*` (optional `?mailboxName=`)
- `POST {{baseUrl}}/api/Messages/markAllRead`
- `GET|DELETE {{baseUrl}}/api/Messages/{id}`
- `GET {{baseUrl}}/api/Messages/{id}/source` · `/html` · `/plaintext`
- `GET {{baseUrl}}/api/Messages/{id}/part/{partId}/content` · `/source`
- `POST {{baseUrl}}/api/Messages/{id}/markRead` · `/relay`
- `GET {{baseUrl}}/api/Sessions` · `DELETE /api/Sessions/*`
- `GET|DELETE {{baseUrl}}/api/Sessions/{id}` · `GET /api/Sessions/{id}/log`

### One mock addition, marked in its response

`POST /api/Messages` — smtp4dev only accepts mail over SMTP, which a mock
cannot offer. This stands in for that delivery, answers **201** with the mailbox
the recipient routed to, and opens a session with a matching transcript.

### Behaviour worth knowing

- The delete-everything routes really are spelled `DELETE /api/Messages/*` and
  `DELETE /api/Sessions/*` — the literal star is smtp4dev's. They are declared
  before `/{id}` in the router so an id pattern cannot swallow them.
- Headers come back as a **list of name/value pairs**, not a map.
- `relay` uses the message's own recipients unless `overrideRecipientAddresses`
  is given; success flips `isRelayed` and clears any earlier `relayError`.
- `/html` on a text-only message and `/plaintext` on an HTML-only message are
  each 404.
- Delivered ids and session ids are UUIDs per call, so they differ per run.
- Mutations are held in process memory and reset on container restart.

### Error codes

| HTTP | Condition |
|------|-----------|
| 400 | an unsortable `sortColumn`, asking a container part for content, a relay while relay is disabled, a malformed or non-array relay override, a message with no recipients, an unknown or invalid server setting, a delivery with a missing/malformed `from` or `to` |
| 404 | an unknown message or session, an unknown part section number, `/html` on a text-only message, `/plaintext` on an HTML-only message, a `mailboxName` that does not exist |

---

## 24. MailCatcher API

**Port:** 8125 · **Env var:** `MAILCATCHER_API_URL`

MailCatcher is a Ruby/Sinatra app and the **smallest** surface of the five mail
services. Thirteen routes, all under `/messages`. There is no search, no tags,
no read state, no mailboxes, no sessions and no settings — **the minimalism is
the identity**, not a gap. What it does have is distinctive.

### 1. The format is a file extension, not a path segment

`/messages/1.json` · `.html` · `.plain` · `.source` · `.eml`

Which of those a given message offers is advertised in its `formats` array, so a
client checks rather than guesses:

| Id | `formats` |
|----|-----------|
| 1, 3, 6 | `["source", "html", "plain"]` |
| 2, 4, 7, 8 | `["source", "plain"]` |
| 5 | `["source", "html"]` |

Asking for one a message does not offer is a **404 that names what it does**;
an extension the API does not know at all is a **400** doing the same. An
unknown *message* is a 404 whichever extension is used — the message is checked
before the format.

### 2. Ids are plain integers, and they restart

`1`, `2`, `3` in arrival order. Every other capture tool in this fleet uses an
opaque token, a 22-character id, a timestamp or a GUID. After
`DELETE /messages` clears the catcher, the next delivery is **id 1 again**.

### 3. Addresses are angle-bracketed

```json
"sender": "<billing@orbit-labs.com>",
"recipients": ["<finance@orbit-labs.com>", "<audit@orbit-labs.com>"]
```

MailCatcher reports the envelope, so the seeded bounce has `"sender": "<>"` —
a real, empty return path rather than a missing field. On the way in,
`POST /messages` takes an address with or without the brackets.

### 4. Attachments are addressed by Content-ID

`/messages/{id}/parts/{cid}` — not by index, filename or MIME section number.

| Message | cid | File |
|---------|-----|------|
| 1 | `receipt-4417@orbit-labs.com` | `receipt-ORD-2026-4417.pdf` |
| 2 | `invoice-0417@orbit-labs.com` | `invoice-INV-2026-0417.csv` |
| 5 | `partner-hero@orbit-labs.com` | `partner-hero.png` (inline) |
| 6 | `orbit-logo@orbit-labs.com` | `orbit-logo.png` (inline) |
| 6 | `uptime-w21@orbit-labs.com` | `uptime-2026-w21.csv` |

A cid is **scoped to its message** — message 6 does not answer for message 1's
cid. Three distinguishable 404s: an unknown cid lists the real ones, a message
with no parts says so, and an unknown message says that.

### 5. `.html` rewrites `cid:` so the result is renderable

Message 5 stores `<img src="cid:partner-hero@orbit-labs.com" …>`, and the
endpoint returns
`<img src="/messages/5/parts/partner-hero@orbit-labs.com" …>`. That is the
reason the endpoint exists, and the collection fetches the rewritten path
afterwards so it is verified rather than asserted.

### Ruby shows in the JSON

Keys are snake_case (`created_at`, `is_attachment`) and **`size` is a string**.

### Seed data

- **Messages** (8): three with both bodies, four plain-text only, one **HTML
  only**; one with a `Cc`, one with two recipients, one with the `<>` sender
- **Parts** (5), keyed `{messageId}#{cid}` — a PDF, two CSVs, two inline PNGs
- Nothing else. There is no other seed file because there is nothing else to
  configure.

The mail matches the rest of the fleet: the recovery code `770412` is the
authentication services', and `INC-4417` is the incident §20–§23 also captured.

### Endpoints

- `GET {{baseUrl}}/health` · `/info`
- `GET|POST|DELETE {{baseUrl}}/messages` — list, deliver, clear
- `GET {{baseUrl}}/messages/{id}.json` · `.html` · `.plain` · `.source` · `.eml`
- `GET {{baseUrl}}/messages/{id}/parts/{cid}`
- `DELETE {{baseUrl}}/messages/{id}` — **204, no body**

### One mock addition, marked in its response

`POST /messages` — MailCatcher only accepts mail over SMTP, which a mock cannot
offer. This stands in for that delivery, answers **201** with the full read
shape, and is what makes the id scheme and the `formats` array demonstrable.

### Behaviour worth knowing

- `DELETE /messages/{id}` answers **204 with no body** — the only 204 in this
  fleet — and deleting a message takes its parts with it, so a cid that
  resolved a moment earlier then 404s.
- `.source` and `.eml` return the same bytes; `.eml` sets `message/rfc822`.
- The five known extensions are declared before the catch-all
  `/{id}.{extension}` in the router, so only genuinely unknown ones reach it.
- Messages list oldest first, which for integer ids is id order.
- `/info` is a convenience summary; MailCatcher's own `/` serves the web UI.
- Mutations are held in process memory and reset on container restart.

### Error codes

| HTTP | Condition |
|------|-----------|
| 400 | an unrecognised extension on a known message; a delivery with no `sender`, no `recipients`, a malformed address, or no body |
| 404 | an unknown message (whichever extension); a format the message does not offer; an unknown or out-of-scope cid; a message with no parts; deleting a message twice |

---

## 25. Orbit Payments API (in-house)

**Port:** 8126 · **Env var:** `INHOUSE_PAYMENTS_API_URL`

Not a clone of a hosted processor. This is the shape a team ends up with when
they own the ledger, and four things follow from that.

### 1. Every movement of money is double-entry

| Movement | Legs |
|----------|------|
| capture *A* | DR `gateway_clearing` *A* · CR `merchant_revenue` *A* |
| fee *F* | DR `processing_fees` *F* · CR `gateway_clearing` *F* |
| refund *R* | DR `merchant_revenue` *R* · CR `gateway_clearing` *R* |
| dispute opened *D* | DR `disputed_funds` *D* · CR `gateway_clearing` *D* |
| dispute **won** | DR `gateway_clearing` *D* · CR `disputed_funds` *D* |
| dispute **lost** | DR `merchant_revenue` *D* · CR `disputed_funds` *D*, plus the network fee |
| payout *P* | DR `bank_settlement` *P* · CR `gateway_clearing` *P* |

`/v1/ledger/trial_balance` proves debits equal credits **per currency**, and a
posting whose legs disagree is refused before anything is written.
`/v1/balance` is **derived** from those entries at read time — `available_minor`
*is* the `gateway_clearing` balance — rather than being a counter kept beside
them. The collection pays out 50000 and shows the balance fall by exactly that.

### 2. Idempotency keys are mandatory on every write

| Request | Result |
|---------|--------|
| POST with no `Idempotency-Key` | **400** `idempotency_key_required` |
| a fresh key | the write happens |
| the same key, **same body** | the original response, `idempotent_replay: true` |
| the same key, **different body** | **409** `idempotency_key_reuse` |

Stricter than most hosted APIs, and deliberately so: an in-house ledger that
double-charges is worse than a rejected request. Only *successes* are recorded,
so a declined card can be retried with the same key — the collection charges a
declining card twice with one key and gets 402 both times.

### 3. Payments are an enforced state machine

| Status | `next_actions` |
|--------|----------------|
| `requires_confirmation` | confirm, cancel |
| `authorized` | capture, cancel |
| `partially_captured` | capture, cancel, refund |
| `captured` · `partially_refunded` | refund |
| `refunded` · `failed` · `canceled` | *(terminal)* |

Every payment carries its own `next_actions`, and an illegal transition is a
**409** that names them. Partial captures and refunds carry running totals, so
`capturable_minor` and `refundable_minor` make over-capture and over-refund
arithmetic rather than guesswork.

### 4. The card decides the outcome

| Method | Outcome |
|--------|---------|
| `pm_visa_4242` `pm_mc_5555` `pm_visa_1881` `pm_visa_0259` | authorize cleanly |
| `pm_visa_0002` | **402** `insufficient_funds` |
| `pm_visa_0119` | **402** `expired_card` |
| `pm_visa_3220` | step-up, then confirm succeeds |
| `pm_visa_3221` | step-up, then confirm **fails** |
| `pm_amex_0005` | authorizes; the **capture** is refused |

A refused capture leaves the authorization open, so it can be retried or
cancelled. `cus_dmitri_2d47b9e0` is `delinquent` and is refused before the card
is considered at all.

### Disputes hold the funds

A dispute withdraws the money when it opens, so a disputed payment **cannot be
refunded** until it closes — a 409 that says so. Two are seeded:
`dp_6b19d5ec8f30` (USD, evidence window open) and `dp_9e21b7304c15` (EUR,
window **closed**), which is how both the happy path and
`evidence_window_closed` are reachable.

### Money handling

Amounts are **integers in the currency's minor unit** and always travel with
their currency; there is no float in the module and fees use integer half-up
arithmetic. A customer settles in exactly one currency.

| Currency | Fee | Minimum charge |
|----------|-----|----------------|
| EUR | 1.40% + 25 | 50 |
| GBP | 1.50% + 20 | 30 |
| USD | 2.90% + 30 | 50 |

### Seed data

- **Customers** (5) across ES/IE/DE/PL/US — one **delinquent**, one settling in
  **USD** · **Payment methods** (10) across eight behaviours
- **Payments** (9) spanning every status in both currencies · **Refunds** (1) ·
  **Disputes** (2) · **Ledger entries** (22, balanced in both currencies) ·
  **Events** (7)

The amounts tie to the rest of the fleet: 1932.00 EUR is the invoice total the
mail services carry, and `INV-2026-0417` / `ORD-2026-4417` are the same
documents.

### Endpoints

- `GET {{baseUrl}}/health` · `/v1/service`
- `GET|POST {{baseUrl}}/v1/customers`; `GET /v1/customers/{id}`
- `GET {{baseUrl}}/v1/payment_methods`; `GET /v1/payment_methods/{id}`
- `GET|POST {{baseUrl}}/v1/payments`; `GET /v1/payments/{id}`
- `POST {{baseUrl}}/v1/payments/{id}/confirm` · `/capture` · `/cancel`
- `GET|POST {{baseUrl}}/v1/refunds`; `GET /v1/refunds/{id}`
- `GET {{baseUrl}}/v1/disputes`; `GET /v1/disputes/{id}`;
  `POST /v1/disputes/{id}/evidence` · `/close`
- `GET {{baseUrl}}/v1/ledger/entries` · `/v1/ledger/trial_balance` ·
  `/v1/balance`
- `GET|POST {{baseUrl}}/v1/payouts`; `GET /v1/payouts/{id}`
- `GET {{baseUrl}}/v1/events`

### Behaviour worth knowing

- Ids are prefixed and **derived from the request**, so the same idempotency key
  yields the same id: `pay_`, `re_`, `dp_`, `po_`, `cus_`, `le_`, `evt_`.
- Omitting `amount_minor` captures or refunds whatever remains.
- Cancelling reports `released_minor`.
- Every mutation appends to `/v1/events`, filterable by `object` and `type`.
- Mutations are held in process memory and reset on container restart.

### Error codes

Errors are a **typed envelope**: `{"error": {"type", "code", "message",
"param"}}`, and a `card_error` also carries the payment it created under
`resource`.

| Type | HTTP | Codes |
|------|------|-------|
| `idempotency_error` | 400 / 409 | `idempotency_key_required`, `idempotency_key_reuse` |
| `invalid_request_error` | 400 | `amount_too_large`, `amount_too_small`, `amount_invalid`, `currency_mismatch`, `currency_unsupported`, `payment_method_mismatch`, `reason_invalid`, `status_unknown`, `account_unknown`, `insufficient_balance`, `resolution_invalid`, `parameter_missing`, `parameter_invalid` |
| `card_error` | **402** | `insufficient_funds`, `expired_card`, `authentication_failed`, `processor_declined`, `customer_delinquent` |
| `state_error` | 409 | `payment_state_invalid`, `payment_terminal`, `payment_disputed`, `dispute_not_open`, `dispute_closed`, `evidence_window_closed` |
| `not_found_error` | 404 | `resource_missing` |

---

## 26. Lago API

**Port:** 8127 · **Env var:** `LAGO_API_URL`

Open-source **usage-based billing**, and a different animal from §25. **Nothing
here charges anyone.**

### 1. You ingest events, not charges

A usage event names a subscription, a billable-metric `code` and some
`properties`. What it costs is not decided at ingestion — it is computed later
by aggregating the period's events and running the plan's charges over the
result.

### 2. Aggregation decides "how much", the charge model decides "what it costs"

| Aggregation | Reduces the period's events to |
|-------------|-------------------------------|
| `sum_agg` | the sum of a property |
| `max_agg` | the **peak** of a property |
| `unique_count_agg` | the count of **distinct** values |
| `count_agg` | the number of events |

| Charge model | Rule |
|--------------|------|
| `standard` | `units × per_unit_amount_millicents` |
| `package` | `ceil((units − free_units) / package_size) × amount_cents` |
| `graduated` | each tier bills **its own slice** at its own rate |
| `volume` | the **whole** quantity falls in one tier and is billed entirely there |
| `percentage` | `units × rate_bps / 10000` plus a fixed amount per event |

All five are seeded, and the arithmetic checks out:

| Model | Plan · metric | Units | Cents |
|-------|---------------|-------|-------|
| graduated | growth · api_calls | 320 000 | 44 400 |
| volume | growth · data_egress_gb | 420 | 5 120 |
| standard | growth · active_seats | 24 (peak) | 28 800 |
| package | starter · api_calls | 34 000 | 1 500 |
| percentage | scale · payment_volume_cents | 1 250 000 | 18 850 |

`graduated` versus `volume` is the distinction that matters: crossing a tier
re-prices only the new slice under `graduated`, but **everything** under
`volume`. `/events/estimate_fees` shows it — adding 700 GB to 420 takes the
charge from 5 120 to 10 960 cents, an increment of 5 840 rather than the 7 700
the old rate implied, and stores nothing.

### 3. `current_usage` exists before any invoice does

`GET /api/v1/customers/{id}/current_usage?external_subscription_id=…`
recomputes the open period on every read, with a per-charge `breakdown` so the
number is auditable. It is the endpoint people actually integrate against.

The collection proves the aggregations rather than asserting them: a seat
reading *below* the peak changes nothing, a *repeat* user changes nothing, a
*new* user moves the charge, and an event dated outside the period is ignored.

### 4. Ingestion is idempotent, batches are atomic

`transaction_id` is the caller's own key: a repeat is **422
`value_already_exist`**, never a second charge. A batch is all-or-nothing — one
bad entry rejects the whole thing, named by index, and the collection reads back
the *good* half to show it did not land.

### Other things that are Lago's

- **Identity is dual**: a `lago_id` the service owns, an `external_id` the
  caller owns. Customers, subscriptions and events use yours; invoices, credit
  notes and wallets only ever had a `lago_id`.
- **Responses are wrapped** (`{"customer": …}`,
  `{"customers": […], "meta": {…}}`) and errors carry a per-field
  `error_details` map. Validation failures are **422**, not 400.
- **`POST /api/v1/customers` upserts** on `external_id` and answers 200, keeping
  the existing `lago_id`.
- **A plan carries its own currency**, so a customer can only subscribe to one
  priced in theirs — `orbit_scale` is USD.
- **Invoices have two independent axes**: `status` (draft → finalized → voided)
  and `payment_status` (pending/succeeded/failed). A draft cannot record a
  payment or be voided or credited; only a draft can be refreshed or finalized;
  a **paid** invoice must be credited rather than voided.

### Money

Amounts are integer **cents**; per-unit rates are **millicents** (1 cent =
1000), so €0.002 per API call is exact, and totals round half-up to cents once,
at the end. Lago itself uses decimal strings; millicents keep the arithmetic
exact without floats, and the choice is reported in `/api/v1/service`.

### Seed data

- **Billable metrics** (6) across four aggregation types
- **Plans** (3) covering **all five** charge models; `orbit_scale` in USD
- **Customers** (4), one with no subscription · **Subscriptions** (4), one
  terminated
- **Events** (20) inside their subscriptions' open periods
- **Invoices** (3) — draft, paid, payment-failed — with 8 fee lines ·
  **Credit note** (1) · **Wallet** (1)

`ORB-2026-0004-001` is the invoice the mail services carry, and the customers
are the same Orbit Labs, Acme and Northwind accounts.

### Endpoints

- `GET {{baseUrl}}/health` · `/api/v1/service`
- `GET|POST {{baseUrl}}/api/v1/billable_metrics`; `GET /{code}`
- `GET|POST {{baseUrl}}/api/v1/plans`; `GET /{code}`
- `GET|POST {{baseUrl}}/api/v1/customers`; `GET /{external_id}` ·
  `/{external_id}/current_usage`
- `GET|POST {{baseUrl}}/api/v1/subscriptions`; `GET|DELETE /{external_id}`
- `GET|POST {{baseUrl}}/api/v1/events`; `POST /batch` · `/estimate_fees`;
  `GET /{transaction_id}`
- `GET {{baseUrl}}/api/v1/invoices`; `GET|PUT /{lago_id}`;
  `POST /{lago_id}/refresh` · `/finalize` · `/void`
- `GET|POST {{baseUrl}}/api/v1/credit_notes`; `GET /{lago_id}`
- `GET|POST {{baseUrl}}/api/v1/wallets`; `GET /{lago_id}`
- `GET {{baseUrl}}/api/v1/analytics/gross_revenue` · `/mrr`

### Behaviour worth knowing

- `current_usage` reads the subscription's declared
  `current_period_from`/`current_period_to`, so the seeded May events are the
  open period regardless of the wall clock — pass an explicit `timestamp` when
  metering.
- `refresh` rebuilds a draft's fees from the usage as it stands, which is how a
  draft catches up with events ingested since it opened.
- `/analytics/mrr` divides each active plan by its interval and counts plan fees
  only; usage is not recurring revenue.
- Mutations are held in process memory and reset on container restart.

### Error codes

| HTTP | Condition |
|------|-----------|
| 422 | any validation failure, with `error_details` naming the field: a repeated `transaction_id`, a duplicate inside a batch, a missing aggregation property, a metric the plan does not charge, a terminated subscription, a plan/customer currency mismatch, an unknown aggregation type or charge model, a charge missing its required property, an invalid invoice transition, over-crediting |
| 404 | an unknown customer, subscription, plan, metric, event, invoice, credit note or wallet |

---

## 27. Kill Bill API

**Port:** 8128 · **Env var:** `KILLBILL_API_URL`

The enterprise end of the fleet: a Java, multi-tenant subscription platform.
Paths live under `/1.0/kb`, version and namespace both in the URL.

### 1. The tenant is a header, and it partitions everything

`X-Killbill-ApiKey` and `X-Killbill-ApiSecret` decide which data exists:

| Tenant | Secret | Holds |
|--------|--------|-------|
| `orbit-labs` | `orbit-labs-secret-9f14c73e` | Amelia, Acme, Northwind |
| `acme-reseller` | `acme-reseller-secret-5b07d21f` | Helios |

An account in one tenant is a **404** from the other — not a 403. From over
there, it does not exist. A missing or wrong pair is a **401** (code 4000).

**Writes need one more header**: `X-Killbill-CreatedBy`, because every change is
audited against a person. Omit it and the request is a **400** (4001), checked
before the body.

### 2. Creates answer 201 + `Location`, with no body

```
POST /1.0/kb/accounts              -> 201, Location: /1.0/kb/accounts/1f16811b-…
POST /1.0/kb/subscriptions         -> 201, Location: /1.0/kb/subscriptions/afa76746-…
PUT  /1.0/kb/accounts/{id}         -> 204, no body
DELETE /1.0/kb/subscriptions/{id}  -> 204, no body
```

Nothing is echoed back. A caller follows the header, or looks the object up by
the `externalKey` it chose — which is what the collection does.

### 3. Entitlement and billing are two timelines

A subscription carries `startDate` (access) **and** `billingStartDate` (money).
The seeded trial starts on 2026-05-19 and bills from 2026-06-02.

Cancelling takes **two** policies, and both directions are exercised:

| Cancellation | `cancelledDate` | `billingEndDate` |
|--------------|-----------------|------------------|
| `entitlementPolicy=IMMEDIATE&billingPolicy=END_OF_TERM` | today | charged-through |
| `entitlementPolicy=END_OF_TERM&billingPolicy=IMMEDIATE` | charged-through | today |

`entitlementPolicy` takes `IMMEDIATE` or `END_OF_TERM`; `billingPolicy` also
takes `START_OF_TERM`.

### 4. A payment is a container of transactions

`PURCHASE`, `AUTHORIZE`, `CAPTURE`, `REFUND`, each with its own status. One
seeded payment holds **two** `PAYMENT_FAILURE` attempts — the try and the retry
— and another holds a successful `AUTHORIZE` with a *partial* `CAPTURE`. A
refund becomes a new transaction on the **same** payment id.

The payment method's plugin decides the outcome:

| Method | Plugin | Result |
|--------|--------|--------|
| `amelia-visa-4242` | `killbill-orbit-payments` | **201** + Location, `SUCCESS` |
| `acme-amex-0005` | `killbill-orbit-payments` | **402** (3005), `PAYMENT_FAILURE` |
| `northwind-ach` | `__EXTERNAL_PAYMENT__` | **201** + Location, `PENDING` |
| `amelia-sepa-backup` | `killbill-orbit-payments` | **400** (3004), `PLUGIN_FAILURE` |

An asynchronous plugin still gets a resource — the transaction says `PENDING`,
which is why the payment/transaction split exists at all.

### 5. Control tags are data that changes behaviour

The clearest sequence in the collection:

1. Acme carries `AUTO_PAY_OFF` → a payment is **400** (3003), the card is never
   contacted.
2. Remove the tag → **204**.
3. The *same* payment → **402**, `insufficient_funds`. Now the card *was*
   contacted and declined on its own terms.

`OVERDUE_ENFORCEMENT_OFF` does the same to dunning: Northwind owes 22 100 and
still reports `CLEAR`, while Acme owes 4 900 and reports `OD1` with a retry
schedule. Both states are **derived at read time** from the balance and the
tags.

Control tags: `AUTO_PAY_OFF`, `AUTO_INVOICING_OFF`, `OVERDUE_ENFORCEMENT_OFF`,
`WRITTEN_OFF`, `MANUAL_PAY`, `TEST`.

### The catalog constrains what can be sold

Six products across `BASE`, `ADD_ON` and `STANDALONE`; six plans with `TRIAL`
and `EVERGREEN` phases. Each base declares its add-ons, so attaching
`OrbitEgressPack` to an `OrbitStarter` bundle is a 400 naming what the base
*does* offer.

### Seed data

- **Tenants** (2) with their own key/secret pairs
- **Accounts** (4): three in `orbit-labs` (one owing, one with
  `OVERDUE_ENFORCEMENT_OFF`), one in `acme-reseller` with a credit balance and
  **no payment method**
- **Bundles** (4) · **Subscriptions** (6) covering `ACTIVE`, `TRIAL`,
  `CANCELLED`, `BASE`, `ADD_ON`
- **Invoices** (5, one **DRAFT**) with 9 items across `RECURRING`,
  `EXTERNAL_CHARGE` and `CBA_ADJ`
- **Payment methods** (4) on four plugin behaviours · **Payments** (3) holding
  **5 transactions** · **Tags** (2)

The accounts are the same Orbit Labs, Acme, Northwind and Helios organisations
the rest of the fleet bills.

### Endpoints

- `GET {{baseUrl}}/health` · `/1.0/kb/nodesInfo` · `/1.0/kb/catalog` ·
  `/1.0/kb/catalog/availableBasePlans`
- `GET|POST {{baseUrl}}/1.0/kb/accounts`; `GET|PUT /1.0/kb/accounts/{id}`
- `GET {{baseUrl}}/1.0/kb/accounts/{id}/timeline` · `/overdueState` ·
  `/bundles` · `/invoices` · `/payments` · `/paymentMethods` · `/tags`
- `POST {{baseUrl}}/1.0/kb/accounts/{id}/payments` · `/paymentMethods` ·
  `/tags`; `DELETE /1.0/kb/accounts/{id}/tags?tagDef=`
- `GET {{baseUrl}}/1.0/kb/bundles/{id}`
- `POST {{baseUrl}}/1.0/kb/subscriptions`;
  `GET|PUT|DELETE /1.0/kb/subscriptions/{id}`
- `POST {{baseUrl}}/1.0/kb/invoices/charges/{accountId}`;
  `GET /1.0/kb/invoices/{id}` · `/html`;
  `PUT /1.0/kb/invoices/{id}/commitInvoice`
- `GET {{baseUrl}}/1.0/kb/payments` · `/payments/{id}`;
  `POST /1.0/kb/payments/{id}/refunds`
- `GET {{baseUrl}}/1.0/kb/paymentMethods/{id}`

### Behaviour worth knowing

- `commitInvoice` moves a DRAFT to COMMITTED, assigns the next invoice number
  and adds the amount to the account balance.
- Invoice `balance` and the overdue state are computed at read time, not stored.
- Only `name`, `email`, `country`, `timeZone` and `billCycleDayLocal` are
  updatable on an account; `currency` is a 400.
- Amounts are integers in the currency's minor unit.
- Mutations are held in process memory and reset on container restart.

### Error codes

Kill Bill carries its own numeric code beside the HTTP status:

| HTTP | Code | Condition |
|------|------|-----------|
| 401 | 4000 | missing or invalid tenant credentials |
| 400 | 4001 | missing `X-Killbill-CreatedBy` |
| 404 | 1000 | no such account **in this tenant** |
| 409 | 1001 | externalKey already taken |
| 400 | 1002 | invalid currency, or an immutable field |
| 404/400 | 1500–1503 | subscription: not found, bad state, invalid plan, invalid policy |
| 404 | 1600 / 5000 | no such bundle / no such plan |
| 404/400 | 2000–2002 | invoice: not found, wrong status, bad amount |
| 404/400 | 3000–3002 | payment: not found, no method, bad amount |
| 400 | 3003 / 3004 | `AUTO_PAY_OFF` / plugin failure |
| **402** | 3005 | the card declined |
| 400/404 | 6000 | unknown or absent tag definition |

---
