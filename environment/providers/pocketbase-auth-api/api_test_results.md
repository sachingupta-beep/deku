# PocketBase Auth Mock API — Test Results

Base URL: `http://localhost:8114` (in docker-compose: `http://pocketbase-auth-api:8114`)

## Endpoints covered

| Method | Path                                                                  | Status          |
|--------|-----------------------------------------------------------------------|-----------------|
| GET    | /health                                                               | 200             |
| GET    | /api/health                                                           | 200             |
| GET    | /api/collections                                                      | 200/403         |
| GET    | /api/collections/{collection}/auth-methods                            | 200/404         |
| POST   | /api/collections/{collection}/auth-with-password                      | 200/400/401/403 |
| POST   | /api/collections/{collection}/request-otp                             | 200/400         |
| POST   | /api/collections/{collection}/auth-with-otp                           | 200/400/401/403 |
| POST   | /api/collections/{collection}/auth-with-oauth2                        | 200/400/403     |
| POST   | /api/collections/{collection}/auth-refresh                            | 200/401/403     |
| POST   | /api/collections/{collection}/impersonate/{id}                        | 200/403/404     |
| POST   | /api/collections/{collection}/request-verification                    | 204/400         |
| POST   | /api/collections/{collection}/confirm-verification                    | 204/400         |
| POST   | /api/collections/{collection}/request-password-reset                  | 204/400         |
| POST   | /api/collections/{collection}/confirm-password-reset                  | 204/400         |
| POST   | /api/collections/{collection}/request-email-change                    | 204/400/401     |
| POST   | /api/collections/{collection}/confirm-email-change                    | 204/400         |
| GET    | /api/collections/{collection}/records                                 | 200/403/404     |
| POST   | /api/collections/{collection}/records                                 | 200/400/403     |
| GET    | /api/collections/{collection}/records/{id}                            | 200/403/404     |
| PATCH  | /api/collections/{collection}/records/{id}                            | 200/400/403/404 |
| DELETE | /api/collections/{collection}/records/{id}                            | 204/400/403/404 |
| GET    | /api/collections/{collection}/records/{id}/external-auths             | 200/403/404     |
| DELETE | /api/collections/{collection}/records/{id}/external-auths/{provider}  | 200/400/403/404 |
| GET    | /api/logs                                                             | 200/403         |
| GET    | /api/logs/stats                                                       | 200/403         |

Collection run: **PASS 42 / WARN 43 / FAIL 0 / SKIP 0**. Every WARN is an
intentional error-path request, labelled `(N expected)` in the collection.

## Seed data summary

- Auth collections: 2
  - `users` — identities `email` + `username`, `authRule = "verified = true"`,
    OTP on (8 digits, 180s), MFA on (1800s), OAuth2 `github` + `google`,
    minimum password length 8
  - `_superusers` — system collection, identity `email` only, no OTP, no MFA, no
    OAuth2, minimum password length 10
- Auth records: 8 (6 in `users`, 2 in `_superusers`) — same record ids as `pocketbase-api`
  - `amelia` — `mfaEnabled`, `emailVisibility = true`, github external auth
  - `jonas` — google external auth, an unused password-reset token
  - `helena` — **no password hash**; github is her only sign-in method
  - `rohit` — a pending **email-change** token to `@orbit-labs.io`
  - `noor` — **`verified = false`**, so the `users` authRule refuses the login
  - `orbit_sync_bot` — authenticates by **username**, not email
  - `ops@orbit-labs.com`, `deploy@orbit-labs.com` — superusers
- External auths: 3 (`github` ×2, `google` ×1)
- OAuth2 providers: 3 (`github`, `google` enabled; `gitlab` disabled)
- Mail tokens: 4 — an unused verification, an unused reset, a **spent** reset, a
  pending email change
- OTP requests: 2 — one open, one **expired**
- MFA records: 1 open password-factor challenge for `amelia`
- Auth logs: 8, including two failures (a 400 and a 403)
- Settings: singleton from `settings.json` (PocketBase `v0.24.4`)

Seed passwords are listed in `settings.json` under `seed_credentials`.

## Tokens

Tokens are `<header>.<recordId>.<tokenKey>` and resolve only while the record
still carries that `tokenKey`:

| Token | Record |
|-------|--------|
| `eyJhbGciOiJIUzI1NiJ9.usramelia000001.tk_amelia_5f1c` | amelia (`users`) |
| `eyJhbGciOiJIUzI1NiJ9.usrjonas0000002.tk_jonas_2b90` | jonas (`users`) |
| `eyJhbGciOiJIUzI1NiJ9.usrsyncbot00006.tk_syncbot_7d4f` | sync bot (`users`) |
| `eyJhbGciOiJIUzI1NiJ9.sup0admin000001.tk_ops_e64a` | ops (`_superusers`) |
| `eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status` | the legacy token `pocketbase-api` mints, accepted as ops |

The `Bearer` prefix is optional, as in PocketBase.

## Notes

- **Auth is per collection.** The same request against `users` and
  `_superusers` behaves differently: `_superusers` refuses a username identity,
  refuses OTP and refuses OAuth2, all from its own seeded configuration rather
  than a hard-coded branch.
- **A password or email change rotates `tokenKey`**, which invalidates every
  token already issued for that record. The collection ends by resetting jonas's
  password and then showing his pre-reset token fail with 401.
- **The `authRule` is real.** `users` carries `verified = true`, so an
  unverified record authenticates its password correctly and is still refused
  with 403 — a different outcome from a wrong password, which is 400.
- **No account enumeration.** An unknown identity, a wrong password and a record
  with no password hash all return the same
  `400 validation_invalid_credentials`. `request-otp`,
  `request-password-reset` and `request-verification` answer the same way for a
  known and an unknown address.
- **MFA is a two-request handshake.** The first factor returns
  `401 {"data": {"mfaId": ...}}`; the second must be a *different* method and
  quote that `mfaId`. Replaying the same method is refused with
  `mfa_same_method`.
- **OAuth2 has no upstream to call**, so the authorization `code` names the
  external account: a code matching a seeded `providerId` signs that record in,
  anything else creates a record and reports `meta.isNew = true`.
- Unlinking the last external auth from a record with no password is refused —
  it would lock the record out permanently.
- `emailVisibility` is honoured: another record's email is masked unless it
  opted in, the viewer is the record itself, or the viewer is a superuser.
- Mail flows return 204 with an empty body in PocketBase; because nothing is
  actually delivered, the mock returns the token it would have emailed with a
  200 instead, and notes why.
- Errors carry the PocketBase body shape — `{"code": 400, "message": "...",
  "data": {"<field>": {"code": "...", "message": "..."}}}` — alongside the
  fleet-standard `error` key.
- Mutations (new records, rotated keys, spent tokens, unlinked providers) are
  held in process memory and reset on container restart.
