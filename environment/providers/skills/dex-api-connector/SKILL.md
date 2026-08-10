---
name: dex-api-connector
description: >
  Dex API (Mock) mock HTTP API. Base URL is provided via the
  `DEX_API_URL` environment variable. 27 endpoint(s) across GET, POST, PUT, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Dex API (Mock)

Mock of Dex, the OIDC federator. **All requests go to the base URL in
`$DEX_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `DEX_API_URL` | Base URL for all requests (e.g. `http://dex-api:8120`) |

## Read this before using it

**Dex has no user database.** Identities live behind *connectors*; the only
local store is the `local` connector's static passwords. Everything else Dex
knows about a person exists only because a refresh token remembers it — so
`/api/v2/refresh/{user_id}` and `/api/v2/offline-sessions` are the closest thing
to a user list.

**The `/api/v2` surface answers 200 with a flag, not a status code.** Creating a
client that exists is `{"already_exists": true}`; deleting one that does not is
`{"not_found": true}`. Do not switch on the HTTP status there.

## Connectors

| Connector | Password grant | Note |
|-----------|----------------|------|
| `local` | **yes** | the static-password store |
| `ldap` | **yes** | same credentials, `sub` keyed by the DN |
| `github` | **no** | browser flow only → 400 |
| `orbit-saml` | — | **disabled** → 400 |

## Clients

| Client id | Secret | Grants |
|-----------|--------|--------|
| `orbit-status-web` | `dex-secret-status-web-9f14c73e0b2a` | code, refresh, **password** |
| `orbit-cli` | _(public — send none)_ | code, refresh, **device** |
| `orbit-grafana` | `dex-secret-grafana-5b07d21f8c64` | code, refresh; `trustedPeers: [orbit-kubectl]` |
| `orbit-kubectl` | `dex-secret-kubectl-1c84f065` | code, refresh, **device** |

A client may request `audience:server:client_id:<other>` only if it is on that
other client's `trustedPeers`.

## Identities

| Email | Password | Available through |
|-------|----------|-------------------|
| `amelia.ortega@orbit-labs.com` | `OrbitDex2026!` | local, ldap |
| `jonas.pereira@orbit-labs.com` | `OrbitJonas2026!` | local, ldap |
| `rohit.bansal@orbit-labs.com` | `OrbitRohit2026!` | local, ldap |
| `sync-bot@orbit-labs.com` | `OrbitSyncBot2026!` | local, ldap |
| `helena.park@orbit-labs.com` | — | **github refresh token only** |
| `noor.aziz@orbit-labs.com` | — | **ldap refresh token only** |

## Seeded grant material

| Value | Kind | State |
|-------|------|-------|
| `dex-code-amelia-e70b2c948d15` | auth code (PKCE) | unused |
| `dex-code-jonas-used-5a1c93e08b74` | auth code | **used** |
| `dex-code-helena-expired-3a6d80e5` | auth code | **expired** |
| `dex-rt-amelia-status-4c19f7e0b83d` | refresh token | live |
| `dex-rt-jonas-cli-0e47c95b3d18` | refresh token | **two rotations old** |
| `dex-device-pending-9f14c73e0b2a` (`BDWD-HQMK`) | device code | pending |
| `dex-device-approved-5b07d21f8c64` (`JKZN-WPTR`) | device code | approved |
| `dex-device-denied-c8e05a1976b3` | device code | denied |
| `dex-device-expired-2d47b9e01f5c` | device code | expired |
| `dex-device-redeemed-7a63f04c9e21` | device code | redeemed |

PKCE pair: verifier `dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk` → challenge
`E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM`.

## Endpoints

| Method | Path |
|--------|------|
| GET | `/healthz` · `/dex/.well-known/openid-configuration` · `/dex/keys` · `/dex/connectors` |
| GET | `/dex/auth` · `/dex/auth/{connector_id}` |
| POST | `/dex/approval` · `/dex/token` · `/dex/token/introspect` |
| GET | `/dex/userinfo` |
| POST | `/dex/device/code` · `/dex/device/auth/verify` · `/dex/device/token` |
| GET | `/dex/device?user_code=` |
| GET | `/api/v2/version` |
| GET/POST | `/api/v2/clients` |
| GET/PUT/DELETE | `/api/v2/clients/{id}` |
| GET/POST | `/api/v2/passwords` |
| PUT/DELETE | `/api/v2/passwords/{email}` |
| POST | `/api/v2/passwords/verify` |
| GET | `/api/v2/refresh/{user_id}` |
| POST | `/api/v2/refresh/revoke` |
| GET | `/api/v2/offline-sessions` |

## Usage

```bash
# password grant, choosing the connector
curl -s -X POST "$DEX_API_URL/dex/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-web",
       "client_secret": "dex-secret-status-web-9f14c73e0b2a",
       "connector_id": "ldap",
       "username": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!",
       "scope": "openid email groups offline_access"}'

# device flow: request, approve, redeem
curl -s -X POST "$DEX_API_URL/dex/device/code" \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "orbit-cli", "scope": "openid email offline_access"}'
curl -s -X POST "$DEX_API_URL/dex/device/auth/verify" \
  -H 'Content-Type: application/json' \
  -d '{"user_code": "BDWD-HQMK", "connector_id": "local",
       "username": "amelia.ortega@orbit-labs.com", "password": "OrbitDex2026!"}'
curl -s -X POST "$DEX_API_URL/dex/device/token" \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "orbit-cli", "device_code": "dex-device-pending-9f14c73e0b2a"}'

# who does dex still remember
curl -s "$DEX_API_URL/api/v2/offline-sessions"
```

Errors on `/dex/*` follow RFC 6749 and RFC 8628: `invalid_grant`,
`invalid_client`, `unauthorized_client`, `invalid_scope`, `access_denied`,
`authorization_pending`, `slow_down`, `expired_token`.

The audit log of every call the agent makes is available at
`$DEX_API_URL/audit/requests` (used for grading).
