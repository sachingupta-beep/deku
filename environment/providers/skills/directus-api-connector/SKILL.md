---
name: directus-api-connector
description: >
  Directus API (Mock) mock HTTP API. Base URL is provided via the
  `DIRECTUS_API_URL` environment variable. 25 endpoint(s) across GET, POST, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Directus API (Mock)

Mock HTTP API. **All requests go to the base URL in `$DIRECTUS_API_URL`.** A
static token selects the role (any token is accepted; the documented tokens are
the canonical ones). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `DIRECTUS_API_URL` | Base URL for all requests (e.g. `http://directus-api:8105`) |

## Tokens

| Token | Role | Sees |
|-------|------|------|
| _(none)_ | Public | `posts` where `status = published`, all `categories`, `job_openings` where `status = open` |
| `dr_static_editor_2b90d7fc1e6a4830`, or any other token | Editor | All posts and job openings; may create posts and update non-archived ones |
| `dr_static_admin_4f81c6a930b7e254` | Administrator | Everything, including users, roles, permissions, activity, flows and settings |

Send it as `Authorization: Bearer <token>` or as an `access_token` query
parameter. `POST /auth/login` with `noor.aziz@orbit-labs.com` /
`OrbitContent2026!` mints a session token equivalent to the editor token.

## Endpoints

| Method | Path |
|--------|------|
| GET | `/server/ping` |
| GET | `/server/health` |
| GET | `/server/info` |
| POST | `/auth/login` |
| GET | `/items/{collection}` |
| POST | `/items/{collection}` |
| GET | `/items/{collection}/{item_id}` |
| PATCH | `/items/{collection}/{item_id}` |
| DELETE | `/items/{collection}/{item_id}` |
| GET | `/collections` |
| GET | `/collections/{collection}` |
| GET | `/fields` |
| GET | `/fields/{collection}` |
| GET | `/users` |
| GET | `/users/me` |
| GET | `/users/{user_id}` |
| GET | `/roles` |
| GET | `/roles/{role_id}` |
| GET | `/permissions` |
| GET | `/files` |
| GET | `/files/{file_id}` |
| GET | `/activity` |
| GET | `/flows` |
| GET | `/settings` |

Collections: `posts`, `categories`, `job_openings`.

## Query parameters

`filter` (Directus filter JSON), `fields` (supports `*`, `*.*` and relational
dot-notation such as `category.name`), `sort` (`-publish_date,title`), `search`,
`limit` / `offset` / `page`, `meta` (`*`, `total_count`, `filter_count`), and
`aggregate` with `groupBy`. Filter operators: `_eq`, `_neq`, `_lt`, `_lte`,
`_gt`, `_gte`, `_in`, `_nin`, `_null`, `_nnull`, `_empty`, `_nempty`,
`_contains`, `_icontains`, `_ncontains`, `_starts_with`, `_ends_with`,
`_between`, `_nbetween`, `_and`, `_or`.

Note: Directus answers **403 FORBIDDEN** for anything the caller may not see,
including items that do not exist — it never reveals record existence.

## Usage

```bash
# GET example
curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"status":{"_eq":"published"}}' \
  --data-urlencode 'fields=id,title,category.name'

# POST example
curl -s -X POST "$DIRECTUS_API_URL/items/posts" -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer dr_static_editor_2b90d7fc1e6a4830' -d '{}'
```

The audit log of every call the agent makes is available at
`$DIRECTUS_API_URL/audit/requests` (used for grading).
