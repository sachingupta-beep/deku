# Appwrite API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$APPWRITE_API_URL`.** Appwrite's auth headers select the scope (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `APPWRITE_API_URL` | Base URL for all requests |

Set the credentials once to follow the examples:

```bash
export AW_PROJECT='orbit-app'
export AW_KEY='standard_9f3c1a7e5b2d4086af51c7e93b0d6248'
export AW_SESSION='session_orbit_priya_9f3c1a7e'
```

## Health, locale and project

```bash
curl -s "$APPWRITE_API_URL/v1/health"
curl -s "$APPWRITE_API_URL/v1/health/db"
curl -s "$APPWRITE_API_URL/v1/health/storage"
curl -s "$APPWRITE_API_URL/v1/locale" -H "X-Appwrite-Project: $AW_PROJECT"
curl -s "$APPWRITE_API_URL/v1/project" -H "X-Appwrite-Project: $AW_PROJECT"
```

## Databases and collections

```bash
curl -s "$APPWRITE_API_URL/v1/databases" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/databases/orbit_app" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/databases/orbit_app/collections" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```

## Documents

```bash
curl -s "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"

curl -s --get "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  --data-urlencode 'queries[]=equal("platform", ["ios"])' \
  --data-urlencode 'queries[]=lessThan("rating", 4)' \
  --data-urlencode 'queries[]=orderDesc("$createdAt")' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"

curl -s --get "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feature_flags/documents" \
  --data-urlencode 'queries[]=contains("platforms", ["ios"])' \
  -H "X-Appwrite-Project: $AW_PROJECT"

curl -s "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents/fb_aurora_001" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"

curl -s -X POST "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  -H 'Content-Type: application/json' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION" \
  -d '{"documentId": "unique()", "data": {"rating": 4, "message": "Nice release.",
       "platform": "ios", "appVersion": "4.8.1", "status": "open", "userId": "usr_priya_raman"}}'

curl -s -X PATCH "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents/fb_lumen_003" \
  -H 'Content-Type: application/json' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY" \
  -d '{"data": {"status": "triaged"}}'

curl -s -X DELETE "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents/fb_pelagic_006" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```

Permission behaviour depends on the collection's `documentSecurity`: when true
the per-document ACL filters rows; when false the collection ACL gates the whole
request and a caller without it gets 401.

## Storage

```bash
curl -s "$APPWRITE_API_URL/v1/storage/buckets" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/storage/buckets/app_uploads" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/storage/buckets/app_uploads/files" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION"
curl -s "$APPWRITE_API_URL/v1/storage/buckets/release_artifacts/files/file_orbit_ios_481" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s -X DELETE "$APPWRITE_API_URL/v1/storage/buckets/app_uploads/files/file_offline_bug" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```

## Functions

```bash
curl -s "$APPWRITE_API_URL/v1/functions" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/functions/fn_aggregate_feedback" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s --get "$APPWRITE_API_URL/v1/functions/fn_aggregate_feedback/executions" \
  --data-urlencode 'queries[]=orderDesc("$createdAt")' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s -X POST "$APPWRITE_API_URL/v1/functions/fn_aggregate_feedback/executions" \
  -H 'Content-Type: application/json' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY" \
  -d '{"body": {"window": "7d"}, "async": false}'
```

## Teams, users and account

```bash
curl -s "$APPWRITE_API_URL/v1/teams" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION"
curl -s "$APPWRITE_API_URL/v1/teams/team_helix" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/teams/team_helix/memberships" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s --get "$APPWRITE_API_URL/v1/users" \
  --data-urlencode 'queries[]=equal("status", [true])' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/users/usr_marcus_feld" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
curl -s "$APPWRITE_API_URL/v1/account" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION"
```
