---
name: pocketbase-api-connector
description: >
  PocketBase API (Mock) mock HTTP API. Base URL is provided via the
  `POCKETBASE_API_URL` environment variable. 20 endpoint(s) across GET, POST, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# PocketBase API (Mock)

Mock HTTP API. **All requests go to the base URL in `$POCKETBASE_API_URL`.** The
`Authorization` header carries a PocketBase token (any token is accepted; the
superuser token has special meaning). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `POCKETBASE_API_URL` | Base URL for all requests (e.g. `http://pocketbase-api:8103`) |

## Tokens

| Token | Identity | Effect |
|-------|----------|--------|
| _(none)_ | guest | Public collections only (`services`, `incidents`, `incident_updates`) |
| `eyJhbGciOiJIUzI1NiJ9.users_amelia.orbit-labs-status`, or any other token | user `usramelia000001` | Adds the `users` collection |
| `eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status` | superuser | Bypasses every collection rule; required for `subscribers`, collections, logs, backups, crons, settings |

Send it as `Authorization: <token>` — the `Bearer` prefix is also accepted.

## Endpoints

| Method | Path |
|--------|------|
| GET | `/api/health` |
| GET | `/api/collections` |
| GET | `/api/collections/{collection}` |
| GET | `/api/collections/{collection}/records` |
| GET | `/api/collections/{collection}/records/{record_id}` |
| POST | `/api/collections/{collection}/records` |
| PATCH | `/api/collections/{collection}/records/{record_id}` |
| DELETE | `/api/collections/{collection}/records/{record_id}` |
| GET | `/api/files/{collection}/{record_id}/{filename}` |
| POST | `/api/files/token` |
| GET | `/api/logs` |
| GET | `/api/logs/stats` |
| GET | `/api/backups` |
| POST | `/api/backups` |
| DELETE | `/api/backups/{key}` |
| GET | `/api/crons` |
| GET | `/api/settings` |
| POST | `/api/realtime` |
| GET | `/api/realtime` |

Collections: `users` (auth), `services`, `incidents`, `incident_updates`, `subscribers`.

## Query parameters on record lists

`page`, `perPage` (max 500), `sort` (`-started,title`), `filter`, `expand`,
`fields`, `skipTotal`. Filter operators: `=`, `!=`, `>`, `>=`, `<`, `<=`, `~`
(contains), `!~`, `?=` / `?!=` (any-of, for multi-value fields), joined with
`&&` and `||`.

## Usage

```bash
# GET example
curl -s --get "$POCKETBASE_API_URL/api/collections/incidents/records" \
  --data-urlencode 'filter=status!="resolved"' --data-urlencode 'expand=service,assignee'

# POST example
curl -s -X POST "$POCKETBASE_API_URL/api/collections/subscribers/records" \
  -H 'Content-Type: application/json' -d '{}'
```

The audit log of every call the agent makes is available at
`$POCKETBASE_API_URL/audit/requests` (used for grading).
