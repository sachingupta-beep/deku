# Zitadel Mock API — Test Results

Base URL: `http://localhost:8118` (in docker-compose: `http://zitadel-api:8118`)

## Endpoints covered

Every endpoint reads the organization from the `x-zitadel-orgid` header.

| Method | Path                                                    | Status          |
|--------|---------------------------------------------------------|-----------------|
| GET    | /health · /debug/healthz                                | 200             |
| GET    | /admin/v1/instance                                      | 200/401/403     |
| POST   | /admin/v1/orgs/_search                                  | 200/401/403     |
| POST   | /admin/v1/events/_search                                | 200/401/403     |
| GET    | /management/v1/orgs/me                                  | 200/400/403/404 |
| GET    | /management/v1/policies/login                           | 200/403/404     |
| POST   | /v2/users/human                                         | 201/400/403/409 |
| POST   | /v2/users/_search                                       | 200/403         |
| GET    | /v2/users/{id}                                          | 200/403/404     |
| PUT    | /v2/users/human/{id}                                    | 200/403/404/409 |
| DELETE | /v2/users/{id}                                          | 200/403/404     |
| POST   | /v2/users/{id}/email · /email/_verify                   | 200/400/403/404/409 |
| POST   | /v2/users/{id}/password · /password_reset               | 200/400/403/404 |
| POST   | /v2/users/{id}/deactivate · /reactivate · /lock · /unlock| 200/400/403/404 |
| GET    | /v2/users/{id}/authentication_factors                   | 200/403/404     |
| POST   | /v2/users/{id}/totp · /totp/_verify                     | 200/201/400/403/404/409 |
| DELETE | /v2/users/{id}/authentication_factors/{factorId}        | 200/403/404     |
| POST   | /v2/sessions                                            | 201/400/404     |
| GET    | /v2/sessions/{id}                                       | 200/400/403/404 |
| PATCH  | /v2/sessions/{id}                                       | 200/400/403/404 |
| DELETE | /v2/sessions/{id}                                       | 200/400/403/404 |
| POST   | /v2/sessions/_search                                    | 200/403         |
| GET    | /v2/oidc/auth_requests/{id}                             | 200/404         |
| POST   | /v2/oidc/auth_requests/{id}                             | 200/400/403/404 |
| POST   | /management/v1/projects · /_search                      | 200/201/403/409 |
| GET    | /management/v1/projects/{id}                            | 200/403/404     |
| POST   | /management/v1/projects/{id}/roles · /roles/_search      | 200/201/403/404/409 |
| POST   | /management/v1/users/grants/_search                     | 200/403         |
| POST   | /management/v1/users/{id}/grants                        | 201/400/403/404/409 |
| PUT/DELETE | /management/v1/users/{id}/grants/{grantId}          | 200/400/403/404 |
| POST   | /management/v1/orgs/me/members · /_search               | 200/201/400/403/409 |
| DELETE | /management/v1/orgs/me/members/{userId}                 | 200/400/403/404 |

Collection run: **PASS 62 / WARN 51 / FAIL 0 / SKIP 0**. Every WARN is an
intentional error-path request, labelled `(N expected)` in the collection.

## Sessions are built up factor by factor

This is the part of Zitadel that differs most from every other auth service in
the fleet, so the collection walks it explicitly:

| Request | Factors afterwards |
|---------|--------------------|
| `POST /v2/sessions` with `{"checks": {"user": {...}}}` | `user` |
| same call with `user` + `password` | `user`, `password` |
| same call with `user` + `password` + `totp` | `user`, `password`, `totp` |
| `PATCH /v2/sessions/{id}` with `{"checks": {"totp": {...}}}` | adds `totp` to whatever was there |

Each factor carries its own `verifiedAt`. A failing check aborts the whole
call — Zitadel does not partially apply a `checks` block. **Every update
rotates the session token**, so replaying the pre-rotation token is
`403 Invalid session token`; the collection asserts that too.

## The login policy is enforced at the end, not at the password prompt

`POST /v2/oidc/auth_requests/{id}` is where a session becomes an OIDC callback,
and where the org's login policy is checked:

| Session | Org | Result |
|---------|-----|--------|
| amelia, `user` + `password` only | orbit-labs (`forceMfa: true`) | **400** — *missing: a second factor* |
| helena, `user` + `webAuthN` | orbit-labs | **200** — passwordless satisfies it |
| priya, `user` + `password` only | orbit-partners (`forceMfa: false`) | **200** |

The same session shape succeeds in one org and is refused in the other. An auth
request can only be completed once; a second attempt is
`400 AUTH_REQUEST_STATE_SUCCEEDED`.

## Seed data summary

- **Organizations**: 3 — `Orbit Labs` (default, `forceMfa`), `Orbit Partners`
  (registration open, no forced MFA), `Orbit Archive` (**inactive**, so every
  request against it is `400 FAILED_PRECONDITION`)
- **Login policies**: one per org
- **Users**: 8 across two orgs
  - `amelia` — TOTP **and** U2F registered, `ORG_OWNER`
  - `jonas` — TOTP registered but `AUTH_FACTOR_STATE_NOT_READY`
  - `helena` — passkey registered, no TOTP
  - `rohit` — `USER_STATE_INITIAL`, **no password**; setting one activates him
  - `noor` — `USER_STATE_INACTIVE`
  - `dmitri` — `USER_STATE_LOCKED`
  - `orbit-ci` — a **machine** user, the one PATs are issued for
  - `priya` — in `Orbit Partners`
- **Auth factors**: 5 (TOTP ×3, U2F, passkey), one deliberately not ready
- **Sessions**: 6 — one full MFA, one password-only, one passwordless, one in
  the partner org, one **expired**, and a second password-only one for the
  forceMfa demonstration
- **Projects**: 3 with 6 roles; **user grants**: 6, one `INACTIVE`
- **Org members**: 4 · **PATs**: 5, one revoked
- **Auth requests**: 4, one already succeeded
- **Events**: 8 eventstore entries

Seed passwords: `amelia OrbitZitadel2026!`, `jonas OrbitJonas2026!`,
`helena OrbitHelena2026!`, `noor OrbitNoor2026!`, `dmitri OrbitDmitri2026!`,
`priya OrbitPriya2026!`. Rohit has none until one is set.

## Notes

- **Three distinct authorization refusals**: no usable token
  (`16 UNAUTHENTICATED`), a token for another org (`7 PERMISSION_DENIED`), and a
  read-only token attempting a write (`7 PERMISSION_DENIED` naming the role).
- **The session endpoints take no bearer** — the session token *is* the
  credential, which is why creating a session is unauthenticated and every
  subsequent call quotes the token the previous one returned.
- **Instance endpoints need `IAM_OWNER`**, not merely an org role; an org PAT
  gets 403 on `/admin/v1/instance` and `/admin/v1/orgs/_search`.
- **An inactive org is a precondition failure, not a 404** — it exists, it just
  cannot serve requests.
- Setting the first password on a `USER_STATE_INITIAL` user activates the
  account; changing a password drops every session that authenticated with one;
  deactivating or locking a user drops all of theirs.
- Password complexity (8 characters, upper case, digit, symbol) is enforced on
  create and on reset, each violation naming its own Zitadel error id.
- Grants are validated against the project's declared roles — granting a role
  the project does not define is `3 INVALID_ARGUMENT`.
- An org must keep at least one `ORG_OWNER`; removing the last one is refused.
- Because no mail is delivered, `set email` and `password_reset` return the code
  when the caller passes `returnCode`, and say so otherwise.
- Every write returns `details.sequence`, drawn from the same monotonic counter
  the event log uses, so a write's sequence and its event line up.
- Mutations (new users, sessions, grants, projects, members) are held in process
  memory and reset on container restart.
