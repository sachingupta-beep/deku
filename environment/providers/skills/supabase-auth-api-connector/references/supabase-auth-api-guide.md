# Supabase Auth API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$SUPABASE_AUTH_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SUPABASE_AUTH_API_URL` | Base URL for all requests |

Set the credentials once to follow the examples:

```bash
export ANON_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost'
export SERVICE_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost'
export AMELIA='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.amelia-session.orbit-labs'
export JONAS='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.jonas-session.orbit-labs'
```

## Seed accounts

| Email | Password | Quirk |
|-------|----------|-------|
| `amelia.ortega@orbit-labs.com` | `OrbitSupabase2026!` | verified TOTP factor `e97d2b40-5c81-4f36-a729-1b6e0d94c8f5` (code `482913`) |
| `jonas.pereira@orbit-labs.com` | `OrbitJonas2026!` | unverified factor `af5810c6-72b3-4e09-95d1-c0e3b74f2681` |
| `rohit.bansal@orbit-labs.com` | `OrbitRohit2026!` | email not confirmed → 400 `email_not_confirmed` |
| `noor.aziz@orbit-labs.com` | `OrbitNoor2026!` | banned until 2027-01-01 → 403 `user_banned` |
| `helena.park@orbit-labs.com` | _(none)_ | GitHub identity only → 400 `invalid_credentials` |

## Health and settings

```bash
curl -s "$SUPABASE_AUTH_API_URL/health"
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/health"
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/settings"
```

## Sign in and sign out

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=password" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "OrbitSupabase2026!"}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=refresh_token" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -d '{"refresh_token": "71b09e4c6a2d48f5c803"}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/logout?scope=global" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $AMELIA"
```

`scope=local` revokes only the presented session; `scope=global` (the default)
revokes every session the user holds. Refresh-token rotation is on, so a
refreshed token cannot be replayed.

## Sign up and anonymous sign-in

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/signup" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -d '{"email": "iris.tanaka@orbit-labs.com", "password": "OrbitIris2026!",
       "data": {"full_name": "Iris Tanaka", "role": "analyst"}}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/signup/anonymous" -H "apikey: $ANON_KEY"
```

`mailer_autoconfirm` is off, so signup returns `{"user": …, "session": null}`
plus a confirmation token; call `/auth/v1/verify` to get a session.

## Current user

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/user" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $AMELIA"

curl -s -X PUT "$SUPABASE_AUTH_API_URL/auth/v1/user" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -H "Authorization: Bearer $JONAS" \
  -d '{"data": {"full_name": "Jonas Pereira", "role": "engineer"}}'
```

An email change is staged, not applied: the address only moves once the
`email_change` token is verified.

## One-time tokens

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/recover" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -d '{"email": "jonas.pereira@orbit-labs.com"}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/magiclink" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -d '{"email": "amelia.ortega@orbit-labs.com"}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/otp" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -d '{"email": "helena.park@orbit-labs.com"}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/verify" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -d '{"type": "confirmation", "token": "1f6b0d9c47a3428eb5710c82d64fa395"}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/resend" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -d '{"type": "signup", "email": "iris.tanaka@orbit-labs.com"}'
```

No mail is delivered, so `recover`, `magiclink`, `otp` and `resend` return the
`otp` and `token` in the body. `/auth/v1/verify` accepts either `token`, or
`otp` plus `email`. Token types: `confirmation`, `recovery`, `magiclink`,
`email_change`, `invite`, `sms`.

Seeded one-time tokens:

| Token | Type | For | State |
|-------|------|-----|-------|
| `1f6b0d9c47a3428eb5710c82d64fa395` | `confirmation` | rohit.bansal | unused |
| `8c30a7f52d194be6a0c17b3d95e408f2` | `recovery` | jonas.pereira | unused |
| `47d9e01b6c3f4a82b95c0d716ef23a48` | `magiclink` | amelia.ortega | already used → 403 |

## OAuth

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/authorize?provider=github&redirect_to=https://app.orbit-labs.com/callback" \
  -H "apikey: $ANON_KEY"
```

Enabled providers come from `settings.external`: `email`, `phone`,
`anonymous_users`, `github`, `google`. `gitlab`, `apple`, `azure` and `saml` are
off and return 400 `provider_disabled`.

## MFA

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/factors" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -H "Authorization: Bearer $JONAS" \
  -d '{"factor_type": "totp", "friendly_name": "Laptop authenticator"}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/factors/e97d2b40-5c81-4f36-a729-1b6e0d94c8f5/challenge" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $AMELIA"

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/factors/e97d2b40-5c81-4f36-a729-1b6e0d94c8f5/verify" \
  -H 'Content-Type: application/json' -H "apikey: $ANON_KEY" \
  -H "Authorization: Bearer $AMELIA" \
  -d '{"challenge_id": "b7d1e6c4-08a3-4f52-9e7b-2c60d81f4a93", "code": "482913"}'

curl -s -X DELETE "$SUPABASE_AUTH_API_URL/auth/v1/factors/af5810c6-72b3-4e09-95d1-c0e3b74f2681" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $JONAS"
```

Enrol and challenge both return the code the mock expects, since no authenticator
app is really involved. A successful verify promotes the session to `aal2` and
flips an `unverified` factor to `verified`. Challenge `b7d1e6c4-08a3-4f52-9e7b-2c60d81f4a93`
is seeded open against amelia's factor.

## Admin (service key required)

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/users?page=1&per_page=5" -H "apikey: $SERVICE_KEY"
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/users/d05b3f61-9c27-4e8a-b134-6a8d0e52f7c3" \
  -H "apikey: $SERVICE_KEY"

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/admin/users" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -d '{"email": "ops-bot@orbit-labs.com", "password": "OrbitOps2026!",
       "email_confirm": true, "user_metadata": {"full_name": "Ops Bot", "role": "service"}}'

curl -s -X PUT "$SUPABASE_AUTH_API_URL/auth/v1/admin/users/d05b3f61-9c27-4e8a-b134-6a8d0e52f7c3" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -d '{"ban_duration": "none"}'

curl -s -X DELETE "$SUPABASE_AUTH_API_URL/auth/v1/admin/users/0f9a2c7d-4e61-4b03-8d75-3c1e9f60a284" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -d '{"should_soft_delete": true}'

curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/admin/generate_link" \
  -H 'Content-Type: application/json' -H "apikey: $SERVICE_KEY" \
  -d '{"type": "recovery", "email": "jonas.pereira@orbit-labs.com"}'

curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/audit?action=login&per_page=5" -H "apikey: $SERVICE_KEY"
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/sessions?user_id=3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901" \
  -H "apikey: $SERVICE_KEY"
```

`ban_duration` takes `24h` / `30m` / `90s`, or `none` to unban. `generate_link`
types: `signup`, `invite`, `magiclink`, `recovery`, `email_change_current`,
`email_change_new`. The sessions view strips access and refresh tokens.

## User ids

The same uuids appear as `public.profiles.id` in `supabase-api`:

| User | Id |
|------|----|
| amelia.ortega | `3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901` |
| jonas.pereira | `6b2d4e10-77c3-4a9b-8f52-1d9e6c02a445` |
| helena.park | `a41f7c88-5be9-42d7-9c03-77e2f8b41d16` |
| rohit.bansal | `c72e5a94-1d38-4b6f-ae90-2f4b8c07d532` |
| noor.aziz | `d05b3f61-9c27-4e8a-b134-6a8d0e52f7c3` |
| sync-bot | `0f9a2c7d-4e61-4b03-8d75-3c1e9f60a284` |
| anonymous | `7c4e1b8a-0d33-4f95-b201-8e6a3c17d940` |

## Errors

| HTTP | `error_code` | When |
|------|--------------|------|
| 400 | `invalid_credentials` | wrong password, unknown email, or an account with no password |
| 400 | `email_not_confirmed` | password is right but the address is unconfirmed |
| 400 | `mfa_verification_failed` | wrong TOTP code |
| 400 | `refresh_token_not_found` | unknown or revoked refresh token |
| 400 | `provider_disabled` | OAuth provider is off in settings |
| 401 | `no_authorization` | missing or dead bearer token |
| 403 | `user_banned` | `banned_until` is in the future |
| 403 | `not_admin` | admin endpoint without the service key |
| 403 | `otp_expired` | one-time token spent, expired or of the wrong type |
| 404 | `user_not_found` / `mfa_factor_not_found` / `mfa_challenge_not_found` | unknown id |
| 422 | `user_already_exists` / `email_exists` | duplicate address |
| 422 | `weak_password` | shorter than 6 characters |
| 422 | `validation_failed` | missing or malformed field |
