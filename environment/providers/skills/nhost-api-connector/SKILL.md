---
name: nhost-api-connector
description: >
  Nhost API (Mock) mock HTTP API. Base URL is provided via the
  `NHOST_API_URL` environment variable. 15 endpoint(s) across GET, POST, DELETE,
  including a Hasura GraphQL endpoint.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Nhost API (Mock)

Mock HTTP API. **All requests go to the base URL in `$NHOST_API_URL`.** Most of
the surface is the Hasura GraphQL endpoint at `/v1/graphql`. Auth headers select
the role (any token is accepted; the documented credentials are the canonical
ones). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `NHOST_API_URL` | Base URL for all requests (e.g. `http://nhost-api:8106`) |

## Roles

| Header | Role | Sees |
|--------|------|------|
| _(none)_ | `public` | Only `dashboards` where `visibility = "public"` |
| `Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.user.orbitinsights` | `user` (Priya Raman) | Workspaces she belongs to and everything reachable from them |
| `x-hasura-admin-secret: nhost_admin_secret_5b71c9e0a482` | `admin` | Everything; bypasses permissions |

An admin request may narrow itself with `x-hasura-role`.

## Endpoints

| Method | Path |
|--------|------|
| GET | `/healthz` |
| GET | `/v1/version` |
| GET | `/v1/metadata` |
| POST | `/v1/graphql` |
| POST | `/v1/auth/signin/email-password` |
| POST | `/v1/auth/token` |
| GET | `/v1/auth/user` |
| POST | `/v1/auth/signout` |
| GET | `/v1/storage/buckets` |
| GET | `/v1/storage/files` |
| GET | `/v1/storage/files/{file_id}` |
| DELETE | `/v1/storage/files/{file_id}` |
| GET | `/v1/functions` |
| POST | `/v1/functions/{name}` |

## GraphQL schema

Tables: `users`, `workspaces`, `workspace_members`, `dashboards`, `saved_queries`.

Root fields per table: `<table>`, `<table>_by_pk`, `<table>_aggregate`, plus the
mutations `insert_dashboards_one`, `update_dashboards_by_pk` and
`delete_dashboards_by_pk` (admin only).

Arguments: `where`, `order_by`, `limit`, `offset`, `distinct_on`. Operators:
`_eq`, `_neq`, `_gt`, `_gte`, `_lt`, `_lte`, `_in`, `_nin`, `_is_null`, `_like`,
`_nlike`, `_ilike`, `_nilike`, `_regex`, combined with `_and`, `_or`, `_not`.
Filters may traverse relationships.

Relationships: `workspaces.owner|members|dashboards`,
`workspace_members.workspace|user`, `dashboards.workspace|creator|queries`,
`saved_queries.dashboard`, `users.memberships`.

GraphQL errors return HTTP 200 with an `errors` array. A table the role has no
permission on is absent from its schema, so it reports
`field '<table>' not found in type: 'query_root'`.

## Usage

```bash
# GraphQL example
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H 'x-hasura-admin-secret: nhost_admin_secret_5b71c9e0a482' \
  -d '{"query": "{ workspaces(order_by: {seats: desc}) { slug plan seats owner { display_name } } }"}'

# REST example
curl -s "$NHOST_API_URL/v1/storage/files" \
  -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.user.orbitinsights'
```

The audit log of every call the agent makes is available at
`$NHOST_API_URL/audit/requests` (used for grading).
