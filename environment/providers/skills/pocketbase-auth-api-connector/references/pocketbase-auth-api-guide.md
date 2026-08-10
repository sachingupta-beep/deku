# PocketBase Auth API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$POCKETBASE_AUTH_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `POCKETBASE_AUTH_API_URL` | Base URL for all requests |

Set the tokens once to follow the examples:

```bash
export SUPERUSER='eyJhbGciOiJIUzI1NiJ9.sup0admin000001.tk_ops_e64a'
export AMELIA='eyJhbGciOiJIUzI1NiJ9.usramelia000001.tk_amelia_5f1c'
export JONAS='eyJhbGciOiJIUzI1NiJ9.usrjonas0000002.tk_jonas_2b90'
```

## Seed accounts

| Collection | Identity | Password | Quirk |
|------------|----------|----------|-------|
| `users` | `amelia.ortega@orbit-labs.com` | `OrbitStatus2026!` | MFA on → password auth answers 401 with an `mfaId` |
| `users` | `jonas.pereira@orbit-labs.com` | `OrbitJonas2026!` | google external auth; unused reset token |
| `users` | `helena.park@orbit-labs.com` | _(none)_ | github only → password auth is 400 |
| `users` | `rohit.bansal@orbit-labs.com` | `OrbitRohit2026!` | pending email-change token |
| `users` | `noor.aziz@orbit-labs.com` | `OrbitNoor2026!` | `verified = false` → authRule refuses with 403 |
| `users` | `orbit_sync_bot` | `OrbitSyncBot2026!` | username identity, not email |
| `_superusers` | `ops@orbit-labs.com` | `OrbitSuperuser2026!` | may impersonate |
| `_superusers` | `deploy@orbit-labs.com` | `OrbitDeploy2026!` | |

Record ids: `usramelia000001`, `usrjonas0000002`, `usrhelena000003`,
`usrrohit0000004`, `usrnoor00000005`, `usrsyncbot00006`, `sup0admin000001`,
`sup0deploy00002`. They match `pocketbase-api`'s `users` collection.

## Health and discovery

```bash
curl -s "$POCKETBASE_AUTH_API_URL/health"
curl -s "$POCKETBASE_AUTH_API_URL/api/health"
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-methods"
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/_superusers/auth-methods"
curl -s "$POCKETBASE_AUTH_API_URL/api/collections" -H "Authorization: $SUPERUSER"
```

`auth-methods` is the discovery document: which identity fields the collection
accepts, whether OTP and MFA are on, and one fresh OAuth2 `state` /
`codeVerifier` / `codeChallenge` per enabled provider.

## Password auth

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!"}'

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "orbit_sync_bot", "password": "OrbitSyncBot2026!"}'

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/_superusers/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "ops@orbit-labs.com", "password": "OrbitSuperuser2026!"}'
```

Returns `{token, record}`. `_superusers` rejects a username identity because its
`identityFields` are `["email"]` only.

## OTP and MFA

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/request-otp" \
  -H 'Content-Type: application/json' -d '{"email": "jonas.pereira@orbit-labs.com"}'

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-otp" \
  -H 'Content-Type: application/json' \
  -d '{"otpId": "otp1amelia00001", "password": "47182930", "mfaId": "mfa1amelia00001"}'
```

MFA is a two-request handshake: the first factor returns
`401 {"data": {"mfaId": ...}}`, and the second must be a **different** method
quoting that `mfaId`. Seeded: OTP `otp1amelia00001` (code `47182930`, open),
`otp2jonas000002` (expired), MFA record `mfa1amelia00001` (method `password`).

An OTP login also marks the record verified.

## OAuth2

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-oauth2" \
  -H 'Content-Type: application/json' \
  -d '{"provider": "github", "code": "2210448", "codeVerifier": "6f3a1c85d0b74e29",
       "redirectURL": "https://status.orbit-labs.com/oauth"}'
```

There is no provider to call, so the `code` names the external account:

| Code | Result |
|------|--------|
| `1840221` (github) | signs in amelia |
| `2210448` (github) | signs in helena |
| `108224503917744021883` (google) | signs in jonas |
| anything else | creates a record; `meta.isNew` is `true` |

`gitlab` is registered but disabled, and `_superusers` has OAuth2 off — both are
400.

## Refresh and impersonation

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-refresh" \
  -H "Authorization: $AMELIA"

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/impersonate/usrrohit0000004" \
  -H 'Content-Type: application/json' -H "Authorization: $SUPERUSER" \
  -d '{"duration": 600}'
```

Refreshing against the wrong collection is 403. Impersonation is superuser-only.

## Verification, password reset, email change

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/request-verification" \
  -H 'Content-Type: application/json' -d '{"email": "noor.aziz@orbit-labs.com"}'

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/confirm-verification" \
  -H 'Content-Type: application/json' -d '{"token": "pb_verif_9c41e7a5b2d80f36"}'

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/request-password-reset" \
  -H 'Content-Type: application/json' -d '{"email": "jonas.pereira@orbit-labs.com"}'

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/confirm-password-reset" \
  -H 'Content-Type: application/json' \
  -d '{"token": "pb_reset_4f82c0e91b7d5a63", "password": "OrbitJonasNew2026!",
       "passwordConfirm": "OrbitJonasNew2026!"}'

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/request-email-change" \
  -H 'Content-Type: application/json' -H "Authorization: $JONAS" \
  -d '{"newEmail": "jonas.pereira@orbit-labs.io"}'

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/confirm-email-change" \
  -H 'Content-Type: application/json' \
  -d '{"token": "pb_email_7b39f1c084a6d25e", "password": "OrbitRohit2026!"}'
```

Seeded mail tokens:

| Token | Type | For | State |
|-------|------|-----|-------|
| `pb_verif_9c41e7a5b2d80f36` | verification | noor | unused |
| `pb_reset_4f82c0e91b7d5a63` | passwordReset | jonas | unused |
| `pb_reset_1a05d7b3e6c94f28` | passwordReset | amelia | already spent → 400 |
| `pb_email_7b39f1c084a6d25e` | emailChange | rohit → `@orbit-labs.io` | unused |

Confirming an email change re-checks the password: a stolen token alone must not
complete it. Both a password reset and an email change rotate the record's
`tokenKey`, invalidating every token already issued for it.

## Auth records

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/records?page=1&perPage=5" \
  -H "Authorization: $JONAS"
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/records?role=engineer" \
  -H "Authorization: $JONAS"
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrjonas0000002" \
  -H "Authorization: $JONAS"

curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/records" \
  -H 'Content-Type: application/json' \
  -d '{"email": "iris.tanaka@orbit-labs.com", "password": "OrbitIris2026!",
       "passwordConfirm": "OrbitIris2026!", "username": "iris", "name": "Iris Tanaka"}'

curl -s -X PATCH "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrjonas0000002" \
  -H 'Content-Type: application/json' -H "Authorization: $JONAS" \
  -d '{"name": "Jonas Pereira", "emailVisibility": true}'

curl -s -X DELETE "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrsyncbot00006" \
  -H "Authorization: $SUPERUSER"
```

Rules the mock enforces:

- Listing or viewing requires a token; `_superusers` requires a superuser one.
- A record may edit itself, but not set `role` or `verified` — those need a
  superuser.
- Changing a password as the record itself requires `oldPassword`.
- Another record's `email` is masked unless it set `emailVisibility`, the viewer
  is that record, or the viewer is a superuser.
- The last superuser cannot be deleted.

## External auth providers

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrjonas0000002/external-auths" \
  -H "Authorization: $JONAS"

curl -s -X DELETE \
  "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usramelia000001/external-auths/github" \
  -H "Authorization: $SUPERUSER"
```

Unlinking the last provider from a record with no password is refused with 400 —
it would lock the record out permanently.

## Logs (superuser only)

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/logs?page=1&perPage=5" -H "Authorization: $SUPERUSER"
curl -s "$POCKETBASE_AUTH_API_URL/api/logs?authId=usramelia000001" -H "Authorization: $SUPERUSER"
curl -s "$POCKETBASE_AUTH_API_URL/api/logs?status=400" -H "Authorization: $SUPERUSER"
curl -s "$POCKETBASE_AUTH_API_URL/api/logs/stats" -H "Authorization: $SUPERUSER"
```

## Errors

| HTTP | `data` code | When |
|------|-------------|------|
| 400 | `validation_invalid_credentials` | wrong password, unknown identity, or no password hash |
| 400 | `validation_required` | a required field is missing |
| 400 | `validation_not_unique` | email or username already taken |
| 400 | `validation_length_out_of_range` | password shorter than the collection minimum |
| 400 | `validation_values_mismatch` | `passwordConfirm` differs |
| 400 | `validation_invalid_token` / `validation_expired_token` | mail token unknown, spent or expired |
| 400 | `validation_invalid_otp_id` / `validation_expired_otp` | OTP unknown, spent or expired |
| 400 | `validation_invalid_provider` | OAuth2 provider disabled or not on the collection |
| 401 | `mfaId` present | first factor accepted, second required |
| 401 | — | missing or invalidated token |
| 403 | — | authRule not satisfied, or the action needs a superuser |
| 404 | — | unknown collection or record |
