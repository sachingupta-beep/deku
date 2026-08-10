---
name: logto-api-connector
description: >
  Logto API (Mock) mock HTTP API. Base URL is provided via the
  `LOGTO_API_URL` environment variable. 43 endpoint(s) across GET, POST, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Logto API (Mock)

Mock of Logto, the OIDC-first identity service. **All requests go to the base URL
in `$LOGTO_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `LOGTO_API_URL` | Base URL for all requests (e.g. `http://logto-api:8116`) |

## Two planes

| Prefix | What it is | Error shape |
|--------|------------|-------------|
| `/oidc/*` | OAuth 2.0 authorization server — discovery, authorize, token, introspect, revoke, userinfo | RFC 6749 `{"error", "error_description"}` |
| `/api/*` | Management API, itself just another protected resource | Logto `{"code", "message", "data"}` |

**A bearer only works on `/api/*` if it was issued FOR
`https://default.logto.app/api`** and carries a wide enough scope. A valid token
minted for another resource gets **403**, not 401.

## Seeded bearers

| Token | Audience | Scope | On `/api/*` |
|-------|----------|-------|-------------|
| `logto_at_ci_full_9f14c73e0b2a` | Management API | `all` | everything |
| `logto_at_reporting_ro_5b07d21f8c64` | Management API | `read:user` | reads 200, writes 403 |
| `logto_at_amelia_status_c8e05a1976b3` | `https://api.orbit-labs.com/status` | `read:incidents write:incidents read:services` | 403 wrong audience |
| `logto_at_amelia_org_platform_7a63f04c9e21` | `urn:logto:organization:org5platform1` | `org:read org:write org:invite org:billing` | 403, but reaches `/api/my-organization` |
| `logto_at_jonas_revoked_1e94c7a305df` | status API | — | revoked → 401 |

## Applications

| Client id | Name | Type | Secret |
|-----------|------|------|--------|
| `app6qk2v9x1m` | Orbit Status SPA | SPA | none (PKCE required) |
| `appt3z7w0b8n` | Orbit Admin Console | Traditional | `logto_secret_admin_console_4f19c7e0` |
| `appk9d4r2f6c` | Orbit Mobile | Native | none (PKCE required) |
| `appm2m1a5e0y` | Orbit CI Pipeline | MachineToMachine | `logto_secret_ci_pipeline_9a2b6d31` |
| `appm2m7c3u4p` | Orbit Reporting Job | MachineToMachine | `logto_secret_reporting_1c84f065` |

## Users

| Id | Username | Password | Note |
|----|----------|----------|------|
| `n4k29xqf7bd1` | amelia | `OrbitLogto2026!` | admin; github + google identities |
| `t8m3vc06wzr5` | jonas | `OrbitJonas2026!` | operator |
| `p1s7ea94hgu2` | helena | — | **social only, no password** |
| `d6y0jl52nvk8` | rohit | `OrbitRohit2026!` | viewer |
| `c3b8wq71tfm4` | noor | `OrbitNoor2026!` | **suspended** |
| `z5r2od38kxa9` | orbit_sync_bot | `OrbitSyncBot2026!` | bound to the CI app |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/oidc/.well-known/openid-configuration` · `/oidc/jwks` · `/oidc/auth` · `/oidc/me` |
| POST | `/oidc/token` · `/oidc/token/introspection` · `/oidc/token/revocation` |
| GET | `/api/status` |
| GET/POST | `/api/users` |
| GET/PATCH/DELETE | `/api/users/{id}` |
| PATCH | `/api/users/{id}/password` · `/api/users/{id}/is-suspended` · `/api/users/{id}/custom-data` |
| POST | `/api/users/{id}/password/verify` · `/api/users/{id}/roles` |
| GET | `/api/users/{id}/custom-data` · `/identities` · `/roles` · `/organizations` |
| DELETE | `/api/users/{id}/identities/{target}` · `/api/users/{id}/roles/{roleId}` |
| GET/POST | `/api/roles` · `/api/applications` · `/api/organizations` |
| GET/DELETE | `/api/roles/{id}` · `/api/applications/{id}` · `/api/organizations/{id}` |
| GET | `/api/resources` · `/api/resources/{id}/scopes` |
| GET/POST | `/api/organizations/{id}/users` |
| DELETE | `/api/organizations/{id}/users/{userId}` |
| POST | `/api/organizations/{id}/users/{userId}/roles` |
| GET | `/api/organization-roles` · `/api/organization-scopes` · `/api/my-organization` |
| GET | `/api/connectors` · `/api/connectors/{id}` |
| GET/PATCH | `/api/sign-in-exp` |
| GET | `/api/logs` · `/api/logs/{id}` · `/api/dashboard/users/total` |

## Usage

```bash
# Mint a management token
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "client_credentials", "client_id": "appm2m1a5e0y",
       "client_secret": "logto_secret_ci_pipeline_9a2b6d31",
       "resource": "https://default.logto.app/api", "scope": "all"}'

# Use the seeded one directly
curl -s "$LOGTO_API_URL/api/users?page_size=5" \
  -H 'Authorization: Bearer logto_at_ci_full_9f14c73e0b2a'

# Userinfo with a user token
curl -s "$LOGTO_API_URL/oidc/me" \
  -H 'Authorization: Bearer logto_at_amelia_status_c8e05a1976b3'
```

The password policy in `sign_in_experience.json` is enforced: at least 10
characters, two character classes, and the words `orbit` and `logto` are
rejected.

The audit log of every call the agent makes is available at
`$LOGTO_API_URL/audit/requests` (used for grading).
