# Appwrite Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$APPWRITE_API_URL`; responses are verbatim (long arrays elided
with `…`). The examples assume:

```bash
export AW_PROJECT='orbit-app'
export AW_KEY='standard_9f3c1a7e5b2d4086af51c7e93b0d6248'
export AW_SESSION='session_orbit_priya_9f3c1a7e'
```

## Health and locale

```bash
curl -s "$APPWRITE_API_URL/health"
curl -s "$APPWRITE_API_URL/v1/health/db"
curl -s "$APPWRITE_API_URL/v1/locale" -H "X-Appwrite-Project: $AW_PROJECT"
```
```json
{"status": "ok"}
{"name": "database", "ping": 3, "status": "pass"}
{"ip": "203.0.113.41", "countryCode": "US", "country": "United States",
 "continentCode": "NA", "continent": "North America", "eu": false, "currency": "USD"}
```

A wrong `X-Appwrite-Project` returns 404 on every `/v1` route:

```json
{"message": "Project with the requested ID could not be found. Please check the value of the X-Appwrite-Project header to ensure the correct project ID is being used.",
 "code": 404, "type": "project_not_found", "version": "1.6.0"}
```

## Databases and collections

Server-key scope is required for the schema endpoints.

```bash
curl -s "$APPWRITE_API_URL/v1/databases" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```
```json
{"total": 1, "databases": [{"$id": "orbit_app", "name": "Orbit App", "enabled": true,
 "$createdAt": "2024-09-10T09:00:00.000+00:00", "$updatedAt": "2026-04-11T08:30:00.000+00:00"}]}
```

Without the key the same request is refused:

```json
{"message": "app.current-user is missing scope (databases.read)", "code": 401,
 "type": "general_unauthorized_scope", "version": "1.6.0"}
```

```bash
curl -s "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```
```json
{"$id": "feedback", "databaseId": "orbit_app", "name": "Feedback", "enabled": true,
 "documentSecurity": true, "$permissions": ["create(\"users\")"],
 "attributes": [{"key": "rating", "type": "integer", "array": false, "required": true, "status": "available"},
                {"key": "message", "type": "string", "array": false, "required": true, "status": "available"}, "…"],
 "indexes": [{"key": "idx_status", "type": "key", "attributes": ["status"], "orders": ["ASC"], "status": "available"}, "…"]}
```

## Permissions: one query, three identities

`feedback` has `documentSecurity: true`, so per-document ACLs filter the result.

```bash
# guest — only read("any")
curl -s "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  -H "X-Appwrite-Project: $AW_PROJECT"
# -> {"total": 1, ...}   fb_verdant_005

# session user usr_priya_raman — adds her own row and team_aurora's
curl -s "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION"
# -> {"total": 2, ...}   fb_aurora_001, fb_verdant_005

# server key — bypasses permissions
curl -s "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
# -> {"total": 6, ...}
```

`releases` has `documentSecurity: false` and a collection ACL of `read("users")`,
so the collection permission gates the whole request instead of filtering rows —
a guest gets 401, not an empty list:

```json
{"message": "app.current-user is missing scope (collection.read)", "code": 401,
 "type": "general_unauthorized_scope", "version": "1.6.0"}
```

## Query DSL

```bash
curl -s --get "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  --data-urlencode 'queries[]=equal("platform", ["ios"])' \
  --data-urlencode 'queries[]=lessThan("rating", 4)' \
  --data-urlencode 'queries[]=select(["message","rating","platform"])' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```
```json
{"total": 3, "documents": [
  {"$id": "fb_aurora_001", "$collectionId": "feedback", "$databaseId": "orbit_app",
   "$permissions": ["read(\"user:usr_priya_raman\")", "read(\"team:team_aurora\")", "update(\"user:usr_priya_raman\")"],
   "rating": 2, "message": "Sign-in hangs for about four seconds every morning. Started this week.",
   "platform": "ios"}, "…"]}
```

```bash
curl -s --get "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  --data-urlencode 'queries[]=search("message", "dark mode")' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
# -> total 1: fb_lumen_003

curl -s --get "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feature_flags/documents" \
  --data-urlencode 'queries[]=contains("platforms", ["ios"])' \
  --data-urlencode 'queries[]=select(["key","platforms","rolloutPercent"])' \
  -H "X-Appwrite-Project: $AW_PROJECT"
```
```json
{"total": 3, "documents": [
  {"$id": "flag_offline_queue", "$collectionId": "feature_flags", "$databaseId": "orbit_app",
   "$permissions": ["read(\"any\")"], "key": "offline_queue",
   "rolloutPercent": 100, "platforms": ["ios", "android"]}, "…"]}
```

```bash
curl -s --get "$APPWRITE_API_URL/v1/databases/orbit_app/collections/releases/documents" \
  --data-urlencode 'queries[]=isNull("releasedAt")' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION"
# -> total 1: rel_ios_4_9_0_beta (still in testing)
```

## Documents: create, update, delete

```bash
curl -s -X POST "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents" \
  -H 'Content-Type: application/json' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION" \
  -d '{"documentId": "unique()",
       "data": {"rating": 4, "message": "Passkey sign-in in the beta build works well on iOS.",
                "platform": "ios", "appVersion": "4.9.0-beta.2", "status": "open",
                "userId": "usr_priya_raman"},
       "permissions": ["read(\"user:usr_priya_raman\")", "read(\"team:team_aurora\")"]}'
```
```json
{"$id": "598ddc2edea34f1c8563", "$collectionId": "feedback", "$databaseId": "orbit_app",
 "$permissions": ["read(\"user:usr_priya_raman\")", "read(\"team:team_aurora\")"],
 "rating": 4, "message": "Passkey sign-in in the beta build works well on iOS.",
 "platform": "ios", "appVersion": "4.9.0-beta.2", "status": "open",
 "userId": "usr_priya_raman", "screenshotId": "", "$createdAt": "…", "$updatedAt": "…"}
```

```bash
curl -s -X PATCH "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents/fb_lumen_003" \
  -H 'Content-Type: application/json' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY" \
  -d '{"data": {"status": "triaged"}}'

curl -s -X DELETE "$APPWRITE_API_URL/v1/databases/orbit_app/collections/feedback/documents/fb_pelagic_006" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```
```json
{"$id": "fb_lumen_003", "status": "triaged", "$updatedAt": "…", "…": "…"}
{"deleted": "fb_pelagic_006"}
```

## Error paths

| Request | Status | Body |
|---------|--------|------|
| `data` missing a required attribute | 400 | `{"type": "document_invalid_structure", "message": "Invalid document structure: Missing required attribute \"message\""}` |
| `data` with an undeclared attribute | 400 | `{"type": "document_invalid_structure", "message": "Invalid document structure: Unknown attribute: \"sentiment\""}` |
| Create as guest (`create("users")` rule) | 401 | `{"type": "general_unauthorized_scope", "message": "app.current-user is missing scope (documents.write)"}` |
| `GET .../documents/fb_aurora_001` as guest | 404 | `{"type": "document_not_found", "message": "Document with the requested ID could not be found."}` |
| `GET /v1/teams/team_helix` as Priya | 404 | `{"type": "team_not_found", "message": "Team with the requested ID could not be found."}` |
| Execute the disabled `fn_flag_evaluator` | 400 | `{"type": "function_not_found", "message": "Function is not enabled and cannot be executed."}` |

## Storage

`app_uploads` has `fileSecurity: true`, so files filter per identity; guests see
one file, the session user sees two, the server key sees three.

```bash
curl -s "$APPWRITE_API_URL/v1/storage/buckets/app_uploads/files" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION"
```
```json
{"total": 2, "files": [
  {"$id": "file_signin_lag", "bucketId": "app_uploads", "name": "signin-lag-2026-05-26.png",
   "$permissions": ["read(\"user:usr_priya_raman\")", "read(\"team:team_aurora\")"],
   "signature": "9d3f01a6c47b5e28", "mimeType": "image/png", "sizeOriginal": 184320,
   "chunksTotal": 1, "chunksUploaded": 1, "$createdAt": "2026-05-26T07:12:04.000+00:00"}, "…"]}
```

```bash
curl -s "$APPWRITE_API_URL/v1/storage/buckets/release_artifacts/files/file_orbit_ios_481" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```
```json
{"$id": "file_orbit_ios_481", "bucketId": "release_artifacts", "name": "orbit-4.8.1.ipa",
 "$permissions": ["read(\"team:team_helix\")"], "signature": "b58e1f70c3aa2d61",
 "mimeType": "application/octet-stream", "sizeOriginal": 78643200,
 "chunksTotal": 15, "chunksUploaded": 15}
```

## Functions

```bash
curl -s --get "$APPWRITE_API_URL/v1/functions/fn_aggregate_feedback/executions" \
  --data-urlencode 'queries[]=orderDesc("$createdAt")' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```
```json
{"total": 2, "executions": [
  {"$id": "exec_agg_9f21", "functionId": "fn_aggregate_feedback", "trigger": "schedule",
   "status": "completed", "responseStatusCode": 200,
   "responseBody": "{\"open\":2,\"triaged\":1,\"escalated\":1,\"closed\":2,\"averageRating\":3.33}",
   "duration": 0.842, "logs": "Aggregated 6 feedback documents.",
   "$createdAt": "2026-05-26T08:00:01.000+00:00"}, "…"]}
```

`fn_aggregate_feedback` computes its result from the live `feedback` table, so
the response reflects any documents created earlier in the run:

```bash
curl -s -X POST "$APPWRITE_API_URL/v1/functions/fn_aggregate_feedback/executions" \
  -H 'Content-Type: application/json' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY" \
  -d '{"body": {"window": "7d"}, "path": "/", "method": "POST", "async": false}'
```
```json
{"$id": "exec_…", "functionId": "fn_aggregate_feedback", "trigger": "http",
 "status": "completed", "requestMethod": "POST", "requestPath": "/",
 "responseStatusCode": 200,
 "responseBody": "{\"triaged\": 1, \"closed\": 2, \"open\": 2, \"escalated\": 1, \"total\": 6, \"averageRating\": 3.33}",
 "duration": 0.412, "logs": "Executed Aggregate Feedback."}
```

## Teams, users, account

```bash
curl -s "$APPWRITE_API_URL/v1/teams" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION"
```
```json
{"total": 1, "teams": [{"$id": "team_aurora", "name": "Aurora Bistro", "total": 2,
 "prefs": {"plan": "starter"}, "$createdAt": "2025-03-04T10:25:00.000+00:00"}]}
```

```bash
curl -s "$APPWRITE_API_URL/v1/teams/team_helix/memberships" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"
```
```json
{"total": 2, "memberships": [
  {"$id": "mem_helix_marcus", "teamId": "team_helix", "teamName": "Helix Robotics",
   "userId": "usr_marcus_feld", "userName": "Marcus Feld", "roles": ["owner"],
   "confirm": true, "joined": "2024-09-12T08:14:00.000+00:00"},
  {"$id": "mem_helix_daniel", "roles": ["member", "billing"], "…": "…"}]}
```

```bash
curl -s --get "$APPWRITE_API_URL/v1/users" \
  --data-urlencode 'queries[]=equal("status", [true])' \
  --data-urlencode 'queries[]=orderAsc("name")' --data-urlencode 'queries[]=limit(5)' \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Key: $AW_KEY"

curl -s "$APPWRITE_API_URL/v1/account" \
  -H "X-Appwrite-Project: $AW_PROJECT" -H "X-Appwrite-Session: $AW_SESSION"
```
```json
{"total": 5, "users": [{"$id": "usr_daniel_osei", "name": "Daniel Osei", "…": "…"}, "…"]}
{"$id": "usr_priya_raman", "name": "Priya Raman", "email": "priya.raman@aurorabistro.com",
 "emailVerification": true, "status": true, "labels": ["customer", "beta"],
 "prefs": {"theme": "dark", "locale": "en-US"}}
```

Blocked users (`status: false`) are excluded by `equal("status", [true])` — that
is why the list returns 5 of 6. `GET /v1/account` without a session returns 401.
