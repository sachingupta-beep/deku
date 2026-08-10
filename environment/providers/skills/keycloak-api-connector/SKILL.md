---
name: keycloak-api-connector
description: >
  Keycloak API (Mock) mock HTTP API. Base URL is provided via the
  `KEYCLOAK_API_URL` environment variable. 48 endpoint(s) across GET, POST, PUT, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Keycloak API (Mock)

Mock of Keycloak. **All requests go to the base URL in `$KEYCLOAK_API_URL`.**
Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `KEYCLOAK_API_URL` | Base URL for all requests (e.g. `http://keycloak-api:8117`) |

## Everything is realm-scoped

Two realms, and nothing crosses between them:

| Realm | Brute force | Password policy |
|-------|-------------|-----------------|
| `orbit-labs` | on, `failureFactor` 5 | `length(12) and upperCase(1) and digits(1) and notUsername` |
| `orbit-partners` | off | `length(8)` |

| Prefix | What it is | Error shape |
|--------|------------|-------------|
| `/realms/{realm}/protocol/openid-connect/...` | the OIDC surface a client talks to | RFC 6749 `{"error", "error_description"}` |
| `/admin/realms/{realm}/...` | the Admin REST API | `{"error", "errorMessage"}` |

## Tokens

| Token | Who | On the Admin API |
|-------|-----|------------------|
| `kc-at-master-admin-cli-8f0c31d47a92` | master `admin-cli` | any realm, everything |
| `kc-at-amelia-ui-6b40d2a97f15` | amelia, `orbit-labs` | `realm-admin` — everything in orbit-labs |
| `kc-at-jonas-ui-2f83b0e6c194` | jonas, `orbit-labs` | only `view-users` — reads yes, writes 403 |
| `kc-at-priya-portal-1d75a0e934bc` | priya, `orbit-partners` | orbit-partners only |
| `kc-at-amelia-cli-revoked-0e47c95b` | expired | 401 |

## Seed users (`orbit-labs`)

| Username | Password | Direct grant result |
|----------|----------|---------------------|
| `amelia` | `OrbitKeycloak2026!` | 200 — realm-admin, TOTP configured |
| `jonas` | `OrbitJonas2026!` | 200 — `view-users` via the `/platform` group |
| `helena` | — | 401 — federated (`github-oidc`), no local credential |
| `rohit` | `OrbitRohit2026!` | **400 Account is not fully set up** — pending required actions |
| `noor` | `OrbitNoor2026!` | **400 Account disabled** |
| `dmitri` | `OrbitDmitri2026!` | **401** — brute-force locked |

`priya` / `OrbitPriya2026!` lives in `orbit-partners`.

## Clients (`orbit-labs`)

| clientId | Type | Grants |
|----------|------|--------|
| `orbit-status-ui` | public | authorization code + **direct grant** |
| `orbit-admin-cli` | confidential (`kc-secret-admin-cli-9f14c73e0b2a`) | direct grant only |
| `orbit-backup-service` | confidential (`kc-secret-backup-service-5b07d21f`) | **client credentials only** |
| `realm-management` | bearer-only | holds the admin client roles |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/realms/{realm}` · `/.well-known/openid-configuration` · `/protocol/openid-connect/certs` |
| POST | `/realms/{realm}/protocol/openid-connect/token` · `/token/introspect` · `/logout` |
| GET | `/realms/{realm}/protocol/openid-connect/userinfo` |
| GET | `/admin/serverinfo` · `/admin/realms` |
| GET/PUT | `/admin/realms/{realm}` |
| GET | `/admin/realms/{realm}/clients[/{uuid}][/roles|/client-secret|/user-sessions]` |
| GET/POST | `/admin/realms/{realm}/roles` |
| GET/DELETE | `/admin/realms/{realm}/roles/{roleName}` |
| GET | `/admin/realms/{realm}/roles/{roleName}/composites` |
| GET/POST | `/admin/realms/{realm}/users` · `/users/count` |
| GET/PUT/DELETE | `/admin/realms/{realm}/users/{id}` |
| PUT | `/admin/realms/{realm}/users/{id}/reset-password` · `/execute-actions-email` |
| GET | `/admin/realms/{realm}/users/{id}/sessions` · `/offline-sessions` · `/groups` |
| POST | `/admin/realms/{realm}/users/{id}/logout` |
| GET | `/admin/realms/{realm}/users/{id}/role-mappings[/effective]` |
| POST/DELETE | `/admin/realms/{realm}/users/{id}/role-mappings/realm` |
| GET/POST | `/admin/realms/{realm}/users/{id}/role-mappings/clients/{uuid}` |
| PUT/DELETE | `/admin/realms/{realm}/users/{id}/groups/{groupId}` |
| GET/POST | `/admin/realms/{realm}/groups` |
| GET/DELETE | `/admin/realms/{realm}/groups/{id}` |
| POST | `/admin/realms/{realm}/groups/{id}/children` |
| GET | `/admin/realms/{realm}/groups/{id}/members` · `/role-mappings` |
| GET | `/admin/realms/{realm}/identity-provider/instances[/{alias}]` |
| GET | `/admin/realms/{realm}/authentication/required-actions` |
| GET/DELETE | `/admin/realms/{realm}/attack-detection/brute-force/users[/{id}]` |
| GET | `/admin/realms/{realm}/events` · `/admin-events` |

## Usage

```bash
# Direct grant (the mock takes JSON where real Keycloak takes form-encoded)
curl -s -X POST \
  "$KEYCLOAK_API_URL/realms/orbit-labs/protocol/openid-connect/token" \
  -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-ui",
       "username": "amelia", "password": "OrbitKeycloak2026!"}'

# Admin API with the master token
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users?max=5" \
  -H 'Authorization: Bearer kc-at-master-admin-cli-8f0c31d47a92'

# Direct vs effective roles
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users/a1c07e34-9b52-4f68-8d13-06e2fa945b7c/role-mappings/effective" \
  -H 'Authorization: Bearer kc-at-master-admin-cli-8f0c31d47a92'
```

Composite roles and group memberships are expanded transitively, so a user's
effective roles are usually a much larger set than their direct mappings.

The audit log of every call the agent makes is available at
`$KEYCLOAK_API_URL/audit/requests` (used for grading).
