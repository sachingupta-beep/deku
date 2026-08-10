# Nhost Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$NHOST_API_URL`; responses are verbatim (long arrays elided with
`…`). The examples assume:

```bash
export NH_ADMIN='nhost_admin_secret_5b71c9e0a482'
export NH_TOKEN='eyJhbGciOiJIUzI1NiJ9.user.orbitinsights'
```

A helper for the GraphQL examples:

```bash
gql() { curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
          "${@:2}" -d "$(jq -cn --arg q "$1" '{query:$q}')"; }
```

## Health and version

```bash
curl -s "$NHOST_API_URL/health"
curl -s "$NHOST_API_URL/healthz"
curl -s "$NHOST_API_URL/v1/version"
```
```json
{"status": "ok"}
{"status": "ok", "services": {"hasura": "ok", "auth": "ok", "storage": "ok", "postgres": "ok"}}
{"subdomain": "orbitinsights", "name": "Orbit Insights", "region": "eu-central-1",
 "plan": "pro",
 "versions": {"hasura": "v2.42.0", "auth": "0.36.1", "storage": "0.6.1",
              "postgres": "15.6", "functions": "1.5.0"},
 "endpoints": {"graphql": "/v1/graphql", "auth": "/v1/auth",
               "storage": "/v1/storage", "functions": "/v1/functions"}}
```

## The same query under three roles

```graphql
{ workspaces(order_by: {seats: desc}) { id slug plan seats owner { display_name } } }
```

**admin** (`-H "x-hasura-admin-secret: $NH_ADMIN"`) — all four workspaces:
```json
{"data": {"workspaces": [
  {"id": 2, "slug": "helix-robotics", "plan": "enterprise", "seats": 50,
   "owner": {"display_name": "Marcus Feld"}},
  {"id": 3, "slug": "lumen-design", "plan": "pro", "seats": 12,
   "owner": {"display_name": "Sofia Duarte"}},
  {"id": 1, "slug": "aurora-bistro", "plan": "starter", "seats": 5,
   "owner": {"display_name": "Priya Raman"}},
  {"id": 4, "slug": "pelagic-freight", "plan": "starter", "seats": 3,
   "owner": {"display_name": "Tobias Krause"}}]}}
```

**user** (`-H "Authorization: Bearer $NH_TOKEN"`) — only Priya's two workspaces,
because the permission filter is
`{"members": {"user_id": {"_eq": "X-Hasura-User-Id"}}}`:
```json
{"data": {"workspaces": [{"id": 3, "slug": "lumen-design", "plan": "pro", "seats": 12},
                         {"id": 1, "slug": "aurora-bistro", "plan": "starter", "seats": 5}]}}
```

**public** (no header) — the table is not in the role's schema at all:
```json
{"errors": [{"message": "field 'workspaces' not found in type: 'query_root'",
             "extensions": {"code": "validation-failed", "path": "$"}}]}
```

The `public` role does hold a select permission on `dashboards`, filtered to
`visibility = public` with a seven-column allow-list:

```json
{"data": {"dashboards": [
  {"id": 102, "name": "Public Status Metrics", "slug": "public-status-metrics",
   "visibility": "public", "widget_count": 3},
  {"id": 105, "name": "Uptime Scorecard", "slug": "uptime-scorecard",
   "visibility": "public", "widget_count": 5}]}}
```

## Nested relationships

```graphql
{ workspaces(where: {slug: {_eq: "helix-robotics"}}) {
    name
    dashboards(order_by: {widget_count: desc}, limit: 2) {
      name widget_count
      queries { name runtime_ms cached }
    } } }
```
```json
{"data": {"workspaces": [{"name": "Helix Robotics", "dashboards": [
  {"name": "Fleet Telemetry", "widget_count": 21, "queries": [
     {"name": "Robot uptime by site", "runtime_ms": 1840, "cached": false},
     {"name": "Fault codes this week", "runtime_ms": 620, "cached": false}]},
  {"name": "Revenue by Region", "widget_count": 12, "queries": [
     {"name": "MRR by region", "runtime_ms": 204, "cached": true}]}]}]}}
```

Per-relation `where`, `order_by`, `limit` and `offset` all apply, and nesting is
unbounded.

## Aggregates

```graphql
{ workspaces_aggregate { aggregate {
    count sum { seats monthly_events } avg { seats } max { monthly_events } } } }
```
```json
{"data": {"workspaces_aggregate": {"aggregate": {
  "count": 4, "sum": {"seats": 70, "monthly_events": 10347195},
  "avg": {"seats": 17.5}, "max": {"monthly_events": 9420115}}}}}
```

`aggregate` and `nodes` can be selected together:

```graphql
{ dashboards_aggregate(where: {visibility: {_eq: "workspace"}}) {
    aggregate { count sum { widget_count } } nodes { id name } } }
```
```json
{"data": {"dashboards_aggregate": {
  "aggregate": {"count": 4, "sum": {"widget_count": 50}},
  "nodes": [{"id": 101, "name": "Storefront Overview"},
            {"id": 103, "name": "Fleet Telemetry"},
            {"id": 104, "name": "Revenue by Region"},
            {"id": 106, "name": "Client Delivery Health"}]}}}
```

## Boolean expressions

```graphql
{ dashboards(where: {_or: [
      {visibility: {_eq: "public"}},
      {_and: [{starred: {_eq: true}}, {widget_count: {_gte: 9}}]}]},
    order_by: {id: asc}) { id name visibility starred widget_count } }
```
```json
{"data": {"dashboards": [
  {"id": 102, "name": "Public Status Metrics", "visibility": "public", "starred": false, "widget_count": 3},
  {"id": 103, "name": "Fleet Telemetry", "visibility": "workspace", "starred": true, "widget_count": 21},
  {"id": 105, "name": "Uptime Scorecard", "visibility": "public", "starred": false, "widget_count": 5},
  {"id": 106, "name": "Client Delivery Health", "visibility": "workspace", "starred": true, "widget_count": 9}]}}
```

Filters can traverse a relationship — "workspaces that own at least one public
dashboard":

```graphql
{ workspaces(where: {dashboards: {visibility: {_eq: "public"}}}, order_by: {id: asc}) { id slug } }
```
```json
{"data": {"workspaces": [{"id": 1, "slug": "aurora-bistro"},
                         {"id": 2, "slug": "helix-robotics"}]}}
```

Other supported forms:

```graphql
{ users(where: {email: {_ilike: "%orbit-labs.com"}}) { display_name email roles } }
{ workspaces(where: {plan: {_in: ["starter", "pro"]}, region: {_is_null: false}}) { slug plan } }
{ dashboards(distinct_on: workspace_id, order_by: {workspace_id: asc}) { workspace_id name } }
{ dashboards_by_pk(id: 103) { id name workspace { name plan } creator { display_name } } }
{ large: workspaces(where: {seats: {_gte: 12}}) { __typename slug seats } }
```

## Variables

```bash
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "x-hasura-admin-secret: $NH_ADMIN" \
  -d '{"query": "query ByPlan($plan: String!, $minSeats: Int!) { workspaces(where: {plan: {_eq: $plan}, seats: {_gte: $minSeats}}) { slug seats } }",
       "variables": {"plan": "enterprise", "minSeats": 10}}'
```
```json
{"data": {"workspaces": [{"slug": "helix-robotics", "seats": 50}]}}
```

## Mutations

```graphql
mutation { insert_dashboards_one(object: {
    workspace_id: 1, name: "Churn Watch", slug: "churn-watch",
    visibility: "workspace", widget_count: 4}) { id name workspace { slug } } }
```
```json
{"data": {"insert_dashboards_one": {"id": 108, "name": "Churn Watch",
                                    "workspace": {"slug": "aurora-bistro"}}}}
```

```graphql
mutation { update_dashboards_by_pk(pk_columns: {id: 101},
    _set: {widget_count: 11, starred: false}) { id widget_count starred updated_at } }
```
```json
{"data": {"update_dashboards_by_pk": {"id": 101, "widget_count": 11,
                                      "starred": false, "updated_at": "…"}}}
```

## GraphQL error paths

All answer HTTP 200 with an `errors` array, as GraphQL requires.

| Query | Error |
|-------|-------|
| `{ workspaces { id } }` as `public` | `field 'workspaces' not found in type: 'query_root'` (`validation-failed`) |
| `{ invoices { id } }` | `field 'invoices' not found in type: 'query_root'` |
| `{ users { email } }` as `user` | `field 'email' not found in type: 'users'` — column permission |
| `insert_dashboards_one` into a workspace you are not in | `check constraint of an insert permission has failed` (`permission-error`) |
| `insert_dashboards_one` with `workspace_id: 99` | `Foreign key violation … "dashboards_workspace_id_fkey"` (`constraint-violation`) |
| `delete_dashboards_by_pk` as `user` | `field 'delete_dashboards_by_pk' not found in type: 'mutation_root'` |
| `{ workspaces { id ` | `expected NAME, found ''` |

## Auth

```bash
curl -s -X POST "$NHOST_API_URL/v1/auth/signin/email-password" \
  -H 'Content-Type: application/json' \
  -d '{"email": "priya.raman@aurorabistro.com", "password": "OrbitInsights2026!"}'
```
```json
{"session": {"accessToken": "eyJhbGciOiJIUzI1NiJ9.user.f6d250145b0f410d",
             "accessTokenExpiresIn": 900,
             "refreshToken": "c5962941-f856-4f3a-b455-63ff51b2d450",
             "refreshTokenId": "c5962941-f856-4f3a-b455-63ff51b2d450",
             "user": {"id": "2b7f1c94-…", "email": "priya.raman@aurorabistro.com",
                      "displayName": "Priya Raman", "defaultRole": "user",
                      "roles": ["user", "me"], "emailVerified": true, "…": "…"}},
 "mfa": null}
```

```bash
curl -s -X POST "$NHOST_API_URL/v1/auth/token" -H 'Content-Type: application/json' \
  -d '{"refreshToken": "1c6e0a94-73b5-4f28-8d10-9a2c74e5b063"}'
curl -s "$NHOST_API_URL/v1/auth/user" -H "Authorization: Bearer $NH_TOKEN"
curl -s -X POST "$NHOST_API_URL/v1/auth/signout" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $NH_TOKEN" -d '{"all": true}'
```

A wrong password returns 401 `{"message": "Incorrect email or password",
"extensions": {"code": "invalid-email-password"}}`.

## Storage

```bash
curl -s "$NHOST_API_URL/v1/storage/buckets" -H "x-hasura-admin-secret: $NH_ADMIN"
curl -s "$NHOST_API_URL/v1/storage/files?bucketId=exports" -H "x-hasura-admin-secret: $NH_ADMIN"
curl -s "$NHOST_API_URL/v1/storage/files" -H "Authorization: Bearer $NH_TOKEN"
```

The `user` role sees only its own uploads:

```json
{"files": [{"id": "7f31b0c5-4a92-4e18-b306-5d9c0e27f4a1", "bucket_id": "exports",
            "name": "storefront-overview-2026-05-24.csv", "size": 482310,
            "mime_type": "text/csv", "is_uploaded": true,
            "uploaded_by_user_id": "2b7f1c94-…", "…": "…"},
           {"id": "b58170ea-…", "name": "priya-avatar.png", "…": "…"}]}
```

Fetching a file uploaded by someone else returns 403
`{"extensions": {"code": "forbidden"}}`.

## Functions

```bash
curl -s "$NHOST_API_URL/v1/functions"
curl -s -X POST "$NHOST_API_URL/v1/functions/refresh-usage" \
  -H 'Content-Type: application/json' -H "x-hasura-admin-secret: $NH_ADMIN" -d '{}'
curl -s -X POST "$NHOST_API_URL/v1/functions/export-dashboard" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $NH_TOKEN" \
  -d '{"dashboard_id": 103}'
```
```json
{"function": "refresh-usage", "statusCode": 200,
 "body": {"refreshed": 4, "total_monthly_events": 10347195, "billable_workspaces": 3}}
{"function": "export-dashboard", "statusCode": 200,
 "body": {"exported": true, "dashboard": "fleet-telemetry", "widgets": 21,
          "file": "fleet-telemetry-2026-05-26.csv"}}
```

`refresh-usage` reads the live `workspaces` rows, so its totals reflect any
mutations made earlier in the run. Invoking without auth returns 401; invoking
the disabled `rotate-api-keys` returns 404 `function-not-deployed`.

## Hasura metadata

```bash
curl -s "$NHOST_API_URL/v1/metadata" -H "x-hasura-admin-secret: $NH_ADMIN"
```
```json
{"resource_version": 41, "metadata": {"version": 3, "sources": [{
  "name": "default", "kind": "postgres", "tables": [
    {"table": {"schema": "public", "name": "workspaces"},
     "object_relationships": [{"name": "owner", "using": {"foreign_key_constraint_on": "owner_id"}}],
     "array_relationships": [
        {"name": "members", "using": {"foreign_key_constraint_on": {"table": "workspace_members", "column": "workspace_id"}}},
        {"name": "dashboards", "using": {"foreign_key_constraint_on": {"table": "dashboards", "column": "workspace_id"}}}],
     "select_permissions": [{"role": "user", "permission": {
        "columns": "*", "limit": 100,
        "filter": {"members": {"user_id": {"_eq": "X-Hasura-User-Id"}}}}}]}, "…"]}]}}
```

Without the admin secret this returns 401 `{"extensions": {"code": "access-denied"}}`.
