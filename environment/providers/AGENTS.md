# environment — MOCK-API FLEET (backend / database / auth / email / payments)

Self-contained FastAPI mock services (`<name>-api/`) + the shared admin/drift/audit
plane vendored from the upstream fleet. Each runs in its own container; agents reach
them via injected `*_API_URL` env vars.

## PER-API LAYOUT (`<name>-api/`)
```
server.py        # FastAPI app: mirrors a real API subset; installs tracker + admin plane
<name>_data.py   # in-memory data layer (the `_store`); CSV/JSON seed files alongside
service.toml     # [service] name/port/env_var_name/healthcheck_path
Dockerfile  requirements.txt  requirements-locked.txt  *.json
*_postman_collection.json  api_test_results.md  examples.md  openapi.json  README.md
```
`server.py` boilerplate (keep this shape):
```python
import <name>_data
try:
    from tracking_middleware import install_tracker
    from admin_plane import install_admin_plane
except ModuleNotFoundError:           # standalone run: no-op fallbacks
    ...
app = FastAPI(...); install_tracker(app); install_admin_plane(app, store=<name>_data._store)
@app.get("/health") ...
```

## SHARED PLANE (repo-root of environment/)
| File | Role |
|------|------|
| `tracking_middleware.py` | captures all req/resp → `GET /audit/requests`, `/audit/summary` (skips `/audit`,`/admin`) |
| `admin_plane.py` | `/admin/*` out-of-band mutation surface; **off unless `MOCK_ADMIN_ENABLED=1`** + IP allowlist |
| `_mutable_store.py` | mutable store backing drift |
| `test_all_apis.py` | cross-fleet smoke harness; boots each service and fires its Postman collection |
| `smoke_eager_load.py` | import-time loader check for every `<name>_data.py` |
| `skills/` | `<api>-connector/` skill dirs injected into tasks |

## PORT MAP
Ports 8000–8101 are reserved by the upstream fleet and are NOT reused here.
This fleet allocates from 8102 upward, one unique port + `env_var_name` per service,
declared in `service.toml`.

| Range | Group |
|-------|-------|
| 8102–8107 | Backend / BaaS |
| 8108–8112 | Relational databases |
| 8113–8120 | Authentication |
| 8121–8125 | Email |
| 8126–8128 | Payments |

| Port | Service | Env var |
|------|---------|---------|
| 8102 | supabase-api | `SUPABASE_API_URL` |
| 8103 | pocketbase-api | `POCKETBASE_API_URL` |
| 8104 | appwrite-api | `APPWRITE_API_URL` |
| 8105 | directus-api | `DIRECTUS_API_URL` |
| 8106 | nhost-api | `NHOST_API_URL` |
| 8107 | postgres-backend-api | `POSTGRES_BACKEND_API_URL` |
| 8108 | sqlite-api | `SQLITE_API_URL` |
| 8109 | postgresql-api | `POSTGRESQL_API_URL` |
| 8110 | mysql-api | `MYSQL_API_URL` |
| 8111 | mariadb-api | `MARIADB_API_URL` |
| 8112 | cockroachdb-api | `COCKROACHDB_API_URL` |
| 8113 | supabase-auth-api | `SUPABASE_AUTH_API_URL` |
| 8114 | pocketbase-auth-api | `POCKETBASE_AUTH_API_URL` |
| 8115 | supertokens-api | `SUPERTOKENS_API_URL` |
| 8116 | logto-api | `LOGTO_API_URL` |
| 8117 | keycloak-api | `KEYCLOAK_API_URL` |
| 8118 | zitadel-api | `ZITADEL_API_URL` |
| 8119 | ory-kratos-api | `ORY_KRATOS_API_URL` |
| 8120 | dex-api | `DEX_API_URL` |
| 8121 | mailhog-api | `MAILHOG_API_URL` |
| 8122 | mailpit-api | `MAILPIT_API_URL` |
| 8123 | inbucket-api | `INBUCKET_API_URL` |
| 8124 | smtp4dev-api | `SMTP4DEV_API_URL` |
| 8125 | mailcatcher-api | `MAILCATCHER_API_URL` |
| 8126 | inhouse-payments-api | `INHOUSE_PAYMENTS_API_URL` |
| 8127 | lago-api | `LAGO_API_URL` |
| 8128 | killbill-api | `KILLBILL_API_URL` |

## CONVENTIONS
- Data lives in `<name>_data.py` module-global `_store`; servers are thin route wrappers.
- Seed files are flat rows with string cells (CSV-compatible) so a bind-mounted `.csv`
  overlay can shadow the baked `.json` without a callsite change. Lists use `;`.
- Coercion happens once, in `_coerce_*`, using the `strict_*` / `opt_*` helpers from
  `_mutable_store`; route handlers never re-parse seed values.
- The relational-database services (8108-8112) run **real SQL** via `sql_engine.py`,
  which materializes the store into an in-memory SQLite database per request and syncs
  writes back. The store stays canonical, so drift keeps working; each service maps the
  engine's neutral error kinds onto its own dialect's codes.
- Every service ends `<name>_data.py` with `_store.eager_load()` so a bad seed fails at
  import time, before the container reports healthy.
- Error convention: data functions return `{"error": "...", "code": "..."}`; the server
  maps `code` onto the HTTP status. Never raise out of a data function.
- Drift = admin plane mutates `_store` mid-run so responses diverge from persona MEMORY.md;
  drift events are hidden from the agent's `/audit` view by design.
- Seed data shares one universe with the upstream fleet: Orbit Labs, staffed by
  Amelia Ortega, Jonas Pereira, Helena Park, Rohit Bansal and Noor Aziz, with the
  auth-api / billing-api / web-app / infra / docs projects. "Now" is late May 2026.

## ANTI-PATTERNS
- Don't enable `/admin/*` in normal runs — default-absent keeps behavior byte-identical to
  plain mocks; only DriftDirector (host) flips `MOCK_ADMIN_ENABLED=1`.
- Don't let `/admin/*` or `/audit/*` show up in agent-visible audit logs (skip-lists already set).
- Don't make a mock reject a request purely because a token is unfamiliar — the fleet
  contract is that any token is accepted. Services with an auth layer map tokens onto
  *roles* instead, so behavior stays observable without becoming unreachable.

## IMAGE BUILD
- All per-API Dockerfiles are `python:3.12-slim` SHA-pinned, use hash-verified
  `pip install --require-hashes -r requirements-locked.txt`, run as non-root `app` user.
- **Build context is this directory, not the service directory** — the image needs the
  shared plane next to the service code:
  ```
  docker build -f <name>-api/Dockerfile -t mocks-<name>-api:v1 .
  docker compose up -d <name>-api
  ```
  Upstream builds one umbrella image over `environment/*`; here each service is its own
  image so it can run independently, which is why the Dockerfile copies
  `_mutable_store.py admin_plane.py tracking_middleware.py` explicitly before the
  service directory. Everything else about the Dockerfile is unchanged.

## DOCKERFILE PINNING POLICY
- Each `<name>-api/requirements-locked.txt` is hash-pinned. NEVER regenerate without re-running
  `pip-compile --generate-hashes` and committing both `.in` and `.txt` together.

## VERIFICATION GATE
Every change must pass both:
```
python smoke_eager_load.py                  # every data module imports
python test_all_apis.py --only <name>-api   # 0 FAIL; 4xx WARNs only on error-path requests
```
