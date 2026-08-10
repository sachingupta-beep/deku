---
name: supabase-auth-api-connector
description: >
  Supabase Auth API (Mock) mock HTTP API. Base URL is provided via the
  `SUPABASE_AUTH_API_URL` environment variable. 28 endpoint(s) across GET, POST, PUT, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Supabase Auth API (Mock)

Mock HTTP API for GoTrue, mounted at `/auth/v1`. **All requests go to the base
URL in `$SUPABASE_AUTH_API_URL`.** The `apikey` header selects the project role;
end-user endpoints read `Authorization: Bearer <access_token>`. Responses are
deterministic fixtures. This is the same self-hosted project `supabase-api`
serves — the keys and user ids match.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SUPABASE_AUTH_API_URL` | Base URL for all requests (e.g. `http://supabase-auth-api:8113`) |

## Credentials

| Header | Meaning |
|--------|---------|
| _(none)_ or `apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost` | project role `anon`; admin endpoints return 403 |
| `apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost` | project role `service_role`; admin allowed |
| `Authorization: Bearer <access_token>` | the signed-in user, resolved to a live session |

Three sessions are seeded with fixed access tokens, so a bearer can be used
without signing in first:

| Token | User |
|-------|------|
| `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.amelia-session.orbit-labs` | amelia.ortega (verified TOTP factor) |
| `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.jonas-session.orbit-labs` | jonas.pereira (unverified factor) |
| `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.syncbot-session.orbit-labs` | sync-bot (service account) |

Seed passwords live in the service's `settings.json` under `seed_credentials`.

## Endpoints

| Method | Path |
|--------|------|
| GET | `/auth/v1/health` |
| GET | `/auth/v1/settings` |
| POST | `/auth/v1/signup` |
| POST | `/auth/v1/signup/anonymous` |
| POST | `/auth/v1/token?grant_type=password` |
| POST | `/auth/v1/token?grant_type=refresh_token` |
| POST | `/auth/v1/logout` |
| GET | `/auth/v1/user` |
| PUT | `/auth/v1/user` |
| POST | `/auth/v1/recover` |
| POST | `/auth/v1/magiclink` |
| POST | `/auth/v1/otp` |
| POST | `/auth/v1/verify` |
| POST | `/auth/v1/resend` |
| GET | `/auth/v1/authorize` |
| POST | `/auth/v1/factors` |
| POST | `/auth/v1/factors/{factor_id}/challenge` |
| POST | `/auth/v1/factors/{factor_id}/verify` |
| DELETE | `/auth/v1/factors/{factor_id}` |
| GET | `/auth/v1/admin/users` |
| POST | `/auth/v1/admin/users` |
| GET | `/auth/v1/admin/users/{user_id}` |
| PUT | `/auth/v1/admin/users/{user_id}` |
| DELETE | `/auth/v1/admin/users/{user_id}` |
| POST | `/auth/v1/admin/generate_link` |
| GET | `/auth/v1/admin/audit` |
| GET | `/auth/v1/admin/sessions` |

## Usage

```bash
# Sign in
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=password" \
  -H 'Content-Type: application/json' \
  -H 'apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost' \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "OrbitSupabase2026!"}'

# Read the current user with a seeded session token
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/user" \
  -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.amelia-session.orbit-labs'

# Admin: list users (service key required)
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/users?per_page=5" \
  -H 'apikey: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost'
```

Errors use the GoTrue body shape: `{"code": 400, "error_code":
"invalid_credentials", "msg": "Invalid login credentials"}`.

The audit log of every call the agent makes is available at
`$SUPABASE_AUTH_API_URL/audit/requests` (used for grading).
