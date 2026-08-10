# Supabase Self-Host Mock API — Test Results

Base URL: `http://localhost:8102` (in docker-compose: `http://supabase-api:8102`)

## Endpoints covered

| Method | Path                                              | Status      |
|--------|---------------------------------------------------|-------------|
| GET    | /health                                           | 200         |
| GET    | /rest/v1/                                         | 200         |
| GET    | /rest/v1/{table}                                  | 200/404     |
| POST   | /rest/v1/{table}                                  | 201/401/404/409 |
| PATCH  | /rest/v1/{table}                                  | 200/401/404 |
| DELETE | /rest/v1/{table}                                  | 200/400/401/404 |
| POST   | /rest/v1/rpc/{fn_name}                            | 200/400/401/404 |
| GET    | /storage/v1/bucket                                | 200         |
| GET    | /storage/v1/bucket/{bucket_id}                    | 200/404     |
| POST   | /storage/v1/bucket                                | 201/401/409 |
| DELETE | /storage/v1/bucket/{bucket_id}                    | 200/401/404/409 |
| POST   | /storage/v1/object/list/{bucket_id}               | 200/404     |
| GET    | /storage/v1/object/info/{bucket_id}/{path}        | 200/404     |
| POST   | /storage/v1/object/sign/{bucket_id}/{path}        | 200/401/404 |
| DELETE | /storage/v1/object/{bucket_id}/{path}             | 200/401/404 |
| GET    | /functions/v1                                     | 200         |
| POST   | /functions/v1/{slug}                              | 200/401/404/429 |
| GET    | /realtime/v1/channels                             | 200         |
| POST   | /realtime/v1/api/broadcast                        | 202/400/401 |
| GET    | /v1/projects                                      | 200         |
| GET    | /v1/projects/{ref}                                | 200/404     |

Collection run: **PASS 31 / WARN 6 / FAIL 0 / SKIP 0**. All six WARNs are the
intentional error-path requests (unknown relation, FK violation, anon insert,
unknown function, non-empty bucket delete, throttled function).

## Seed data summary

- Profiles: 6 (`public.profiles`, uuid PKs) — 5 people + 1 service bot, one inactive (Noor Aziz)
- Projects: 5 (`101`–`105`) — 2 public, 3 private, one archived (Legacy Importer)
- Documents: 8 (`501`–`508`) in published/draft/archived status across all 5 projects
- Comments: 7 (`9001`–`9007`), 3 resolved
- Storage buckets: 4 (`avatars` public; `project-assets`, `invoices`, `db-backups` private)
- Storage objects: 9 spread across the four buckets
- Edge functions: 4 (`send-welcome-email`, `billing-webhook`, `generate-report`,
  `resize-avatar` — the last one is `THROTTLED`)
- Realtime channels: 3 (one private: `project:101`)
- Project settings: singleton from `settings.json` (ref `orbitlabsselfhost01`)

## Roles and RLS

The `apikey` header — or `Authorization: Bearer <token>` — selects the Postgres
role every request is evaluated as:

| Key sent                                    | Role            | Sees                                    |
|---------------------------------------------|-----------------|-----------------------------------------|
| none, or `...anon.orbit-labs-selfhost`      | `anon`          | public projects, published documents, public buckets |
| any other non-empty token                   | `authenticated` | everything; may insert and update       |
| `...service_role.orbit-labs-selfhost`       | `service_role`  | everything; may also delete             |

Keys are in `settings.json` under `api`. `GET /v1/projects/{ref}` masks the
service key, matching a real project's settings view.

## Notes

- List responses are bare PostgREST arrays with a `Content-Range` response
  header (`0-4/5`, or `*/0` when empty), not an object envelope.
- Horizontal filters use PostgREST grammar: `?status=eq.published`,
  `?star_count=gte.20`, `?body=ilike.*rollback*`, `?tags=cs.{security}`,
  `?id=in.(101,103)`, `?published_at=is.null`, and `not.` negation.
- `select` supports column projection and one level of resource embedding —
  `select=id,title,profiles(username),comments(id,body)`. The join key is read
  before projection, so embedding works even when the FK column is not selected.
- `order=col.desc`, `limit` and `offset` follow PostgREST; `limit` is capped at 1000.
- `POST /rest/v1/documents` validates `project_id` against `public.projects` and
  returns `23503` (409) on a foreign-key violation.
- `DELETE /rest/v1/{table}` refuses an unfiltered delete (`PGRST109`, 400) and
  requires the service key.
- RPCs: `project_stats`, `search_documents` (read) and `publish_document`
  (write — patches status and `published_at`).
- Errors carry the PostgREST body shape (`code`, `details`, `hint`, `message`)
  alongside the fleet-standard `error` key.
- GoTrue endpoints (`/auth/v1/*`) are served by `supabase-auth-api`, not here.
- Mutations (inserted rows, patches, deletes, created buckets, signed URLs,
  function invocations) are held in process memory and reset on container restart.
