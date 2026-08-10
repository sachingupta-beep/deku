# Zitadel API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$ZITADEL_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `ZITADEL_API_URL` | Base URL for all requests |

Set the tokens and org ids once to follow the examples:

```bash
export ZT_ADMIN='zt-pat-instance-admin-5b07d21f8c64'
export ZT_CI='zt-pat-orbit-ci-9f14c73e0b2a'
export ZT_RO='zt-pat-readonly-c8e05a1976b3'
export ZT_PARTNER='zt-pat-partners-2d47b9e01f5c'
export ORBIT_LABS='280310551611113987'
export ORBIT_PARTNERS='280310551611113988'
```

## The two things that shape this API

**1. The organization is a header.** `x-zitadel-orgid` scopes the whole request.
Absent, the instance default (Orbit Labs) is used. A user in one org is not
found from another, and a PAT for one org cannot administer another.

**2. Sessions accumulate factors.** There is no login call. Each `check` that
passes contributes a factor with its own `verifiedAt`; the org's login policy is
checked only when the session is exchanged for an OIDC callback.

## Health and instance

```bash
curl -s "$ZITADEL_API_URL/health"
curl -s "$ZITADEL_API_URL/debug/healthz"
curl -s "$ZITADEL_API_URL/admin/v1/instance" -H "Authorization: Bearer $ZT_ADMIN"
curl -s -X POST "$ZITADEL_API_URL/admin/v1/orgs/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_ADMIN" \
  -d '{"limit": 10}'
```

`/admin/v1/*` needs `IAM_OWNER`; an org PAT gets `7 PERMISSION_DENIED`.

## Organization and login policy

```bash
curl -s "$ZITADEL_API_URL/management/v1/orgs/me" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"

curl -s "$ZITADEL_API_URL/management/v1/policies/login" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"
```

| Org | `forceMfa` | `allowRegister` | second factors |
|-----|-----------|-----------------|----------------|
| Orbit Labs `280310551611113987` | **true** | false | OTP, U2F |
| Orbit Partners `280310551611113988` | false | true | OTP |
| Orbit Archive `280310551611113989` | — | — | **inactive org** |

## Users

```bash
curl -s -X POST "$ZITADEL_API_URL/v2/users/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"limit": 10}'

curl -s -X POST "$ZITADEL_API_URL/v2/users/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"query": "park", "type": "human"}'

curl -s "$ZITADEL_API_URL/v2/users/280310551611114001" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"

curl -s -X POST "$ZITADEL_API_URL/v2/users/human" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"username": "iris@orbit-labs.zitadel.cloud",
       "profile": {"givenName": "Iris", "familyName": "Tanaka"},
       "email": {"email": "iris.tanaka@orbit-labs.com", "isVerified": true},
       "password": {"password": "StellarIris2026!"}}'

curl -s -X PUT "$ZITADEL_API_URL/v2/users/human/280310551611114003" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"profile": {"nickName": "hel"}}'

curl -s -X DELETE "$ZITADEL_API_URL/v2/users/280310551611114005" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"
```

Password complexity: at least 8 characters, an upper-case letter, a digit and a
symbol. Each violation names its own Zitadel error id.

### Email and password

```bash
curl -s -X POST "$ZITADEL_API_URL/v2/users/280310551611114004/email" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"email": "rohit.bansal@orbit-labs.io", "verification": {"returnCode": {}}}'

curl -s -X POST "$ZITADEL_API_URL/v2/users/280310551611114004/email/_verify" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"verificationCode": "<from above>"}'

curl -s -X POST "$ZITADEL_API_URL/v2/users/280310551611114004/password" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"newPassword": {"password": "NebulaRohit2026!"}}'

curl -s -X POST "$ZITADEL_API_URL/v2/users/280310551611114002/password_reset" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"returnCode": {}}'
```

Setting the first password on a `USER_STATE_INITIAL` user activates the account.
Changing a password drops every session that authenticated with one. `verification`
accepts `currentPassword` or a `verificationCode` from `password_reset`.

### Lifecycle

```bash
curl -s -X POST "$ZITADEL_API_URL/v2/users/{id}/deactivate" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"
# also: /reactivate, /lock, /unlock
```

Each transition requires the matching current state, so deactivating an already
inactive user is `9 FAILED_PRECONDITION`. Deactivating or locking a user drops
all of their sessions.

## Authentication factors

```bash
curl -s "$ZITADEL_API_URL/v2/users/280310551611114001/authentication_factors" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"

curl -s -X POST "$ZITADEL_API_URL/v2/users/280310551611114004/totp" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"

curl -s -X POST "$ZITADEL_API_URL/v2/users/280310551611114002/totp/_verify" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"code": "770412"}'

curl -s -X DELETE \
  "$ZITADEL_API_URL/v2/users/280310551611114001/authentication_factors/af-amelia-u2f-0001" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"
```

Registering TOTP returns the `otpauth://` URI and the code the mock expects,
since no authenticator app is really enrolled. Seeded codes: amelia `482913`
(ready), jonas `770412` (**not ready** until verified), priya `605144`.

## Sessions

```bash
# 1. start with a user check
curl -s -X POST "$ZITADEL_API_URL/v2/sessions" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"checks": {"user": {"loginName": "amelia@orbit-labs.zitadel.cloud"}},
       "metadata": {"device": "thinkpad-t14"},
       "userAgent": {"fingerprintId": "fp-cli"}}'

# 2. add the password -- quote the token the previous call returned
curl -s -X PATCH "$ZITADEL_API_URL/v2/sessions/<sessionId>" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"sessionToken": "<sessionToken>",
       "checks": {"password": {"password": "OrbitZitadel2026!"}}}'

# 3. add the second factor
curl -s -X PATCH "$ZITADEL_API_URL/v2/sessions/<sessionId>" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"sessionToken": "<rotated token>", "checks": {"totp": {"code": "482913"}}}'

curl -s "$ZITADEL_API_URL/v2/sessions/<sessionId>?sessionToken=<token>" \
  -H "x-zitadel-orgid: $ORBIT_LABS"

curl -s -X POST "$ZITADEL_API_URL/v2/sessions/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"userId": "280310551611114001"}'

curl -s -X DELETE "$ZITADEL_API_URL/v2/sessions/<sessionId>" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"sessionToken": "<token>"}'
```

Checks understood: `user` (`loginName` or `userId`), `password`, `totp`,
`webAuthN`, `idpIntent`. Rules:

- All checks in one call are applied together, or none are.
- A `password`/`totp`/`webAuthN` check without a user on the session is
  `9 FAILED_PRECONDITION`.
- A deactivated or locked user cannot start a session at all.
- **Every update rotates the session token**; the old one is `7 PERMISSION_DENIED`.
- The session endpoints take **no bearer** — the session token is the credential.

Seeded sessions:

| Session | Token | Factors |
|---------|-------|---------|
| `281940113077370881` | `zt-session-amelia-4c19f7e0b83d` | user, password, totp |
| `281940113077370882` | `zt-session-jonas-91e5c7d40a26` | user, password |
| `281940113077370883` | `zt-session-helena-70b2e4f9c81d` | user, webAuthN |
| `281940113077370884` | `zt-session-priya-1d75a0e934bc` | user, password (partner) |
| `281940113077370885` | `zt-session-amelia-expired-3a6d80e5` | **expired** |
| `281940113077370886` | `zt-session-amelia-laptop-58c0e7d3` | user, password only |

## OIDC auth requests

```bash
curl -s "$ZITADEL_API_URL/v2/oidc/auth_requests/281940113077373001" \
  -H "x-zitadel-orgid: $ORBIT_LABS"

curl -s -X POST "$ZITADEL_API_URL/v2/oidc/auth_requests/281940113077373001" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"session": {"sessionId": "281940113077370883",
                   "sessionToken": "zt-session-helena-70b2e4f9c81d"}}'

curl -s -X POST "$ZITADEL_API_URL/v2/oidc/auth_requests/281940113077373002" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"deny": true}'
```

This is where the login policy bites:

| Session factors | Org | Result |
|-----------------|-----|--------|
| user + password | Orbit Labs (`forceMfa`) | `9` — *missing: a second factor* |
| user + password + totp | Orbit Labs | 200 with a `callbackUrl` |
| user + webAuthN | Orbit Labs | 200 — passwordless satisfies it |
| user + password | Orbit Partners | 200 |

An auth request can only be completed once. Seeded requests:
`281940113077373001` and `…002` in Orbit Labs, `…003` in Orbit Partners, and
`…004` already succeeded.

## Projects, roles and grants

```bash
curl -s -X POST "$ZITADEL_API_URL/management/v1/projects/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{}'

curl -s "$ZITADEL_API_URL/management/v1/projects/281940113077371001" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"

curl -s -X POST "$ZITADEL_API_URL/management/v1/projects" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"name": "Orbit Telemetry"}'

curl -s -X POST \
  "$ZITADEL_API_URL/management/v1/projects/281940113077371001/roles/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{}'

curl -s -X POST \
  "$ZITADEL_API_URL/management/v1/projects/281940113077371001/roles" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"roleKey": "status.audit", "displayName": "Status Auditor"}'

curl -s -X POST "$ZITADEL_API_URL/management/v1/users/grants/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"userId": "280310551611114001"}'

curl -s -X POST \
  "$ZITADEL_API_URL/management/v1/users/280310551611114003/grants" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"projectId": "281940113077371002", "roleKeys": ["billing.read"]}'
```

Projects: `281940113077371001` Orbit Status Platform (`status.admin`,
`status.incident.write`, `status.read`), `281940113077371002` Orbit Billing
(`billing.read`, `billing.write`), `281940113077371003` Partner Portal
(`partner.read`, in the partner org). A grant naming a role the project does not
declare is `3 INVALID_ARGUMENT`.

## Org members

```bash
curl -s -X POST "$ZITADEL_API_URL/management/v1/orgs/me/members/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{}'

curl -s -X POST "$ZITADEL_API_URL/management/v1/orgs/me/members" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"userId": "280310551611114003", "roles": ["ORG_PROJECT_CREATOR"]}'

curl -s -X DELETE \
  "$ZITADEL_API_URL/management/v1/orgs/me/members/280310551611114003" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"
```

Roles: `ORG_OWNER`, `ORG_USER_MANAGER`, `ORG_PROJECT_CREATOR`,
`ORG_OWNER_VIEWER`. An org must keep at least one `ORG_OWNER`.

## Events

```bash
curl -s -X POST "$ZITADEL_API_URL/admin/v1/events/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"limit": 10}'

curl -s -X POST "$ZITADEL_API_URL/admin/v1/events/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"eventTypes": ["user.human.password.check.succeeded"], "limit": 5}'
```

Filters: `aggregateTypes`, `aggregateId`, `eventTypes`, `limit`, `asc`. Every
write allocates from the same monotonic counter, so a write's `details.sequence`
matches its event.

## Errors

Errors carry a gRPC status code in the body alongside the HTTP status.

| gRPC | HTTP | When |
|------|------|------|
| 3 INVALID_ARGUMENT | 400 | bad password complexity, wrong code, unknown role or org role, malformed body |
| 5 NOT_FOUND | 404 | unknown org, user, session, project, grant, member, auth request — including one in another org |
| 6 ALREADY_EXISTS | 409 | duplicate username, email, project name, project role, grant, member, TOTP |
| 7 PERMISSION_DENIED | 403 | token for another org, read-only token writing, missing `IAM_OWNER`, wrong session token |
| 9 FAILED_PRECONDITION | 400 | inactive org, deactivated/locked user, wrong lifecycle state, expired session, session missing a required factor, auth request already completed, last org owner |
| 16 UNAUTHENTICATED | 401 | missing or revoked token |
