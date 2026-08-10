# Logto API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$LOGTO_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `LOGTO_API_URL` | Base URL for all requests |

Set the bearers once to follow the examples:

```bash
export MGMT='logto_at_ci_full_9f14c73e0b2a'
export MGMT_RO='logto_at_reporting_ro_5b07d21f8c64'
export STATUS_TOKEN='logto_at_amelia_status_c8e05a1976b3'
export ORG_TOKEN='logto_at_amelia_org_platform_7a63f04c9e21'
```

## The one thing to understand first

`/api/*` is not "the API with an admin key". It is a **protected resource**, and
a bearer reaches it only when it was issued **for** the indicator
`https://default.logto.app/api` with a wide enough scope:

| Bearer | `GET /api/users` | `POST /api/users` |
|--------|------------------|-------------------|
| `$MGMT` (scope `all`) | 200 | 201 |
| `$MGMT_RO` (scope `read:user`) | 200 | 403 `auth.insufficient_scope` |
| `$STATUS_TOKEN` (Orbit Status API) | 403 `auth.forbidden` | 403 |
| `$ORG_TOKEN` (organization) | 403 `auth.forbidden` | 403 |
| none / revoked | 401 `auth.authorization_header_missing` | 401 |

## Discovery

```bash
curl -s "$LOGTO_API_URL/oidc/.well-known/openid-configuration"
curl -s "$LOGTO_API_URL/oidc/jwks"
curl -s "$LOGTO_API_URL/api/status"
```

## Token endpoint

Three grants; the mock accepts JSON with the standard field names.

```bash
# client_credentials -- machine-to-machine
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "client_credentials", "client_id": "appm2m1a5e0y",
       "client_secret": "logto_secret_ci_pipeline_9a2b6d31",
       "resource": "https://default.logto.app/api", "scope": "all"}'

# authorization_code -- with PKCE
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "authorization_code", "client_id": "app6qk2v9x1m",
       "code": "logto_code_amelia_e70b2c948d15",
       "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
       "redirect_uri": "https://status.orbit-labs.com/callback"}'

# refresh_token
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "refresh_token", "client_id": "app6qk2v9x1m",
       "refresh_token": "logto_rt_jonas_spa_6c19af35e082"}'

# refresh_token -> organization token
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "refresh_token", "client_id": "app6qk2v9x1m",
       "refresh_token": "logto_rt_amelia_spa_04b7e21c9d38",
       "organization_id": "org5platform1"}'
```

Rules the mock enforces:

- Confidential clients (`Traditional`, `MachineToMachine`) must send the right
  `client_secret`; a wrong one is `401 invalid_client`.
- An app may only use the grants listed on it — an SPA asking for
  `client_credentials` is `400 unauthorized_client`.
- Authorization codes are **single-use**; replaying one is `400 invalid_grant`.
- A code minted with a `code_challenge` needs the matching `code_verifier`.
- Refresh tokens **rotate**: the presented token is revoked and a descendant
  returned. A revoked token is `400 invalid_grant`.
- The granted `scope` is the intersection of what was asked for with what the
  subject's roles allow **on that resource**.

Seeded grant material:

| Value | Kind | State |
|-------|------|-------|
| `logto_code_amelia_e70b2c948d15` | authorization code (amelia, PKCE) | unused |
| `logto_code_rohit_used_5a1c93e08b74` | authorization code | **already used** |
| `logto_rt_amelia_spa_04b7e21c9d38` | refresh token | unused |
| `logto_rt_jonas_spa_6c19af35e082` | refresh token | unused |
| `logto_rt_rohit_web_b530d7419ce6` | refresh token | **revoked** |

PKCE verifier/challenge pair for the seeded code:
`dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk` →
`E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM`.

## Authorize

```bash
curl -s "$LOGTO_API_URL/oidc/auth?client_id=app6qk2v9x1m\
&redirect_uri=https://status.orbit-labs.com/callback&response_type=code\
&scope=openid%20profile%20email%20offline_access\
&resource=https://api.orbit-labs.com/status\
&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM\
&code_challenge_method=S256&state=orbit-status-42"
```

Returns the authorization code rather than a 302, so the flow stays inspectable.
Public clients (`SPA`, `Native`) must send `code_challenge`; an unregistered
`redirect_uri` is refused.

## Introspection, revocation, userinfo

```bash
curl -s -X POST "$LOGTO_API_URL/oidc/token/introspection" \
  -H 'Content-Type: application/json' -d "{\"token\": \"$STATUS_TOKEN\"}"

curl -s -X POST "$LOGTO_API_URL/oidc/token/revocation" \
  -H 'Content-Type: application/json' -d '{"token": "logto_at_jonas_status_2d47b9e01f5c"}'

curl -s "$LOGTO_API_URL/oidc/me" -H "Authorization: Bearer $STATUS_TOKEN"
```

Introspection reports `{"active": false}` for an unknown, revoked or expired
token (RFC 7662). Revocation is always 200 (RFC 7009). Userinfo needs a *user*
token — a machine token gets `403 insufficient_scope`.

## Users

```bash
curl -s "$LOGTO_API_URL/api/users?page=1&page_size=10" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/users?search=park" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/users?isSuspended=true" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/users/n4k29xqf7bd1" -H "Authorization: Bearer $MGMT"

curl -s -X POST "$LOGTO_API_URL/api/users" -H "Authorization: Bearer $MGMT" \
  -H 'Content-Type: application/json' \
  -d '{"username": "iris", "primaryEmail": "iris.tanaka@orbit-labs.com",
       "password": "Stellar-Iris-2026!", "name": "Iris Tanaka"}'

curl -s -X PATCH "$LOGTO_API_URL/api/users/d6y0jl52nvk8" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"name": "Rohit K. Bansal"}'

curl -s -X PATCH "$LOGTO_API_URL/api/users/d6y0jl52nvk8/password" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"password": "Nebula-Rohit-2026!"}'

curl -s -X POST "$LOGTO_API_URL/api/users/d6y0jl52nvk8/password/verify" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"password": "OrbitRohit2026!"}'

curl -s -X PATCH "$LOGTO_API_URL/api/users/t8m3vc06wzr5/is-suspended" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"isSuspended": true}'

curl -s -X DELETE "$LOGTO_API_URL/api/users/z5r2od38kxa9" -H "Authorization: Bearer $MGMT"
```

**Password policy** (from `sign_in_experience.json`, enforced on create *and*
update): minimum 10 characters, at least 2 character classes, and the words
`orbit` and `logto` are rejected. A rejection is `422 password.rejected` with a
`data` field naming the reason. Note that most of the seed passwords would not
pass it — they predate the policy, which is exactly the situation a real
deployment ends up in.

Suspending, resetting a password and deleting all drop the user's live access
and refresh tokens.

## Custom data, identities, roles

```bash
curl -s "$LOGTO_API_URL/api/users/n4k29xqf7bd1/custom-data" -H "Authorization: Bearer $MGMT"
curl -s -X PATCH "$LOGTO_API_URL/api/users/n4k29xqf7bd1/custom-data" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"customData": {"team": "platform-core", "oncall": "true"}}'

curl -s "$LOGTO_API_URL/api/users/n4k29xqf7bd1/identities" -H "Authorization: Bearer $MGMT"
curl -s -X DELETE "$LOGTO_API_URL/api/users/n4k29xqf7bd1/identities/google" \
  -H "Authorization: Bearer $MGMT"

curl -s "$LOGTO_API_URL/api/users/n4k29xqf7bd1/roles" -H "Authorization: Bearer $MGMT"
curl -s -X POST "$LOGTO_API_URL/api/users/p1s7ea94hgu2/roles" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"roleIds": ["rol2viewer001"]}'
curl -s -X DELETE "$LOGTO_API_URL/api/users/p1s7ea94hgu2/roles/rol2viewer001" \
  -H "Authorization: Bearer $MGMT"
```

Custom data is a shallow merge. Unlinking the last identity from a user with no
password is refused (`422 user.cannot_delete_only_identity`).

## Roles, applications, resources

```bash
curl -s "$LOGTO_API_URL/api/roles" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/roles?type=MachineToMachine" -H "Authorization: Bearer $MGMT"
curl -s -X POST "$LOGTO_API_URL/api/roles" -H "Authorization: Bearer $MGMT" \
  -H 'Content-Type: application/json' \
  -d '{"name": "auditor", "scopeNames": ["read:incidents", "read:services"]}'

curl -s "$LOGTO_API_URL/api/applications" -H "Authorization: Bearer $MGMT"
curl -s -X POST "$LOGTO_API_URL/api/applications" -H "Authorization: Bearer $MGMT" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Orbit Webhook Relay", "type": "MachineToMachine"}'

curl -s "$LOGTO_API_URL/api/resources" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/resources/res5statusapi/scopes" -H "Authorization: Bearer $MGMT"
```

Roles: `admin`, `operator`, `viewer` (type `User`), `machine:ci`,
`machine:reporting` (type `MachineToMachine`). Deleting an application that
still has users bound to it is refused.

## Organizations

```bash
curl -s "$LOGTO_API_URL/api/organizations" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/organizations/org5platform1/users" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/organization-roles" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/organization-scopes" -H "Authorization: Bearer $MGMT"

curl -s -X POST "$LOGTO_API_URL/api/organizations/org6acmepart1/users" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"userIds": ["z5r2od38kxa9"]}'

curl -s -X POST "$LOGTO_API_URL/api/organizations/org6acmepart1/users/z5r2od38kxa9/roles" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"organizationRoleIds": ["orl2guest0001"]}'

# The one endpoint an organization token reaches
curl -s "$LOGTO_API_URL/api/my-organization" -H "Authorization: Bearer $ORG_TOKEN"
```

Organizations: `org5platform1` (Orbit Platform, MFA required),
`org6acmepart1` (Acme Partner). Organization roles: `orl0admin0001` (`org:admin`),
`orl1member001` (`org:member`), `orl2guest0001` (`org:guest`).

## Connectors, sign-in experience, logs, dashboard

```bash
curl -s "$LOGTO_API_URL/api/connectors" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/connectors?type=Social" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/sign-in-exp" -H "Authorization: Bearer $MGMT"
curl -s -X PATCH "$LOGTO_API_URL/api/sign-in-exp" -H "Authorization: Bearer $MGMT" \
  -H 'Content-Type: application/json' -d '{"supportEmail": "help@orbit-labs.com"}'
curl -s "$LOGTO_API_URL/api/logs?page_size=5" -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/logs?logKey=ExchangeTokenBy.ClientCredentials" \
  -H "Authorization: Bearer $MGMT"
curl -s "$LOGTO_API_URL/api/dashboard/users/total" -H "Authorization: Bearer $MGMT"
```

Log keys in the seed: `ExperienceApi.SignIn.Submit`,
`ExperienceApi.SignIn.Social.Authorization`, `ExperienceApi.Register.Submit`,
`ExperienceApi.ForgotPassword.Submit`, `ExchangeTokenBy.ClientCredentials`,
`ExchangeTokenBy.RefreshToken`.

## Errors

### OIDC plane (RFC 6749)

| HTTP | `error` | When |
|------|---------|------|
| 400 | `invalid_grant` | code replayed/unknown/expired, verifier mismatch, refresh token revoked, user suspended |
| 400 | `invalid_request` | missing PKCE, unregistered redirect uri |
| 400 | `unauthorized_client` | the app may not use that grant |
| 400 | `unsupported_grant_type` / `unsupported_response_type` | |
| 400 | `invalid_scope` | the subject has no scopes on that resource |
| 401 | `invalid_client` | unknown client, or wrong client secret |
| 401 | `invalid_token` | userinfo without a live bearer |
| 403 | `access_denied` | organization token asked for by a non-member |
| 403 | `insufficient_scope` | userinfo with a machine token |

### Management API (Logto)

| HTTP | `code` | When |
|------|--------|------|
| 401 | `auth.authorization_header_missing` | no bearer, or it is revoked/expired |
| 403 | `auth.forbidden` | the bearer's audience is not the Management API |
| 403 | `auth.insufficient_scope` | right audience, too narrow a scope |
| 404 | `entity.not_found` | unknown user, role, application, organization, connector or log |
| 422 | `user.email_already_in_use` / `user.username_already_in_use` | duplicate identifier |
| 422 | `password.rejected` | fails the sign-in-experience password policy |
| 422 | `session.invalid_credentials` | password verify failed |
| 422 | `user.password_not_set` | password verify on a social-only account |
| 422 | `user.cannot_delete_only_identity` | would lock the account out |
| 422 | `user.role_exists` / `role.name_in_use` | duplicate assignment or name |
| 422 | `application.in_use` | deleting an app that still has users |
| 422 | `guard.invalid_input` | missing or malformed field |
