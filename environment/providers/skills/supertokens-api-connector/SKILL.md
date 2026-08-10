---
name: supertokens-api-connector
description: >
  SuperTokens Core API (Mock) mock HTTP API. Base URL is provided via the
  `SUPERTOKENS_API_URL` environment variable. 46 endpoint(s) across GET, POST, PUT.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# SuperTokens Core API (Mock)

Mock of the SuperTokens **core** — the service a backend SDK talks to, not the
SDK's frontend routes. **All requests go to the base URL in
`$SUPERTOKENS_API_URL`.** Responses are deterministic fixtures.

## Base URL and headers

| Variable | Purpose |
|----------|---------|
| `SUPERTOKENS_API_URL` | Base URL for all requests (e.g. `http://supertokens-api:8115`) |

| Header | Value |
|--------|-------|
| `api-key` | `orbit-labs-supertokens-core-key` |
| `cdi-version` | `5.1` (also accepts `3.0`, `4.0`, `5.0`, `5.2`) |

## Read this before interpreting a response

**The core reports domain outcomes in the body, not the status line.** A wrong
password is `200 {"status": "WRONG_CREDENTIALS_ERROR"}`. Always check
`body.status`, not just the HTTP code. Non-2xx means a transport problem:

| HTTP | Cause |
|------|-------|
| 401 | missing or wrong `api-key` |
| 400 | unsupported `cdi-version`, or a malformed body |
| 404 | unknown tenant in the path |
| 403 | deleting the `public` tenant |

## Tenants

Every recipe path is tenant-scoped. `/recipe/...` is shorthand for
`/appid-public/public/recipe/...`.

| Tenant | emailpassword | thirdparty | passwordless |
|--------|---------------|------------|--------------|
| `public` | on | on (`github`, `google`) | off |
| `orbit-enterprise` | off | on (`okta`) | on (email, code + link) |

A recipe that is off on a tenant returns `EMAIL_PASSWORD_NOT_ENABLED_ERROR` /
`PASSWORDLESS_NOT_ENABLED_ERROR` rather than failing the credentials.

## Seed users

| User id | Recipes | Password | Note |
|---------|---------|----------|------|
| `0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1` | emailpassword + thirdparty | `OrbitSuperTokens2026!` | amelia; **primary user**, two login methods |
| `5a92c04f-1b76-4d38-9e51-c8f0b273a469` | emailpassword | `OrbitJonas2026!` | jonas; two sessions, one rotated refresh token |
| `b3f61d08-9e24-4a75-8c30-71d5e0a94b26` | thirdparty | — | helena; github only |
| `e84c25b7-0a63-4f91-bd28-3c7016fa5d84` | emailpassword | `OrbitRohit2026!` | rohit; **email not verified** |
| `7c05f9e2-46b1-48da-9037-2ba8d1c6e053` | passwordless | — | noor; `orbit-enterprise` only |
| `2f7a83c1-d504-4e69-b1a2-60e9c745f83b` | emailpassword | `OrbitSyncBot2026!` | sync bot |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/hello` · `/apiversion` · `/config` · `/recipe/jwt/jwks` |
| POST | `/recipe/signup` · `/recipe/signin` |
| GET/PUT | `/recipe/user` |
| POST | `/recipe/user/password/reset/token` · `/recipe/user/password/reset` |
| POST | `/recipe/signinup` |
| POST | `/recipe/signinup/code` · `/recipe/signinup/code/consume` |
| POST | `/recipe/session` · `/recipe/session/verify` · `/recipe/session/refresh` · `/recipe/session/remove` |
| GET | `/recipe/session/user` |
| GET/PUT | `/recipe/session/data` |
| POST | `/recipe/user/email/verify/token` · `/recipe/user/email/verify` |
| GET | `/recipe/user/email/verify` |
| GET/PUT | `/recipe/user/metadata` |
| POST | `/recipe/user/metadata/remove` |
| PUT | `/recipe/role` · `/recipe/user/role` |
| GET | `/recipe/roles` · `/recipe/role/permissions` · `/recipe/role/users` · `/recipe/user/roles` |
| POST | `/recipe/role/remove` · `/recipe/user/role/remove` |
| GET | `/recipe/multitenancy/tenant/list` · `/appid-{appId}/{tenantId}/recipe/multitenancy/tenant` |
| PUT | `/recipe/multitenancy/tenant` |
| POST | `/recipe/multitenancy/tenant/remove` · `/recipe/multitenancy/tenant/user` |
| POST | `/recipe/accountlinking/user/primary` · `/user/link` · `/user/unlink` |
| GET | `/users` · `/users/count` · `/user/id` |
| POST | `/user/remove` |

## Usage

```bash
# Sign in (check body.status, not the HTTP code)
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/signin" \
  -H 'Content-Type: application/json' \
  -H 'api-key: orbit-labs-supertokens-core-key' -H 'cdi-version: 5.1' \
  -d '{"email": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!"}'

# Verify a session
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session/verify" \
  -H 'Content-Type: application/json' \
  -H 'api-key: orbit-labs-supertokens-core-key' -H 'cdi-version: 5.1' \
  -d '{"accessToken": "st-at-amelia-4c19f7e0b83d"}'

# The other tenant
curl -s "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/users?limit=10" \
  -H 'api-key: orbit-labs-supertokens-core-key' -H 'cdi-version: 5.1'
```

The audit log of every call the agent makes is available at
`$SUPERTOKENS_API_URL/audit/requests` (used for grading).
