# PocketBase Auth Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$POCKETBASE_AUTH_API_URL`; responses are verbatim (long objects
elided with `…`). Examples assume:

```bash
export SUPERUSER='eyJhbGciOiJIUzI1NiJ9.sup0admin000001.tk_ops_e64a'
export AMELIA='eyJhbGciOiJIUzI1NiJ9.usramelia000001.tk_amelia_5f1c'
export JONAS='eyJhbGciOiJIUzI1NiJ9.usrjonas0000002.tk_jonas_2b90'
```

A token is `<header>.<recordId>.<tokenKey>` and resolves only while the record
still carries that `tokenKey`. The `Bearer` prefix is optional.

## Health

```bash
curl -s "$POCKETBASE_AUTH_API_URL/health"
```
```json
{"status": "ok"}
```

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/health"
```
```json
{"code": 200, "message": "API is healthy.",
 "data": {"canBackup": true, "realtime": false, "version": "v0.24.4"}}
```

## Auth methods: the two collections differ

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-methods"
```
```json
{
  "mfa": {"enabled": true, "duration": 1800},
  "otp": {"enabled": true, "duration": 180, "length": 8},
  "password": {"enabled": true, "identityFields": ["email", "username"]},
  "oauth2": {
    "enabled": true,
    "providers": [
      {"name": "github", "displayName": "GitHub",
       "state": "5e94a86d75dd4e5584f84fdb8a52a96e",
       "authURL": "https://github.com/login/oauth/authorize?client_id=Iv1.orbit-labs-status&response_type=code&scope=read:user+user:email&state=5e94a86d75dd4e5584f84fdb8a52a96e&redirect_uri=",
       "codeVerifier": "96eda9ddcb6341f98eb7e06722e723ba08b4c7a4bae44cb888f930a1861dc17a",
       "codeChallenge": "bbfe3993ceed6a4a2ff71e7c1e7ae99ad4e5ce32f57",
       "codeChallengeMethod": "S256", "pkce": true},
      {"name": "google", "displayName": "Google", "…": "…"}
    ]
  }
}
```

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/_superusers/auth-methods"
```
```json
{"mfa": {"enabled": false, "duration": 1800},
 "otp": {"enabled": false, "duration": 180, "length": 8},
 "password": {"enabled": true, "identityFields": ["email"]},
 "oauth2": {"enabled": false, "providers": []}}
```

## Auth with a password

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!"}'
```
```json
{
  "token": "eyJhbGciOiJIUzI1NiJ9.usrjonas0000002.tk_jonas_2b90",
  "record": {
    "id": "usrjonas0000002",
    "collectionId": "colusers0000001",
    "collectionName": "users",
    "username": "jonas",
    "email": "jonas.pereira@orbit-labs.com",
    "emailVisibility": false,
    "verified": true,
    "name": "Jonas Pereira",
    "avatar": "jonas_4bQ7x.png",
    "role": "engineer",
    "oncall": true,
    "created": "2024-02-04 11:30:00.000Z",
    "updated": "2026-05-25 17:40:00.000Z"
  }
}
```

`users` accepts a username too, because its `identityFields` are
`["email", "username"]`:

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "orbit_sync_bot", "password": "OrbitSyncBot2026!"}'
```

`_superusers` does not — its `identityFields` are `["email"]`:

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/_superusers/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "ops", "password": "OrbitSuperuser2026!"}'
```
```json
{"code": 400, "message": "Failed to authenticate.",
 "data": {"identity": {"code": "validation_invalid_credentials",
                       "message": "Invalid login credentials."}}}
```

## Two different failures

A wrong password, an unknown identity and an OAuth2-only record are
indistinguishable — all `400 validation_invalid_credentials`. A record whose
password is *correct* but which fails the collection's `authRule` is a different
answer:

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "noor.aziz@orbit-labs.com", "password": "OrbitNoor2026!"}'
```
```json
{"code": 403,
 "message": "The request doesn't satisfy the collection requirements to authenticate.",
 "data": {}}
```

`users` carries `authRule = "verified = true"` and Noor's record is unverified.

## MFA: a two-request handshake

The first factor succeeds and PocketBase answers 401 with an `mfaId`:

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-password" \
  -H 'Content-Type: application/json' \
  -d '{"identity": "amelia.ortega@orbit-labs.com", "password": "OrbitStatus2026!"}'
```
```json
{"code": 401, "message": "Missing second auth factor.",
 "data": {"mfaId": "mfa9308dac8186f"}}
```

The second factor must be a *different* method and quote that `mfaId`. The seed
carries an open password-factor challenge (`mfa1amelia00001`) and an open OTP
(`otp1amelia00001`):

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-otp" \
  -H 'Content-Type: application/json' \
  -d '{"otpId": "otp1amelia00001", "password": "47182930", "mfaId": "mfa1amelia00001"}'
```
```json
{"token": "eyJhbGciOiJIUzI1NiJ9.usramelia000001.tk_amelia_5f1c",
 "record": {"id": "usramelia000001", "username": "amelia", "…": "…"}}
```

## Request an OTP

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/request-otp" \
  -H 'Content-Type: application/json' \
  -d '{"email": "jonas.pereira@orbit-labs.com"}'
```
```json
{"otpId": "otpa4f44180096d", "password": "22292002",
 "note": "the one-time password is returned because no mail is actually delivered by the mock"}
```

An unknown address still gets an `otpId`, so the response cannot enumerate
accounts:

```json
{"otpId": "otp38beeb75a63c"}
```

## OAuth2

There is no provider to call, so the authorization `code` names the external
account. A code matching a seeded `providerId` signs that record in:

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-oauth2" \
  -H 'Content-Type: application/json' \
  -d '{"provider": "github", "code": "2210448", "codeVerifier": "6f3a1c85d0b74e29"}'
```
```json
{
  "token": "eyJhbGciOiJIUzI1NiJ9.usrhelena000003.tk_helena_7fT1",
  "record": {"id": "usrhelena000003", "username": "helena",
             "email": "helena.park@orbit-labs.com", "verified": true, "…": "…"},
  "meta": {"id": "2210448", "name": "Helena Park", "username": "helena",
           "email": "helena.park@orbit-labs.com", "isNew": false,
           "avatarURL": "", "accessToken": "gho_339427723938461fbb66d71c",
           "refreshToken": "", "expiry": "2026-08-05 20:46:57.000Z",
           "rawUser": {"id": "2210448", "login": "helena"}}
}
```

Any other code creates a record and reports `meta.isNew = true`. A provider that
is disabled, or not listed on the collection, is refused:

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-with-oauth2" \
  -H 'Content-Type: application/json' -d '{"provider": "gitlab", "code": "77120"}'
```
```json
{"code": 400, "message": "An error occurred while submitting the form.",
 "data": {"provider": {"code": "validation_invalid_provider",
                       "message": "Missing or invalid provider."}}}
```

## Impersonation (superuser only)

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/impersonate/usrrohit0000004" \
  -H 'Content-Type: application/json' -H "Authorization: $SUPERUSER" \
  -d '{"duration": 600}'
```
```json
{"token": "eyJhbGciOiJIUzI1NiJ9.usrrohit0000004.tk_rohit_c81b",
 "record": {"id": "usrrohit0000004", "username": "rohit",
            "email": "rohit.bansal@orbit-labs.com", "role": "support", "…": "…"},
 "duration": 600}
```

## Records and `emailVisibility`

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/records?page=1&perPage=2" \
  -H "Authorization: $JONAS"
```
```json
{
  "page": 1, "perPage": 2, "totalItems": 6, "totalPages": 3,
  "items": [
    {"id": "usramelia000001", "username": "amelia",
     "email": "amelia.ortega@orbit-labs.com", "emailVisibility": true,
     "verified": true, "name": "Amelia Ortega", "role": "owner", "…": "…"},
    {"id": "usrjonas0000002", "username": "jonas",
     "email": "jonas.pereira@orbit-labs.com", "emailVisibility": false,
     "verified": true, "name": "Jonas Pereira", "role": "engineer", "…": "…"}
  ]
}
```

Amelia's email shows because she opted in; Jonas's shows because he *is* the
viewer. Rohit's does not:

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrrohit0000004" \
  -H "Authorization: $JONAS"
```
```json
{"id": "usrrohit0000004", "username": "rohit", "email": "",
 "emailVisibility": false, "verified": true, "name": "Rohit Bansal", "…": "…"}
```

## A record cannot promote itself

```bash
curl -s -X PATCH "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrjonas0000002" \
  -H 'Content-Type: application/json' -H "Authorization: $JONAS" \
  -d '{"role": "owner"}'
```
```json
{"code": 403,
 "message": "The authorized record model is not allowed to perform this action.",
 "data": {}}
```

Nor change its password without the old one:

```bash
curl -s -X PATCH "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrjonas0000002" \
  -H 'Content-Type: application/json' -H "Authorization: $JONAS" \
  -d '{"password": "OrbitJonasNew2026!", "passwordConfirm": "OrbitJonasNew2026!"}'
```
```json
{"code": 400, "message": "Failed to update record.",
 "data": {"oldPassword": {"code": "validation_required",
                          "message": "Missing required value."}}}
```

## External auth providers

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrjonas0000002/external-auths" \
  -H "Authorization: $JONAS"
```
```json
[{"id": "eah3jonas000003", "collectionRef": "colusers0000001",
  "recordRef": "usrjonas0000002", "provider": "google",
  "providerId": "108224503917744021883",
  "created": "2025-08-06 13:10:00.000Z", "updated": "2026-05-25 17:40:00.000Z"}]
```

Unlinking the last one from a record with no password would lock it out for
good, so it is refused:

```bash
curl -s -X DELETE \
  "$POCKETBASE_AUTH_API_URL/api/collections/users/records/usrhelena000003/external-auths/github" \
  -H "Authorization: $SUPERUSER"
```
```json
{"code": 400,
 "message": "Cannot unlink the last external auth provider from a record without a password.",
 "data": {}}
```

## Auth logs (superuser only)

```bash
curl -s "$POCKETBASE_AUTH_API_URL/api/logs/stats" -H "Authorization: $SUPERUSER"
```
```json
[{"total": 1, "date": "", "message": "auth-refresh"},
 {"total": 2, "date": "", "message": "auth-with-oauth2"},
 {"total": 6, "date": "", "message": "auth-with-password"},
 {"total": 1, "date": "", "message": "request-otp"},
 {"total": 1, "date": "", "message": "request-password-reset"}]
```

## A password reset invalidates every issued token

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/confirm-password-reset" \
  -H 'Content-Type: application/json' \
  -d '{"token": "pb_reset_4f82c0e91b7d5a63", "password": "OrbitJonasNew2026!",
       "passwordConfirm": "OrbitJonasNew2026!"}'
```
```
204 No Content
```

Jonas's `tokenKey` has rotated, so the token minted before the reset no longer
resolves:

```bash
curl -s -X POST "$POCKETBASE_AUTH_API_URL/api/collections/users/auth-refresh" \
  -H "Authorization: $JONAS"
```
```json
{"code": 401,
 "message": "The request requires valid record authorization token to be set.",
 "data": {}}
```

There is no session row to delete — the old token simply stops verifying.
