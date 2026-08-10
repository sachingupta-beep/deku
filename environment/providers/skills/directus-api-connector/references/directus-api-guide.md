# Directus API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$DIRECTUS_API_URL`.** A static token selects the role (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `DIRECTUS_API_URL` | Base URL for all requests |

Set the tokens once to follow the examples:

```bash
export DR_ADMIN='dr_static_admin_4f81c6a930b7e254'
export DR_EDITOR='dr_static_editor_2b90d7fc1e6a4830'
```

## Server and auth

```bash
curl -s "$DIRECTUS_API_URL/server/ping"
curl -s "$DIRECTUS_API_URL/server/health"
curl -s "$DIRECTUS_API_URL/server/info"
curl -s -X POST "$DIRECTUS_API_URL/auth/login" -H 'Content-Type: application/json' \
  -d '{"email": "noor.aziz@orbit-labs.com", "password": "OrbitContent2026!"}'
```

## Items

```bash
curl -s "$DIRECTUS_API_URL/items/posts?fields=id,status,title&sort=-publish_date"
curl -s "$DIRECTUS_API_URL/items/posts?fields=id,status,title" -H "Authorization: Bearer $DR_EDITOR"
curl -s "$DIRECTUS_API_URL/items/posts?meta=*&limit=3" -H "Authorization: Bearer $DR_ADMIN"

curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"hits":{"_gt":3000},"category":{"_in":[1,4]}}' \
  -H "Authorization: Bearer $DR_ADMIN"

curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"_or":[{"status":{"_eq":"draft"}},{"hits":{"_gte":8000}}]}' \
  -H "Authorization: Bearer $DR_ADMIN"

curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'filter={"category":{"slug":{"_eq":"security"}}}' \
  --data-urlencode 'fields=id,title,category.name' -H "Authorization: Bearer $DR_ADMIN"

curl -s "$DIRECTUS_API_URL/items/posts?search=passkey" -H "Authorization: Bearer $DR_ADMIN"

curl -s --get "$DIRECTUS_API_URL/items/posts" \
  --data-urlencode 'aggregate={"count":"*","sum":"hits"}' --data-urlencode 'groupBy=status' \
  -H "Authorization: Bearer $DR_ADMIN"

curl -s "$DIRECTUS_API_URL/items/posts/13?fields=*.*" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/items/categories?sort=sort"
curl -s "$DIRECTUS_API_URL/items/job_openings?fields=id,status,title"

curl -s -X POST "$DIRECTUS_API_URL/items/posts" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $DR_EDITOR" \
  -d '{"status": "draft", "title": "New post", "slug": "new-post", "category": 2}'

curl -s -X PATCH "$DIRECTUS_API_URL/items/posts/15" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $DR_EDITOR" -d '{"status": "published"}'

curl -s -X DELETE "$DIRECTUS_API_URL/items/posts/17" -H "Authorization: Bearer $DR_ADMIN"
```

Filter operators: `_eq`, `_neq`, `_lt`, `_lte`, `_gt`, `_gte`, `_in`, `_nin`,
`_null`, `_nnull`, `_empty`, `_nempty`, `_contains`, `_icontains`, `_ncontains`,
`_starts_with`, `_ends_with`, `_between`, `_nbetween`, plus `_and` and `_or`.

## Schema

```bash
curl -s "$DIRECTUS_API_URL/collections" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/collections/posts" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/fields" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/fields/job_openings" -H "Authorization: Bearer $DR_ADMIN"
```

## Users, roles and permissions

```bash
curl -s --get "$DIRECTUS_API_URL/users" \
  --data-urlencode 'filter={"status":{"_eq":"active"}}' -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/users/me" -H "Authorization: Bearer $DR_EDITOR"
curl -s "$DIRECTUS_API_URL/users/1d9f4a02-7b36-4c81-a5e0-92f7c103b846" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/roles" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/permissions" -H "Authorization: Bearer $DR_ADMIN"
```

## Files, activity, flows and settings

```bash
curl -s --get "$DIRECTUS_API_URL/files" --data-urlencode "access_token=$DR_EDITOR" \
  --data-urlencode 'filter={"type":{"_eq":"image/png"}}'
curl -s "$DIRECTUS_API_URL/files/3a7f92c1-6b04-4e58-9c31-8d70f2a5b6e9" -H "Authorization: Bearer $DR_ADMIN"
curl -s --get "$DIRECTUS_API_URL/activity" \
  --data-urlencode 'filter={"collection":{"_eq":"posts"}}' -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/flows" -H "Authorization: Bearer $DR_ADMIN"
curl -s "$DIRECTUS_API_URL/settings" -H "Authorization: Bearer $DR_ADMIN"
```
