# Logto Mock API — Test Results

Base URL: `http://localhost:8116` (in docker-compose: `http://logto-api:8116`)

## Endpoints covered

### OIDC plane

| Method | Path                                     | Status      |
|--------|------------------------------------------|-------------|
| GET    | /oidc/.well-known/openid-configuration   | 200         |
| GET    | /oidc/jwks                               | 200         |
| GET    | /oidc/auth                               | 200/400     |
| POST   | /oidc/token                              | 200/400/401 |
| POST   | /oidc/token/introspection                | 200         |
| POST   | /oidc/token/revocation                   | 200         |
| GET    | /oidc/me                                 | 200/401/403 |

### Management API

| Method | Path                                             | Status              |
|--------|--------------------------------------------------|---------------------|
| GET    | /api/status                                      | 200                 |
| GET    | /api/users                                       | 200/401/403         |
| POST   | /api/users                                       | 201/401/403/422     |
| GET    | /api/users/{id}                                  | 200/401/403/404     |
| PATCH  | /api/users/{id}                                  | 200/403/404/422     |
| DELETE | /api/users/{id}                                  | 204/403/404         |
| PATCH  | /api/users/{id}/password                         | 200/403/404/422     |
| POST   | /api/users/{id}/password/verify                  | 204/403/404/422     |
| PATCH  | /api/users/{id}/is-suspended                     | 200/403/404/422     |
| GET/PATCH | /api/users/{id}/custom-data                   | 200/403/404         |
| GET    | /api/users/{id}/identities                       | 200/403/404         |
| DELETE | /api/users/{id}/identities/{target}              | 204/403/404/422     |
| GET/POST | /api/users/{id}/roles                          | 200/201/403/404/422 |
| DELETE | /api/users/{id}/roles/{roleId}                   | 204/403/404         |
| GET    | /api/users/{id}/organizations                    | 200/403/404         |
| GET/POST | /api/roles                                     | 200/201/403/422     |
| GET/DELETE | /api/roles/{id}                              | 200/204/403/404     |
| GET/POST | /api/applications                              | 200/201/403/422     |
| GET/DELETE | /api/applications/{id}                       | 200/204/403/404/422 |
| GET    | /api/resources · /api/resources/{id}/scopes      | 200/403/404         |
| GET/POST | /api/organizations                             | 200/201/403/422     |
| GET/DELETE | /api/organizations/{id}                      | 200/204/403/404     |
| GET/POST | /api/organizations/{id}/users                  | 200/201/403/404     |
| DELETE | /api/organizations/{id}/users/{userId}           | 204/403/404         |
| POST   | /api/organizations/{id}/users/{userId}/roles     | 201/403/404         |
| GET    | /api/organization-roles · /api/organization-scopes | 200/403           |
| GET    | /api/my-organization                             | 200/401/403         |
| GET    | /api/connectors · /api/connectors/{id}           | 200/403/404         |
| GET/PATCH | /api/sign-in-exp                              | 200/403             |
| GET    | /api/logs · /api/logs/{id}                       | 200/403/404         |
| GET    | /api/dashboard/users/total                       | 200/403             |

Collection run: **PASS 71 / WARN 53 / FAIL 0 / SKIP 0**. Every WARN is an
intentional error-path request, labelled `(N expected)` in the collection. The
count is high because an OIDC authorization server is mostly defined by what it
refuses, and the collection exercises each refusal explicitly.

## The Management API gate

The collection sends the **same** `GET /api/users` with four different bearers.
All four are legitimate tokens; they get four different answers, and that is the
central behaviour of this service:

| Token | Audience | Result |
|-------|----------|--------|
| `logto_at_ci_full_9f14c73e0b2a` | Management API, scope `all` | **200** |
| `logto_at_reporting_ro_5b07d21f8c64` | Management API, scope `read:user` | **200** on reads, **403 `auth.insufficient_scope`** on writes |
| `logto_at_amelia_status_c8e05a1976b3` | Orbit Status API | **403 `auth.forbidden`** — right token, wrong audience |
| `logto_at_amelia_org_platform_7a63f04c9e21` | `urn:logto:organization:org5platform1` | **403 `auth.forbidden`** |
| _(none)_, or a revoked token | — | **401 `auth.authorization_header_missing`** |

The organization token is not useless — it reaches `GET /api/my-organization`,
which the Management API token is in turn refused from.

## Seed data summary

- **Applications**: 6 — an SPA, a Traditional web app, a Native app, two
  MachineToMachine apps (`Orbit CI Pipeline` with `all`, `Orbit Reporting Job`
  with `read:user`) and a third-party partner app. Public clients (`SPA`,
  `Native`) carry no client secret and **must** use PKCE.
- **API resources**: 3 — the Management API (`https://default.logto.app/api`),
  the Orbit Status API and the Orbit Billing API, with 7 scopes between them.
- **Users**: 6 — amelia (admin, github + google identities), jonas (operator),
  helena (**social-only, no password**), rohit (viewer), noor (**suspended**),
  the sync bot (bound to the CI app).
- **Roles**: 5 with scope assignments; roles are typed `User` or
  `MachineToMachine`, and an app's client-credentials scopes come from its
  machine roles.
- **Organizations**: 2 (`Orbit Platform`, MFA required; `Acme Partner`) with
  3 organization roles, 4 organization scopes and 5 memberships.
- **Tokens**: 6 access tokens (one revoked), 3 refresh tokens (one revoked),
  2 authorization codes (one already used).
- **Connectors**: 4 (GitHub, Google, SMTP enabled; Twilio SMS disabled).
- **Logs**: 8 entries across sign-in, register and token-exchange keys.
- Singletons: `sign_in_experience.json` (branding, MFA policy, password policy)
  and `oidc_config.json`.

Seed passwords: `amelia OrbitLogto2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `noor OrbitNoor2026!`,
`orbit_sync_bot OrbitSyncBot2026!`. Helena has none.

## Notes

- **PKCE is enforced.** A `SPA` or `Native` client that omits `code_challenge`
  is refused at the authorization endpoint, and a code minted with a challenge
  cannot be exchanged without the matching verifier.
- **Authorization codes are single-use.** Replaying one is
  `400 invalid_grant`, which is the attack signal the spec calls for.
- **Refresh tokens rotate.** The presented token is revoked and a descendant
  issued; a revoked token is `400 invalid_grant`.
- **Scopes are intersected, not granted.** A token gets `requested ∩ (what the
  subject's roles allow on that resource)`, so asking for more than the roles
  permit silently narrows rather than failing.
- **Organization tokens** come from a refresh exchange with `organization_id`;
  their audience is `urn:logto:organization:<id>` and their scopes come from the
  member's organization roles. A non-member gets `403 access_denied`.
- **The password policy is real.** `sign_in_experience.json` sets a 10-character
  minimum, two character classes and a rejected-word list (`orbit`, `logto`) —
  all three are enforced on create and on password update, with a
  `password.rejected` body naming the reason.
- **Introspection follows RFC 7662**: an unknown, revoked or expired token is
  `{"active": false}` with HTTP 200, not an error. **Revocation follows RFC
  7009**: always 200, even for a token that was never issued.
- Suspending a user, changing their password and deleting them all drop the
  user's live access and refresh tokens.
- Unlinking the last social identity from a user with no password is refused —
  it would lock the account out.
- Deleting an application that still has users bound to it is refused.
- Mutations (new users, rotated tokens, role grants, organizations) are held in
  process memory and reset on container restart.
