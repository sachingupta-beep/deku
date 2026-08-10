# Ory Kratos API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$ORY_KRATOS_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `ORY_KRATOS_API_URL` | Base URL for all requests |

Set the tokens and flow ids once to follow the examples:

```bash
export AMELIA='ory_st_amelia_4c19f7e0b83d'
export JONAS='ory_st_jonas_91e5c7d40a26'
export LOGIN_FLOW='f1a0c7e2-5b93-4d68-8017-2e6f931c5d47'
export BROWSER_FLOW='d80c5f13-27ba-4e69-91d4-6a03e7b28c50'
export AAL2_FLOW='2a97e0b8-4d16-43cf-8572-b1e0c9d64f35'
export REG_FLOW='b41d7e02-96c8-4f35-a80b-2e6f931c5d47'
export RECOVERY_FLOW='9e05a73f-1c48-4b26-a09d-58f2c6e34b17'
export VERIFY_FLOW='7c4e1b8a-0d33-4f95-b201-8e6a3c17d940'
export SETTINGS_FLOW='1d9f4a02-7b36-4c81-a5e0-92f7c103b846'
```

## The shape of everything

Kratos is flow-based. Every self-service interaction is two calls: create the
flow, then submit against its id. The flow object carries a `ui` you render:

```json
{"id": "…", "type": "api", "expires_at": "…",
 "ui": {"action": "…/self-service/login?flow=…", "method": "POST",
        "nodes": [{"type": "input", "group": "password",
                   "attributes": {"name": "identifier", "required": true},
                   "messages": [], "meta": {"label": {"text": "E-Mail"}}}],
        "messages": []},
 "state": "choose_method"}
```

**A failed submission returns 400 with that same object**, messages attached to
the offending nodes. Read `ui.nodes[].messages[].id` and `ui.messages[].id`, not
the HTTP status alone.

## Health and schemas

```bash
curl -s "$ORY_KRATOS_API_URL/health"
curl -s "$ORY_KRATOS_API_URL/health/alive"
curl -s "$ORY_KRATOS_API_URL/health/ready"
curl -s "$ORY_KRATOS_API_URL/version"
curl -s "$ORY_KRATOS_API_URL/schemas"
curl -s "$ORY_KRATOS_API_URL/schemas/default"
curl -s "$ORY_KRATOS_API_URL/schemas/partner"
```

| Schema | Required traits | Constraints |
|--------|-----------------|-------------|
| `default` | `email`, `name.first`, `name.last` | `role` ∈ {owner, engineer, support, service}; `seat_id` matches `^SEAT-[0-9]{3}$` |
| `partner` | `email`, `company` | |

Both set `additionalProperties: false`, so an unlisted trait is rejected with
`4000040`.

## Creating flows

```bash
curl -s "$ORY_KRATOS_API_URL/self-service/login/api"
curl -s "$ORY_KRATOS_API_URL/self-service/login/browser"
curl -s "$ORY_KRATOS_API_URL/self-service/login/api?aal=aal2" \
  -H "X-Session-Token: $JONAS"
curl -s "$ORY_KRATOS_API_URL/self-service/login/api?refresh=true" \
  -H "X-Session-Token: $JONAS"
curl -s "$ORY_KRATOS_API_URL/self-service/registration/api"
curl -s "$ORY_KRATOS_API_URL/self-service/recovery/api"
curl -s "$ORY_KRATOS_API_URL/self-service/verification/api"
curl -s "$ORY_KRATOS_API_URL/self-service/settings/api" -H "X-Session-Token: $JONAS"
```

`aal=aal2`, `refresh=true` and any settings flow need a live session (401
otherwise). Browser flows carry a hidden `csrf_token` node; API flows never do.

## Fetching a flow

```bash
curl -s "$ORY_KRATOS_API_URL/self-service/login/flows?id=$LOGIN_FLOW"
curl -s "$ORY_KRATOS_API_URL/self-service/registration/flows?id=$REG_FLOW"
curl -s "$ORY_KRATOS_API_URL/self-service/settings/flows?id=$SETTINGS_FLOW"
```

| Situation | Result |
|-----------|--------|
| unknown id | 404 `self_service_flow_not_found` |
| expired | **410 `self_service_flow_expired`** with `details.expired_at` |
| right id, wrong type | 404 |

## Login

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$LOGIN_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"method": "password", "identifier": "jonas.pereira@orbit-labs.com",
       "password": "OrbitJonas2026!"}'

# browser flows must echo the csrf token
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$BROWSER_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"csrf_token": "csrf-a71e0c93d45b8f26", "method": "password",
       "identifier": "jonas.pereira@orbit-labs.com",
       "password": "OrbitJonas2026!"}'

# oidc
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$LOGIN_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"method": "oidc", "provider": "github", "subject": "2210448"}'

# aal2 step-up
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$AAL2_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"method": "totp", "totp_code": "482913"}'

curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$AAL2_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"method": "lookup_secret", "lookup_secret": "91cd2f7a"}'
```

Failure modes:

| Situation | Where the message lands |
|-----------|-------------------------|
| missing `identifier` or `password` | on that node, `4000001` |
| wrong password / unknown identifier / no password credential | `ui.messages`, `4000006` — all three identical |
| identity `state: inactive` | `ui.messages`, `4000035` |
| browser flow without `csrf_token` | 403 `security_csrf_violation` |
| wrong TOTP or lookup secret | on the node, `4060006` |

Logging in as an identity with TOTP (amelia) returns an **aal1** session plus a
`redirect_browser_to` naming a fresh aal2 flow. A consumed lookup secret is
removed from the credential.

## Registration

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/registration?flow=$REG_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"traits": {"email": "iris.tanaka@orbit-labs.com",
                  "name": {"first": "Iris", "last": "Tanaka"},
                  "role": "support", "seat_id": "SEAT-410"},
       "password": "StellarIris2026"}'

# the same payload against the other schema
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/registration?flow=$REG_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"schema_id": "partner",
       "traits": {"email": "iris.tanaka@orbit-labs.com",
                  "name": {"first": "Iris", "last": "Tanaka"}},
       "password": "StellarIris2026"}'
```

The second is 400: `traits.company` required (`4000001`) and `traits.name` not
allowed (`4000040`). Passwords shorter than 8 characters are `4000032`; a taken
email is `4000007` on `traits.email`.

A successful registration returns the identity, a session, and `continue_with`
holding `set_ory_session_token` plus `show_verification_ui` with the new
verification flow — and, because no mail is delivered, the code itself.

## Recovery and verification

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/recovery?flow=$RECOVERY_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"email": "jonas.pereira@orbit-labs.com"}'

curl -s -X POST "$ORY_KRATOS_API_URL/self-service/recovery?flow=$RECOVERY_FLOW" \
  -H 'Content-Type: application/json' -d '{"code": "770412"}'

curl -s -X POST "$ORY_KRATOS_API_URL/self-service/verification?flow=$VERIFY_FLOW" \
  -H 'Content-Type: application/json' -d '{"code": "482913"}'
```

Seeded codes: recovery `770412` (jonas, unused), recovery `605144` (amelia,
**spent** → `4060006`), verification `482913` (rohit, unused).

Starting recovery for an address Kratos does not know still returns the same
"code sent" flow and still writes a courier message — the `recovery_invalid`
template — so the response cannot be used to discover whether an account exists.

Accepting a recovery code returns `continue_with` holding
`show_settings_ui`, because Kratos forces a password change afterwards.

## Settings

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/settings?flow=$SETTINGS_FLOW" \
  -H 'Content-Type: application/json' -H "X-Session-Token: $JONAS" \
  -d '{"method": "profile",
       "traits": {"email": "jonas.pereira@orbit-labs.io",
                  "name": {"first": "Jonas", "last": "Pereira"},
                  "role": "engineer", "seat_id": "SEAT-207"}}'

curl -s -X POST "$ORY_KRATOS_API_URL/self-service/settings?flow=$SETTINGS_FLOW" \
  -H 'Content-Type: application/json' -H "X-Session-Token: $JONAS" \
  -d '{"method": "password", "password": "NebulaJonas2026"}'
```

A settings flow is bound to its identity: submitting it with someone else's
session is 403 `session_refresh_required`, and with none is 401. Changing the
email marks it unverified and returns a verification flow in `continue_with`;
changing the password revokes every other session.

## Sessions

```bash
curl -s "$ORY_KRATOS_API_URL/sessions/whoami" -H "X-Session-Token: $AMELIA"
curl -s "$ORY_KRATOS_API_URL/sessions" -H "X-Session-Token: $AMELIA"
curl -s -X DELETE "$ORY_KRATOS_API_URL/sessions" -H "X-Session-Token: $AMELIA"
curl -s -X DELETE "$ORY_KRATOS_API_URL/sessions/<id>" -H "X-Session-Token: $AMELIA"
curl -s -X DELETE "$ORY_KRATOS_API_URL/self-service/logout/api" \
  -H 'Content-Type: application/json' \
  -d '{"session_token": "ory_st_priya_1d75a0e934bc"}'
```

`whoami` reports `authenticator_assurance_level` and the ordered
`authentication_methods` that produced it. `DELETE /sessions` revokes every
session *except* the caller's.

## Admin: identities

```bash
curl -s "$ORY_KRATOS_API_URL/admin/identities?page_size=10"
curl -s "$ORY_KRATOS_API_URL/admin/identities?credentials_identifier=helena.park@orbit-labs.com"
curl -s "$ORY_KRATOS_API_URL/admin/identities/9f1c07e3-4b52-4d68-8a13-06e2fa945b7c?include_credential=password,totp,lookup_secret"

curl -s -X POST "$ORY_KRATOS_API_URL/admin/identities" \
  -H 'Content-Type: application/json' \
  -d '{"schema_id": "default",
       "traits": {"email": "ops.bot@orbit-labs.com",
                  "name": {"first": "Ops", "last": "Bot"}, "role": "service"},
       "metadata_admin": {"costCenter": "CC-100"},
       "verifiable_addresses_verified": true,
       "credentials": {"password": {"config": {"password": "NebulaOps2026"}}}}'

curl -s -X PUT "$ORY_KRATOS_API_URL/admin/identities/<id>" \
  -H 'Content-Type: application/json' \
  -d '{"schema_id": "default", "state": "active",
       "traits": {"email": "helena.park@orbit-labs.com",
                  "name": {"first": "Helena", "last": "Park"}, "role": "owner"}}'

curl -s -X DELETE "$ORY_KRATOS_API_URL/admin/identities/<id>"
```

`include_credential` never returns the hash. `metadata_admin` appears only on
admin responses.

### JSON Patch

```bash
curl -s -X PATCH "$ORY_KRATOS_API_URL/admin/identities/<id>" \
  -H 'Content-Type: application/json' \
  -d '[{"op": "replace", "path": "/traits/role", "value": "engineer"},
       {"op": "replace", "path": "/metadata_admin", "value": {"costCenter": "CC-999"}},
       {"op": "replace", "path": "/state", "value": "inactive"}]'
```

Writable paths: `/state`, `/metadata_public`, `/metadata_admin`,
`/traits/email`, `/traits/name/first`, `/traits/name/last`, `/traits/role`,
`/traits/seat_id`, `/traits/company`. Operations: `replace`, `add`, `remove`.
Anything else is 400 with the supported list in `details`. Patching `/state` to
`inactive` revokes the identity's sessions.

## Admin: sessions, credentials, recovery, courier

```bash
curl -s "$ORY_KRATOS_API_URL/admin/identities/<id>/sessions?active=true"
curl -s -X DELETE "$ORY_KRATOS_API_URL/admin/identities/<id>/sessions"
curl -s -X DELETE "$ORY_KRATOS_API_URL/admin/identities/<id>/credentials/totp"

curl -s "$ORY_KRATOS_API_URL/admin/sessions?active=true&page_size=10"
curl -s "$ORY_KRATOS_API_URL/admin/sessions/<id>"
curl -s -X PATCH "$ORY_KRATOS_API_URL/admin/sessions/<id>/extend"
curl -s -X DELETE "$ORY_KRATOS_API_URL/admin/sessions/<id>"

curl -s -X POST "$ORY_KRATOS_API_URL/admin/recovery/code" \
  -H 'Content-Type: application/json' \
  -d '{"identity_id": "<id>", "expires_in_seconds": 900}'
curl -s -X POST "$ORY_KRATOS_API_URL/admin/recovery/link" \
  -H 'Content-Type: application/json' -d '{"identity_id": "<id>"}'

curl -s "$ORY_KRATOS_API_URL/admin/courier/messages?status=sent&page_size=10"
curl -s "$ORY_KRATOS_API_URL/admin/courier/messages/msg-rohit-verify01"
```

Removing the `password` credential through the admin API is refused — Kratos
requires a settings flow. Extending an inactive session is 400. Courier statuses
in the seed: `sent`, `queued`, `abandoned`.

## Errors

### Flow submissions

400 with the flow re-rendered; read the message ids listed at the top of this
guide.

### Everything else

| HTTP | `error.id` | When |
|------|-----------|------|
| 401 | `session_inactive` | missing, revoked or expired session token |
| 403 | `security_csrf_violation` | browser flow submitted without `csrf_token` |
| 403 | `session_refresh_required` | settings flow submitted with another identity's session |
| 404 | `self_service_flow_not_found` | unknown flow, or one of the wrong type |
| 404 | `not_found` | unknown identity, session, schema or courier message |
| 409 | `identity_conflict` | admin create with an existing identifier |
| 410 | `self_service_flow_expired` | the flow's lifetime elapsed |
| 400 | `identity_schema_validation_failed` | admin create/update with traits that fail the schema |
| 400 | `patch_path_invalid` / `patch_op_invalid` | unsupported JSON Patch path or operation |
| 400 | `identity_state_invalid` | a state other than `active` or `inactive` |
| 400 | `credential_type_not_removable` | removing the password credential via the admin API |
