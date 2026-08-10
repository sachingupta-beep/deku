# Zitadel Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$ZITADEL_API_URL`; responses are verbatim (long objects elided
with `…`). Examples assume:

```bash
export ZT_ADMIN='zt-pat-instance-admin-5b07d21f8c64'   # IAM_OWNER
export ZT_CI='zt-pat-orbit-ci-9f14c73e0b2a'            # Orbit Labs, may write
export ZT_RO='zt-pat-readonly-c8e05a1976b3'            # Orbit Labs, read only
export ZT_PARTNER='zt-pat-partners-2d47b9e01f5c'       # Orbit Partners
export ORBIT_LABS='280310551611113987'
export ORBIT_PARTNERS='280310551611113988'
```

## Health

```bash
curl -s "$ZITADEL_API_URL/health"
```
```json
{"status": "ok"}
```

## The organization is a header

```bash
curl -s "$ZITADEL_API_URL/management/v1/orgs/me" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"
```
```json
{"org": {"id": "280310551611113987", "name": "Orbit Labs",
         "primaryDomain": "orbit-labs.zitadel.cloud",
         "state": "ORG_STATE_ACTIVE",
         "details": {"sequence": "1842", "changeDate": "2026-05-26T08:12:00Z",
                     "resourceOwner": "280310551611113987"}}}
```

The same token pointed at another org is refused — not because the org is
unknown, but because the token does not belong to it:

```bash
curl -s "$ZITADEL_API_URL/management/v1/orgs/me" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_PARTNERS"
```
```json
{"code": 7,
 "message": "No matching permissions found (AUTH-boeQa): token belongs to organisation 280310551611113987, not 280310551611113988"}
```

An inactive org is a *precondition* failure — it exists, it just cannot serve
requests:

```json
{"code": 9, "message": "Organisation Orbit Archive is not active (ORG-Aq49k)"}
```

## Sessions are built up factor by factor

There is no login call. Start with whatever you can prove:

```bash
curl -s -X POST "$ZITADEL_API_URL/v2/sessions" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"checks": {"user": {"loginName": "amelia@orbit-labs.zitadel.cloud"}},
       "metadata": {"device": "thinkpad-t14"},
       "userAgent": {"fingerprintId": "fp-doc-run"}}'
```
```json
{
  "sessionId": "281940113077380001",
  "sessionToken": "zt-session-d905e17e7aa0d0a9fc2a",
  "details": {"sequence": "1105", "changeDate": "2026-08-06T05:50:37Z",
              "resourceOwner": "280310551611113987"},
  "factors": {
    "user": {"verifiedAt": "2026-08-06T05:50:37Z",
             "id": "280310551611114001",
             "loginName": "amelia@orbit-labs.zitadel.cloud",
             "displayName": "Amelia Ortega",
             "organizationId": "280310551611113987"}
  }
}
```

Then add the password:

```bash
curl -s -X PATCH "$ZITADEL_API_URL/v2/sessions/281940113077380001" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"sessionToken": "zt-session-d905e17e7aa0d0a9fc2a",
       "checks": {"password": {"password": "OrbitZitadel2026!"}}}'
```
```json
{"sessionToken": "zt-session-9763226d4df486e095aa",
 "details": {"sequence": "1106", "…": "…"},
 "factors": {"user": {"verifiedAt": "2026-08-06T05:50:37Z", "…": "…"},
             "password": {"verifiedAt": "2026-08-06T05:50:37Z"}}}
```

**The token rotated.** Replaying the old one is refused:

```json
{"code": 7, "message": "Invalid session token (COMMAND-sGr42)"}
```

Then the second factor:

```bash
curl -s -X PATCH "$ZITADEL_API_URL/v2/sessions/281940113077380001" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"sessionToken": "zt-session-9763226d4df486e095aa",
       "checks": {"totp": {"code": "482913"}}}'
```
```json
{"sessionToken": "zt-session-f93fc675b5d9d43addce",
 "details": {"sequence": "1107", "…": "…"},
 "factors": {"user": {"verifiedAt": "2026-08-06T05:50:37Z", "…": "…"},
             "password": {"verifiedAt": "2026-08-06T05:50:37Z"},
             "totp": {"verifiedAt": "2026-08-06T05:50:37Z"}}}
```

Each factor keeps its own `verifiedAt`. A failing check aborts the whole call —
Zitadel does not partially apply a `checks` block.

## The login policy is enforced at the end

The seed carries a password-only session for the same user on a second device.
Orbit Labs sets `forceMfa`:

```bash
curl -s -X POST "$ZITADEL_API_URL/v2/oidc/auth_requests/281940113077373002" \
  -H 'Content-Type: application/json' -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"session": {"sessionId": "281940113077370886",
                   "sessionToken": "zt-session-amelia-laptop-58c0e7d3"}}'
```
```json
{"code": 9,
 "message": "Session does not satisfy the login policy; missing: a second factor (the organisation forces MFA) (COMMAND-Sfefs)"}
```

The session that reached `aal2` above finishes cleanly:

```json
{"details": {"sequence": "1107", "…": "…"},
 "callbackUrl": "https://status.orbit-labs.com/callback?code=zt-code-0c5727d24347b047&state=orbit-status-42",
 "sessionId": "281940113077380001",
 "factors": ["password", "totp", "user"]}
```

And the *same shape* of session — user plus password only — succeeds in the
partner org, which does not force MFA:

```json
{"details": {"sequence": "1108", "resourceOwner": "280310551611113988", "…": "…"},
 "callbackUrl": "https://portal.orbit-partners.com/callback?code=zt-code-ea6378f9b84406d1&state=partner-19",
 "sessionId": "281940113077370884",
 "factors": ["password", "user"]}
```

A passwordless session works too: Helena has a passkey, and `user` + `webAuthN`
satisfies the policy without a password.

## Users

```bash
curl -s "$ZITADEL_API_URL/v2/users/280310551611114001" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"
```
```json
{
  "user": {
    "userId": "280310551611114001",
    "details": {"sequence": "1104", "changeDate": "2026-05-26T08:12:00Z",
                "resourceOwner": "280310551611113987"},
    "state": "USER_STATE_ACTIVE",
    "username": "amelia@orbit-labs.zitadel.cloud",
    "loginNames": ["amelia@orbit-labs.zitadel.cloud",
                   "amelia.ortega@orbit-labs.com"],
    "preferredLoginName": "amelia@orbit-labs.zitadel.cloud",
    "human": {
      "profile": {"givenName": "Amelia", "familyName": "Ortega",
                  "nickName": "amelia", "displayName": "Amelia Ortega"},
      "email": {"email": "amelia.ortega@orbit-labs.com", "isVerified": true},
      "phone": {"phone": "+14155550101", "isVerified": true},
      "passwordChangeRequired": false, "…": "…"
    }
  }
}
```

The same id fetched through the partner org is simply not there:

```json
{"code": 5, "message": "User 280310551611114001 not found (QUERY-Dfbg2)"}
```

## Setting the first password activates an INITIAL user

```bash
curl -s -X POST "$ZITADEL_API_URL/v2/users/280310551611114004/password" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"newPassword": {"password": "NebulaRohit2026!"}}'
```
```json
{"details": {"sequence": "1109", "changeDate": "2026-08-06T05:50:37Z",
             "resourceOwner": "280310551611113987"}}
```

Rohit's `state` moves from `USER_STATE_INITIAL` to `USER_STATE_ACTIVE`. A
password that fails the complexity policy names the rule it broke:

```json
{"code": 3,
 "message": "Password does not fulfil the complexity policy: needs a symbol (COMMAND-2Md9a)"}
```

## Three distinct refusals

```bash
curl -s "$ZITADEL_API_URL/admin/v1/instance"
```
```json
{"code": 16, "message": "authentication failed (AUTH-7fs3d)"}
```

```bash
curl -s "$ZITADEL_API_URL/admin/v1/instance" -H "Authorization: Bearer $ZT_CI"
```
```json
{"code": 7,
 "message": "No matching permissions found (AUTH-boeQa): IAM_OWNER required"}
```

```bash
curl -s -X POST "$ZITADEL_API_URL/v2/users/human" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_RO" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"username": "denied@orbit-labs.zitadel.cloud",
       "profile": {"givenName": "De", "familyName": "Nied"}}'
```
```json
{"code": 7,
 "message": "No matching permissions found (AUTH-boeQa): ORG_OWNER_VIEWER may not write"}
```

## Grants are checked against the project's declared roles

```bash
curl -s -X POST "$ZITADEL_API_URL/management/v1/users/280310551611114004/grants" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" \
  -d '{"projectId": "281940113077371002", "roleKeys": ["billing.superuser"]}'
```
```json
{"code": 3,
 "message": "Roles not defined on this project: billing.superuser (COMMAND-8M9fa)"}
```

```bash
curl -s -X POST "$ZITADEL_API_URL/management/v1/users/grants/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"userId": "280310551611114001"}'
```
```json
{"details": {"totalResult": "2", "processedSequence": "1109",
             "timestamp": "2026-08-06T05:50:37Z"},
 "result": [
   {"id": "281940113077372001", "userId": "280310551611114001",
    "projectId": "281940113077371001",
    "roleKeys": ["status.admin", "status.incident.write", "status.read"],
    "state": "USER_GRANT_STATE_ACTIVE", "displayName": "Amelia Ortega",
    "projectName": "Orbit Status Platform", "…": "…"},
   {"id": "281940113077372002", "projectName": "Orbit Billing", "…": "…"}]}
```

## The eventstore

Every write allocates from the same monotonic counter the event log uses, so a
write's `details.sequence` and its event line up.

```bash
curl -s -X POST "$ZITADEL_API_URL/admin/v1/events/_search" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $ZT_CI" \
  -H "x-zitadel-orgid: $ORBIT_LABS" -d '{"limit": 2}'
```
```json
{"events": [
  {"sequence": "1107", "orgId": "280310551611113987",
   "type": "user.human.mfa.otp.check.succeeded", "aggregateType": "user",
   "aggregateId": "280310551611114001", "editorUserId": "",
   "editorDisplayName": "", "creationDate": "2026-08-06T05:50:37Z",
   "payload": {}},
  {"sequence": "1106", "type": "user.human.password.check.succeeded",
   "aggregateId": "280310551611114001", "…": "…"}]}
```

Failed password checks are recorded too — `user.human.password.check.failed` —
which is how the seeded lock on Dmitri is explained in the log.

## An org must keep an owner

```bash
curl -s -X DELETE \
  "$ZITADEL_API_URL/management/v1/orgs/me/members/280310551611114001" \
  -H "Authorization: Bearer $ZT_CI" -H "x-zitadel-orgid: $ORBIT_LABS"
```
```json
{"code": 9, "message": "Cannot remove the last organisation owner (COMMAND-5M9fb)"}
```
