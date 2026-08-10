# Keycloak Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$KEYCLOAK_API_URL`; responses are verbatim (long objects elided
with `…`). Examples assume:

```bash
export KC_ADMIN='kc-at-master-admin-cli-8f0c31d47a92'   # master admin-cli
export KC_AMELIA='kc-at-amelia-ui-6b40d2a97f15'         # orbit-labs, realm-admin
export KC_JONAS='kc-at-jonas-ui-2f83b0e6c194'           # orbit-labs, view-users only
export TOKEN_URL="$KEYCLOAK_API_URL/realms/orbit-labs/protocol/openid-connect"
```

## Health and discovery

```bash
curl -s "$KEYCLOAK_API_URL/health"
```
```json
{"status": "ok"}
```

```bash
curl -s "$KEYCLOAK_API_URL/realms/orbit-labs"
```
```json
{"realm": "orbit-labs",
 "public_key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQ-orbit-labs-mock",
 "token-service": "/realms/orbit-labs/protocol/openid-connect",
 "account-service": "/realms/orbit-labs/account", "tokens-not-before": 0}
```

An unknown realm is a real 404:

```bash
curl -s "$KEYCLOAK_API_URL/realms/orbit-nope"
```
```json
{"error": "Realm does not exist", "errorMessage": "Realm does not exist"}
```

## The direct grant

```bash
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-ui",
       "username": "amelia", "password": "OrbitKeycloak2026!"}'
```
```json
{
  "access_token": "kc-at-39e8f458bb2ac6f4cc1e",
  "expires_in": 300,
  "refresh_expires_in": 1800,
  "refresh_token": "kc-rt-17a6d0634f3998ec6c39",
  "token_type": "Bearer",
  "id_token": "eyJhbGciOiJSUzI1NiJ9.a1c07e34-9b52-4f68-8d13-06e2fa945b7c.orbit-status-ui.orbit-labs-mock-signature",
  "not-before-policy": 0,
  "session_state": "09d0ad20-b10c-4c9c-b2d8-f18589921dae",
  "scope": "openid profile email",
  "realm_access": {
    "roles": ["default-roles-orbit-labs", "incident-responder",
              "offline_access", "platform-operator", "status-viewer",
              "uma_authorization"]
  },
  "resource_access": {
    "realm-management": {
      "roles": ["manage-realm", "manage-users", "realm-admin", "view-users"]
    }
  }
}
```

`realm_access` and `resource_access` carry the **effective** roles — the closure
of amelia's composite role and her group memberships, not the two mappings
actually written against her.

## Four different refusals

```bash
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-ui",
       "username": "amelia", "password": "notmypassword"}'
```
```json
{"error": "invalid_grant", "error_description": "Invalid user credentials"}
```
```
HTTP 401
```

```bash
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-ui",
       "username": "noor", "password": "OrbitNoor2026!"}'
```
```json
{"error": "invalid_grant", "error_description": "Account disabled"}
```

```bash
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-ui",
       "username": "rohit", "password": "OrbitRohit2026!"}'
```
```json
{"error": "invalid_grant", "error_description": "Account is not fully set up"}
```

Rohit's password is correct; he has `UPDATE_PASSWORD` and `VERIFY_EMAIL`
pending.

```bash
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-ui",
       "username": "dmitri", "password": "OrbitDmitri2026!"}'
```
```json
{"error": "invalid_grant", "error_description": "Invalid user credentials"}
```

Dmitri's password is *also* correct — he is brute-force locked. Keycloak
deliberately returns the same message as a wrong password so the response cannot
confirm that the account exists and is locked. Clearing the lock proves it:

```bash
curl -s -X DELETE \
  "$KEYCLOAK_API_URL/admin/realms/orbit-labs/attack-detection/brute-force/users/d4a86f20-5c31-49b7-b0e8-73f1a2c65d94" \
  -H "Authorization: Bearer $KC_ADMIN"
# 204, and the same login now returns a token
```

## Client types are enforced

```bash
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-admin-cli",
       "username": "amelia", "password": "OrbitKeycloak2026!"}'
```
```json
{"error": "invalid_client",
 "error_description": "Invalid client or Invalid client credentials"}
```

`orbit-admin-cli` is confidential and needs its secret. Conversely,
`orbit-backup-service` has `directAccessGrantsEnabled: false`:

```json
{"error": "unauthorized_client",
 "error_description": "Client not allowed for direct access grants"}
```

## Service accounts

```bash
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "client_credentials", "client_id": "orbit-backup-service",
       "client_secret": "kc-secret-backup-service-5b07d21f"}'
```
```json
{
  "access_token": "kc-at-2d2d7bfea6f28203b2a5",
  "expires_in": 300,
  "token_type": "Bearer",
  "id_token": "eyJhbGciOiJSUzI1NiJ9.0c5b73e9-8f16-4a24-95d7-6b0e2c81f435.orbit-backup-service.orbit-labs-mock-signature",
  "session_state": "9ce5ef99-2782-495d-9fa2-4f08d9aa2130",
  "realm_access": {"roles": []},
  "resource_access": {
    "orbit-backup-service": {"roles": ["backup-runner"]},
    "realm-management": {"roles": ["view-users"]}
  }
}
```

No `refresh_token` — that matches Keycloak's default for service accounts.

## Introspection

```bash
curl -s -X POST "$TOKEN_URL/token/introspect" -H 'Content-Type: application/json' \
  -d "{\"token\": \"$KC_AMELIA\"}"
```
```json
{"active": true, "sub": "a1c07e34-9b52-4f68-8d13-06e2fa945b7c",
 "username": "amelia", "email": "amelia.ortega@orbit-labs.com",
 "client_id": "orbit-status-ui", "session_state": "s1-amelia-ui-000001",
 "typ": "Bearer",
 "realm_access": {"roles": ["default-roles-orbit-labs", "incident-responder",
                            "offline_access", "platform-operator",
                            "status-viewer", "uma_authorization"]},
 "resource_access": {"realm-management": {"roles": ["manage-realm",
                                                    "manage-users",
                                                    "realm-admin",
                                                    "view-users"]}},
 "exp": 1812182400, "iat": 1780646400, "iss": "/realms/orbit-labs"}
```

The same token introspected against `orbit-partners` is simply inactive — realms
do not share tokens.

## Direct vs effective role mappings

```bash
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users/a1c07e34-9b52-4f68-8d13-06e2fa945b7c/role-mappings" \
  -H "Authorization: Bearer $KC_ADMIN"
```
```json
{
  "realmMappings": [
    {"id": "r1-default-orbit-labs", "name": "default-roles-orbit-labs",
     "description": "Default roles granted to every new user",
     "composite": true, "clientRole": false, "containerId": "orbit-labs"}
  ],
  "clientMappings": {
    "realm-management": {
      "id": "f6b23c91-08de-4a75-b3c0-97e15d24a608",
      "client": "realm-management",
      "mappings": [{"id": "cr1-realm-admin00000", "name": "realm-admin",
                    "composite": true, "clientRole": true, "…": "…"}]
    }
  }
}
```

Two mappings. Now the closure:

```bash
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users/a1c07e34-9b52-4f68-8d13-06e2fa945b7c/role-mappings/effective" \
  -H "Authorization: Bearer $KC_ADMIN"
```
```json
{"realmMappings": ["default-roles-orbit-labs", "incident-responder",
                   "offline_access", "platform-operator", "status-viewer",
                   "uma_authorization"],
 "clientMappings": {"realm-management": ["manage-realm", "manage-users",
                                          "realm-admin", "view-users"]},
 "note": "composite roles and group-inherited roles are expanded; compare with /role-mappings for the direct set"}
```

Six realm roles and four client roles, from two mappings plus two group
memberships.

## Composite expansion

```bash
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-labs/roles/platform-operator/composites" \
  -H "Authorization: Bearer $KC_ADMIN"
```
```json
[{"id": "r5-incident-responde", "name": "incident-responder",
  "composite": false, "clientRole": false, "containerId": "orbit-labs"},
 {"id": "r6-status-viewer0000", "name": "status-viewer",
  "composite": false, "clientRole": false, "containerId": "orbit-labs"},
 {"id": "cr3-view-users000000", "name": "view-users",
  "composite": false, "clientRole": true,
  "containerId": "f6b23c91-08de-4a75-b3c0-97e15d24a608"}]
```

A composite realm role reaching into a *client* role is what gives Jonas his
Admin API access without any mapping of his own.

## The Admin API gate

Jonas holds `view-users` and nothing more, so he can read:

```bash
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users?max=3" \
  -H "Authorization: Bearer $KC_JONAS"
```
```json
[{"id": "a1c07e34-9b52-4f68-8d13-06e2fa945b7c", "username": "amelia", "…": "…"},
 "…"]
```

…and not write:

```bash
curl -s -X POST "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users" \
  -H "Authorization: Bearer $KC_JONAS" -H 'Content-Type: application/json' \
  -d '{"username": "denied"}'
```
```json
{"error": "Forbidden",
 "errorMessage": "Missing realm-management role 'manage-users'"}
```

And a realm-scoped token cannot reach across:

```bash
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-partners/users" \
  -H "Authorization: Bearer $KC_AMELIA"
```
```json
{"error": "Forbidden",
 "errorMessage": "Token issued for realm orbit-labs cannot administer realm orbit-partners"}
```

## The realm password policy is parsed, not hard-coded

`orbit-labs` carries `length(12) and upperCase(1) and digits(1) and
notUsername`:

```bash
curl -s -X POST "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '{"username": "shorty",
       "credentials": [{"type": "password", "value": "Short1"}]}'
```
```json
{"error": "invalidPasswordMinLength",
 "errorMessage": "Invalid password: minimum length 12."}
```

```bash
curl -s -X POST "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '{"username": "nodigits",
       "credentials": [{"type": "password", "value": "NoDigitsAtAllHere"}]}'
```
```json
{"error": "invalidPasswordMinDigits",
 "errorMessage": "Invalid password: must contain at least 1 numerical digits."}
```

## Groups and subgroup inheritance

```bash
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-labs/groups" \
  -H "Authorization: Bearer $KC_ADMIN"
```
```json
[{"id": "g1-platform00000001", "name": "platform", "path": "/platform",
  "realmRoles": ["platform-operator"], "clientRoles": {},
  "attributes": {"costCenter": ["CC-100"], "region": ["us-west"]},
  "subGroups": [
    {"id": "g2-platform-oncall01", "name": "on-call", "path": "/platform/on-call",
     "realmRoles": ["incident-responder"],
     "clientRoles": {"realm-management": ["view-users"]},
     "attributes": {"rotation": ["weekly"]}, "subGroups": []}
  ]},
 {"id": "g3-support000000001", "name": "support", "path": "/support",
  "realmRoles": ["status-viewer"], "…": "…"}]
```

## Brute-force detection

```bash
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-labs/attack-detection/brute-force/users/d4a86f20-5c31-49b7-b0e8-73f1a2c65d94" \
  -H "Authorization: Bearer $KC_ADMIN"
```
```json
{"numFailures": 6, "disabled": true, "lastIPFailure": "198.51.100.12",
 "lastFailure": 1780642800000}
```

Failed direct grants increment this counter live; once it reaches the realm's
`failureFactor` (5), the account is locked.

## Temporary passwords force a required action

```bash
curl -s -X PUT \
  "$KEYCLOAK_API_URL/admin/realms/orbit-labs/users/3b60e5c1-7a94-42d8-9f01-2c86d47e0b53/reset-password" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '{"type": "password", "value": "TemporaryOrbit2026", "temporary": true}'
```
```
204 No Content
```

The next login with that password is refused:

```json
{"error": "invalid_grant", "error_description": "Account is not fully set up"}
```
