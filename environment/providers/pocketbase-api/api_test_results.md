# PocketBase Mock API — Test Results

Base URL: `http://localhost:8103` (in docker-compose: `http://pocketbase-api:8103`)

## Endpoints covered

| Method | Path                                                  | Status      |
|--------|-------------------------------------------------------|-------------|
| GET    | /health                                               | 200         |
| GET    | /api/health                                           | 200         |
| GET    | /api/collections                                      | 200/403     |
| GET    | /api/collections/{collection}                         | 200/403/404 |
| GET    | /api/collections/{collection}/records                 | 200/400/403/404 |
| GET    | /api/collections/{collection}/records/{id}            | 200/403/404 |
| POST   | /api/collections/{collection}/records                 | 200/400/403/404 |
| PATCH  | /api/collections/{collection}/records/{id}            | 200/400/403/404 |
| DELETE | /api/collections/{collection}/records/{id}            | 200/403/404 |
| GET    | /api/files/{collection}/{recordId}/{filename}         | 200/404     |
| POST   | /api/files/token                                      | 200/403     |
| GET    | /api/logs                                             | 200/403     |
| GET    | /api/logs/stats                                       | 200/403     |
| GET    | /api/backups                                          | 200/403     |
| POST   | /api/backups                                          | 200/400/403 |
| DELETE | /api/backups/{key}                                    | 200/403/404 |
| GET    | /api/crons                                            | 200/403     |
| GET    | /api/settings                                         | 200/403     |
| POST   | /api/realtime                                         | 200/400     |
| GET    | /api/realtime                                         | 200/403     |

Collection run: **PASS 30 / WARN 9 / FAIL 0 / SKIP 0**. All nine WARNs are the
intentional error-path requests (four rule denials, a missing record, a missing
file, a required-field failure, a bad relation, and an unknown realtime topic).

## Seed data summary

- Collections: 5 (`users` auth-type, `services`, `incidents`, `incident_updates`, `subscribers`)
- Users: 6 auth records — Jonas is the on-call engineer; only Amelia has `emailVisibility: true`
- Services: 5 (`auth-api` degraded, `infra` in maintenance, the rest operational)
- Incidents: 6 (`incident0000001`–`incident0000006`) — 2 open, 4 resolved, severities 1–4
- Incident updates: 8, forming the timeline for each incident
- Subscribers: 5 status-page subscribers, one unconfirmed (Pelagic Freight)
- Logs: 8 request-log entries across levels 0/4/8
- Backups: 4 archives; crons: 6 (5 system + `digestStatusEmail`)
- Settings: singleton from `settings.json` (PocketBase v0.24.4, SQLite `pb_data/data.db`)

## Identity and collection rules

`Authorization: <token>` (with or without the `Bearer` prefix) selects the caller:

| Token | Identity | Notes |
|-------|----------|-------|
| absent | guest | Public collections only |
| `eyJhbGciOiJIUzI1NiJ9.users_amelia.orbit-labs-status`, or any other token | user `usramelia000001` | Any token is accepted, matching the fleet convention |
| `eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status` | superuser | Bypasses every collection rule |

Seeded rules, and what PocketBase reports for them in `GET /api/collections`:

| Collection | list / view | create | update | delete |
|------------|-------------|--------|--------|--------|
| `users` | `@request.auth.id != ''` | `""` (public) | `id = @request.auth.id` | `null` |
| `services` | `""` | `null` | `null` | `null` |
| `incidents` | `""` | `null` | `null` | `null` |
| `incident_updates` | `""` | `null` | `null` | `null` |
| `subscribers` | `null` | `""` | `null` | `null` |

`""` means public and `null` means superuser-only, exactly as PocketBase encodes
them. The seed files carry `@public` / `@auth` / `@owner` / `@superuser` tokens
instead, because a CSV overlay cannot express the blank-versus-null distinction.

## Notes

- List reads return the PocketBase envelope
  `{"page", "perPage", "totalItems", "totalPages", "items"}`; `skipTotal=true`
  reports `totalItems: -1` and `totalPages: -1`.
- Every record carries the system fields `id`, `collectionId`, `collectionName`,
  `created`, `updated`. Timestamps use PocketBase's `YYYY-MM-DD HH:MM:SS.mmmZ`.
- `filter` implements the PocketBase grammar: `=`, `!=`, `>`, `>=`, `<`, `<=`,
  `~`, `!~`, `?=`, `?!=`, combined with `&&` and `||` (`&&` binds tighter).
  Quoted spans are respected, so an operator inside a string literal is safe.
- `expand` resolves relations one level deep into an `expand` object —
  `service` and `assignee` on incidents, `incident` and `author` on updates, and
  the multi-relation `services` on subscribers (which expands to an array).
- `fields` projects the response; `sort` accepts `-field` for descending and
  comma-separated keys.
- Auth-collection records hide `email` unless the caller is the record owner, is
  a superuser, or the record sets `emailVisibility: true` — real PocketBase behaviour.
- Record creates return **200**, not 201, matching PocketBase.
- `GET /api/files/...` returns the file descriptor (id, field, mime type, size,
  url) rather than the bytes, so benchmark runs stay deterministic and diffable.
  Sizes are derived from the filename, so they never change between runs.
- `GET /api/settings` strips the `tokens` block that the mock uses internally to
  resolve identities; the tokens are documented above and in the connector skill.
- `GET /api/realtime` lists recorded subscriptions instead of opening an SSE
  stream — an SSE response cannot be captured deterministically by the harness.
- Mutations (created/updated/deleted records, backups, realtime subscriptions,
  file tokens) are held in process memory and reset on container restart.
