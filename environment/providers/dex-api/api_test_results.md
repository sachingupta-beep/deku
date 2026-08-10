# Dex Mock API — Test Results

Base URL: `http://localhost:8120` (in docker-compose: `http://dex-api:8120`)

## Endpoints covered

### OIDC provider

| Method | Path                                       | Status      |
|--------|--------------------------------------------|-------------|
| GET    | /health · /healthz                         | 200         |
| GET    | /dex/.well-known/openid-configuration      | 200         |
| GET    | /dex/keys                                  | 200         |
| GET    | /dex/connectors                            | 200         |
| GET    | /dex/auth · /dex/auth/{connector_id}       | 200/400     |
| POST   | /dex/approval                              | 200/400/401 |
| POST   | /dex/token                                 | 200/400/401 |
| POST   | /dex/token/introspect                      | 200         |
| GET    | /dex/userinfo                              | 200/401     |
| POST   | /dex/device/code                           | 200/400     |
| GET    | /dex/device                                | 200/404     |
| POST   | /dex/device/auth/verify                    | 200/400/401/404 |
| POST   | /dex/device/token                          | 200/400     |

### The gRPC API over HTTP

| Method | Path                                | Status      |
|--------|-------------------------------------|-------------|
| GET    | /api/v2/version                     | 200         |
| GET/POST | /api/v2/clients                   | 200         |
| GET/PUT/DELETE | /api/v2/clients/{id}        | 200/404     |
| GET/POST | /api/v2/passwords                 | 200/400     |
| PUT/DELETE | /api/v2/passwords/{email}       | 200         |
| POST   | /api/v2/passwords/verify            | 200         |
| GET    | /api/v2/refresh/{user_id}           | 200         |
| POST   | /api/v2/refresh/revoke              | 200         |
| GET    | /api/v2/offline-sessions            | 200         |

Collection run: **PASS 51 / WARN 48 / FAIL 0 / SKIP 0**. Every WARN is an
intentional error-path request, labelled `(N expected)` in the collection.

**Note on the API surface.** Several requests that would be errors elsewhere are
PASS rows here on purpose: Dex's gRPC API answers **200 with a boolean flag**
rather than a status code. Creating a client that already exists is
`{"already_exists": true}`, and deleting one that does not is
`{"not_found": true}`. Those requests are labelled with the flag they assert
rather than `(N expected)`, because they really are successful calls.

## Connectors decide what is possible

Dex has no opinion about credentials of its own — the connector does:

| Connector | Type | Password grant | In the collection |
|-----------|------|----------------|-------------------|
| `local` | static passwords | **yes** | 200 with an id token |
| `ldap` | directory | **yes** | 200, `sub` keyed by the DN |
| `github` | social | **no** | 400 *does not support password authentication; use the browser flow* |
| `orbit-saml` | SAML, **disabled** | — | 400 *connector is disabled* |

The same username and password produce a *different* `sub` through `local` and
`ldap`, because Dex's subject encodes the connector — ids are only unique within
one.

## The device authorization grant

RFC 8628 in full, with a seeded device request for each state:

| Device code | State | Polling it returns |
|-------------|-------|--------------------|
| `dex-device-pending-9f14c73e0b2a` | pending | `authorization_pending`, then `slow_down` from the fourth poll |
| `dex-device-approved-5b07d21f8c64` | approved | tokens |
| `dex-device-denied-c8e05a1976b3` | denied | `access_denied` |
| `dex-device-expired-2d47b9e01f5c` | expired | `expired_token` |
| `dex-device-redeemed-7a63f04c9e21` | redeemed | `invalid_grant` |

The collection polls the pending code four times to trip `slow_down`, then
approves it through the `local` connector and polls once more for the tokens —
so the whole state machine is walked, not asserted.

## Cross-client audiences

A client may request `audience:server:client_id:<other>` only if it appears on
that other client's `trustedPeers`:

| Requester | Audience | Result |
|-----------|----------|--------|
| `orbit-kubectl` | `orbit-grafana` | **allowed** — kubectl is on grafana's trustedPeers |
| `orbit-status-web` | `orbit-grafana` | 400 `invalid_scope`, naming the fix |
| `orbit-kubectl` | `not-a-client` | 400 `invalid_scope` |

## Seed data summary

- **Connectors**: 4 — `local`, `ldap`, `github`, and a **disabled** `orbit-saml`
- **Clients**: 4 — a confidential web app allowed the password grant, a
  **public** CLI allowed the device grant, Grafana (which trusts kubectl), and
  kubectl
- **Passwords**: 4 (the entire local identity store: amelia, jonas, rohit, the
  sync bot)
- **Refresh tokens**: 5 across three connectors, one carrying a
  `obsoleteToken` from a previous rotation and one carrying a cross-client
  audience scope
- **Authorization codes**: 3 — one unused with PKCE, one **already used**, one
  **expired**
- **Authorization requests**: 3, one **expired**
- **Device requests**: 5, one per state

Seed passwords: `amelia OrbitDex2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `orbit_sync_bot OrbitSyncBot2026!`. Helena exists only
as a GitHub refresh token; Noor only as an LDAP one — neither has a local
password, which is the point.

## Notes

- **The only user list is the refresh tokens.** `/api/v2/offline-sessions`
  groups every remembered identity by connector; `/api/v2/refresh/{user_id}`
  takes a path parameter because an LDAP identity id is a full DN.
- **Client authentication follows client type.** A confidential client must
  present its secret (401 otherwise); a public one carries none. A grant a
  client does not declare is `unauthorized_client`.
- **PKCE is verified** when the authorization code carries a challenge, and both
  `S256` and `plain` methods are supported.
- **Authorization codes are single-use**; a replay is `invalid_grant`, which is
  the attack signal the spec asks for.
- **Refresh tokens rotate, and Dex keeps exactly one previous generation** so a
  client that crashed mid-rotation can recover. Presenting a token two
  generations old gets a distinct message from an unknown one.
- **A refresh may narrow scopes but never widen them** — asking for a scope
  outside the original grant is `invalid_scope` naming the offending scope.
- Changing a password through the API drops every offline session it anchored,
  and the collection logs in with the old password afterwards to show it fail.
- Deleting a client also removes its refresh tokens and device requests.
- Errors on `/dex/*` follow RFC 6749 and RFC 8628; the `/api/v2` surface uses
  flags, as described above.
- Mutations (new clients, passwords, codes, device approvals, rotated tokens)
  are held in process memory and reset on container restart.
