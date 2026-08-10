# Implementing a service

How to turn a `declared` catalog entry into a working simulator. Written against the 26
services still to build; [`services/supabase/`](../services/supabase/) is the worked example
to copy from.

---

## The 15-minute version

```bash
python tools/new_service.py keycloak     # scaffold from the existing manifest
python -m pytest services/keycloak       # 9 green tests, generic /records CRUD
uvicorn main:app --port 8080
curl localhost:8080/keycloak/health
```

You now have a loading, healthy, tested service with placeholder endpoints. Replace them one
at a time, keeping the suite green. Starting from something that works beats starting from
an empty file that fails for six unrelated reasons at once.

---

## What a complete service ships

The 14 required artefacts, where each lives, and what "done" means.

| # | Artefact | Location | Done when |
|---|----------|----------|-----------|
| 1 | Module structure | `services/<pkg>/` | `service.py`, `routes.py`, `data.py`, `models.py` |
| 2 | API endpoints | `routes.py` | the manifest's `route_prefixes` are all reachable |
| 3 | Data model | `data.py` | tables registered with primary keys; coercion in one place |
| 4 | Mock datasets | `data/<slug>/*.json` | flat rows, string cells, one shared persona universe |
| 5 | Authentication | `data.py` → `resolve_*` | credential maps to a **role**; unknown tokens are not rejected |
| 6 | CRUD | `routes.py` + `data.py` | list, get, create, update, delete — with the upstream's error codes |
| 7 | Health endpoint | *(automatic)* | `health()` returns cheap counts; the base class serves the route |
| 8 | Startup hook | `service.py` | `on_startup` builds the data layer and calls `ctx.eager_load()` |
| 9 | Shutdown hook | `service.py` | `on_shutdown` releases what startup built |
| 10 | OpenAPI schema | `services/<pkg>/openapi.json` | `python tools/export_openapi.py` |
| 11 | Test suite | `services/<pkg>/tests/` | happy path *and* every error path, via the hub |
| 12 | Example requests | `examples.md` | captured from a running container, not written by hand |
| 13 | Example responses | `examples.md` | ditto — real bytes, including the error bodies |
| 14 | Service metadata | `services/<pkg>/service.toml` | `status = "implemented"` |

Plus a `README.md`: endpoint table, auth model, seeded data, and any deviation from upstream.

---

## The five rules

Everything else is detail; these are the ones that break things if ignored.

### 1. All state on the instance, never at module scope

```python
class KeycloakService(ServiceModule):
    async def on_startup(self):
        self.data = KeycloakData(self.ctx)      # correct

_DATA = KeycloakData(...)                       # wrong — survives unload
_CACHE = {}                                     # wrong — shared between hub instances
```

Module globals cannot be reclaimed on unload, cannot be rewound between benchmark tasks, and
leak across the two hub instances the test suite builds in one process. Module-level
*constants* are fine (`ERROR_CODES`, regexes, pure functions); anything that changes is not.

### 2. Data functions return errors, routes map them

```python
# data.py — never raises
def get_realm(self, name):
    realm = self.store.table("realms").get(name)
    return realm or _error(f"Realm not found: {name}", "404")

# routes.py — one table, so a code cannot mean 404 here and 401 there
STATUS_BY_CODE = {"404": 404, "401": 401, "409": 409}
```

Keeping status mapping in one dict per service is what stops the same upstream error code
being a 404 on one endpoint and a 400 on the next — a class of inconsistency that is
invisible in review and maddening in a benchmark.

### 3. Never reject a request purely because a token is unfamiliar

Map credentials onto **roles**:

```python
def resolve_role(self, token):
    if token == self.settings()["service_role_key"]: return "service_role"
    if not token:                                    return "anon"
    return "authenticated"        # any other token — observable, still reachable
```

A simulator that 401s an unrecognised credential turns every task into a credential hunt
instead of the task it was meant to be. The auth layer stays observable — roles produce
visibly different responses — without becoming a wall.

### 4. Call `ctx.eager_load()` in `on_startup`

Without it the first seed read happens inside whatever request touches that table first, so a
malformed `users.json` surfaces as a confusing 500 halfway through a task. With it, the
**load** fails, the hub reports the service `failed`, and the error names the file, row and
column. Two-second fix instead of a debugging session.

### 5. Never write the slug into a path

```python
@router.get("/admin/realms")             # correct — served at /keycloak/admin/realms
@router.get("/keycloak/admin/realms")    # wrong — becomes /keycloak/keycloak/...
```

The mount adds the prefix. Hardcoding it also breaks the moment the slug changes in the
manifest.

---

## Anatomy of a service

### `service.py` — the seam

```python
class KeycloakService(ServiceModule):
    data: KeycloakData

    async def on_startup(self) -> None:
        self.data = KeycloakData(self.ctx)
        self.ctx.eager_load()

    def build_router(self) -> APIRouter:
        return build_router(self.data)

    def health(self) -> HealthReport:
        # Cheap: len() on the store. /hub/health calls this per loaded service.
        return HealthReport(checks={"realms": len(self.ctx.table("realms"))})

    async def on_shutdown(self) -> None:
        self.data = None
```

Twenty lines. If yours is longer, logic has leaked out of `data.py`.

### `data.py` — everything interesting

Register tables in `__init__`; the loaders run at `eager_load`, not at registration:

```python
def _register_tables(self):
    seed = self.ctx.seed
    self.ctx.register_table("realms", "id", lambda: _coerce_realms(seed("realms.json", "realms")))
    self.ctx.register_table("users",  "id", lambda: _coerce_users(seed("users.json", "users")))
    self.ctx.register_table("sessions", "id", list)      # born empty: runtime rows only
```

Coerce once, in `_coerce_*`, using `strict_*` / `opt_*` from `hub.store`. Route handlers must
never re-parse a seed value. `strict_*` raises on a missing or unparseable cell (required
fields); `opt_*` falls back to a default (optional ones). That distinction is how the seed
encodes its own schema.

### `routes.py` — thin

Read headers, call one data method, map the code. No business logic. The payoff is that
everything a task can assert on is testable without an HTTP client.

### `models.py` — request bodies only

Model bodies for validation and a useful OpenAPI. Do **not** model responses: the point of a
simulator is to return the upstream's shapes byte-for-byte — bare arrays, `signedURL`
casing, `Content-Range` headers — and a response model quietly normalises exactly the details
an agent is meant to encounter.

---

## Seed data

Flat JSON arrays of row objects, all cells strings:

```json
[{"id": "u_amelia", "username": "amelia", "enabled": "true", "roles": "admin;developer"}]
```

- **All-string cells** keep a bind-mounted `.csv` overlay compatible with the baked `.json`,
  which is how a task ships its own fixtures. `hub.store.read_seed_with_ctx` prefers a
  sibling `.csv` when one exists.
- **`;`-separated** lists, `""` for empty.
- **One persona universe.** Orbit Labs: Amelia Ortega, Jonas Pereira, Helena Park, Rohit
  Bansal, Noor Aziz, Dmitri Volkov, Priya Raman, plus a `sync-bot`. Projects: auth-service,
  billing, web-app, infra, docs. "Now" is late May 2026. Cross-service tasks only work if
  Keycloak's users are Supabase's authors are Lago's customers.
- **Reachable error paths.** If the service can return 409, seed the row that causes it. An
  error path with no data behind it is untestable and, in practice, wrong.
- **Deterministic identifiers.** `sha256` digest slices, never `hash()` — it is salted per
  process, so a "stable" id built on it changes between runs.

---

## Fidelity

Simulate the product's *semantics*, not a generic CRUD API wearing its name. The
distinctions between same-category services are the whole point — a task that can be solved
by pattern-matching against any REST API is not testing anything.

Worth stealing from the reference fleet, service by service:

| Service | The thing that makes it itself |
|---------|--------------------------------|
| PocketBase | per-collection API rules; `Authorization: <token>` with no `Bearer` |
| Appwrite | `X-Appwrite-Project` scoping; `Query()` filter syntax; its own error codes |
| Directus | permissions-driven field visibility; deep `filter[_and][...]` |
| Nhost | GraphQL with Hasura role claims; `x-hasura-admin-secret` bypass |
| PostgreSQL / MySQL / MariaDB | same SQL, *different error codes* — SQLSTATE vs numeric |
| CockroachDB | PostgreSQL-compatible plus retryable `40001` |
| SQLite | type affinity, `PRAGMA`, no auth at all |
| Keycloak | realm-scoped admin: a token for realm A cannot touch realm B |
| Zitadel | org context via `x-zitadel-orgid`; v2 sessions |
| Ory Kratos | flow-based: create a flow, then submit it — not a plain login POST |
| Dex | pure federation; authorization-code and device flows; JWKS |
| SuperTokens | session handles with rotating refresh tokens |
| MailHog | structured envelope `Path` objects; v1 bare array vs v2 envelope; Jim chaos |
| Mailpit | a real query language (`from:`, `is:unread`, `has:attachment`); HTML/spam checks |
| Inbucket | **no global inbox** — the mailbox is derived from the address |
| smtp4dev | .NET paged envelopes; MIME parts as a tree; sessions stored separately |
| MailCatcher | format-as-file-extension: `.json` / `.html` / `.plain` / `.source` |
| In-house payments | double-entry ledger; mandatory `Idempotency-Key` |
| Lago | metered events through five disagreeing charge models |
| Kill Bill | multi-tenant; cross-tenant reads are **404, not 403**; entitlement ≠ billing clock |

**Where you must deviate, mark it.** If an endpoint has no upstream equivalent, say so in the
response body itself and in the README. A silent invention is a trap: a task built on it will
pass against the simulator and fail against the real product.

---

## Porting from the per-container fleet

If a service already exists as `<name>-api/` in the fleet, the conversion is mechanical:

| Fleet | Hub |
|-------|-----|
| `<name>-api/server.py` — module-level `app` | `routes.py` — `build_router(data)` returning an `APIRouter` |
| `<name>_data.py` — module-level `_store`, module functions | `data.py` — a class; `self.store`; methods |
| `_store = get_store("<name>-api")` | `self.store = ctx.store` (fresh per load) |
| `read_seed_with_ctx(DATA_DIR / f, api, table)` | `ctx.seed(f, table)` |
| `_store.eager_load()` at import | `ctx.eager_load()` in `on_startup` |
| `@app.get("/health")` | delete it — the base class installs it |
| `install_tracker(app)` | delete it — the hub audits centrally |
| `<name>-api/*.json` seeds | `data/<slug>/*.json` |
| `service.toml` `[service] port/env_var_name` | `service.toml` `[service] slug/module/category` |

The real work is step two: turning module-level functions into methods on a class. Everything
else is moving files. The Supabase service in this repo was ported exactly this way, and its
behaviour is unchanged from the fleet's — same PostgREST grammar, same SQLSTATEs, same RLS.

---

## Testing

Test **through the hub**, not against the router in isolation. A service that only works when
its routes sit at the root is broken in the hub, and an isolated test will not notice.

```python
BASE = "/keycloak"

def test_health(client):
    assert client.get(f"{BASE}/health").json()["status"] == "ok"

def test_cross_realm_read_is_404(client, admin_token):
    """404, not 403 — from another realm the object does not exist."""
    r = client.get(f"{BASE}/admin/realms/other/users", headers=admin_token)
    assert r.status_code == 404
```

Fixtures come from the root [`conftest.py`](../conftest.py): `client`, `app`, `registry`,
`config`.

Cover every error path you implemented. In the reference service that is roughly a third of
the suite — RLS denials, foreign-key violations, unfiltered deletes, throttled functions,
private-channel broadcasts. An unexercised error path is a guess.

---

## Checklist

```
[ ] service.toml: status = "implemented", module points at the class
[ ] data/<slug>/*.json seeded, all-string cells, Orbit Labs universe
[ ] data.py: class-scoped state, tables registered, coercion in _coerce_*
[ ] data.py: resolve_role maps unknown credentials onto a role, never rejects
[ ] routes.py: no slug in any path; STATUS_BY_CODE covers every code data.py returns
[ ] service.py: on_startup builds the data layer and calls ctx.eager_load()
[ ] service.py: on_shutdown releases it; health() is cheap
[ ] tests: happy path AND every error path, through the hub
[ ] python tools/export_openapi.py            (commits openapi.json)
[ ] README.md: endpoints, auth, seeded data, deviations from upstream
[ ] examples.md: captured from a running container
[ ] python -m pytest                          (whole suite still green)
[ ] docker build . && curl /<slug>/health     (works under the pinned versions)
```

The last line is not ceremony. Local development here runs FastAPI 0.141 while the image pins
0.115 — a version gap that has already produced one real bug in this repo (`include_router`
changed how routes are stored, which broke route introspection on the newer version only).
Build the image before calling a service done.
