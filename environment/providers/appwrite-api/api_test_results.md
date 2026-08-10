# Appwrite Mock API — Test Results

Base URL: `http://localhost:8104` (in docker-compose: `http://appwrite-api:8104`)

## Endpoints covered

| Method | Path                                                              | Status      |
|--------|-------------------------------------------------------------------|-------------|
| GET    | /health                                                           | 200         |
| GET    | /v1/health                                                        | 200         |
| GET    | /v1/health/db                                                     | 200         |
| GET    | /v1/health/storage                                                | 200         |
| GET    | /v1/locale                                                        | 200/404     |
| GET    | /v1/project                                                       | 200/404     |
| GET    | /v1/databases                                                     | 200/401/404 |
| GET    | /v1/databases/{databaseId}                                        | 200/401/404 |
| GET    | /v1/databases/{databaseId}/collections                            | 200/401/404 |
| GET    | /v1/databases/{databaseId}/collections/{collectionId}             | 200/401/404 |
| GET    | /v1/databases/{db}/collections/{col}/documents                    | 200/400/401/404 |
| POST   | /v1/databases/{db}/collections/{col}/documents                    | 201/400/401/404/409 |
| GET    | /v1/databases/{db}/collections/{col}/documents/{documentId}       | 200/401/404 |
| PATCH  | /v1/databases/{db}/collections/{col}/documents/{documentId}       | 200/400/401/404 |
| DELETE | /v1/databases/{db}/collections/{col}/documents/{documentId}       | 200/401/404 |
| GET    | /v1/storage/buckets                                               | 200/401/404 |
| GET    | /v1/storage/buckets/{bucketId}                                    | 200/401/404 |
| GET    | /v1/storage/buckets/{bucketId}/files                              | 200/401/404 |
| GET    | /v1/storage/buckets/{bucketId}/files/{fileId}                     | 200/401/404 |
| DELETE | /v1/storage/buckets/{bucketId}/files/{fileId}                     | 200/401/404 |
| GET    | /v1/functions                                                     | 200/401/404 |
| GET    | /v1/functions/{functionId}                                        | 200/401/404 |
| GET    | /v1/functions/{functionId}/executions                             | 200/401/404 |
| POST   | /v1/functions/{functionId}/executions                             | 201/400/401/404 |
| GET    | /v1/teams                                                         | 200/401/404 |
| GET    | /v1/teams/{teamId}                                                | 200/401/404 |
| GET    | /v1/teams/{teamId}/memberships                                    | 200/401/404 |
| GET    | /v1/users                                                         | 200/401/404 |
| GET    | /v1/users/{userId}                                                | 200/401/404 |
| GET    | /v1/account                                                       | 200/401/404 |

Collection run: **PASS 39 / WARN 12 / FAIL 0 / SKIP 0**. All twelve WARNs are the
intentional error-path requests (wrong project, six permission denials, unknown
collection, unreadable document, missing file, two validation failures, and a
disabled function).

## Seed data summary

- Project: `orbit-app`, Appwrite 1.6.0, self-hosted, three platforms registered
- Database: 1 (`orbit_app`) with 3 collections
  - `feedback` — 6 documents, `documentSecurity: true`, per-document ACLs
  - `feature_flags` — 4 documents, `documentSecurity: false`, collection ACL `read("any")`
  - `releases` — 5 documents, `documentSecurity: false`, collection ACL `read("users")`
- Users: 6 customer-side app users, one blocked (`usr_tobias_krause`)
- Teams: 3 (`team_aurora`, `team_helix`, `team_lumen`) with 6 memberships, one unconfirmed
- Storage: 2 buckets — `app_uploads` (`fileSecurity: true`) and `release_artifacts`
  (`fileSecurity: false`, `read("team:team_helix")`) — with 5 files
- Functions: 3 (one disabled) with 4 seeded executions, one of them failed

## Scopes and permissions

| Header | Scope | Sees |
|--------|-------|------|
| none | `guest` | Only rows granting `read("any")` |
| `X-Appwrite-Session` or `X-Appwrite-JWT` | `session` as `usr_priya_raman` | Adds `read("users")`, `read("user:usr_priya_raman")` and `read("team:team_aurora")` |
| `X-Appwrite-Key` | `server` | Everything; required for databases, collections, buckets, functions and users |

`X-Appwrite-Project` must be `orbit-app` when supplied; a wrong value returns 404
`project_not_found`. Omitting it resolves to the seeded project, so read-only
exploration works without any headers.

The same document list under three identities returns three different results —
guest 1 of 6, session user 2 of 6, server key 6 of 6 — which makes the
permission model directly observable in a benchmark run.

## Notes

- Documents carry Appwrite's system attributes: `$id`, `$collectionId`,
  `$databaseId`, `$createdAt`, `$updatedAt`, `$permissions`. Other resources
  carry `$id`, `$createdAt`, `$updatedAt`.
- List responses use the `{"total": n, "<resource>": [...]}` envelope, where the
  key is the resource name (`documents`, `files`, `teams`, `users`, …).
- `queries[]` accepts the Appwrite Query DSL as strings: `equal("status", ["open"])`,
  `notEqual`, `lessThan`, `lessThanEqual`, `greaterThan`, `greaterThanEqual`,
  `between`, `search`, `contains`, `startsWith`, `endsWith`, `isNull`, `isNotNull`,
  `orderAsc`, `orderDesc`, `limit`, `offset`, `cursorAfter`, `cursorBefore`,
  `select`. `$id`, `$createdAt` and `$updatedAt` are valid query attributes.
  The default page size is 25, matching Appwrite.
- **Document security decides how a denial is reported.** With
  `documentSecurity: true` the per-document ACL filters rows, so an unreadable
  document is simply absent (and 404 when fetched by id). With
  `documentSecurity: false` the collection ACL gates the whole request, so a
  caller without it gets 401 `general_unauthorized_scope` rather than an empty
  list. Buckets behave the same way through `fileSecurity`.
- `POST .../documents` takes Appwrite's `{documentId, data, permissions}` body;
  `documentId: "unique()"` generates a 20-character id. Missing required
  attributes and unknown attributes both return 400 `document_invalid_structure`.
- `POST .../executions` runs the function synchronously and records the
  execution; `"async": true` records a `waiting` execution instead. Executing a
  disabled function returns 400.
- Teams are scoped to membership: the session user sees only `team_aurora`, and
  requesting a team they do not belong to returns 404 `team_not_found`.
- `GET /v1/project` strips the `credentials` block that the mock uses internally
  to resolve scopes; the credentials are documented above and in the connector skill.
- Mutations (created/updated/deleted documents, deleted files, executions) are
  held in process memory and reset on container restart.
