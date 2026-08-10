# Ory Kratos Mock API — Test Results

Base URL: `http://localhost:8119` (in docker-compose: `http://ory-kratos-api:8119`)

## Endpoints covered

### Public: self-service flows

| Method | Path                                              | Status          |
|--------|---------------------------------------------------|-----------------|
| GET    | /health · /health/alive · /health/ready · /version | 200             |
| GET    | /schemas · /schemas/{id}                          | 200/404         |
| GET    | /self-service/login/{api\|browser}                 | 200/401/404     |
| GET    | /self-service/registration/{api\|browser}          | 200/404         |
| GET    | /self-service/recovery/{api\|browser}              | 200/404         |
| GET    | /self-service/verification/{api\|browser}          | 200/404         |
| GET    | /self-service/settings/{api\|browser}              | 200/401/404     |
| GET    | /self-service/{type}/flows?id=                     | 200/404/410     |
| POST   | /self-service/login?flow=                          | 200/400/403/404/410 |
| POST   | /self-service/registration?flow=                   | 200/400/403/404/410 |
| POST   | /self-service/recovery?flow=                       | 200/400/403/404/410 |
| POST   | /self-service/verification?flow=                   | 200/400/403/404/410 |
| POST   | /self-service/settings?flow=                       | 200/400/401/403/404 |
| DELETE | /self-service/logout/api                           | 204/401         |

### Public: sessions

| Method | Path                     | Status      |
|--------|--------------------------|-------------|
| GET    | /sessions/whoami         | 200/401     |
| GET    | /sessions                | 200/401     |
| DELETE | /sessions                | 200/401     |
| DELETE | /sessions/{id}           | 204/401/404 |

### Admin

| Method | Path                                                  | Status          |
|--------|-------------------------------------------------------|-----------------|
| GET/POST | /admin/identities                                   | 200/201/400/409 |
| GET/PUT/PATCH/DELETE | /admin/identities/{id}                  | 200/204/400/404 |
| GET/DELETE | /admin/identities/{id}/sessions                   | 200/204/404     |
| DELETE | /admin/identities/{id}/credentials/{type}             | 204/400/404     |
| POST   | /admin/recovery/code · /admin/recovery/link           | 200/201/404     |
| GET    | /admin/sessions · /admin/sessions/{id}                | 200/404         |
| PATCH  | /admin/sessions/{id}/extend                           | 200/400/404     |
| DELETE | /admin/sessions/{id}                                  | 204/404         |
| GET    | /admin/courier/messages · /messages/{id}              | 200/404         |

Collection run: **PASS 59 / WARN 53 / FAIL 0 / SKIP 0**. Every WARN is an
intentional error-path request, labelled `(N expected)` in the collection. The
count is high because a flow-based API is largely defined by how it refuses a
submission, and each refusal has its own shape.

## Failed submissions re-render the flow

This is the part of Kratos that differs most from every other auth service in
the fleet. A bad login does not return `{"error": ...}`; it returns **400 with
the flow**, and the message lives on the node it belongs to:

```json
{
  "id": "f1a0c7e2-5b93-4d68-8017-2e6f931c5d47",
  "type": "api",
  "ui": {
    "action": "https://kratos.orbit-labs.com/self-service/login?flow=f1a0c7e2-…",
    "method": "POST",
    "nodes": [
      {"type": "input", "group": "password",
       "attributes": {"name": "identifier", "type": "text", "required": true},
       "messages": [{"id": 4000001, "text": "Property identifier is missing.",
                     "type": "error"}]},
      "…"
    ],
    "messages": []
  },
  "state": "choose_method"
}
```

Invalid credentials attach to `ui.messages` instead, because they do not belong
to any one field. The collection asserts both placements.

## Trait validation against the identity schema

Two schemas are seeded with different required fields:

| Schema | Required traits | Extras |
|--------|-----------------|--------|
| `default` | `email`, `name.first`, `name.last` | `role` (enum), `seat_id` (pattern `^SEAT-[0-9]{3}$`) |
| `partner` | `email`, `company` | — |

Both set `additionalProperties: false`. The collection registers the *same*
payload against each and shows it succeed on `default` and fail on `partner`,
plus one request per validation rule — missing property, malformed email, value
outside the enum, value failing the pattern, and a trait the schema does not
allow — each landing on its own node.

## `continue_with`

Kratos tells the client what to do next rather than leaving it to infer:

| After | `continue_with` |
|-------|-----------------|
| registration | `set_ory_session_token`, then `show_verification_ui` with the new verification flow |
| recovery code accepted | `set_ory_session_token`, then `show_settings_ui` — Kratos forces a password change |
| settings changing the email | `show_verification_ui` for the new address |
| login where the identity has TOTP | `set_ory_session_token` (aal1) and `redirect_browser_to` the aal2 flow |

## Seed data summary

- **Identity schemas**: 2 (`default`, `partner`)
- **Identities**: 7
  - `amelia` — password **+ totp + lookup_secret**, verified, aal2 session
  - `jonas` — password only, two sessions
  - `helena` — **oidc only** (`github:2210448`), no password
  - `rohit` — **unverified email**, with an open verification flow and code
  - `noor` — **state `inactive`**, so a correct password is still refused
  - `sync-bot`, `priya` (on the `partner` schema)
- **Credentials**: 8 across `password`, `oidc`, `totp` and `lookup_secret`
- **Flows**: 9 — api and browser logins, an aal2 step-up, an **expired** one, a
  registration, a recovery, a verification and two settings flows
- **Sessions**: 6, one **revoked**, one at `aal2`
- **Codes**: 3 — an unused verification, an unused recovery, a **spent** recovery
- **Courier messages**: 5 across `sent`, `queued` and `abandoned`

Seed passwords: `amelia OrbitKratos2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `noor OrbitNoor2026!`, `priya OrbitPriya2026!`.
Helena has none. TOTP code `482913`; lookup secrets `91cd2f7a`, `4b60e18d`,
`7fa3c052`.

## Notes

- **Flow lifecycle is enforced.** An unknown flow is 404
  `self_service_flow_not_found`; an expired one is **410
  `self_service_flow_expired`**; a flow fetched under the wrong type is 404.
- **Browser flows carry an anti-CSRF token and API flows do not.** Submitting a
  browser flow without echoing `csrf_token` is 403
  `security_csrf_violation`; the same submission with it succeeds.
- **No account enumeration.** An unknown identifier, a wrong password and an
  identity with no password credential all produce the same `4000006` message.
  Recovery sends mail either way — the seed contains the `recovery_invalid`
  message Kratos sends to an address it does not know.
- **aal2 is a second flow, not a second field.** Logging in as an identity with
  TOTP yields an aal1 session plus a `redirect_browser_to` pointing at the aal2
  flow; submitting that flow with `totp` or `lookup_secret` yields an aal2
  session. A consumed lookup secret is removed from the credential.
- **Settings flows are bound to their identity.** Submitting one with a
  different session is 403 `session_refresh_required`, and with no session at
  all is 401.
- Changing an email through settings marks it unverified again and hands back a
  verification flow in `continue_with`. Changing a password revokes every other
  session.
- **`PATCH /admin/identities/{id}` is JSON Patch.** Only a fixed set of paths is
  writable; an unsupported path or operation is rejected with the supported list
  rather than silently ignored.
- Deleting the `password` credential through the admin API is refused — Kratos
  requires a settings flow for that.
- Because no mail is delivered, recovery, verification and registration return
  the code in the body and say so; the courier log records what would have been
  sent.
- Mutations (new identities, sessions, flows, codes, messages) are held in
  process memory and reset on container restart.
