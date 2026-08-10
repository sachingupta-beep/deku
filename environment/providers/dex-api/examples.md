# Dex Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$DEX_API_URL`; responses are verbatim (long lists elided with
`…`). Examples assume:

```bash
export WEB_SECRET='dex-secret-status-web-9f14c73e0b2a'
export GRAFANA_SECRET='dex-secret-grafana-5b07d21f8c64'
export KUBECTL_SECRET='dex-secret-kubectl-1c84f065'
export VERIFIER='dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
```

## Health and discovery

```bash
curl -s "$DEX_API_URL/health"
```
```json
{"status": "ok"}
```

```bash
curl -s "$DEX_API_URL/dex/.well-known/openid-configuration"
```
```json
{"issuer": "https://dex.orbit-labs.com/dex",
 "authorization_endpoint": "https://dex.orbit-labs.com/dex/auth",
 "token_endpoint": "https://dex.orbit-labs.com/dex/token",
 "jwks_uri": "https://dex.orbit-labs.com/dex/keys",
 "userinfo_endpoint": "https://dex.orbit-labs.com/dex/userinfo",
 "device_authorization_endpoint": "https://dex.orbit-labs.com/dex/device/code",
 "grant_types_supported": ["authorization_code", "refresh_token", "password",
                           "urn:ietf:params:oauth:grant-type:device_code"],
 "scopes_supported": ["openid", "email", "groups", "profile", "offline_access"],
 "…": "…"}
```

## The connectors are the identity sources

```bash
curl -s "$DEX_API_URL/dex/connectors"
```
```json
{
  "connectors": [
    {"id": "local", "type": "local", "name": "Email", "enabled": true,
     "supportsPasswordGrant": true, "supportsRefresh": true, "config": {}},
    {"id": "ldap", "type": "ldap", "name": "Orbit LDAP", "enabled": true,
     "supportsPasswordGrant": true, "supportsRefresh": true,
     "config": {"host": "ldap.orbit-labs.com:636",
                "bindDN": "cn=dex,ou=service,dc=orbit-labs,dc=com",
                "userSearch.baseDN": "ou=people,dc=orbit-labs,dc=com",
                "userSearch.username": "uid",
                "groupSearch.baseDN": "ou=groups,dc=orbit-labs,dc=com"}},
    {"id": "github", "type": "github", "name": "GitHub", "enabled": true,
     "supportsPasswordGrant": false, "supportsRefresh": true,
     "config": {"clientID": "Iv1.orbit-labs-dex", "orgs": "orbit-labs", "…": "…"}},
    {"id": "orbit-saml", "type": "saml", "name": "Acme SAML", "enabled": false,
     "…": "…"}
  ]
}
```

## Authorization: Dex offers a chooser

```bash
curl -s "$DEX_API_URL/dex/auth?client_id=orbit-status-web\
&redirect_uri=https://status.orbit-labs.com/callback&response_type=code\
&scope=openid%20profile%20email%20groups%20offline_access&state=orbit-status-42"
```
```json
{
  "auth_request_id": "arq-b2c8a16b713349",
  "state": "orbit-status-42",
  "scopes": ["openid", "profile", "email", "groups", "offline_access"],
  "note": "the mock returns the authorization request rather than rendering the login page, so the flow stays inspectable",
  "connectors": [
    {"id": "local", "name": "Email", "type": "local",
     "url": "https://dex.orbit-labs.com/dex/auth/local?req=arq-b2c8a16b713349"},
    {"id": "ldap", "name": "Orbit LDAP", "type": "ldap", "url": "…"},
    {"id": "github", "name": "GitHub", "type": "github", "url": "…"}
  ]
}
```

The disabled `orbit-saml` connector is absent from the chooser, and asking for
it directly is refused:

```json
{"error": "invalid_request",
 "error_description": "Connector 'orbit-saml' is disabled."}
```

Then approve the request against a connector:

```bash
curl -s -X POST "$DEX_API_URL/dex/approval" -H 'Content-Type: application/json' \
  -d '{"req": "arq-b2c8a16b713349", "connector_id": "local",
       "username": "amelia.ortega@orbit-labs.com", "password": "OrbitDex2026!"}'
```
```json
{"code": "dex-code-fa908de662d66409b1ef", "state": "orbit-status-42",
 "redirect_uri": "https://status.orbit-labs.com/callback?code=dex-code-fa908de662d66409b1ef&state=orbit-status-42"}
```

## The connector decides what the password grant can do

```bash
curl -s -X POST "$DEX_API_URL/dex/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-web",
       "client_secret": "'"$WEB_SECRET"'",
       "username": "amelia.ortega@orbit-labs.com", "password": "OrbitDex2026!",
       "scope": "openid profile email groups offline_access"}'
```
```json
{
  "access_token": "dex-at-7d93e208841516fe76c74b51",
  "token_type": "bearer",
  "expires_in": 86400,
  "id_token": "eyJhbGciOiJSUzI1NiJ9.08a8684b-db88-4b73-90a9-3cd1661f.local-orbit-status-web",
  "id_token_claims": {
    "iss": "https://dex.orbit-labs.com/dex",
    "sub": "Ch3608a8684b-db88-4b73-90a9-3cd1661f5466Egrlocal",
    "aud": "orbit-status-web",
    "exp": 86400,
    "name": "amelia",
    "email": "amelia.ortega@orbit-labs.com",
    "email_verified": true,
    "groups": ["orbit-labs:platform", "orbit-labs:oncall"]
  },
  "scope": "openid profile email groups offline_access",
  "refresh_token": "dex-rt-ff4ffb1912415221994b4a3a"
}
```

The **same credentials through `ldap`** produce a different subject, because
Dex's `sub` encodes the connector — ids are only unique within one:

```json
{"id_token_claims": {
   "sub": "Ch40uid=jonas,ou=people,dc=orbit-labs,dc=comEgrldap",
   "name": "jonas", "email": "jonas.pereira@orbit-labs.com",
   "groups": ["orbit-labs:platform"], "…": "…"},
 "scope": "openid email groups"}
```

And `github` has no passwords for Dex to check at all:

```json
{"error": "invalid_request",
 "error_description": "Connector 'github' does not support password authentication; use the browser flow."}
```

## The device authorization grant

```bash
curl -s -X POST "$DEX_API_URL/dex/device/code" \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "orbit-cli", "scope": "openid email groups offline_access"}'
```
```json
{"device_code": "dex-device-3d765182a55dacda5cb1", "user_code": "QXMJ-ZRWC",
 "verification_uri": "https://dex.orbit-labs.com/dex/device",
 "verification_uri_complete": "https://dex.orbit-labs.com/dex/device?user_code=QXMJ-ZRWC",
 "expires_in": 600, "interval": 5}
```

Polling before approval:

```bash
curl -s -X POST "$DEX_API_URL/dex/device/token" \
  -H 'Content-Type: application/json' \
  -d '{"client_id": "orbit-cli", "device_code": "dex-device-pending-9f14c73e0b2a"}'
```
```json
{"error": "authorization_pending",
 "error_description": "The user has not yet approved this request."}
```

Polling too eagerly:

```json
{"error": "slow_down",
 "error_description": "Polling too frequently; wait at least 10 seconds."}
```

A denied request:

```json
{"error": "access_denied",
 "error_description": "The user denied the authorization request."}
```

Approving, then polling once more:

```bash
curl -s -X POST "$DEX_API_URL/dex/device/auth/verify" \
  -H 'Content-Type: application/json' \
  -d '{"user_code": "BDWD-HQMK", "connector_id": "local",
       "username": "amelia.ortega@orbit-labs.com", "password": "OrbitDex2026!"}'
```
```json
{"user_code": "BDWD-HQMK", "state": "approved", "username": "amelia"}
```
```json
{"access_token": "dex-at-cb51893c22c714259eafc6d3", "token_type": "bearer",
 "expires_in": 86400,
 "id_token_claims": {"sub": "Ch3608a8684b-…Egrlocal", "aud": "orbit-cli",
                     "name": "amelia", "…": "…"},
 "scope": "openid profile email groups offline_access",
 "refresh_token": "dex-rt-6957a1bff8045e3a8e6c3238"}
```

Polling it again is `invalid_grant` — the code has been redeemed.

## Cross-client audiences need a trusted peer

```bash
curl -s "$DEX_API_URL/dex/auth?client_id=orbit-status-web\
&redirect_uri=https://status.orbit-labs.com/callback&response_type=code\
&scope=openid%20audience:server:client_id:orbit-grafana"
```
```json
{"error": "invalid_scope",
 "error_description": "Client orbit-status-web is not a trusted peer of orbit-grafana; add it to that client's trustedPeers to request its audience."}
```

`orbit-kubectl` *is* on grafana's `trustedPeers`, so the identical request from
that client succeeds.

## The only user list is the refresh tokens

```bash
curl -s "$DEX_API_URL/api/v2/offline-sessions"
```
```json
{"offline_sessions": [
  {"connectorId": "github", "userId": "2210448", "username": "helena-park",
   "email": "helena.park@orbit-labs.com",
   "groups": ["orbit-labs:infrastructure"], "clients": ["orbit-grafana"]},
  {"connectorId": "ldap", "userId": "uid=noor,ou=people,dc=orbit-labs,dc=com",
   "username": "noor", "email": "noor.aziz@orbit-labs.com",
   "clients": ["orbit-kubectl"], "…": "…"},
  {"connectorId": "local", "username": "amelia",
   "clients": ["orbit-status-web", "orbit-kubectl"], "…": "…"},
  {"connectorId": "local", "username": "jonas", "clients": ["orbit-cli"],
   "…": "…"}]}
```

Helena and Noor have no local password — Dex knows them only because a refresh
token remembers what their connector said.

```bash
curl -s "$DEX_API_URL/api/v2/refresh/08a8684b-db88-4b73-90a9-3cd1661f5466"
```
```json
{"refresh_tokens": [
  {"id": "rt-amelia-status-01", "clientId": "orbit-status-web",
   "connectorId": "local",
   "scopes": ["openid", "profile", "email", "groups", "offline_access"],
   "createdAt": "2026-05-26T08:12:00Z", "lastUsed": "2026-05-26T08:12:00Z"},
  {"id": "rt-amelia-kubectl1", "clientId": "orbit-kubectl", "…": "…"}]}
```

## The gRPC API answers with flags, not status codes

```bash
curl -s -X POST "$DEX_API_URL/api/v2/clients" \
  -H 'Content-Type: application/json' \
  -d '{"client": {"id": "orbit-cli", "name": "Orbit CLI"}}'
```
```
HTTP 200
```
```json
{"already_exists": true,
 "client": {"id": "orbit-cli", "name": "Orbit CLI", "secret": null,
            "redirectURIs": ["urn:ietf:wg:oauth:2.0:oob",
                             "http://127.0.0.1/callback"],
            "public": true,
            "grantTypes": ["authorization_code", "refresh_token",
                           "urn:ietf:params:oauth:grant-type:device_code"],
            "…": "…"}}
```

```bash
curl -s -X DELETE "$DEX_API_URL/api/v2/clients/not-a-client"
```
```
HTTP 200
```
```json
{"not_found": true}
```

That is Dex's shape, inherited from gRPC — worth knowing before writing a client
that switches on the status code.

## Passwords

```bash
curl -s -X POST "$DEX_API_URL/api/v2/passwords/verify" \
  -H 'Content-Type: application/json' \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "OrbitDex2026!"}'
```
```json
{"verified": true, "not_found": false}
```

A wrong password is `{"verified": false, "not_found": false}`; an unknown email
is `{"verified": false, "not_found": true}` — both at 200.

Updating a password drops every offline session it anchored, so the collection
logs in with the old one afterwards and watches it fail with
`access_denied`.
