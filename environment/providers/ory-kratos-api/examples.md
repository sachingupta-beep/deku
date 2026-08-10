# Ory Kratos Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$ORY_KRATOS_API_URL`; responses are verbatim (long node lists
elided with `…`). Examples assume:

```bash
export AMELIA='ory_st_amelia_4c19f7e0b83d'      # aal2
export JONAS='ory_st_jonas_91e5c7d40a26'
export LOGIN_FLOW='f1a0c7e2-5b93-4d68-8017-2e6f931c5d47'
export REG_FLOW='b41d7e02-96c8-4f35-a80b-2e6f931c5d47'
export RECOVERY_FLOW='9e05a73f-1c48-4b26-a09d-58f2c6e34b17'
```

## Creating a flow

There is no login endpoint. You ask for a flow, and get back a form to render.

```bash
curl -s "$ORY_KRATOS_API_URL/self-service/login/api"
```
```json
{
  "id": "b55cc8ca-cdc0-4e6c-b333-890f621ceeea",
  "type": "api",
  "expires_at": "2026-08-06T07:11:25.459Z",
  "issued_at": "2026-08-06T06:11:25.459Z",
  "request_url": "https://kratos.orbit-labs.com/self-service/login/api",
  "ui": {
    "action": "https://kratos.orbit-labs.com/self-service/login?flow=b55cc8ca-…",
    "method": "POST",
    "nodes": [
      {"type": "input", "group": "password",
       "attributes": {"name": "identifier", "type": "text", "value": "",
                      "required": true, "disabled": false,
                      "node_type": "input"},
       "messages": [],
       "meta": {"label": {"id": 1070000, "text": "E-Mail", "type": "info",
                          "context": {}}}},
      {"type": "input", "group": "password",
       "attributes": {"name": "password", "type": "password", "required": true,
                      "…": "…"},
       "messages": [], "meta": {"label": {"text": "Password", "…": "…"}}},
      {"type": "input", "group": "password",
       "attributes": {"name": "method", "type": "submit", "value": "password"},
       "…": "…"},
      {"type": "input", "group": "oidc",
       "attributes": {"name": "provider", "type": "submit", "value": "github"},
       "…": "…"}
    ],
    "messages": []
  },
  "state": "choose_method"
}
```

A **browser** flow is the same except it carries a hidden `csrf_token` node; an
API flow never does.

## A failed submission re-renders the flow

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$LOGIN_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"method": "password", "password": "x"}'
```
```
HTTP 400
```
```json
{
  "id": "f1a0c7e2-5b93-4d68-8017-2e6f931c5d47",
  "type": "api",
  "ui": {
    "action": "https://kratos.orbit-labs.com/self-service/login?flow=f1a0c7e2-…",
    "method": "POST",
    "nodes": [
      {"type": "input", "group": "password",
       "attributes": {"name": "identifier", "type": "text", "required": true},
       "messages": [{"id": 4000001,
                     "text": "Property identifier is missing.",
                     "type": "error", "context": {}}],
       "meta": {"label": {"text": "E-Mail", "…": "…"}}},
      {"type": "input", "attributes": {"name": "password"}, "messages": [],
       "…": "…"}
    ],
    "messages": []
  },
  "state": "choose_method"
}
```

The message is on the node it belongs to. Invalid credentials go to
`ui.messages` instead, because they belong to no single field:

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$LOGIN_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"method": "password", "identifier": "jonas.pereira@orbit-labs.com",
       "password": "nope"}'
```
```json
{"id": "f1a0c7e2-…", "ui": {"nodes": ["…"],
  "messages": [{"id": 4000006,
    "text": "The provided credentials are invalid, check for spelling mistakes in your password or username, email address, or phone number.",
    "type": "error", "context": {}}]}, "state": "choose_method"}
```

An unknown identifier and an identity with no password credential (helena, who
only has OIDC) produce the *same* message.

## A successful login

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$LOGIN_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"method": "password", "identifier": "jonas.pereira@orbit-labs.com",
       "password": "OrbitJonas2026!"}'
```
```json
{
  "session_token": "ory_st_1696759e6bd1afc14bcde2f1",
  "session": {
    "id": "d04c35f1-8d24-40d4-bd1d-45654a0a5e7e",
    "active": true,
    "expires_at": "2026-09-05T06:11:40.839Z",
    "authenticated_at": "2026-08-06T06:11:40.839Z",
    "authenticator_assurance_level": "aal1",
    "authentication_methods": [
      {"method": "password", "completed_at": "2026-08-06T06:11:40.838Z",
       "aal": "aal1"}
    ],
    "identity": {
      "id": "5e93b1a7-2c48-4d06-b7f5-91e0c34d6a28",
      "schema_id": "default",
      "state": "active",
      "traits": {"email": "jonas.pereira@orbit-labs.com",
                 "name": {"first": "Jonas", "last": "Pereira"},
                 "role": "engineer", "seat_id": "SEAT-207"},
      "verifiable_addresses": [{"value": "jonas.pereira@orbit-labs.com",
                                "verified": true, "via": "email",
                                "status": "completed", "…": "…"}],
      "recovery_addresses": [{"value": "jonas.pereira@orbit-labs.com",
                              "via": "email", "…": "…"}],
      "…": "…"
    }
  },
  "continue_with": [
    {"action": "set_ory_session_token",
     "ory_session_token": "ory_st_1696759e6bd1afc14bcde2f1"}
  ]
}
```

Logging in as an identity that has TOTP returns an **aal1** session plus a
`redirect_browser_to` pointing at a fresh aal2 flow — the step-up is a second
flow, not a second field.

## Browser flows need the anti-CSRF token

```bash
curl -s -X POST \
  "$ORY_KRATOS_API_URL/self-service/login?flow=d80c5f13-27ba-4e69-91d4-6a03e7b28c50" \
  -H 'Content-Type: application/json' \
  -d '{"method": "password", "identifier": "jonas.pereira@orbit-labs.com",
       "password": "OrbitJonas2026!"}'
```
```json
{"error": {"id": "security_csrf_violation", "code": 403, "status": "Forbidden",
  "reason": "The request was rejected to protect you from Cross-Site-Request-Forgery (CSRF) which could cause account takeover, leaking personal information, and other serious security issues.",
  "message": "…"}}
```

Adding `"csrf_token": "csrf-a71e0c93d45b8f26"` makes the identical request
succeed.

## Flow lifecycle

An expired flow is `410 Gone`, not 404 — the distinction matters, because the
client should start a new flow rather than treat the id as bogus:

```bash
curl -s "$ORY_KRATOS_API_URL/self-service/login/flows?id=f6b23c91-08de-4a75-b3c0-97e15d24a608"
```
```json
{"error": {"id": "self_service_flow_expired", "code": 410, "status": "Gone",
  "reason": "The self-service flow expired 0.00 minutes ago, initialize a new one.",
  "details": {"redirect_to": "https://kratos.orbit-labs.com/self-service/login/browser",
              "expired_at": "2026-05-26T09:00:00Z"}}}
```

## Trait validation against the identity schema

The `default` schema requires `name.first` and `name.last`, constrains `role` to
an enum and `seat_id` to a pattern, and forbids extra properties.

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/registration?flow=$REG_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"traits": {"email": "wizard@orbit-labs.com",
                  "name": {"first": "Iris", "last": "Tanaka"},
                  "role": "wizard"},
       "password": "StellarIris2026"}'
```
```json
{"id": "b41d7e02-…", "ui": {"nodes": [
  {"attributes": {"name": "traits.role"},
   "messages": [{"id": 4000038,
     "text": "value must be one of owner, engineer, support, service",
     "type": "error",
     "context": {"expected": ["owner", "engineer", "support", "service"]}}],
   "…": "…"}, "…"]}, "state": "choose_method"}
```

The **same payload** against the `partner` schema fails differently — that
schema wants `company` and does not allow `name`:

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/registration?flow=$REG_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"schema_id": "partner",
       "traits": {"email": "iris.tanaka@orbit-labs.com",
                  "name": {"first": "Iris", "last": "Tanaka"}},
       "password": "StellarIris2026"}'
```

`traits.company` gets `4000001` (required) and `traits.name` gets `4000040`
(not allowed by the schema).

## `continue_with` says what happens next

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/registration?flow=$REG_FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"traits": {"email": "iris.tanaka@orbit-labs.com",
                  "name": {"first": "Iris", "last": "Tanaka"},
                  "role": "support", "seat_id": "SEAT-410"},
       "password": "StellarIris2026"}'
```
```json
{
  "identity": {"id": "…", "traits": {"…": "…"}, "…": "…"},
  "session_token": "ory_st_769896241165a13b16cb459d",
  "session": {"…": "…"},
  "continue_with": [
    {"action": "set_ory_session_token",
     "ory_session_token": "ory_st_769896241165a13b16cb459d"},
    {"action": "show_verification_ui",
     "flow": {"id": "c98c1796-b604-4cf5-9476-02232fae5aee",
              "verifiable_address": "iris.tanaka@orbit-labs.com",
              "url": "https://kratos.orbit-labs.com/self-service/verification?flow=c98c1796-…"}}
  ],
  "verification_code": "836854",
  "note": "the verification code is returned because no mail is actually delivered by the mock"
}
```

Completing a recovery hands back a **settings** flow, because Kratos forces a
password change afterwards:

```bash
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/recovery?flow=$RECOVERY_FLOW" \
  -H 'Content-Type: application/json' -d '{"code": "770412"}'
```
```json
{"session_token": "ory_st_973e141f895a5e83c4c04da1",
 "session": {"…": "…"},
 "continue_with": [
   {"action": "set_ory_session_token",
    "ory_session_token": "ory_st_973e141f895a5e83c4c04da1"},
   {"action": "show_settings_ui",
    "flow": {"id": "f80413e1-9462-40ac-a81b-b96e8474c30b",
             "url": "https://kratos.orbit-labs.com/self-service/settings?flow=f80413e1-…"}}]}
```

## Sessions

```bash
curl -s "$ORY_KRATOS_API_URL/sessions/whoami" -H "X-Session-Token: $AMELIA"
```
```json
{"id": "0a4f1c7e-8b25-4d93-a610-5f2c9e08b374", "active": true,
 "authenticator_assurance_level": "aal2",
 "authentication_methods": [
   {"method": "password", "completed_at": "2026-05-26T08:12:02Z", "aal": "aal1"},
   {"method": "totp", "completed_at": "2026-05-26T08:12:20Z", "aal": "aal2"}],
 "identity": {"traits": {"email": "amelia.ortega@orbit-labs.com", "…": "…"},
              "…": "…"},
 "devices": [{"id": "dev-0a4f1c7e", "ip_address": "203.0.113.41",
              "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
              "location": "San Francisco, US"}]}
```

## Admin: JSON Patch on an identity

```bash
curl -s -X PATCH \
  "$ORY_KRATOS_API_URL/admin/identities/c72f4d80-6e19-4b35-a204-8f7b0e15c9d6" \
  -H 'Content-Type: application/json' \
  -d '[{"op": "replace", "path": "/traits/role", "value": "owner"},
       {"op": "replace", "path": "/metadata_admin",
        "value": {"costCenter": "CC-999"}}]'
```
```json
{"state": "active",
 "traits": {"email": "helena.park@orbit-labs.com",
            "name": {"first": "Helena", "last": "Park"},
            "role": "owner", "seat_id": "SEAT-251"},
 "metadata_admin": {"costCenter": "CC-999"},
 "…": "…"}
```

An unsupported path is rejected with the list of writable ones rather than
silently ignored:

```json
{"error": {"id": "patch_path_invalid", "code": 400, "status": "Bad Request",
  "reason": "The JSON Patch path '/id' cannot be modified.",
  "details": {"supported_paths": ["/metadata_admin", "/metadata_public",
                                  "/state", "/traits/company", "/traits/email",
                                  "/traits/name/first", "/traits/name/last",
                                  "/traits/role", "/traits/seat_id"]}}}
```

## The courier log

Nothing is actually delivered, so the mock records what would have been:

```bash
curl -s "$ORY_KRATOS_API_URL/admin/courier/messages?page_size=2"
```
```json
[{"id": "msg-9e622dd105d9", "status": "queued", "type": "email",
  "recipient": "iris.tanaka@orbit-labs.com",
  "subject": "Please verify your email address",
  "templateType": "verification_code_valid",
  "body": "Hi, please verify your account by entering the following code: 836854",
  "sendCount": 0, "createdAt": "2026-08-06T06:12:00.281Z"},
 {"id": "msg-rohit-verify01", "status": "sent", "…": "…"}]
```

The seed also contains a `recovery_invalid` message — the one Kratos sends to an
address it does not recognise, so a recovery attempt cannot be used to discover
whether an account exists.
