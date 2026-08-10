# SuperTokens Core Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$SUPERTOKENS_API_URL`; responses are verbatim (long objects
elided with `…`). Examples assume:

```bash
export ST_KEY='orbit-labs-supertokens-core-key'
export ST_HEADERS=(-H "api-key: $ST_KEY" -H 'cdi-version: 5.1' -H 'Content-Type: application/json')
```

Two things to keep in mind while reading these: the core puts domain outcomes in
the **body** as a `status` string with HTTP 200, and every recipe path is
tenant-scoped (`/recipe/...` is shorthand for `/appid-public/public/recipe/...`).

## Health

```bash
curl -s "$SUPERTOKENS_API_URL/health"
```
```json
{"status": "ok"}
```

The core's own probe is plain text:

```bash
curl -s "$SUPERTOKENS_API_URL/hello"
```
```
Hello
```

## The api-key is the only thing that gets a 401

```bash
curl -s "$SUPERTOKENS_API_URL/config"
```
```json
{"message": "Invalid API key"}
```
```
HTTP 401
```

```bash
curl -s "$SUPERTOKENS_API_URL/config" -H "api-key: $ST_KEY"
```
```json
{"status": "OK", "path": "/usr/lib/supertokens/config.yaml"}
```

## Tenants

```bash
curl -s "$SUPERTOKENS_API_URL/recipe/multitenancy/tenant/list" -H "api-key: $ST_KEY"
```
```json
{
  "status": "OK",
  "tenants": [
    {"tenantId": "public",
     "emailPassword": {"enabled": true},
     "thirdParty": {"enabled": true, "providers": ["github", "google"]},
     "passwordless": {"enabled": false, "flowType": "", "contactMethod": ""},
     "firstFactors": ["emailpassword", "thirdparty"],
     "requiredSecondaryFactors": [],
     "coreConfig": {"password_reset_token_lifetime": 3600000,
                    "email_verification_token_lifetime": 86400000}},
    {"tenantId": "orbit-enterprise",
     "emailPassword": {"enabled": false},
     "thirdParty": {"enabled": true, "providers": ["okta"]},
     "passwordless": {"enabled": true,
                      "flowType": "USER_INPUT_CODE_AND_MAGIC_LINK",
                      "contactMethod": "EMAIL"},
     "firstFactors": ["thirdparty", "otp-email", "link-email"],
     "requiredSecondaryFactors": ["totp"], "…": "…"}
  ]
}
```

An unknown tenant in the path is one of the few real 404s:

```bash
curl -s "$SUPERTOKENS_API_URL/appid-public/orbit-nope/recipe/multitenancy/tenant" \
  -H "api-key: $ST_KEY"
```
```json
{"message": "Tenant with id orbit-nope does not exist"}
```

## Sign in

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/signin" "${ST_HEADERS[@]}" \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "OrbitSuperTokens2026!"}'
```
```json
{
  "status": "OK",
  "user": {
    "id": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1",
    "isPrimaryUser": true,
    "timeJoined": 1704880800000,
    "tenantIds": ["public"],
    "emails": ["amelia.ortega@orbit-labs.com"],
    "phoneNumbers": [],
    "thirdParty": [{"id": "github", "userId": "1840221"}],
    "loginMethods": [
      {"recipeId": "emailpassword",
       "recipeUserId": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1",
       "tenantIds": ["public"], "timeJoined": 1704880800000,
       "verified": true, "email": "amelia.ortega@orbit-labs.com"},
      {"recipeId": "thirdparty",
       "recipeUserId": "c6b90e47-2f13-4a85-8d60-b41e7c09f2a5",
       "tenantIds": ["public"], "timeJoined": 1739269800000,
       "verified": true, "email": "amelia.ortega@orbit-labs.com",
       "thirdParty": {"id": "github", "userId": "1840221"}}
    ]
  },
  "recipeUserId": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1"
}
```

Amelia is a **primary user** with two login methods folded under one id — the
account-linking shape.

A wrong password is still HTTP 200:

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/signin" "${ST_HEADERS[@]}" \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "notmypassword"}'
```
```json
{"status": "WRONG_CREDENTIALS_ERROR"}
```

So is an unknown email — the two are deliberately indistinguishable.

## The tenant decides which recipes exist

The same user, the same password, the other tenant:

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/recipe/signin" \
  "${ST_HEADERS[@]}" \
  -d '{"email": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!"}'
```
```json
{"status": "EMAIL_PASSWORD_NOT_ENABLED_ERROR"}
```

And the mirror image — passwordless is off on `public`:

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/signinup/code" "${ST_HEADERS[@]}" \
  -d '{"email": "noor.aziz@orbit-labs.com"}'
```
```json
{"status": "PASSWORDLESS_NOT_ENABLED_ERROR"}
```

## Passwordless

```bash
curl -s -X POST \
  "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/recipe/signinup/code" \
  "${ST_HEADERS[@]}" -d '{"email": "priya.raman@orbit-labs.com"}'
```
```json
{"status": "OK", "preAuthSessionId": "st-preauth-99e3cc2657b0",
 "codeId": "st-code-3e0495c60b", "deviceId": "st-device-20f07450f1c6",
 "userInputCode": "124629", "linkCode": "st-link-f10fb078e47a4fae",
 "timeCreated": 1785935137001, "codeLifetime": 900000}
```

Wrong guesses are counted on the device:

```bash
curl -s -X POST \
  "$SUPERTOKENS_API_URL/appid-public/orbit-enterprise/recipe/signinup/code/consume" \
  "${ST_HEADERS[@]}" \
  -d '{"preAuthSessionId": "st-preauth-noor-91d7a205",
       "deviceId": "st-device-noor-3c8b0f4e", "userInputCode": "000000"}'
```
```json
{"status": "INCORRECT_USER_INPUT_CODE_ERROR",
 "failedCodeInputAttemptCount": 1, "maximumCodeInputAttempts": 5}
```

Five wrong guesses burns the device, after which the flow must restart
(`RESTART_FLOW_ERROR`).

## Sessions

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session" "${ST_HEADERS[@]}" \
  -d '{"userId": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1",
       "userDataInJWT": {"role": "owner"},
       "userDataInDatabase": {"device": "cli"}, "enableAntiCsrf": true}'
```
```json
{
  "status": "OK",
  "session": {"handle": "02c89c0c-d5b1-4e8f-8248-3ff393a42beb",
              "userId": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1",
              "recipeUserId": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1",
              "userDataInJWT": {"role": "owner"}, "tenantId": "public"},
  "accessToken": {"token": "st-at-842da608c2884a29",
                  "expiry": 1794575137005, "createdTime": 1785935137005},
  "refreshToken": {"token": "st-rt-232f49f218564ecd",
                   "expiry": 1794575137005, "createdTime": 1785935137005},
  "antiCsrfToken": "st-csrf-0824f6d9"
}
```

Verification distinguishes "gone" from "stale":

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session/verify" "${ST_HEADERS[@]}" \
  -d '{"accessToken": "st-at-does-not-exist"}'
```
```json
{"status": "UNAUTHORISED", "message": "Session does not exist."}
```

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session/verify" "${ST_HEADERS[@]}" \
  -d '{"accessToken": "st-at-amelia-4c19f7e0b83d", "doAntiCsrfCheck": true,
       "antiCsrfToken": "st-csrf-not-mine"}'
```
```json
{"status": "TRY_REFRESH_TOKEN", "message": "anti-csrf check failed"}
```

## Token theft

Refresh tokens rotate. The seed carries a token that has already been rotated
once; replaying it is treated as theft:

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session/refresh" "${ST_HEADERS[@]}" \
  -d '{"refreshToken": "st-rt-jonas-0e47c95b3d18"}'
```
```json
{"status": "TOKEN_THEFT_DETECTED",
 "session": {"handle": "6d2b83f0-14c7-4a59-9e02-b7f5c168d4a3",
             "userId": "5a92c04f-1b76-4d38-9e51-c8f0b273a469",
             "recipeUserId": "5a92c04f-1b76-4d38-9e51-c8f0b273a469"}}
```

The session is revoked as a side effect, so the access token that was working a
moment ago now fails:

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/session/verify" "${ST_HEADERS[@]}" \
  -d '{"accessToken": "st-at-jonas-91e5c7d40a26"}'
```
```json
{"status": "UNAUTHORISED", "message": "Session does not exist."}
```

## User metadata is a shallow merge

```bash
curl -s -X PUT "$SUPERTOKENS_API_URL/recipe/user/metadata" "${ST_HEADERS[@]}" \
  -d '{"userId": "0d1e7b3a-5c92-4f68-a017-9e4b3d6c25f1",
       "metadataUpdate": {"team": "platform-core", "seatId": null,
                          "pagerDuty": "PD-4417"}}'
```
```json
{"status": "OK",
 "metadata": {"firstName": "Amelia", "lastName": "Ortega",
              "team": "platform-core", "onboardedAt": "2024-01-10",
              "pagerDuty": "PD-4417"}}
```

`team` was overwritten, `pagerDuty` added, and the `null` removed `seatId`. The
untouched keys survive.

## Roles and permissions

```bash
curl -s "$SUPERTOKENS_API_URL/recipe/role/permissions?role=owner" -H "api-key: $ST_KEY"
```
```json
{"status": "OK",
 "permissions": ["status:read", "status:write", "incident:write",
                 "billing:read", "billing:write", "user:admin"]}
```

```bash
curl -s "$SUPERTOKENS_API_URL/recipe/role/permissions?role=auditor" -H "api-key: $ST_KEY"
```
```json
{"status": "UNKNOWN_ROLE_ERROR"}
```

## Account linking

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/accountlinking/user/primary" \
  "${ST_HEADERS[@]}" -d '{"recipeUserId": "b3f61d08-9e24-4a75-8c30-71d5e0a94b26"}'
```
```json
{"status": "OK", "wasAlreadyAPrimaryUser": false,
 "user": {"id": "b3f61d08-9e24-4a75-8c30-71d5e0a94b26", "isPrimaryUser": true,
          "emails": ["helena.park@orbit-labs.com"],
          "thirdParty": [{"id": "github", "userId": "2210448"}],
          "loginMethods": [{"recipeId": "thirdparty", "…": "…"}], "…": "…"}}
```

Then folding another recipe user into it:

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/accountlinking/user/link" \
  "${ST_HEADERS[@]}" \
  -d '{"recipeUserId": "e84c25b7-0a63-4f91-bd28-3c7016fa5d84",
       "primaryUserId": "b3f61d08-9e24-4a75-8c30-71d5e0a94b26"}'
```
```json
{"status": "OK", "accountsAlreadyLinked": false,
 "user": {"id": "b3f61d08-9e24-4a75-8c30-71d5e0a94b26",
          "emails": ["helena.park@orbit-labs.com", "rohit.bansal@orbit-labs.com"],
          "loginMethods": [{"recipeId": "thirdparty", "…": "…"},
                           {"recipeId": "emailpassword", "…": "…"}], "…": "…"}}
```

The absorbed id no longer resolves as a user of its own:

```bash
curl -s "$SUPERTOKENS_API_URL/user/id?userId=e84c25b7-0a63-4f91-bd28-3c7016fa5d84" \
  -H "api-key: $ST_KEY"
```
```json
{"status": "UNKNOWN_USER_ID_ERROR"}
```

## Password reset

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/user/password/reset" "${ST_HEADERS[@]}" \
  -d '{"method": "token", "token": "st-pwreset-9f28c4e07b5a13d6",
       "newPassword": "OrbitJonasNew2026!"}'
```
```json
{"status": "OK", "userId": "5a92c04f-1b76-4d38-9e51-c8f0b273a469",
 "email": "jonas.pereira@orbit-labs.com"}
```

Replaying a spent token returns `RESET_PASSWORD_INVALID_TOKEN_ERROR`, and the
old password stops working:

```bash
curl -s -X POST "$SUPERTOKENS_API_URL/recipe/signin" "${ST_HEADERS[@]}" \
  -d '{"email": "jonas.pereira@orbit-labs.com", "password": "OrbitJonas2026!"}'
```
```json
{"status": "WRONG_CREDENTIALS_ERROR"}
```
