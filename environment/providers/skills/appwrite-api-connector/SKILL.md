---
name: appwrite-api-connector
description: >
  Appwrite API (Mock) mock HTTP API. Base URL is provided via the
  `APPWRITE_API_URL` environment variable. 29 endpoint(s) across GET, POST, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Appwrite API (Mock)

Mock HTTP API. **All requests go to the base URL in `$APPWRITE_API_URL`.**
Appwrite's auth headers select the scope (any token is accepted; the documented
credentials are the canonical ones). Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `APPWRITE_API_URL` | Base URL for all requests (e.g. `http://appwrite-api:8104`) |

## Headers

| Header | Value | Effect |
|--------|-------|--------|
| `X-Appwrite-Project` | `orbit-app` | Required by `/v1` routes; a wrong value returns 404. Omitting it resolves to the seeded project |
| `X-Appwrite-Key` | `standard_9f3c1a7e5b2d4086af51c7e93b0d6248` | Server scope — bypasses permissions; required for databases, collections, buckets, functions and users |
| `X-Appwrite-Session` or `X-Appwrite-JWT` | `session_orbit_priya_9f3c1a7e` | Authenticates as `usr_priya_raman` |
| _(none)_ | | Guest — sees only rows granting `read("any")` |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/v1/health` |
| GET | `/v1/health/db` |
| GET | `/v1/health/storage` |
| GET | `/v1/locale` |
| GET | `/v1/project` |
| GET | `/v1/databases` |
| GET | `/v1/databases/{database_id}` |
| GET | `/v1/databases/{database_id}/collections` |
| GET | `/v1/databases/{database_id}/collections/{collection_id}` |
| GET | `/v1/databases/{database_id}/collections/{collection_id}/documents` |
| POST | `/v1/databases/{database_id}/collections/{collection_id}/documents` |
| GET | `/v1/databases/{database_id}/collections/{collection_id}/documents/{document_id}` |
| PATCH | `/v1/databases/{database_id}/collections/{collection_id}/documents/{document_id}` |
| DELETE | `/v1/databases/{database_id}/collections/{collection_id}/documents/{document_id}` |
| GET | `/v1/storage/buckets` |
| GET | `/v1/storage/buckets/{bucket_id}` |
| GET | `/v1/storage/buckets/{bucket_id}/files` |
| GET | `/v1/storage/buckets/{bucket_id}/files/{file_id}` |
| DELETE | `/v1/storage/buckets/{bucket_id}/files/{file_id}` |
| GET | `/v1/functions` |
| GET | `/v1/functions/{function_id}` |
| GET | `/v1/functions/{function_id}/executions` |
| POST | `/v1/functions/{function_id}/executions` |
| GET | `/v1/teams` |
| GET | `/v1/teams/{team_id}` |
| GET | `/v1/teams/{team_id}/memberships` |
| GET | `/v1/users` |
| GET | `/v1/users/{user_id}` |
| GET | `/v1/account` |

Database `orbit_app` holds the collections `feedback`, `feature_flags` and
`releases`. Buckets: `app_uploads`, `release_artifacts`. Functions:
`fn_aggregate_feedback`, `fn_notify_oncall`, `fn_flag_evaluator` (disabled).

## Queries

Pass the Query DSL as repeated `queries[]` parameters:
`equal("status", ["open"])`, `notEqual`, `lessThan`, `lessThanEqual`,
`greaterThan`, `greaterThanEqual`, `between`, `search`, `contains`,
`startsWith`, `endsWith`, `isNull`, `isNotNull`, `orderAsc`, `orderDesc`,
`limit`, `offset`, `cursorAfter`, `cursorBefore`, `select`. The default page
size is 25. `$id`, `$createdAt` and `$updatedAt` are valid query attributes.

## Usage

```bash
# GET example
curl -s --get "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  --data-urlencode 'queries[]=equal("platform", ["ios"])' \
  -H 'X-Appwrite-Project: orbit-app' \
  -H 'X-Appwrite-Key: standard_9f3c1a7e5b2d4086af51c7e93b0d6248'

# POST example
curl -s -X POST "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  -H 'Content-Type: application/json' -H 'X-Appwrite-Project: orbit-app' \
  -H 'X-Appwrite-Session: session_orbit_priya_9f3c1a7e' \
  -d '{"documentId": "unique()", "data": {}}'
```

The audit log of every call the agent makes is available at
`$APPWRITE_API_URL/audit/requests` (used for grading).
