# SuperTokens Core API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$SUPERTOKENS_API_URL`.** Responses are deterministic fixtures.

## Base URL and headers

| Variable | Purpose |
|----------|---------|
| `SUPERTOKENS_API_URL` | Base URL for all requests |

Set the headers once to follow the examples:

```bash
export ST_KEY='orbit-labs-supertokens-core-key'
export ST=(-H "api-key: $ST_KEY" -H 'cdi-version: 5.1' -H 'Content-Type: application/json')
```

## The response contract

Domain outcomes are in the **body**, as a `status` string, with HTTP 200. Check
`body.status`. Non-2xx is a transport problem only:

| HTTP | Cause |
|------|-------|
| 401 | missing or wrong `api-key` |
| 400 | unsupported `cdi-version`, or a malformed body |
| 404 | unknown tenant in the path |
| 403 | deleting the `public` tenant |

Statuses you will see: `OK`, `WRONG_CREDENTIALS_ERROR`,
`EMAIL_ALREADY_EXISTS_ERROR`, `UNKNOWN_EMAIL_ERROR`, `UNKNOWN_USER_ID_ERROR`,
`UNKNOWN_ROLE_ERROR`, `UNKNOWN_PROVIDER_ERROR`,
`EMAIL_PASSWORD_NOT_ENABLED_ERROR`, `PASSWORDLESS_NOT_ENABLED_ERROR`,
`THIRD_PARTY_NOT_ENABLED_ERROR`, `INCORRECT_USER_INPUT_CODE_ERROR`,
`EXPIRED_USER_INPUT_CODE_ERROR`, `RESTART_FLOW_ERROR`, `UNAUTHORISED`,
`TRY_REFRESH_TOKEN`, `TOKEN_THEFT_DETECTED`,
`RESET_PASSWORD_INVALID_TOKEN_ERROR`, `EMAIL_ALREADY_VERIFIED_ERROR`,
`EMAIL_VERIFICATION_INVALID_TOKEN_ERROR`, `INPUT_USER_IS_NOT_A_PRIMARY_USER`,
`RECIPE_USER_ID_ALREADY_LINKED_WITH_PRIMARY_USER_ID_ERROR`.

## Tenancy

Every recipe path exists twice: `/recipe/...` (the `public` tenant) and
`/appid-{appId}/{tenantId}/recipe/...`.

| Tenant | emailpassword | thirdparty | passwordless | first factors |
|--------|---------------|------------|--------------|---------------|
| `public` | on | `github`, `google` | off | `emailpassword`, `thirdparty` |
| `orbit-enterprise` | off | `okta` | on, `EMAIL`, code + link | `thirdparty`, `otp-email`, `link-email` |

```bash
curl -s "$SUPERTOKENS_API_URL/recipe/multitenancy/tenant/list" -H "api-key: $ST_KEY"
curl -s "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/recipe/multitenancy/tenant" \
  -H "api-key: $ST_KEY"
curl -s -X PUT "$SUPERTOKENS_API_URL/recipe/multitenancy/tenant" "${ST[@]}" \
  -d '{"tenantId": "orbit-sandbox", "emailPasswordEnabled": true,
       "firstFactors": ["emailpassword"]}'
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/multitenancy/tenant/remove" "${ST[@]}" \
  -d '{"tenantId": "orbit-sandbox"}'
curl -s -X POST \
  "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/recipe/multitenancy/tenant/user" \
  "${ST[@]}" -d '{"recipeUserId": "5a92c04f-1b76-4d38-9e51-c8f0b273a469"}'
```

Associating a user with a tenant does **not** enable a recipe that tenant has
off — a subsequent sign-in still returns `EMAIL_PASSWORD_NOT_ENABLED_ERROR`.

## Seed users

| User id | Recipes | Password |
|---------|---------|----------|
| `0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1` amelia | emailpassword + thirdparty (linked) | `OrbitSuperTokens2026!` |
| `5a92c04f-1b76-4d38-9e51-c8f0b273a469` jonas | emailpassword | `OrbitJonas2026!` |
| `b3f61d08-9e24-4a75-8c30-71d5e0a94b26` helena | thirdparty (`github`/`2210448`) | — |
| `e84c25b7-0a63-4f91-bd28-3c7016fa5d84` rohit | emailpassword, **unverified** | `OrbitRohit2026!` |
| `7c05f9e2-46b1-48da-9037-2ba8d1c6e053` noor | passwordless, `orbit-enterprise` | — |
| `2f7a83c1-d504-4e69-b1a2-60e9c745f83b` sync bot | emailpassword | `OrbitSyncBot2026!` |

Amelia's thirdparty login method has its own recipe user id
`c6b90e47-2f13-4a85-8d60-b41e7c09f2a5` under the same primary user.

## emailpassword

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/signin" "${ST[@]}" \
  -d '{"email": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!"}'

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/signup" "${ST[@]}" \
  -d '{"email": "iris.tanaka@orbit-labs.com", "password": "OrbitIris2026!"}'

curl -s "$SUPERTOKENS_API_URL/recipe/user?email=jonas.pereira@orbit-labs.com" \
  -H "api-key: $ST_KEY"

curl -s -X PUT "$SUPERTOKENS_API_URL/recipe/user" "${ST[@]}" \
  -d '{"recipeUserId": "2f7a83c1-d504-4e69-b1a2-60e9c745f83b",
       "email": "orbit-sync@orbit-labs.com"}'
```

An unknown email and a wrong password both return `WRONG_CREDENTIALS_ERROR`.
Changing an email marks it unverified again; changing a password revokes every
session that recipe user holds.

## Password reset

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/user/password/reset/token" "${ST[@]}" \
  -d '{"userId": "5a92c04f-1b76-4d38-9e51-c8f0b273a469"}'

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/user/password/reset" "${ST[@]}" \
  -d '{"method": "token", "token": "st-pwreset-9f28c4e07b5a13d6",
       "newPassword": "OrbitJonasNew2026!"}'
```

Seeded tokens: `st-pwreset-9f28c4e07b5a13d6` (jonas, unused),
`st-pwreset-41c7e096b3d825af` (amelia, **already spent** → 
`RESET_PASSWORD_INVALID_TOKEN_ERROR`).

## thirdparty

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/signinup" "${ST[@]}" \
  -d '{"thirdPartyId": "github", "thirdPartyUserId": "2210448",
       "email": "helena.park@orbit-labs.com"}'

curl -s "$SUPERTOKENS_API_URL/recipe/user?thirdPartyId=github&thirdPartyUserId=1840221" \
  -H "api-key: $ST_KEY"
```

Known ids: `github/1840221` (amelia), `github/2210448` (helena),
`google/…` is open. A provider not on the tenant returns
`UNKNOWN_PROVIDER_ERROR`; an unknown pair creates a user and reports
`createdNewUser: true`.

## passwordless (enterprise tenant only)

```bash
curl -s -X POST \
  "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/recipe/signinup/code" \
  "${ST[@]}" -d '{"email": "priya.raman@orbit-labs.com"}'

curl -s -X POST \
  "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/recipe/signinup/code/consume" \
  "${ST[@]}" -d '{"preAuthSessionId": "st-preauth-noor-91d7a205",
                  "deviceId": "st-device-noor-3c8b0f4e", "userInputCode": "482913"}'
```

Seeded devices: `st-preauth-noor-91d7a205` (code `482913`, open) and
`st-preauth-helena-4e08b3f7` (code `770412`, **expired**, 2 failed attempts
already recorded). A wrong code returns `INCORRECT_USER_INPUT_CODE_ERROR` with
the running count; five wrong guesses burns the device and later calls return
`RESTART_FLOW_ERROR`. Consuming with `linkCode` instead of
`deviceId` + `userInputCode` also works.

## session

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session" "${ST[@]}" \
  -d '{"userId": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1",
       "userDataInJWT": {"role": "owner"},
       "userDataInDatabase": {"device": "cli"}, "enableAntiCsrf": true}'

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session/verify" "${ST[@]}" \
  -d '{"accessToken": "st-at-amelia-4c19f7e0b83d", "doAntiCsrfCheck": true,
       "antiCsrfToken": "st-csrf-amelia-e37b"}'

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session/refresh" "${ST[@]}" \
  -d '{"refreshToken": "st-rt-jonas-mobile-c81d6a03"}'

curl -s "$SUPERTOKENS_API_URL/recipe/session/user?userId=0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1" \
  -H "api-key: $ST_KEY"

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session/remove" "${ST[@]}" \
  -d '{"sessionHandles": ["0a4f1c7e-8b25-4d93-a610-5f2c9e08b374"]}'
```

Seeded sessions:

| Handle | User | Access token | Refresh token |
|--------|------|--------------|---------------|
| `0a4f1c7e-8b25-4d93-a610-5f2c9e08b374` | amelia | `st-at-amelia-4c19f7e0b83d` | `st-rt-amelia-6b40d2a97f15` |
| `6d2b83f0-14c7-4a59-9e02-b7f5c168d4a3` | jonas | `st-at-jonas-91e5c7d40a26` | `st-rt-jonas-2f83b0e6c194` |
| `b917e4c2-05d8-4f61-8a37-2c60e9db1745` | jonas (mobile) | `st-at-jonas-mobile-70b2e4f9` | `st-rt-jonas-mobile-c81d6a03` |
| `3e58a1d6-7c04-42bf-9d13-8b0f6e2a57c9` | noor | `st-at-noor-d502a8f371c6` | `st-rt-noor-48c1e7b09d35` |
| `c40d7f19-2a86-4e35-b8c1-905e3f7a26d0` | sync bot | `st-at-syncbot-e6094c2b7f38` | `st-rt-syncbot-1d75a0e934bc` |

`st-rt-jonas-0e47c95b3d18` is the **already-rotated** ancestor of jonas's
desktop token — refreshing with it returns `TOKEN_THEFT_DETECTED` and revokes
the session.

## emailverification

```bash
curl -s "$SUPERTOKENS_API_URL/recipe/user/email/verify?userId=e84c25b7-0a63-4f91-bd28-3c7016fa5d84" \
  -H "api-key: $ST_KEY"

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/user/email/verify/token" "${ST[@]}" \
  -d '{"userId": "e84c25b7-0a63-4f91-bd28-3c7016fa5d84"}'

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/user/email/verify" "${ST[@]}" \
  -d '{"method": "token", "token": "st-emailverify-7b04d1a95c3e628f"}'
```

## usermetadata

```bash
curl -s "$SUPERTOKENS_API_URL/recipe/user/metadata?userId=0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1" \
  -H "api-key: $ST_KEY"

curl -s -X PUT "$SUPERTOKENS_API_URL/recipe/user/metadata" "${ST[@]}" \
  -d '{"userId": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1",
       "metadataUpdate": {"team": "platform-core", "seatId": null}}'
```

Shallow merge; `null` clears a key.

## userroles

```bash
curl -s "$SUPERTOKENS_API_URL/recipe/roles" -H "api-key: $ST_KEY"
curl -s "$SUPERTOKENS_API_URL/recipe/role/permissions?role=owner" -H "api-key: $ST_KEY"
curl -s -X PUT "$SUPERTOKENS_API_URL/recipe/role" "${ST[@]}" \
  -d '{"role": "auditor", "permissions": ["status:read", "billing:read"]}'
curl -s -X PUT "$SUPERTOKENS_API_URL/recipe/user/role" "${ST[@]}" \
  -d '{"userId": "b3f61d08-9e24-4a75-8c30-71d5e0a94b26", "role": "auditor"}'
curl -s "$SUPERTOKENS_API_URL/recipe/user/roles?userId=b3f61d08-9e24-4a75-8c30-71d5e0a94b26" \
  -H "api-key: $ST_KEY"
curl -s "$SUPERTOKENS_API_URL/recipe/role/users?role=engineer" -H "api-key: $ST_KEY"
```

Roles: `owner`, `engineer`, `support`, `service`, `viewer`. Grants are
per tenant.

## Account linking

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/accountlinking/user/primary" "${ST[@]}" \
  -d '{"recipeUserId": "b3f61d08-9e24-4a75-8c30-71d5e0a94b26"}'

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/accountlinking/user/link" "${ST[@]}" \
  -d '{"recipeUserId": "e84c25b7-0a63-4f91-bd28-3c7016fa5d84",
       "primaryUserId": "b3f61d08-9e24-4a75-8c30-71d5e0a94b26"}'

curl -s -X POST "$SUPERTOKENS_API_URL/recipe/accountlinking/user/unlink" "${ST[@]}" \
  -d '{"recipeUserId": "e84c25b7-0a63-4f91-bd28-3c7016fa5d84"}'
```

Linking folds the recipe user into the primary user: the absorbed id stops
resolving through `/user/id`, and the primary user's `emails` and `loginMethods`
grow. Unlinking gives it back its own user row.

## Users

```bash
curl -s "$SUPERTOKENS_API_URL/users?limit=10" -H "api-key: $ST_KEY"
curl -s "$SUPERTOKENS_API_URL/users?limit=10&includeRecipeIds=thirdparty" \
  -H "api-key: $ST_KEY"
curl -s "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/users?limit=10" \
  -H "api-key: $ST_KEY"
curl -s "$SUPERTOKENS_API_URL/users/count?includeAllTenants=true" -H "api-key: $ST_KEY"
curl -s "$SUPERTOKENS_API_URL/user/id?userId=0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1" \
  -H "api-key: $ST_KEY"
curl -s -X POST "$SUPERTOKENS_API_URL/user/remove" "${ST[@]}" \
  -d '{"userId": "2f7a83c1-d504-4e69-b1a2-60e9c745f83b"}'
```

`/users` paginates with `nextPaginationToken`; pass it back as
`paginationToken`. Deleting an unknown user is idempotent and still returns
`OK`.
