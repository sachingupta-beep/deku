# ory-kratos-api

Mock of Ory Kratos.

Run it as its own container (build context is the environment root):
```
docker compose up -d ory-kratos-api
curl http://localhost:8119/health
curl http://localhost:8119/self-service/login/api
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir ory-kratos-api --port 8119
```

**There is no login endpoint.** Kratos has *self-service flows*, and they are
first-class resources:

```
GET  /self-service/login/api          -> a flow object carrying a renderable `ui`
POST /self-service/login?flow=<id>    -> submit against that flow
```

The `ui` is a form description — `action`, `method`, and `nodes` each with their
own attributes and messages. A failed submission is **not** an error body: it is
400 with the whole flow re-rendered and messages attached to the offending
nodes, because that is what a client draws. The numbered ids carry the meaning:

| id | meaning |
|----|---------|
| 4000001 | property is required |
| 4000002 | value too short |
| 4000003 | invalid format |
| 4000006 | invalid credentials |
| 4000007 | identifier already exists |
| 4000032 | password too short |
| 4000038 | value not in the enum |
| 4000040 | trait not allowed by the schema |
| 4060006 | code invalid or already used |

Two more Kratos-specific pieces are modelled rather than flattened:

- **Traits are validated against the identity's JSON Schema.** Two schemas are
  seeded with different required fields, so the same registration payload
  succeeds against `default` and fails against `partner`, with each failure
  attached to the node for the offending trait.
- **`continue_with`** tells the client what to do next. A successful
  registration returns both `set_ory_session_token` and `show_verification_ui`;
  a completed recovery returns `show_settings_ui`, because Kratos forces a
  password change afterwards.

Kratos serves its admin API on a second port; the mock serves both on one and
keeps the `/admin` prefix so the boundary stays visible. `PATCH
/admin/identities/{id}` takes JSON Patch (RFC 6902).

Seeded flows and tokens, so a request can quote one literally:

| Flow | Kind |
|------|------|
| `f1a0c7e2-5b93-4d68-8017-2e6f931c5d47` | login, api |
| `d80c5f13-27ba-4e69-91d4-6a03e7b28c50` | login, browser (csrf `csrf-a71e0c93d45b8f26`) |
| `2a97e0b8-4d16-43cf-8572-b1e0c9d64f35` | login, aal2 step-up for amelia |
| `f6b23c91-08de-4a75-b3c0-97e15d24a608` | login, **expired** → 410 |
| `b41d7e02-96c8-4f35-a80b-2e6f931c5d47` | registration |
| `9e05a73f-1c48-4b26-a09d-58f2c6e34b17` | recovery |
| `7c4e1b8a-0d33-4f95-b201-8e6a3c17d940` | verification, for rohit |
| `1d9f4a02-7b36-4c81-a5e0-92f7c103b846` | settings, for jonas |

| Session token | Identity |
|---------------|----------|
| `ory_st_amelia_4c19f7e0b83d` | amelia, **aal2** |
| `ory_st_jonas_91e5c7d40a26` | jonas |
| `ory_st_helena_d502a8f371c6` | helena, authenticated by oidc |
| `ory_st_priya_1d75a0e934bc` | priya |
| `ory_st_amelia_revoked_3a6d80e5` | **revoked** |

Passwords are verified for real — `sha256(salt + password)`; Kratos uses
Argon2id, and the credential config says so.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`ory_kratos_api_postman_collection.json` for the runnable collection.
