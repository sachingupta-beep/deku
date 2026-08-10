# Nhost API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$NHOST_API_URL`.** Auth headers select the role (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `NHOST_API_URL` | Base URL for all requests |

Set the credentials once to follow the examples:

```bash
export NH_ADMIN='nhost_admin_secret_5b71c9e0a482'
export NH_TOKEN='eyJhbGciOiJIUzI1NiJ9.user.orbitinsights'
```

## Health, version and metadata

```bash
curl -s "$NHOST_API_URL/healthz"
curl -s "$NHOST_API_URL/v1/version"
curl -s "$NHOST_API_URL/v1/metadata" -H "x-hasura-admin-secret: $NH_ADMIN"
```

## GraphQL

Every GraphQL call is a POST to `/v1/graphql` with `{"query": "...", "variables": {...}}`.

```bash
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "x-hasura-admin-secret: $NH_ADMIN" \
  -d '{"query": "{ workspaces(order_by: {seats: desc}) { id slug plan seats owner { display_name } } }"}'

# Row permissions: the same query as the user role returns only their workspaces
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $NH_TOKEN" \
  -d '{"query": "{ workspaces { id slug plan } }"}'

# Public role: only public dashboards are in its schema
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -d '{"query": "{ dashboards { id name visibility widget_count } }"}'

# Nested relationships
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "x-hasura-admin-secret: $NH_ADMIN" \
  -d '{"query": "{ workspaces(where: {slug: {_eq: \"helix-robotics\"}}) { name dashboards(order_by: {widget_count: desc}) { name queries { name runtime_ms } } } }"}'

# Aggregates
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "x-hasura-admin-secret: $NH_ADMIN" \
  -d '{"query": "{ workspaces_aggregate { aggregate { count sum { seats } avg { seats } } } }"}'

# Primary-key lookup
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "x-hasura-admin-secret: $NH_ADMIN" \
  -d '{"query": "{ dashboards_by_pk(id: 103) { id name workspace { name plan } } }"}'

# Variables
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "x-hasura-admin-secret: $NH_ADMIN" \
  -d '{"query": "query ByPlan($plan: String!) { workspaces(where: {plan: {_eq: $plan}}) { slug seats } }", "variables": {"plan": "enterprise"}}'

# Mutations
curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $NH_TOKEN" \
  -d '{"query": "mutation { insert_dashboards_one(object: {workspace_id: 1, name: \"Churn Watch\", slug: \"churn-watch\"}) { id name } }"}'

curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $NH_TOKEN" \
  -d '{"query": "mutation { update_dashboards_by_pk(pk_columns: {id: 101}, _set: {starred: false}) { id starred } }"}'

curl -s -X POST "$NHOST_API_URL/v1/graphql" -H 'Content-Type: application/json' \
  -H "x-hasura-admin-secret: $NH_ADMIN" \
  -d '{"query": "mutation { delete_dashboards_by_pk(id: 107) { id slug } }"}'
```

Operators: `_eq`, `_neq`, `_gt`, `_gte`, `_lt`, `_lte`, `_in`, `_nin`,
`_is_null`, `_like`, `_nlike`, `_ilike`, `_nilike`, `_regex`, combined with
`_and`, `_or` and `_not`. Filters may traverse relationships, e.g.
`where: {dashboards: {visibility: {_eq: "public"}}}`.

## Auth

```bash
curl -s -X POST "$NHOST_API_URL/v1/auth/signin/email-password" \
  -H 'Content-Type: application/json' \
  -d '{"email": "priya.raman@aurorabistro.com", "password": "OrbitInsights2026!"}'
curl -s -X POST "$NHOST_API_URL/v1/auth/token" -H 'Content-Type: application/json' \
  -d '{"refreshToken": "1c6e0a94-73b5-4f28-8d10-9a2c74e5b063"}'
curl -s "$NHOST_API_URL/v1/auth/user" -H "Authorization: Bearer $NH_TOKEN"
curl -s -X POST "$NHOST_API_URL/v1/auth/signout" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $NH_TOKEN" -d '{"all": true}'
```

## Storage

```bash
curl -s "$NHOST_API_URL/v1/storage/buckets" -H "x-hasura-admin-secret: $NH_ADMIN"
curl -s "$NHOST_API_URL/v1/storage/files?bucketId=exports" -H "x-hasura-admin-secret: $NH_ADMIN"
curl -s "$NHOST_API_URL/v1/storage/files" -H "Authorization: Bearer $NH_TOKEN"
curl -s "$NHOST_API_URL/v1/storage/files/7f31b0c5-4a92-4e18-b306-5d9c0e27f4a1" \
  -H "Authorization: Bearer $NH_TOKEN"
curl -s -X DELETE "$NHOST_API_URL/v1/storage/files/3d02c8b1-6f47-40ae-9235-c81b7e05d6a9" \
  -H "x-hasura-admin-secret: $NH_ADMIN"
```

## Functions

```bash
curl -s "$NHOST_API_URL/v1/functions"
curl -s -X POST "$NHOST_API_URL/v1/functions/refresh-usage" \
  -H 'Content-Type: application/json' -H "x-hasura-admin-secret: $NH_ADMIN" -d '{}'
curl -s -X POST "$NHOST_API_URL/v1/functions/export-dashboard" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $NH_TOKEN" \
  -d '{"dashboard_id": 103}'
```
