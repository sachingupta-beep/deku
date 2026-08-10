# Supabase Auth (GoTrue) Mock API — Test Results

Base URL: `http://localhost:8113` (in docker-compose: `http://supabase-auth-api:8113`)

## Endpoints covered

| Method | Path                                              | Status          |
|--------|---------------------------------------------------|-----------------|
| GET    | /health                                           | 200             |
| GET    | /auth/v1/health                                   | 200             |
| GET    | /auth/v1/settings                                 | 200             |
| POST   | /auth/v1/signup                                   | 200/422         |
| POST   | /auth/v1/signup/anonymous                         | 200/422         |
| POST   | /auth/v1/token?grant_type=password                | 200/400/403     |
| POST   | /auth/v1/token?grant_type=refresh_token           | 200/400/403     |
| POST   | /auth/v1/logout                                   | 200/401         |
| GET    | /auth/v1/user                                     | 200/401/404     |
| PUT    | /auth/v1/user                                     | 200/401/422     |
| POST   | /auth/v1/recover                                  | 200             |
| POST   | /auth/v1/magiclink                                | 200             |
| POST   | /auth/v1/otp                                      | 200/422         |
| POST   | /auth/v1/verify                                   | 200/400/403     |
| POST   | /auth/v1/resend                                   | 200/400/422     |
| GET    | /auth/v1/authorize                                | 200/400         |
| POST   | /auth/v1/factors                                  | 200/401/422     |
| POST   | /auth/v1/factors/{id}/challenge                   | 200/401/404     |
| POST   | /auth/v1/factors/{id}/verify                      | 200/400/401/404 |
| DELETE | /auth/v1/factors/{id}                             | 200/401/404     |
| GET    | /auth/v1/admin/users                              | 200/403         |
| POST   | /auth/v1/admin/users                              | 201/403/422     |
| GET    | /auth/v1/admin/users/{id}                         | 200/403/404     |
| PUT    | /auth/v1/admin/users/{id}                         | 200/403/404/422 |
| DELETE | /auth/v1/admin/users/{id}                         | 200/403/404     |
| POST   | /auth/v1/admin/generate_link                      | 200/403/404/422 |
| GET    | /auth/v1/admin/audit                              | 200/403         |
| GET    | /auth/v1/admin/sessions                           | 200/403         |

Collection run: **PASS 32 / WARN 31 / FAIL 0 / SKIP 0**. Every WARN is an
intentional error-path request and is labelled `(N expected)` in the collection —
an auth service is mostly defined by the requests it refuses, so the collection
exercises each refusal explicitly.

## Seed data summary

- Users: 7 (`auth.users`, uuid PKs) — ids match `public.profiles` in `supabase-api`
  - `amelia.ortega@orbit-labs.com` — owner, email + GitHub identities, **verified** TOTP factor
  - `jonas.pereira@orbit-labs.com` — engineer, **unverified** TOTP factor pending
  - `helena.park@orbit-labs.com` — **GitHub identity only**, no password hash
  - `rohit.bansal@orbit-labs.com` — **email not confirmed**
  - `noor.aziz@orbit-labs.com` — **banned until 2027-01-01**
  - `sync-bot@orbit-labs.com` — service account
  - one **anonymous** user with no email
- Identities: 7 (5 `email`, 2 `github`)
- MFA factors: 2 TOTP (`verified` / `unverified`)
- Sessions: 3 live, with fixed access tokens (amelia, jonas, sync-bot)
- Refresh tokens: 4 (one already revoked, for the reuse path)
- One-time tokens: 3 (an unused confirmation, an unused recovery, a used magic link)
- MFA challenges: 1 open challenge against amelia's verified factor
- Audit log: 8 entries across `login`, `logout`, `user_signedup`,
  `user_recovery_requested`, `user_banned`, `factor_verified`
- Settings: singleton from `settings.json` (GoTrue `v2.158.1`)

Seed passwords are listed in `settings.json` under `seed_credentials`.

## Keys, tokens and roles

Two different credentials do two different jobs:

| Header                                            | Selects                                          |
|---------------------------------------------------|--------------------------------------------------|
| `apikey: ...anon.orbit-labs-selfhost` (or absent) | project role `anon` — admin endpoints return 403 |
| `apikey: ...service_role.orbit-labs-selfhost`     | project role `service_role` — admin allowed      |
| `Authorization: Bearer <access_token>`            | the end user, resolved to a live session row     |

The keys are byte-identical to `supabase-api`'s, because it is the same project.
A bearer that is *not* a live access token resolves to no session, so end-user
endpoints answer 401 rather than guessing.

## Notes

- Passwords are verified as `sha256(password_salt + password)`. The hash and the
  salt never appear in a response.
- `POST /auth/v1/token` is one endpoint with a `grant_type` query parameter, as
  in GoTrue: `password` and `refresh_token`. Any other value is 400.
- `mailer_autoconfirm` is off, so `POST /auth/v1/signup` returns
  `{"user": ..., "session": null}` and mints a confirmation token; the session
  only appears after `POST /auth/v1/verify`.
- Refresh-token rotation is on: refreshing revokes the presented token, issues a
  descendant with `parent` set, and re-mints the session's access token.
- Sign-in failures are deliberately indistinguishable: an unknown address, a
  wrong password and an OAuth-only account all return
  `400 invalid_credentials`, so the endpoint cannot enumerate accounts. Bans
  (403) and unconfirmed emails (400 `email_not_confirmed`) are reported only
  *after* the password checks out.
- `POST /auth/v1/recover` returns 200 for an unknown address for the same reason.
- Because no mail is delivered, `recover`, `magiclink`, `otp`, `resend` and
  `admin/generate_link` return the `otp` and `token` in the body. Real GoTrue
  returns only `{}`.
- MFA: enrol returns the TOTP secret and the code the mock expects; challenge
  returns `expected_code`; a successful verify promotes the session to `aal2` and
  flips an `unverified` factor to `verified`.
- Admin `ban_duration` accepts `24h` / `30m` / `90s`, or `none` to unban.
- Deletes are hard by default; `{"should_soft_delete": true}` stamps `deleted_at`
  and keeps the row. Both revoke every session the user holds.
- Errors carry the GoTrue body shape — `{"code": 400, "error_code":
  "invalid_credentials", "msg": "..."}` — with `code` mirroring the HTTP status.
- Mutations (new users, sessions, tokens, factors, bans) are held in process
  memory and reset on container restart.
