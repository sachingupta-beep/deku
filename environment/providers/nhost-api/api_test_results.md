# Nhost Mock API — Test Results

Base URL: `http://localhost:8106` (in docker-compose: `http://nhost-api:8106`)

## Endpoints covered

| Method | Path                                    | Status      |
|--------|-----------------------------------------|-------------|
| GET    | /health                                 | 200         |
| GET    | /healthz                                | 200         |
| GET    | /v1/version                             | 200         |
| GET    | /v1/metadata                            | 200/401     |
| POST   | /v1/graphql                             | 200         |
| POST   | /v1/auth/signin/email-password          | 200/401     |
| POST   | /v1/auth/token                          | 200/401     |
| GET    | /v1/auth/user                           | 200/401     |
| POST   | /v1/auth/signout                        | 200         |
| GET    | /v1/storage/buckets                     | 200/403     |
| GET    | /v1/storage/files                       | 200/403/404 |
| GET    | /v1/storage/files/{id}                  | 200/403/404 |
| DELETE | /v1/storage/files/{id}                  | 200/403/404 |
| GET    | /v1/functions                           | 200         |
| POST   | /v1/functions/{name}                    | 200/401/404 |

Collection run: **PASS 42 / WARN 7 / FAIL 0 / SKIP 0**. All seven WARNs are the
intentional error-path requests. Note that GraphQL failures answer **HTTP 200
with an `errors` array**, as GraphQL requires — those requests are counted as
PASS by the harness, and the error is in the body.

## Seed data summary

- Project: `orbitinsights` — Hasura v2.42.0, Auth 0.36.1, Storage 0.6.1, Postgres 15.6
- `users`: 6 (Nhost auth users) — one disabled (`tobias.krause@pelagicfreight.com`)
- `workspaces`: 4 (Aurora Bistro, Helix Robotics, Lumen Design, Pelagic Freight)
- `workspace_members`: 8 rows; Priya belongs to Aurora Bistro and Lumen Design
- `dashboards`: 7 — 2 public, 4 workspace-scoped, 1 private
- `saved_queries`: 7 attached to five dashboards
- `permissions`: 8 Hasura permission rows across the `public` and `user` roles
- Storage: 2 buckets, 4 files; Functions: 3 (one disabled)

## Roles and permissions

| Auth | Role | Sees |
|------|------|------|
| none | `public` | Only the `dashboards` table, filtered to `visibility = public`, with a 7-column allow-list |
| `Authorization: Bearer <token>` | `user` as Priya Raman | Workspaces she is a member of, and everything reachable from them |
| `x-hasura-admin-secret: nhost_admin_secret_5b71c9e0a482` | `admin` | Everything; bypasses the permission layer |

An admin request may narrow itself with `x-hasura-role`, exactly as Hasura allows.

Permissions live in `permissions.json` in the shape Hasura keeps them — a row
filter, a column allow-list and a row limit per (role, table, action) — so
drifting a permission row changes what the API returns. Filters may traverse
relationships and reference session variables:

```json
{"workspace": {"members": {"user_id": {"_eq": "X-Hasura-User-Id"}}}}
```

Because a table with no select permission is genuinely absent from the role's
schema, querying it reports `field 'workspaces' not found in type: 'query_root'`
rather than an empty list — the same message Hasura returns.

## GraphQL support

`graphql_engine.py` is a real parser and executor, not a canned-response table.

| Feature | Support |
|---------|---------|
| Operations | `query` and `mutation`, named or shorthand, with `$variables` and `operationName` |
| Root fields | `<table>`, `<table>_by_pk`, `<table>_aggregate`, `insert_<table>_one`, `update_<table>_by_pk`, `delete_<table>_by_pk` |
| Arguments | `where`, `order_by`, `limit`, `offset`, `distinct_on` |
| Boolean expressions | `_and`, `_or`, `_not`, `_eq`, `_neq`, `_gt`, `_gte`, `_lt`, `_lte`, `_in`, `_nin`, `_is_null`, `_like`, `_nlike`, `_ilike`, `_nilike`, `_regex`, plus relationship traversal |
| Relationships | Object and array, nested to any depth, with per-relation `where`/`order_by`/`limit` |
| Aggregates | `count`, `sum`, `avg`, `min`, `max`, alongside `nodes` |
| Selection | Aliases and `__typename` |

Tables: `users`, `workspaces`, `workspace_members`, `dashboards`, `saved_queries`.

Relationships:

| From | Field | To | Kind |
|------|-------|----|------|
| `workspaces` | `owner` | `users` | object |
| `workspaces` | `members` | `workspace_members` | array |
| `workspaces` | `dashboards` | `dashboards` | array |
| `workspace_members` | `workspace` / `user` | `workspaces` / `users` | object |
| `dashboards` | `workspace` / `creator` | `workspaces` / `users` | object |
| `dashboards` | `queries` | `saved_queries` | array |
| `saved_queries` | `dashboard` | `dashboards` | object |
| `users` | `memberships` | `workspace_members` | array |

Fragments are not supported and report a clear error.

## Notes

- GraphQL errors return HTTP 200 with `{"errors": [{"message", "extensions": {"code", "path"}}]}`.
  Codes used: `validation-failed`, `permission-error`, `constraint-violation`.
- Column-level permissions are enforced on projection, so selecting `email` as
  the `user` role reports `field 'email' not found in type: 'users'`.
- Permission row limits cap page size: the `public` role is limited to 25 rows
  even if the query asks for more.
- `insert_dashboards_one` validates the workspace foreign key and the insert
  permission's check constraint separately, so a bad id and an unauthorised
  workspace produce different error codes.
- `delete_dashboards_by_pk` exists only for the `admin` role; for `user` it is
  reported as absent from `mutation_root`, which is how Hasura hides it.
- REST error bodies use `{"message", "error", "extensions": {"code"}}` and map
  onto real HTTP statuses. A disabled function answers 404 `function-not-deployed`
  because an undeployed function is not routed.
- `GET /v1/version` and `GET /v1/metadata` never expose the `credentials` block
  from `project.json`; the credentials are documented above and in the connector skill.
- Mutations (inserted/updated/deleted dashboards, sessions, deleted files,
  function invocation counters) are held in process memory and reset on restart.
