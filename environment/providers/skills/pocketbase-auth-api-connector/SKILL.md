---
name: pocketbase-auth-api-connector
description: >
  PocketBase Auth API (Mock) mock HTTP API. Base URL is provided via the
  `POCKETBASE_AUTH_API_URL` environment variable. 25 endpoint(s) across GET, POST, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# PocketBase Auth API (Mock)

Mock HTTP API for the auth half of the self-hosted PocketBase instance
`pocketbase-api` backs. **All requests go to the base URL in
`$POCKETBASE_AUTH_API_URL`.** Responses are deterministic fixtures.

Auth is **per collection**: every endpoint is scoped to
`/api/collections/{collection}`, and `users` and the system `_superusers`
collection carry different rules.

## Base URL

| Variable | Purpose |
|----------|---------|
| `POCKETBASE_AUTH_API_URL` | Base URL for all requests (e.g. `http://pocketbase-auth-api:8114`) |

## Tokens

A token is `<header>.<recordId>.<tokenKey>`, sent in `Authorization` with or
without a `Bearer` prefix. It resolves only while the record still carries that
`tokenKey` — a password or email change rotates it and invalidates every token
already issued.

| Token | Record |
|-------|--------|
| `eyJhbGciOiJIUzI1NiJ9.usramelia000001.tk_amelia_5f1c` | amelia (`users`, MFA on) |
| `eyJhbGciOiJIUzI1NiJ9.usrjonas0000002.tk_jonas_2b90` | jonas (`users`) |
| `eyJhbGciOiJIUzI1NiJ9.usrsyncbot00006.tk_syncbot_7d4f` | sync bot (`users`) |
| `eyJhbGciOiJIUzI1NiJ9.sup0admin000001.tk_ops_e64a` | ops (`_superusers`) |
| `eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status` | the legacy token `pocketbase-api` mints, accepted as ops |

Seed passwords live in the service's `settings.json` under `seed_credentials`.

## Collections

| Collection | Identity fields | OTP | MFA | OAuth2 | authRule |
|------------|-----------------|-----|-----|--------|----------|
| `users` | `email`, `username` | on (8 digits) | on | `github`, `google` | `verified = true` |
| `_superusers` | `email` | off | off | off | _(none)_ |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/api/health` |
| GET | `/api/collections` |
| GET | `/api/collections/{collection}/auth-methods` |
| POST | `/api/collections/{collection}/auth-with-password` |
| POST | `/api/collections/{collection}/request-otp` |
| POST | `/api/collections/{collection}/auth-with-otp` |
| POST | `/api/collections/{collection}/auth-with-oauth2` |
| POST | `/api/collections/{collection}/auth-refresh` |
| POST | `/api/collections/{collection}/impersonate/{record_id}` |
| POST | `/api/collections/{collection}/request-verification` |
| POST | `/api/collections/{collection}/confirm-verification` |
| POST | `/api/collections/{collection}/request-password-reset` |
| POST | `/api/collections/{collection}/confirm-password-reset` |
| POST | `/api/collections/{collection}/request-email-change` |
| POST | `/api/collections/{collection}/confirm-email-change` |
| GET | `/api/collections/{collection}/records` |
| POST | `/api/collections/{collection}/records` |
| GET | `/api/collections/{collection}/records/{record_id}` |
| PATCH | `/api/collections/{collection}/records/{record_id}` |
| DELETE | `/api/collections/{collection}/records/{record_id}` |
| GET | `/api/collections/{collection}/records/{record_id}/external-auths` |
| DELETE | `/api/collections/{collection}/records/{record_id}/external-auths/{provider}` |
| GET | `/api/logs` |
| GET | `/api/logs/stats` |

## Usage

```bash
# Sign in
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!"}'

# Read a record with a seeded token
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrjonas0000002" \
  -H 'Authorization: eyJhbGciOiJIUzI1NiJ9.usrjonas0000002.tk_jonas_2b90'

# Superuser: list the auth logs
curl -s "$POCKETBASE_AUTH_API_URL/api/logs?perPage=5" \
  -H 'Authorization: eyJhbGciOiJIUzI1NiJ9.sup0admin000001.tk_ops_e64a'
```

Errors use the PocketBase body shape: `{"code": 400, "message": "Failed to
authenticate.", "data": {"identity": {"code": "validation_invalid_credentials",
"message": "Invalid login credentials."}}}`.

The audit log of every call the agent makes is available at
`$POCKETBASE_AUTH_API_URL/audit/requests` (used for grading).
