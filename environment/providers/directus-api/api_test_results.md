# Directus Mock API — Test Results

Base URL: `http://localhost:8105` (in docker-compose: `http://directus-api:8105`)

## Endpoints covered

| Method | Path                              | Status      |
|--------|-----------------------------------|-------------|
| GET    | /health                           | 200         |
| GET    | /server/ping                      | 200         |
| GET    | /server/health                    | 200         |
| GET    | /server/info                      | 200         |
| POST   | /auth/login                       | 200/401     |
| GET    | /items/{collection}               | 200/400/403 |
| POST   | /items/{collection}               | 200/400/403 |
| GET    | /items/{collection}/{id}          | 200/403     |
| PATCH  | /items/{collection}/{id}          | 200/400/403 |
| DELETE | /items/{collection}/{id}          | 204/403     |
| GET    | /collections                      | 200/403     |
| GET    | /collections/{collection}         | 200/403     |
| GET    | /fields                           | 200/403     |
| GET    | /fields/{collection}              | 200/403     |
| GET    | /users                            | 200/400/403 |
| GET    | /users/me                         | 200/401     |
| GET    | /users/{id}                       | 200/403     |
| GET    | /roles                            | 200/403     |
| GET    | /roles/{id}                       | 200/403     |
| GET    | /permissions                      | 200/403     |
| GET    | /files                            | 200/400/403 |
| GET    | /files/{id}                       | 200/403     |
| GET    | /activity                         | 200/400/403 |
| GET    | /flows                            | 200/403     |
| GET    | /settings                         | 200/403     |

Collection run: **PASS 34 / WARN 11 / FAIL 0 / SKIP 0**. All eleven WARNs are the
intentional error-path requests (bad credentials, six permission denials, an
invisible draft, a missing item, an unknown collection, and two payload failures).

## Seed data summary

- Collections: `posts` (8), `categories` (4), `job_openings` (4), plus 33 field
  definitions across the three
- Users: 4 (`directus_users`) — one Administrator, three Editors, one of them suspended
- Roles: 3 — Administrator (`admin_access`), Editor, Public
- Permissions: 9 rows mapping (role, collection, action) onto a filter
- Files: 4 (`directus_files`), Activity: 6 entries, Flows: 3 (one inactive)
- Settings: singleton from `settings.json` (Directus 11.1.1 on Postgres 15.6)

## Roles and permissions

Access control is **data-driven from `permissions.json`**, exactly as Directus
stores it, so drifting a permission row changes what the API returns:

| Role | posts | categories | job_openings | directus_files |
|------|-------|------------|--------------|----------------|
| Public | read where `status = published` | read | read where `status = open` | — |
| Editor | read all; create; update where `status != archived` | read | read all | read |
| Administrator | `admin_access` bypasses the table entirely | | | |

Tokens (static, as Directus supports them):

| Token | Role |
|-------|------|
| absent | Public |
| `dr_static_editor_2b90d7fc1e6a4830`, or any other token | Editor |
| `dr_static_admin_4f81c6a930b7e254` | Administrator |

Pass a token as `Authorization: Bearer <token>` **or** as an `access_token`
query parameter. `POST /auth/login` with `noor.aziz@orbit-labs.com` /
`OrbitContent2026!` mints a session token that behaves like the editor token.

The same `GET /items/posts` returns 5 rows as Public and 8 as Editor;
`GET /items/job_openings` returns 2 as Public and 4 as Editor.

## Notes

- Responses are wrapped in `{"data": ...}`. `meta=*` (or
  `meta=total_count,filter_count`) adds a `meta` object where `total_count` is
  what the role may read and `filter_count` applies the query on top.
- `filter` takes Directus filter JSON with `_eq`, `_neq`, `_lt`, `_lte`, `_gt`,
  `_gte`, `_in`, `_nin`, `_null`, `_nnull`, `_empty`, `_nempty`, `_contains`,
  `_icontains`, `_ncontains`, `_starts_with`, `_ends_with`, `_between`,
  `_nbetween`, and the logical `_and` / `_or`. Relational filters nest one level:
  `{"category":{"slug":{"_eq":"security"}}}`.
- `fields` supports `*`, an explicit list, relational dot-notation
  (`category.name`, `author.first_name`, `image.filename_download`) and `*.*`
  to expand every relation one level.
- `sort=-publish_date,title`, `search=`, `limit`/`offset`/`page` behave as in
  Directus; `limit=-1` returns everything.
- `aggregate={"count":"*","sum":"hits"}` with `groupBy=status` returns one row
  per group. `count`, `sum`, `avg`, `min` and `max` are supported.
- **Directus answers 403 `FORBIDDEN` for anything the caller may not see —
  including items that do not exist.** That is deliberate upstream behaviour so
  the API never leaks record existence, and it is reproduced here: `GET
  /items/posts/999` with an admin token is a 403, not a 404.
- `DELETE /items/{collection}/{id}` returns 204 with an empty body.
- Field-level permissions are honoured: the Public role's `posts` permission
  lists explicit fields, so `date_created`, `date_updated` and `user_created`
  are absent from public responses.
- `GET /settings` strips the `tokens` block the mock uses to resolve identities;
  the tokens are documented above and in the connector skill.
- Mutations (created/updated/deleted items, login sessions) are held in process
  memory and reset on container restart.
