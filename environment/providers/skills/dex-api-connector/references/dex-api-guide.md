# Dex API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$DEX_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `DEX_API_URL` | Base URL for all requests |

Set the client secrets once to follow the examples:

```bash
export WEB_SECRET='dex-secret-status-web-9f14c73e0b2a'
export GRAFANA_SECRET='dex-secret-grafana-5b07d21f8c64'
export KUBECTL_SECRET='dex-secret-kubectl-1c84f065'
export VERIFIER='dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
```

## The two things to know first

**Dex has no user database.** It federates. The only identities it stores are
the `local` connector's static passwords; everyone else exists in Dex only for
as long as a refresh token remembers what their connector said. `GET
/api/v2/offline-sessions` is therefore the nearest thing to a user list.

**`/api/v2` answers 200 with a flag.** `already_exists` and `not_found` are
fields, not status codes — a legacy of the gRPC API this mirrors.

## Discovery

```bash
curl -s "$DEX_API_URL/health"
curl -s "$DEX_API_URL/healthz"
curl -s "$DEX_API_URL/dex/.well-known/openid-configuration"
curl -s "$DEX_API_URL/dex/keys"
curl -s "$DEX_API_URL/dex/connectors"
```

| Connector | Type | Password grant | Refresh |
|-----------|------|----------------|---------|
| `local` | static passwords | yes | yes |
| `ldap` | directory | yes | yes |
| `github` | social | **no** | yes |
| `orbit-saml` | SAML | — | — (**disabled**) |

## Authorization

```bash
# no connector named -> Dex returns the chooser
curl -s "$DEX_API_URL/dex/auth?client_id=orbit-status-web\
&redirect_uri=https://status.orbit-labs.com/callback&response_type=code\
&scope=openid%20profile%20email%20groups%20offline_access&state=orbit-42\
&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256"

# straight to a connector
curl -s "$DEX_API_URL/dex/auth/local?client_id=orbit-status-web\
&redirect_uri=https://status.orbit-labs.com/callback&response_type=code\
&scope=openid%20email%20groups%20offline_access"

# complete it
curl -s -X POST "$DEX_API_URL/dex/approval" -H 'Content-Type: application/json' \
  -d '{"req": "<auth_request_id>", "connector_id": "local",
       "username": "amelia.ortega@orbit-labs.com", "password": "OrbitDex2026!"}'
```

Refusals: unknown `client_id` → `invalid_client`; a `redirect_uri` not on the
client → `invalid_request`; anything but `response_type=code` →
`unsupported_response_type`; a disabled or unknown connector →
`invalid_request`.

Seeded authorization requests: `arq-status-web-0001`, `arq-grafana-000001`
(bound to github), `arq-expired-000001` (**expired**).

## Token endpoint

The mock accepts JSON where real Dex takes `application/x-www-form-urlencoded`.

```bash
# authorization_code, with PKCE
curl -s -X POST "$DEX_API_URL/dex/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "authorization_code", "client_id": "orbit-status-web",
       "client_secret": "'"$WEB_SECRET"'",
       "code": "dex-code-amelia-e70b2c948d15", "code_verifier": "'"$VERIFIER"'",
       "redirect_uri": "https://status.orbit-labs.com/callback"}'

# password, through a named connector
curl -s -X POST "$DEX_API_URL/dex/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-web",
       "client_secret": "'"$WEB_SECRET"'", "connector_id": "ldap",
       "username": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!",
       "scope": "openid email groups offline_access"}'

# refresh
curl -s -X POST "$DEX_API_URL/dex/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "refresh_token", "client_id": "orbit-status-web",
       "client_secret": "'"$WEB_SECRET"'",
       "refresh_token": "dex-rt-amelia-status-4c19f7e0b83d"}'
```

Rules the mock enforces:

- A **confidential** client must send its secret (401 `invalid_client`); a
  **public** one carries none.
- A grant the client does not declare is `unauthorized_client` — `orbit-cli`
  cannot use the password grant, `orbit-status-web` cannot use the device grant.
- Authorization codes are **single-use**; a replay is `invalid_grant`.
- PKCE is checked when the code carries a challenge (`S256` and `plain`).
- Refresh tokens **rotate**, and Dex keeps exactly one previous generation so a
  client that crashed mid-rotation can recover. A token two generations old gets
  its own message.
- A refresh may **narrow** scopes but never widen them — a scope outside the
  original grant is `invalid_scope` naming the offender.
- The `sub` claim encodes the connector, so the same person through `local` and
  `ldap` has different subjects.

## Cross-client audiences

```bash
# allowed: kubectl is on grafana's trustedPeers
curl -s "$DEX_API_URL/dex/auth?client_id=orbit-kubectl\
&redirect_uri=http://localhost:8000&response_type=code\
&scope=openid%20email%20audience:server:client_id:orbit-grafana"
```

Any other client asking for grafana's audience is `invalid_scope`, and the
message names the fix.

## Device authorization grant (RFC 8628)

```bash
curl -s -X POST "$DEX_API_URL/dex/device/code" \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "orbit-cli", "scope": "openid email groups offline_access"}'

curl -s "$DEX_API_URL/dex/device?user_code=BDWD-HQMK"

curl -s -X POST "$DEX_API_URL/dex/device/auth/verify" \
  -H 'Content-Type: application/json' \
  -d '{"user_code": "BDWD-HQMK", "connector_id": "local",
       "username": "amelia.ortega@orbit-labs.com", "password": "OrbitDex2026!"}'

# deny instead
curl -s -X POST "$DEX_API_URL/dex/device/auth/verify" \
  -H 'Content-Type: application/json' \
  -d '{"user_code": "BDWD-HQMK", "approve": false}'

curl -s -X POST "$DEX_API_URL/dex/device/token" \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "orbit-cli", "device_code": "dex-device-pending-9f14c73e0b2a"}'
```

Polling returns, by state:

| State | Error |
|-------|-------|
| pending, first three polls | `authorization_pending` |
| pending, fourth poll onward | `slow_down` |
| denied | `access_denied` |
| expired | `expired_token` |
| redeemed | `invalid_grant` |
| approved | tokens |

Seeded device codes cover every one of those, so each can be exercised without
setting up state.

## Userinfo and introspection

```bash
curl -s "$DEX_API_URL/dex/userinfo" \
  -H 'Authorization: Bearer dex-rt-helena-github-70b2e4f9c81d'

curl -s -X POST "$DEX_API_URL/dex/token/introspect" \
  -H 'Content-Type: application/json' \
  -d '{"token": "dex-rt-helena-github-70b2e4f9c81d"}'
```

Introspection reports `{"active": false}` for an unknown token (RFC 7662).

## The gRPC API: clients

```bash
curl -s "$DEX_API_URL/api/v2/version"
curl -s "$DEX_API_URL/api/v2/clients"
curl -s "$DEX_API_URL/api/v2/clients/orbit-cli"

curl -s -X POST "$DEX_API_URL/api/v2/clients" \
  -H 'Content-Type: application/json' \
  -d '{"client": {"id": "orbit-webhook", "name": "Orbit Webhook Relay",
                  "redirectURIs": ["https://hooks.orbit-labs.com/callback"]}}'

curl -s -X PUT "$DEX_API_URL/api/v2/clients/orbit-webhook" \
  -H 'Content-Type: application/json' \
  -d '{"name": "Orbit Webhooks", "trustedPeers": ["orbit-cli"]}'

curl -s -X DELETE "$DEX_API_URL/api/v2/clients/orbit-webhook"
```

`POST` returns `{"already_exists": bool, "client": {...}}`; `PUT` and `DELETE`
return `{"not_found": bool}` — all at 200. Only `GET /api/v2/clients/{id}` uses
a real 404. Deleting a client also removes its refresh tokens and device
requests. Creating a client with `"public": true` gives it no secret.

## The gRPC API: passwords

```bash
curl -s "$DEX_API_URL/api/v2/passwords"

curl -s -X POST "$DEX_API_URL/api/v2/passwords" \
  -H 'Content-Type: application/json' \
  -d '{"password": {"email": "iris.tanaka@orbit-labs.com", "username": "iris",
                    "password": "StellarIris2026",
                    "groups": ["orbit-labs:support"]}}'

curl -s -X POST "$DEX_API_URL/api/v2/passwords/verify" \
  -H 'Content-Type: application/json' \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "OrbitDex2026!"}'

curl -s -X PUT "$DEX_API_URL/api/v2/passwords/iris.tanaka@orbit-labs.com" \
  -H 'Content-Type: application/json' \
  -d '{"username": "iris.t", "newPassword": "NebulaIris2026"}'

curl -s -X DELETE "$DEX_API_URL/api/v2/passwords/iris.tanaka@orbit-labs.com"
```

`verify` returns `{"verified": bool, "not_found": bool}` at 200 in every case.
Updating a password drops every offline session it anchored, so the old password
stops working immediately. A create with no email or no password is a genuine
400.

## The gRPC API: offline sessions

```bash
curl -s "$DEX_API_URL/api/v2/offline-sessions"
curl -s "$DEX_API_URL/api/v2/refresh/08a8684b-db88-4b73-90a9-3cd1661f5466"
curl -s "$DEX_API_URL/api/v2/refresh/uid=noor,ou=people,dc=orbit-labs,dc=com"

curl -s -X POST "$DEX_API_URL/api/v2/refresh/revoke" \
  -H 'Content-Type: application/json' \
  -d '{"user_id": "08a8684b-db88-4b73-90a9-3cd1661f5466",
       "client_id": "orbit-kubectl"}'
```

`user_id` is a path parameter that accepts slashes and equals signs, because an
LDAP identity id is a full DN. Omitting `client_id` on revoke drops every token
for that identity. Revoking nothing returns `{"not_found": true}`.

User ids: amelia `08a8684b-db88-4b73-90a9-3cd1661f5466`, jonas
`5f2b0c94-7a13-4d68-8e05-c71a9f36b204`, rohit
`c93e07a1-4b62-4f85-9d30-2a6e18c05b73`, sync bot
`1d740f62-8c95-4e03-b127-6f0a3e59d418`, helena (github) `2210448`, noor (ldap)
`uid=noor,ou=people,dc=orbit-labs,dc=com`.

## Errors

### `/dex/*` — RFC 6749 and RFC 8628

| HTTP | `error` | When |
|------|---------|------|
| 400 | `invalid_grant` | code unknown/used/expired, refresh token unknown or too old, device code redeemed |
| 400 | `invalid_request` | unregistered redirect uri, unknown or disabled connector, connector without password support |
| 400 | `unauthorized_client` | the client may not use that grant |
| 400 | `unsupported_grant_type` / `unsupported_response_type` | |
| 400 | `invalid_scope` | audience without a trusted peer, or a refresh widening scopes |
| 400 | `authorization_pending` / `slow_down` / `expired_token` / `access_denied` | device flow states |
| 401 | `invalid_client` | unknown client, or a confidential client's secret wrong |
| 401 | `access_denied` | wrong username or password |
| 401 | `invalid_token` | userinfo without a live token |
| 404 | `invalid_request` | unknown user code |

### `/api/v2/*`

| HTTP | Body | When |
|------|------|------|
| 200 | `{"already_exists": true}` | creating a client or password that exists |
| 200 | `{"not_found": true}` | updating/deleting/revoking something absent |
| 400 | `{"error": "..."}` | a password create with no email or no password |
| 404 | `{"error": "..."}` | `GET /api/v2/clients/{id}` for an unknown client |
