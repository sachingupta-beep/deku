# Logto Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$LOGTO_API_URL`; responses are verbatim (long objects elided with
`…`). Examples assume:

```bash
export MGMT='logto_at_ci_full_9f14c73e0b2a'                     # Management API, scope all
export MGMT_RO='logto_at_reporting_ro_5b07d21f8c64'             # Management API, scope read:user
export STATUS_TOKEN='logto_at_amelia_status_c8e05a1976b3'       # Orbit Status API
export ORG_TOKEN='logto_at_amelia_org_platform_7a63f04c9e21'    # urn:logto:organization:org5platform1
```

## Discovery

```bash
curl -s "$LOGTO_API_URL/oidc/.well-known/openid-configuration"
```
```json
{
  "issuer": "https://auth.orbit-labs.com/oidc",
  "authorization_endpoint": "https://auth.orbit-labs.com/oidc/auth",
  "token_endpoint": "https://auth.orbit-labs.com/oidc/token",
  "userinfo_endpoint": "https://auth.orbit-labs.com/oidc/me",
  "jwks_uri": "https://auth.orbit-labs.com/oidc/jwks",
  "revocation_endpoint": "https://auth.orbit-labs.com/oidc/token/revocation",
  "introspection_endpoint": "https://auth.orbit-labs.com/oidc/token/introspection",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token",
                            "client_credentials"],
  "id_token_signing_alg_values_supported": ["ES384"],
  "scopes_supported": ["openid", "offline_access", "profile", "email", "phone",
                       "roles", "urn:logto:scope:organizations",
                       "urn:logto:scope:organization_roles"],
  "code_challenge_methods_supported": ["S256"],
  "…": "…"
}
```

## Client credentials (machine-to-machine)

```bash
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "client_credentials", "client_id": "appm2m1a5e0y",
       "client_secret": "logto_secret_ci_pipeline_9a2b6d31",
       "resource": "https://default.logto.app/api", "scope": "all"}'
```
```json
{"access_token": "logto_at_191300b64996e58a7cf1b70e", "token_type": "Bearer",
 "expires_in": 3600, "scope": "all", "aud": "https://default.logto.app/api"}
```

A public client cannot use this grant at all:

```bash
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "client_credentials", "client_id": "app6qk2v9x1m"}'
```
```json
{"error": "unauthorized_client",
 "error_description": "The application Orbit Status SPA is not allowed to use the client_credentials grant."}
```

## Authorization code with PKCE

```bash
curl -s "$LOGTO_API_URL/oidc/auth?client_id=app6qk2v9x1m\
&redirect_uri=https://status.orbit-labs.com/callback&response_type=code\
&scope=openid%20profile%20email%20offline_access\
&resource=https://api.orbit-labs.com/status\
&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM\
&code_challenge_method=S256&state=orbit-status-42"
```
```json
{"redirect_to": "https://status.orbit-labs.com/callback?code=logto_code_bd585e20c279488a&state=orbit-status-42",
 "code": "logto_code_bd585e20c279488a", "state": "orbit-status-42",
 "sub": "n4k29xqf7bd1", "client_id": "app6qk2v9x1m",
 "note": "the mock returns the authorization code rather than redirecting, so the flow stays inspectable"}
```

PKCE is not optional for a public client:

```bash
curl -s "$LOGTO_API_URL/oidc/auth?client_id=app6qk2v9x1m\
&redirect_uri=https://status.orbit-labs.com/callback&response_type=code"
```
```json
{"error": "invalid_request",
 "error_description": "PKCE is required for SPA applications."}
```

Exchanging the code:

```bash
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "authorization_code", "client_id": "app6qk2v9x1m",
       "code": "logto_code_amelia_e70b2c948d15",
       "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
       "redirect_uri": "https://status.orbit-labs.com/callback"}'
```
```json
{"access_token": "logto_at_8f781011aecd87ee74b3ca74", "token_type": "Bearer",
 "expires_in": 3600,
 "scope": "read:incidents read:services write:incidents",
 "aud": "https://api.orbit-labs.com/status",
 "id_token": "eyJhbGciOiJFUzM4NCJ9.n4k29xqf7bd1.app6qk2v9x1m.orbit-labs-mock-signature",
 "refresh_token": "logto_rt_0a992b851ef92a46add2b83d"}
```

Note the `scope`: it is the intersection of what was requested with what
amelia's roles actually grant on that resource. Replaying the code is refused:

```json
{"error": "invalid_grant",
 "error_description": "The authorization code has already been used."}
```

## Organization tokens

Pass `organization_id` on a refresh exchange instead of a `resource`:

```bash
curl -s -X POST "$LOGTO_API_URL/oidc/token" -H 'Content-Type: application/json' \
  -d '{"grant_type": "refresh_token", "client_id": "app6qk2v9x1m",
       "refresh_token": "logto_rt_amelia_spa_04b7e21c9d38",
       "organization_id": "org5platform1"}'
```
```json
{"access_token": "logto_at_c89d67c29a410f9224165c96", "token_type": "Bearer",
 "expires_in": 3600, "scope": "org:billing org:invite org:read org:write",
 "aud": "urn:logto:organization:org5platform1",
 "refresh_token": "logto_rt_c0768793d0b4ff253ca86038",
 "id_token": "eyJhbGciOiJFUzM4NCJ9.n4k29xqf7bd1.app6qk2v9x1m.orbit-labs-mock-signature"}
```

The audience is the organization, and the scopes come from amelia's `org:admin`
role in that organization.

## Introspection

```bash
curl -s -X POST "$LOGTO_API_URL/oidc/token/introspection" \
  -H 'Content-Type: application/json' -d "{\"token\": \"$ORG_TOKEN\"}"
```
```json
{"active": true, "sub": "n4k29xqf7bd1", "client_id": "app6qk2v9x1m",
 "aud": "urn:logto:organization:org5platform1",
 "scope": "org:read org:write org:invite org:billing",
 "iss": "https://auth.orbit-labs.com/oidc", "token_type": "Bearer",
 "exp": 1812182400, "iat": 1780646400}
```

An unknown, revoked or expired token is not an error — RFC 7662 says report it
inactive:

```json
{"active": false}
```

## Userinfo

```bash
curl -s "$LOGTO_API_URL/oidc/me" -H "Authorization: Bearer $STATUS_TOKEN"
```
```json
{
  "sub": "n4k29xqf7bd1",
  "name": "Amelia Ortega",
  "username": "amelia",
  "picture": "https://cdn.orbit-labs.com/avatars/amelia.png",
  "email": "amelia.ortega@orbit-labs.com",
  "email_verified": true,
  "custom_data": {"seatId": "SEAT-114", "team": "platform",
                  "pagerDuty": "PD-4417"},
  "identities": {"github": {"userId": "1840221", "details": {"id": "1840221"}},
                 "google": {"userId": "108224503917744021883",
                            "details": {"id": "108224503917744021883"}}},
  "roles": ["admin"],
  "organizations": ["org5platform1"]
}
```

A machine token has no user behind it:

```bash
curl -s "$LOGTO_API_URL/oidc/me" -H "Authorization: Bearer $MGMT"
```
```json
{"error": "insufficient_scope",
 "error_description": "A machine-to-machine token has no user profile."}
```

## The Management API gate: one endpoint, four tokens

```bash
curl -s "$LOGTO_API_URL/api/users?page_size=5" -H "Authorization: Bearer $MGMT"
```
```json
{"items": [{"id": "n4k29xqf7bd1", "username": "amelia", "…": "…"}, "…"],
 "totalCount": 6, "page": 1, "pageSize": 5}
```

The read-only management token reads fine but cannot write:

```bash
curl -s -X POST "$LOGTO_API_URL/api/users" -H "Authorization: Bearer $MGMT_RO" \
  -H 'Content-Type: application/json' -d '{"username": "denied"}'
```
```json
{"code": "auth.insufficient_scope",
 "message": "The access token does not carry the required scope 'write:user'.",
 "data": {"scope": ["read:user"], "required": "write:user"}}
```

A valid token minted for a *different* resource is refused on audience, not on
authentication:

```bash
curl -s "$LOGTO_API_URL/api/users" -H "Authorization: Bearer $STATUS_TOKEN"
```
```json
{"code": "auth.forbidden",
 "message": "The access token was issued for https://api.orbit-labs.com/status, not for the Management API (https://default.logto.app/api).",
 "data": {"audience": "https://api.orbit-labs.com/status",
          "expected": "https://default.logto.app/api"}}
```

And no token at all is a 401:

```json
{"code": "auth.authorization_header_missing",
 "message": "Authorization header is missing or the token is invalid, revoked or expired."}
```

The organization token is not useless — it reaches exactly one endpoint, which
the Management API token is in turn refused from:

```bash
curl -s "$LOGTO_API_URL/api/my-organization" -H "Authorization: Bearer $ORG_TOKEN"
```
```json
{"id": "org5platform1", "name": "Orbit Platform",
 "description": "The team that runs status.orbit-labs.com",
 "isMfaRequired": true,
 "customData": {"tier": "internal", "region": "us-west"},
 "createdAt": 1704880800000}
```

## The password policy is enforced

`sign_in_experience.json` sets a 10-character minimum, two character classes and
a rejected-word list:

```bash
curl -s -X POST "$LOGTO_API_URL/api/users" -H "Authorization: Bearer $MGMT" \
  -H 'Content-Type: application/json' \
  -d '{"primaryEmail": "worded@orbit-labs.com", "password": "MyOrbitPassword2026!"}'
```
```json
{"code": "password.rejected",
 "message": "The password must not contain 'orbit'.", "data": {"word": "orbit"}}
```

```bash
curl -s -X POST "$LOGTO_API_URL/api/users" -H "Authorization: Bearer $MGMT" \
  -H 'Content-Type: application/json' \
  -d '{"primaryEmail": "short@orbit-labs.com", "password": "Sh0rt!"}'
```
```json
{"code": "password.rejected",
 "message": "The password must be at least 10 characters.",
 "data": {"minLength": 10}}
```

## Organization members carry their organization roles

```bash
curl -s "$LOGTO_API_URL/api/organizations/org5platform1/users" \
  -H "Authorization: Bearer $MGMT"
```
```json
[
  {"id": "n4k29xqf7bd1", "username": "amelia",
   "primaryEmail": "amelia.ortega@orbit-labs.com",
   "isSuspended": false, "hasPassword": true,
   "customData": {"seatId": "SEAT-114", "team": "platform", "…": "…"},
   "organizationRoles": [{"id": "orl0admin0001", "name": "org:admin"}]},
  {"id": "t8m3vc06wzr5", "username": "jonas",
   "organizationRoles": [{"id": "orl1member001", "name": "org:member"}], "…": "…"},
  "…"
]
```

Password hashes and salts never appear; `hasPassword` reports whether the
account has one at all.

## Suspension kills live tokens

```bash
curl -s -X PATCH "$LOGTO_API_URL/api/users/t8m3vc06wzr5/is-suspended" \
  -H "Authorization: Bearer $MGMT" -H 'Content-Type: application/json' \
  -d '{"isSuspended": true}'
```
```json
{"id": "t8m3vc06wzr5", "username": "jonas", "isSuspended": true, "…": "…"}
```

The refresh token jonas held no longer works:

```json
{"error": "invalid_grant", "error_description": "The refresh token is invalid."}
```

## Dashboard

```bash
curl -s "$LOGTO_API_URL/api/dashboard/users/total" -H "Authorization: Bearer $MGMT"
```
```json
{"totalUserCount": 6, "suspendedUserCount": 1, "applicationCount": 6,
 "organizationCount": 2, "roleCount": 5, "activeTokenCount": 8}
```
