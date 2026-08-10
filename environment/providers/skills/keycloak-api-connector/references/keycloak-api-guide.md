# Keycloak API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$KEYCLOAK_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `KEYCLOAK_API_URL` | Base URL for all requests |

Set the tokens once to follow the examples:

```bash
export KC_ADMIN='kc-at-master-admin-cli-8f0c31d47a92'
export KC_AMELIA='kc-at-amelia-ui-6b40d2a97f15'
export KC_JONAS='kc-at-jonas-ui-2f83b0e6c194'
export TOKEN_URL="$KEYCLOAK_API_URL/realms/orbit-labs/protocol/openid-connect"
export ADMIN_URL="$KEYCLOAK_API_URL/admin/realms/orbit-labs"
```

## Realms

| Realm | Brute force | Password policy |
|-------|-------------|-----------------|
| `orbit-labs` | on, `failureFactor` 5 | `length(12) and upperCase(1) and digits(1) and notUsername` |
| `orbit-partners` | off | `length(8)` |

Realm isolation is enforced everywhere: a token issued in one realm gets 403 on
the other's Admin API, 401 on its userinfo, `{"active": false}` on its
introspection, and 404 for a user fetched through the wrong realm path.

## Ids you will need

| Thing | Id |
|-------|----|
| amelia | `a1c07e34-9b52-4f68-8d13-06e2fa945b7c` |
| jonas | `5e93b1a7-2c48-4d06-b7f5-91e0c34d6a28` |
| helena | `c72f4d80-6e19-4b35-a204-8f7b0e15c9d6` |
| rohit | `3b60e5c1-7a94-42d8-9f01-2c86d47e0b53` |
| noor | `8f21c0b6-3d75-4e92-8a60-b45e19c7d203` |
| dmitri | `d4a86f20-5c31-49b7-b0e8-73f1a2c65d94` |
| service account | `0c5b73e9-8f16-4a24-95d7-6b0e2c81f435` |
| priya (`orbit-partners`) | `6d14a9f3-0b58-4c76-83e2-1f9c40d75b86` |
| client `orbit-status-ui` | `b41d7e02-96c8-4f35-a80b-2e6f931c5d47` |
| client `orbit-admin-cli` | `d80c5f13-27ba-4e69-91d4-6a03e7b28c50` |
| client `orbit-backup-service` | `2a97e0b8-4d16-43cf-8572-b1e0c9d64f35` |
| client `realm-management` | `f6b23c91-08de-4a75-b3c0-97e15d24a608` |
| group `/platform` | `g1-platform00000001` |
| group `/platform/on-call` | `g2-platform-oncall01` |
| group `/support` | `g3-support000000001` |

## Discovery

```bash
curl -s "$KEYCLOAK_API_URL/realms/orbit-labs"
curl -s "$KEYCLOAK_API_URL/realms/orbit-labs/.well-known/openid-configuration"
curl -s "$TOKEN_URL/certs"
```

## The token endpoint

The mock accepts JSON where real Keycloak takes `application/x-www-form-urlencoded`.

```bash
# direct grant (password) -- Keycloak's first-class login
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-ui",
       "username": "amelia", "password": "OrbitKeycloak2026!"}'

# by email, because the realm has loginWithEmailAllowed
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-status-ui",
       "username": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!"}'

# confidential client
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "password", "client_id": "orbit-admin-cli",
       "client_secret": "kc-secret-admin-cli-9f14c73e0b2a",
       "username": "amelia", "password": "OrbitKeycloak2026!"}'

# service account
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "client_credentials", "client_id": "orbit-backup-service",
       "client_secret": "kc-secret-backup-service-5b07d21f"}'

# refresh
curl -s -X POST "$TOKEN_URL/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "refresh_token", "client_id": "orbit-admin-cli",
       "client_secret": "kc-secret-admin-cli-9f14c73e0b2a",
       "refresh_token": "kc-rt-jonas-cli-c81d6a0371b0"}'
```

### The four ways the direct grant fails

| User | Password | HTTP | `error_description` |
|------|----------|------|---------------------|
| amelia | wrong | 401 | `Invalid user credentials` |
| noor | correct | 400 | `Account disabled` |
| rohit | correct | 400 | `Account is not fully set up` |
| dmitri | correct | 401 | `Invalid user credentials` (brute-force locked — same wording on purpose) |
| helena | any | 401 | `Invalid user credentials` (federated, no local credential) |
| priya | correct | 401 | wrong realm |

Client-type refusals: a confidential client without its secret is
`401 invalid_client`; a client with `directAccessGrantsEnabled: false` is
`400 unauthorized_client`; a client without `serviceAccountsEnabled` refuses
client credentials the same way.

Seeded session tokens:

| Access token | Refresh token | Session |
|--------------|---------------|---------|
| `kc-at-amelia-ui-6b40d2a97f15` | `kc-rt-amelia-ui-9f2c4b17e8a0` | amelia / orbit-status-ui |
| `kc-at-jonas-ui-2f83b0e6c194` | `kc-rt-jonas-ui-4e7a1c93d0b6` | jonas / orbit-status-ui |
| `kc-at-jonas-cli-70b2e4f9c81d` | `kc-rt-jonas-cli-c81d6a0371b0` | jonas / orbit-admin-cli (**offline**) |
| `kc-at-backup-e6094c2b7f38` | — | service account |
| `kc-at-priya-portal-1d75a0e934bc` | `kc-rt-priya-portal-71b09e4c6a2d` | priya / partner-portal |
| `kc-at-amelia-cli-revoked-0e47c95b` | `kc-rt-amelia-cli-revoked-3a6d80e5` | **expired** |

## Introspection, userinfo, logout

```bash
curl -s -X POST "$TOKEN_URL/token/introspect" -H 'Content-Type: application/json' \
  -d "{\"token\": \"$KC_AMELIA\"}"

curl -s "$TOKEN_URL/userinfo" -H "Authorization: Bearer $KC_AMELIA"

curl -s -X POST "$TOKEN_URL/logout" -H 'Content-Type: application/json' \
  -d '{"refresh_token": "kc-rt-amelia-ui-9f2c4b17e8a0"}'
```

Introspection returns `{"active": false}` for an unknown, expired or
foreign-realm token rather than an error.

## Admin API: the gate

Three distinct refusals:

```bash
curl -s "$ADMIN_URL/users"                                  # 401, no bearer
curl -s "$KEYCLOAK_API_URL/admin/realms/orbit-partners/users" \
  -H "Authorization: Bearer $KC_AMELIA"                     # 403, wrong realm
curl -s -X POST "$ADMIN_URL/users" -H "Authorization: Bearer $KC_JONAS" \
  -H 'Content-Type: application/json' -d '{"username": "denied"}'
                                                            # 403, missing manage-users
```

The master token administers any realm.

## Users

```bash
curl -s "$ADMIN_URL/users?first=0&max=10" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/users?search=park" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/users?enabled=false" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/users/count" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/users/a1c07e34-9b52-4f68-8d13-06e2fa945b7c" \
  -H "Authorization: Bearer $KC_ADMIN"

curl -s -X POST "$ADMIN_URL/users" -H "Authorization: Bearer $KC_ADMIN" \
  -H 'Content-Type: application/json' \
  -d '{"username": "iris", "email": "iris.tanaka@orbit-labs.com",
       "firstName": "Iris", "lastName": "Tanaka", "enabled": true,
       "credentials": [{"type": "password", "value": "StellarNebula2026"}]}'

curl -s -X PUT "$ADMIN_URL/users/3b60e5c1-7a94-42d8-9f01-2c86d47e0b53" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '{"firstName": "Rohit K.", "requiredActions": []}'

curl -s -X PUT "$ADMIN_URL/users/3b60e5c1-7a94-42d8-9f01-2c86d47e0b53/reset-password" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '{"type": "password", "value": "NebulaOrbit2026", "temporary": false}'

curl -s -X PUT "$ADMIN_URL/users/c72f4d80-6e19-4b35-a204-8f7b0e15c9d6/execute-actions-email" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '["VERIFY_EMAIL", "CONFIGURE_TOTP"]'

curl -s -X POST "$ADMIN_URL/users/5e93b1a7-2c48-4d06-b7f5-91e0c34d6a28/logout" \
  -H "Authorization: Bearer $KC_ADMIN"
```

The realm's `passwordPolicy` string is parsed and enforced, producing Keycloak's
own error codes: `invalidPasswordMinLength`,
`invalidPasswordMinUpperCaseChars`, `invalidPasswordMinDigits`,
`invalidPasswordNotUsername`.

`"temporary": true` adds `UPDATE_PASSWORD` to the user's required actions, so
their next direct grant returns *Account is not fully set up*. Resetting a
password, disabling a user and deleting a user each drop that user's sessions.

## Roles: direct, composite, effective

```bash
curl -s "$ADMIN_URL/users/a1c07e34-9b52-4f68-8d13-06e2fa945b7c/role-mappings" \
  -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/users/a1c07e34-9b52-4f68-8d13-06e2fa945b7c/role-mappings/effective" \
  -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/roles/platform-operator/composites" \
  -H "Authorization: Bearer $KC_ADMIN"

curl -s -X POST "$ADMIN_URL/users/c72f4d80-6e19-4b35-a204-8f7b0e15c9d6/role-mappings/realm" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '[{"name": "status-viewer"}]'

curl -s -X POST "$ADMIN_URL/users/c72f4d80-6e19-4b35-a204-8f7b0e15c9d6/role-mappings/clients/f6b23c91-08de-4a75-b3c0-97e15d24a608" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '[{"name": "view-users"}]'
```

Realm roles: `default-roles-orbit-labs` (composite), `offline_access`,
`uma_authorization`, `platform-operator` (**composite**, reaching into a client
role), `incident-responder`, `status-viewer`.

Client roles on `realm-management`: `realm-admin` (**composite**),
`manage-users`, `view-users`, `manage-realm`.

`/role-mappings` returns only what is written against the user;
`/role-mappings/effective` returns the transitive closure over composites and
group memberships. That endpoint is not a Keycloak path verbatim — the real API
spreads the same information across `composite=true` parameters.

## Groups

```bash
curl -s "$ADMIN_URL/groups" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/groups/g1-platform00000001/members" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/groups/g2-platform-oncall01/role-mappings" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/users/a1c07e34-9b52-4f68-8d13-06e2fa945b7c/groups" \
  -H "Authorization: Bearer $KC_ADMIN"

curl -s -X PUT "$ADMIN_URL/users/c72f4d80-6e19-4b35-a204-8f7b0e15c9d6/groups/g3-support000000001" \
  -H "Authorization: Bearer $KC_ADMIN"

curl -s -X POST "$ADMIN_URL/groups/g1-platform00000001/children" \
  -H "Authorization: Bearer $KC_ADMIN" -H 'Content-Type: application/json' \
  -d '{"name": "sre", "realmRoles": ["incident-responder"]}'
```

A subgroup inherits its parents' role mappings, so `/platform/on-call` grants
everything `/platform` does plus its own. Deleting a group that still has
subgroups is refused.

## Clients

```bash
curl -s "$ADMIN_URL/clients" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/clients?clientId=orbit-admin-cli" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/clients/d80c5f13-27ba-4e69-91d4-6a03e7b28c50/client-secret" \
  -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/clients/f6b23c91-08de-4a75-b3c0-97e15d24a608/roles" \
  -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/clients/b41d7e02-96c8-4f35-a80b-2e6f931c5d47/user-sessions" \
  -H "Authorization: Bearer $KC_ADMIN"
```

Asking a *public* client for its secret is `400`.

## Identity providers, required actions, brute force

```bash
curl -s "$ADMIN_URL/identity-provider/instances" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/identity-provider/instances/github-oidc" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/authentication/required-actions" -H "Authorization: Bearer $KC_ADMIN"

curl -s "$ADMIN_URL/attack-detection/brute-force/users/d4a86f20-5c31-49b7-b0e8-73f1a2c65d94" \
  -H "Authorization: Bearer $KC_ADMIN"
curl -s -X DELETE "$ADMIN_URL/attack-detection/brute-force/users/d4a86f20-5c31-49b7-b0e8-73f1a2c65d94" \
  -H "Authorization: Bearer $KC_ADMIN"
```

Failed direct grants increment the counter live; at `failureFactor` the account
locks. Clearing the lock makes the same login succeed.

Required actions enabled on `orbit-labs`: `VERIFY_EMAIL`, `UPDATE_PROFILE`,
`CONFIGURE_TOTP`, `UPDATE_PASSWORD` (`TERMS_AND_CONDITIONS` is present but
disabled). Sending one the realm does not enable is `400`.

## Sessions and events

```bash
curl -s "$ADMIN_URL/users/5e93b1a7-2c48-4d06-b7f5-91e0c34d6a28/sessions" \
  -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/users/5e93b1a7-2c48-4d06-b7f5-91e0c34d6a28/offline-sessions" \
  -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/events?type=LOGIN_ERROR&max=10" -H "Authorization: Bearer $KC_ADMIN"
curl -s "$ADMIN_URL/admin-events?resourceTypes=USER" -H "Authorization: Bearer $KC_ADMIN"
```

Event types in the seed: `LOGIN`, `LOGIN_ERROR`, `LOGOUT`, `CLIENT_LOGIN`,
`IDENTITY_PROVIDER_LOGIN`, `REGISTER`, `UPDATE_PASSWORD`. Admin event operation
types: `CREATE`, `UPDATE`, `DELETE`.

## Errors

### OIDC (RFC 6749)

| HTTP | `error` | When |
|------|---------|------|
| 401 | `invalid_grant` | wrong password, unknown user, federated account, brute-force lock |
| 400 | `invalid_grant` | disabled account, pending required actions, bad/foreign refresh token |
| 401 | `invalid_client` | unknown client, or a confidential client's secret is wrong or missing |
| 400 | `unauthorized_client` | the client may not use that grant |
| 400 | `unsupported_grant_type` | anything but `password`, `refresh_token`, `client_credentials` |
| 401 | `invalid_token` | userinfo without a live, same-realm bearer |

### Admin REST API

| HTTP | `error` | When |
|------|---------|------|
| 401 | `HTTP 401 Unauthorized` | no bearer, or it is expired |
| 403 | `Forbidden` | bearer belongs to another realm, or lacks the `realm-management` role |
| 404 | `Realm does not exist` / `User not found` / `Could not find role: …` / `Could not find group by id` / `Could not find client` | unknown resource, including one in another realm |
| 409 | `Conflict detected` | duplicate username, email, role name or group path |
| 400 | `invalidPasswordMinLength` / `invalidPasswordMinUpperCaseChars` / `invalidPasswordMinDigits` / `invalidPasswordNotUsername` | fails the realm password policy |
| 400 | plain message | missing username/role/group name, public client secret, group with subgroups, unknown required action |
