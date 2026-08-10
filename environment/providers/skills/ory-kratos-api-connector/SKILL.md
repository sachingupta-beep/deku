---
name: ory-kratos-api-connector
description: >
  Ory Kratos API (Mock) mock HTTP API. Base URL is provided via the
  `ORY_KRATOS_API_URL` environment variable. 39 endpoint(s) across GET, POST, PUT, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Ory Kratos API (Mock)

Mock of Ory Kratos. **All requests go to the base URL in
`$ORY_KRATOS_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `ORY_KRATOS_API_URL` | Base URL for all requests (e.g. `http://ory-kratos-api:8119`) |

## Read this before using it

**There is no login endpoint.** Authentication happens through *self-service
flows*, which are resources in their own right:

```
GET  /self-service/login/api          -> a flow object carrying a renderable `ui`
POST /self-service/login?flow=<id>    -> submit against that flow
```

A failed submission is **not** an error body. It is **400 with the whole flow
re-rendered**, and the message sits on the `ui.nodes` entry it belongs to.
Switch on the numbered id, not the text:

| id | meaning |
|----|---------|
| 4000001 | property required |
| 4000002 | too short |
| 4000003 | invalid format |
| 4000006 | invalid credentials |
| 4000007 | identifier exists |
| 4000032 | password too short |
| 4000038 | not in the enum |
| 4000040 | trait not allowed by the schema |
| 4060006 | code invalid or used |

Non-flow errors use the usual envelope:
`{"error": {"id": "...", "code": 404, "status": "Not Found", "reason": "..."}}`.
Notable ids: `self_service_flow_expired` (**410**),
`self_service_flow_not_found` (404), `security_csrf_violation` (403),
`session_inactive` (401), `session_refresh_required` (403).

## Seeded flows

| Flow id | Kind |
|---------|------|
| `f1a0c7e2-5b93-4d68-8017-2e6f931c5d47` | login, api |
| `d80c5f13-27ba-4e69-91d4-6a03e7b28c50` | login, browser — csrf `csrf-a71e0c93d45b8f26` |
| `2a97e0b8-4d16-43cf-8572-b1e0c9d64f35` | login, **aal2 step-up** for amelia |
| `f6b23c91-08de-4a75-b3c0-97e15d24a608` | login, **expired** → 410 |
| `b41d7e02-96c8-4f35-a80b-2e6f931c5d47` | registration |
| `9e05a73f-1c48-4b26-a09d-58f2c6e34b17` | recovery |
| `7c4e1b8a-0d33-4f95-b201-8e6a3c17d940` | verification, for rohit |
| `1d9f4a02-7b36-4c81-a5e0-92f7c103b846` | settings, for jonas |
| `5c07e83b-1f42-4d69-b3a8-07e5d91c264f` | settings, for amelia |

## Identities and session tokens

| Identity | Password | Note |
|----------|----------|------|
| `amelia.ortega@orbit-labs.com` | `OrbitKratos2026!` | totp `482913`, lookup secrets `91cd2f7a`, `4b60e18d`, `7fa3c052` |
| `jonas.pereira@orbit-labs.com` | `OrbitJonas2026!` | |
| `helena.park@orbit-labs.com` | — | **oidc only**, `github:2210448` |
| `rohit.bansal@orbit-labs.com` | `OrbitRohit2026!` | **email unverified**, code `482913` |
| `noor.aziz@orbit-labs.com` | `OrbitNoor2026!` | **state `inactive`** |
| `priya.raman@acme-partner.com` | `OrbitPriya2026!` | on the `partner` schema |

| Session token | Identity |
|---------------|----------|
| `ory_st_amelia_4c19f7e0b83d` | amelia, **aal2** |
| `ory_st_jonas_91e5c7d40a26` | jonas |
| `ory_st_helena_d502a8f371c6` | helena |
| `ory_st_priya_1d75a0e934bc` | priya |
| `ory_st_amelia_revoked_3a6d80e5` | **revoked** |

Send it as `X-Session-Token`.

## Identity schemas

| Schema | Required | Constraints |
|--------|----------|-------------|
| `default` | `email`, `name.first`, `name.last` | `role` enum (`owner`, `engineer`, `support`, `service`), `seat_id` pattern `^SEAT-[0-9]{3}$` |
| `partner` | `email`, `company` | |

Both forbid extra properties.

## Endpoints

| Method | Path |
|--------|------|
| GET | `/health/alive` · `/health/ready` · `/version` |
| GET | `/schemas` · `/schemas/{id}` |
| GET | `/self-service/{login\|registration\|recovery\|verification\|settings}/{api\|browser}` |
| GET | `/self-service/{type}/flows?id=` |
| POST | `/self-service/login` · `/registration` · `/recovery` · `/verification` · `/settings` (all `?flow=`) |
| DELETE | `/self-service/logout/api` |
| GET | `/sessions/whoami` · `/sessions` |
| DELETE | `/sessions` · `/sessions/{id}` |
| GET/POST | `/admin/identities` |
| GET/PUT/PATCH/DELETE | `/admin/identities/{id}` |
| GET/DELETE | `/admin/identities/{id}/sessions` |
| DELETE | `/admin/identities/{id}/credentials/{type}` |
| POST | `/admin/recovery/code` · `/admin/recovery/link` |
| GET | `/admin/sessions` · `/admin/sessions/{id}` |
| PATCH | `/admin/sessions/{id}/extend` |
| DELETE | `/admin/sessions/{id}` |
| GET | `/admin/courier/messages` · `/admin/courier/messages/{id}` |

## Usage

```bash
# 1. create a flow, 2. submit against it
FLOW=$(curl -s "$ORY_KRATOS_API_URL/self-service/login/api" | jq -r .id)
curl -s -X POST "$ORY_KRATOS_API_URL/self-service/login?flow=$FLOW" \
  -H 'Content-Type: application/json' \
  -d '{"method": "password", "identifier": "jonas.pereira@orbit-labs.com",
       "password": "OrbitJonas2026!"}'

# who am I
curl -s "$ORY_KRATOS_API_URL/sessions/whoami" \
  -H 'X-Session-Token: ory_st_amelia_4c19f7e0b83d'

# admin: JSON Patch an identity
curl -s -X PATCH \
  "$ORY_KRATOS_API_URL/admin/identities/c72f4d80-6e19-4b35-a204-8f7b0e15c9d6" \
  -H 'Content-Type: application/json' \
  -d '[{"op": "replace", "path": "/traits/role", "value": "owner"}]'
```

Successful flows return `continue_with`, telling the client what to do next —
`set_ory_session_token`, `show_verification_ui`, `show_settings_ui`,
`redirect_browser_to`.

The audit log of every call the agent makes is available at
`$ORY_KRATOS_API_URL/audit/requests` (used for grading).
