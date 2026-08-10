---
name: zitadel-api-connector
description: >
  Zitadel API (Mock) mock HTTP API. Base URL is provided via the
  `ZITADEL_API_URL` environment variable. 41 endpoint(s) across GET, POST, PUT, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Zitadel API (Mock)

Mock of Zitadel. **All requests go to the base URL in `$ZITADEL_API_URL`.**
Responses are deterministic fixtures.

## Base URL and the org header

| Variable | Purpose |
|----------|---------|
| `ZITADEL_API_URL` | Base URL for all requests (e.g. `http://zitadel-api:8118`) |

**The organization is a header, not a path segment.** `x-zitadel-orgid` selects
it for the whole request; absent, the instance default (Orbit Labs) is used.

| Org | Id | Notes |
|-----|----|-------|
| Orbit Labs | `280310551611113987` | default; **`forceMfa: true`** |
| Orbit Partners | `280310551611113988` | no forced MFA |
| Orbit Archive | `280310551611113989` | **inactive** → every request is `400` |

## Personal access tokens

| Token | Scope |
|-------|-------|
| `zt-pat-instance-admin-5b07d21f8c64` | `IAM_OWNER` — any org, plus `/admin/v1/*` |
| `zt-pat-orbit-ci-9f14c73e0b2a` | Orbit Labs, `ORG_USER_MANAGER` — may write |
| `zt-pat-readonly-c8e05a1976b3` | Orbit Labs, `ORG_OWNER_VIEWER` — reads only |
| `zt-pat-partners-2d47b9e01f5c` | Orbit Partners |
| `zt-pat-revoked-1e94c7a305df` | revoked → `401` |

## Sessions are built up factor by factor

There is no login endpoint. `POST /v2/sessions` records a factor for each
`check` that passes, and `PATCH` adds more. **Every update rotates the session
token** — always use the token the last call returned.

```
POST /v2/sessions   {"checks": {"user": {...}}}                → factors: user
PATCH /v2/sessions/{id} {"sessionToken": …, "checks": {"password": …}}
                                                               → + password
PATCH /v2/sessions/{id} {"sessionToken": …, "checks": {"totp": …}}
                                                               → + totp
```

The org's login policy is enforced at the **end**, when the session is exchanged
for an OIDC callback via `POST /v2/oidc/auth_requests/{id}`.

## Seed users (Orbit Labs)

| Id | Login name | Password | Note |
|----|------------|----------|------|
| `280310551611114001` | `amelia@orbit-labs.zitadel.cloud` | `OrbitZitadel2026!` | TOTP `482913` + U2F, `ORG_OWNER` |
| `280310551611114002` | `jonas@orbit-labs.zitadel.cloud` | `OrbitJonas2026!` | TOTP `770412`, **not verified** |
| `280310551611114003` | `helena@orbit-labs.zitadel.cloud` | `OrbitHelena2026!` | **passkey**, no TOTP |
| `280310551611114004` | `rohit@orbit-labs.zitadel.cloud` | — | `USER_STATE_INITIAL` |
| `280310551611114005` | `noor@orbit-labs.zitadel.cloud` | `OrbitNoor2026!` | `USER_STATE_INACTIVE` |
| `280310551611114006` | `dmitri@orbit-labs.zitadel.cloud` | `OrbitDmitri2026!` | `USER_STATE_LOCKED` |
| `280310551611114007` | `orbit-ci` | — | **machine** user |

`280310551611114008` / `priya@orbit-partners.zitadel.cloud` / `OrbitPriya2026!`
lives in Orbit Partners.

## Seeded sessions

| Session | Token | Factors |
|---------|-------|---------|
| `281940113077370881` | `zt-session-amelia-4c19f7e0b83d` | user, password, totp |
| `281940113077370882` | `zt-session-jonas-91e5c7d40a26` | user, password |
| `281940113077370883` | `zt-session-helena-70b2e4f9c81d` | user, **webAuthN** |
| `281940113077370884` | `zt-session-priya-1d75a0e934bc` | user, password (partner org) |
| `281940113077370885` | `zt-session-amelia-expired-3a6d80e5` | **expired** |
| `281940113077370886` | `zt-session-amelia-laptop-58c0e7d3` | user, password only |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/debug/healthz` · `/admin/v1/instance` |
| POST | `/admin/v1/orgs/_search` · `/admin/v1/events/_search` |
| GET | `/management/v1/orgs/me` · `/management/v1/policies/login` |
| POST | `/v2/users/human` · `/v2/users/_search` |
| GET/PUT/DELETE | `/v2/users/{id}` · `/v2/users/human/{id}` |
| POST | `/v2/users/{id}/email` · `/email/_verify` · `/password` · `/password_reset` |
| POST | `/v2/users/{id}/deactivate` · `/reactivate` · `/lock` · `/unlock` |
| GET | `/v2/users/{id}/authentication_factors` |
| POST | `/v2/users/{id}/totp` · `/totp/_verify` |
| DELETE | `/v2/users/{id}/authentication_factors/{factorId}` |
| POST | `/v2/sessions` · `/v2/sessions/_search` |
| GET/PATCH/DELETE | `/v2/sessions/{id}` |
| GET/POST | `/v2/oidc/auth_requests/{id}` |
| POST | `/management/v1/projects` · `/projects/_search` · `/projects/{id}/roles` · `/roles/_search` |
| GET | `/management/v1/projects/{id}` |
| POST | `/management/v1/users/grants/_search` · `/users/{id}/grants` |
| PUT/DELETE | `/management/v1/users/{id}/grants/{grantId}` |
| POST | `/management/v1/orgs/me/members` · `/members/_search` |
| DELETE | `/management/v1/orgs/me/members/{userId}` |

## Usage

```bash
# Start a session, then add a password to it
curl -s -X POST "$ZITADEL_API_URL/v2/sessions" \
  -H 'Content-Type: application/json' \
  -H 'x-zitadel-orgid: 280310551611113987' \
  -d '{"checks": {"user": {"loginName": "amelia@orbit-labs.zitadel.cloud"},
                  "password": {"password": "OrbitZitadel2026!"}}}'

# Admin call: bearer plus org header
curl -s -X POST "$ZITADEL_API_URL/v2/users/_search" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer zt-pat-orbit-ci-9f14c73e0b2a' \
  -H 'x-zitadel-orgid: 280310551611113987' -d '{"limit": 5}'
```

Errors carry a gRPC status code in the body next to the HTTP status: `3`
INVALID_ARGUMENT, `5` NOT_FOUND, `6` ALREADY_EXISTS, `7` PERMISSION_DENIED, `9`
FAILED_PRECONDITION, `16` UNAUTHENTICATED. Every write returns a `details`
envelope with a monotonic `sequence`.

The audit log of every call the agent makes is available at
`$ZITADEL_API_URL/audit/requests` (used for grading).
