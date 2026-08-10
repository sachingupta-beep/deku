# SuperTokens Core Mock API — Test Results

Base URL: `http://localhost:8115` (in docker-compose: `http://supertokens-api:8115`)

## Endpoints covered

Every recipe path is also served under `/appid-{appId}/{tenantId}/...`; the bare
form resolves to the `public` tenant.

| Method | Path                                           | HTTP        |
|--------|------------------------------------------------|-------------|
| GET    | /health                                        | 200         |
| GET    | /hello                                         | 200         |
| GET    | /apiversion                                    | 200         |
| GET    | /config                                        | 200/401     |
| GET    | /recipe/jwt/jwks                               | 200         |
| POST   | /recipe/signup                                 | 200/400/404 |
| POST   | /recipe/signin                                 | 200/400/404 |
| GET    | /recipe/user                                   | 200/401/404 |
| PUT    | /recipe/user                                   | 200/401/404 |
| POST   | /recipe/user/password/reset/token              | 200/400/404 |
| POST   | /recipe/user/password/reset                    | 200/400/404 |
| POST   | /recipe/signinup                               | 200/400/404 |
| POST   | /recipe/signinup/code                          | 200/400/404 |
| POST   | /recipe/signinup/code/consume                  | 200/400/404 |
| POST   | /recipe/session                                | 200/400/404 |
| POST   | /recipe/session/verify                         | 200/401     |
| POST   | /recipe/session/refresh                        | 200/401     |
| POST   | /recipe/session/remove                         | 200/400/401 |
| GET    | /recipe/session/user                           | 200/401/404 |
| GET/PUT| /recipe/session/data                           | 200/401     |
| POST   | /recipe/user/email/verify/token                | 200/401/404 |
| POST   | /recipe/user/email/verify                      | 200/400/404 |
| GET    | /recipe/user/email/verify                      | 200/401     |
| GET/PUT| /recipe/user/metadata                          | 200/400/401 |
| POST   | /recipe/user/metadata/remove                   | 200/401     |
| PUT    | /recipe/role                                   | 200/400/401 |
| GET    | /recipe/roles                                  | 200/401     |
| GET    | /recipe/role/permissions                       | 200/401     |
| POST   | /recipe/role/remove                            | 200/401     |
| PUT    | /recipe/user/role                              | 200/401/404 |
| GET    | /recipe/user/roles                             | 200/401/404 |
| POST   | /recipe/user/role/remove                       | 200/401/404 |
| GET    | /recipe/role/users                             | 200/401/404 |
| GET    | /recipe/multitenancy/tenant/list                | 200/401     |
| GET    | /appid-{appId}/{tenantId}/recipe/multitenancy/tenant | 200/401/404 |
| PUT    | /recipe/multitenancy/tenant                    | 200/400/401 |
| POST   | /recipe/multitenancy/tenant/remove             | 200/401/403 |
| POST   | /recipe/multitenancy/tenant/user               | 200/401/404 |
| POST   | /recipe/accountlinking/user/primary            | 200/401     |
| POST   | /recipe/accountlinking/user/link               | 200/401     |
| POST   | /recipe/accountlinking/user/unlink             | 200/401     |
| GET    | /users                                         | 200/400/401/404 |
| GET    | /users/count                                   | 200/401/404 |
| GET    | /user/id                                       | 200/401     |
| POST   | /user/remove                                   | 200/401     |

Collection run: **PASS 102 / WARN 13 / FAIL 0 / SKIP 0**.

The WARN count is low on purpose, and it is not a coverage gap. **The core
reports domain outcomes in the body with HTTP 200**, so 34 distinct error
statuses in this collection — `WRONG_CREDENTIALS_ERROR`, `TOKEN_THEFT_DETECTED`,
`UNKNOWN_ROLE_ERROR`, `RESTART_FLOW_ERROR` and the rest — are exercised as PASS
rows whose bodies carry the failure. Those requests are named after the status
they assert. The 13 WARNs are the only non-2xx paths the core has:

| HTTP | Cause |
|------|-------|
| 401 | missing or wrong `api-key` |
| 400 | unsupported `cdi-version`, or a malformed body (missing `password`, `thirdPartyUserId`, `userId`, no contact for a passwordless code, an unsupported `method`) |
| 404 | unknown tenant in the path |
| 403 | deleting the `public` tenant |

## Seed data summary

- Tenants: 2
  - `public` — emailpassword **on**, thirdparty **on** (`github`, `google`),
    passwordless **off**; first factors `emailpassword`, `thirdparty`
  - `orbit-enterprise` — emailpassword **off**, thirdparty **on** (`okta`),
    passwordless **on** (`EMAIL`, `USER_INPUT_CODE_AND_MAGIC_LINK`); requires a
    `totp` secondary factor
- Users: 6, with 7 login methods across three recipes
  - **amelia** — `isPrimaryUser`, with an `emailpassword` *and* a linked
    `thirdparty` (github) login method under one user id
  - **jonas** — emailpassword; two live sessions, one of which has a **spent**
    refresh token in its chain
  - **helena** — thirdparty (github) only
  - **rohit** — emailpassword, **email not verified**
  - **noor** — passwordless, on `orbit-enterprise` only
  - **sync bot** — emailpassword service account
- Sessions: 5 live, with fixed access/refresh/anti-CSRF tokens
- Refresh tokens: 6, including one already-rotated token for the theft path
- Password reset tokens: 2 (one unused, one **spent**)
- Email verification tokens: 1 (unused, for rohit)
- Passwordless devices/codes: 2 (one open, one **expired**, one with 2 failed
  attempts already recorded)
- Roles: 5 (`owner`, `engineer`, `support`, `service`, `viewer`) with
  permissions; 6 user-role grants across both tenants
- User metadata: 5 records

Seed passwords: `amelia OrbitSuperTokens2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `sync-bot OrbitSyncBot2026!`. Helena and Noor have no
password — their recipes don't have one.

## Notes

- **No account enumeration.** An unknown email and a wrong password both return
  `WRONG_CREDENTIALS_ERROR`.
- **Tenant isolation is real.** `signin` on `orbit-enterprise` returns
  `EMAIL_PASSWORD_NOT_ENABLED_ERROR` even for a user who exists, and creating a
  passwordless code on `public` returns `PASSWORDLESS_NOT_ENABLED_ERROR`.
  Associating a user with a second tenant does not turn a disabled recipe on.
- **Token theft detection.** Refresh tokens rotate; replaying one that has
  already been rotated returns `TOKEN_THEFT_DETECTED` with the victim's
  `session.handle` and `userId`, and revokes the session. The collection verifies
  the same access token before and after to show it die.
- **Anti-CSRF** failures return `TRY_REFRESH_TOKEN`, distinct from a token that
  does not exist (`UNAUTHORISED`).
- **Passwordless codes** count failed attempts on the device; five wrong guesses
  burns the device and subsequent calls return `RESTART_FLOW_ERROR`.
- **Account linking** folds a recipe user into a primary user: the absorbed id
  stops resolving as a user of its own, and the primary user's `emails` and
  `loginMethods` grow. Unlinking gives it back its own user row.
- **User metadata is a shallow merge**, and a `null` value clears that key.
- Changing a password — directly or through a reset token — revokes every
  session the recipe user holds.
- `GET /recipe/user` serves three recipes on one path. A backend SDK reaches it
  through its own recipe router, so add `recipeId=passwordless` or
  `recipeId=thirdparty` to disambiguate here; an email alone means emailpassword.
- Mutations (new users, rotated tokens, revoked sessions, role grants, tenants)
  are held in process memory and reset on container restart.
