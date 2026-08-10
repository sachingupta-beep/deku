# Service Hub

One Docker container that simulates an entire backend fleet — Supabase, Keycloak, MailHog,
Lago, PostgreSQL and 22 more — behind a single port, with each service loaded only when an
agent first calls it.

Built as evaluation infrastructure for agent benchmarks (Harbor, SWE-Bench, WebArena,
Terminal-Bench). The design goal is to give an agent realistic, stateful, individually
authentic APIs to work against while a cold container holds **27 manifests and nothing
else**.

```
$ docker run -d -p 8080:8080 service-hub:v1
$ curl -s localhost:8080/health
{"status":"ok","services_discovered":27,"services_loaded":0}     # 27 available, 0 resident

$ curl -s localhost:8080/supabase/rest/v1/projects | head -c 60
[{"id":103,"owner_id":"...","name":"Web App", ...                 # Supabase loaded on this call

$ curl -s localhost:8080/health
{"status":"ok","services_discovered":27,"services_loaded":1}     # and only Supabase
```

---

## Architecture

```
                    ┌──────────────── ONE CONTAINER : ONE PORT (8080) ────────────────┐
                    │                                                                 │
                    │   uvicorn ─▶ FastAPI (hub)                                      │
                    │                │                                                │
   agent ──HTTP────▶│                ├─ AuditMiddleware ──────────▶ /audit/requests   │
                    │                │    (one trail, all services)                   │
                    │                │                                                │
                    │                ├─ /health   /   /docs                           │
                    │                ├─ /hub/*  ──▶ ServiceRegistry                   │
                    │                │              catalog · lifecycle · metrics     │
                    │                │                                                │
                    │                ├─ Mount /supabase  ─▶ LazyServiceMount ──┐      │
                    │                ├─ Mount /keycloak  ─▶ LazyServiceMount   │      │
                    │                ├─ Mount /mailpit   ─▶ LazyServiceMount   │      │
                    │                ├─ … 24 more, registered at boot,         │      │
                    │                │        importing nothing …              │      │
                    │                └─ /{service}/{path} → 404 + "did you mean"│      │
                    │                                                          │      │
                    │                       ON FIRST REQUEST ONLY ─────────────┘      │
                    │                                  │                              │
                    │            import ─▶ construct ─▶ on_startup ─▶ create_app       │
                    │                                  │                              │
                    │                                  ▼                              │
                    │                        FastAPI (one per service)                │
                    │                          ├─ /health          ← installed by the │
                    │                          ├─ /openapi.json      base class, not  │
                    │                          ├─ /docs              by 27 authors    │
                    │                          └─ routes ─▶ Data ─▶ Store             │
                    │                                                 │               │
                    │                                                 ▼               │
                    │                                    data/<slug>/*.json (seeds)   │
                    └─────────────────────────────────────────────────────────────────┘
```

Five pieces, each in one file:

| File | Role |
|------|------|
| [main.py](main.py) | app factory — assembles everything below, in precedence order |
| [service_registry.py](service_registry.py) | the catalog and the lifecycle: discover, load, unload, reset, report |
| [router.py](router.py) | one lazy `Mount` per service; the "no such service" catch-all |
| [hub/base.py](hub/base.py) | the `ServiceModule` contract every service implements |
| [hub/manifest.py](hub/manifest.py) | `service.toml` → `ServiceDescriptor`, the only thing read at boot |

---

## Quickstart

```bash
docker compose up -d                     # or: docker build -t service-hub:v1 . && docker run -p 8080:8080 service-hub:v1

curl localhost:8080/hub/services         # discover — loads nothing
curl localhost:8080/hub/catalog          # same, grouped by category
curl localhost:8080/supabase/rest/v1/projects   # call — loads Supabase
curl localhost:8080/hub/metrics          # load timings, request counts
```

Locally, without Docker:

```bash
pip install -r requirements.txt
uvicorn main:app --port 8080
python -m pytest                         # 142 tests
```

---

## The 27 services

`status: implemented` is reachable now. `declared` is an honest catalog entry that answers
**501** with a pointer at the authoring guide — never a stub that returns invented data.

| Category | Services | Status |
|----------|----------|--------|
| **Backend / BaaS** | [`supabase`](services/supabase/) | **implemented** |
| | `pocketbase` · `appwrite` · `directus` · `nhost` · `postgres-backend` | declared |
| **Relational DB** | `sqlite` · `postgresql` · `mysql` · `mariadb` · `cockroachdb` | declared |
| **Authentication** | `supabase-auth` · `pocketbase-auth` · `supertokens` · `logto` · `keycloak` · `zitadel` · `ory-kratos` · `dex` | declared |
| **Email** | `mailhog` · `mailpit` · `inbucket` · `smtp4dev` · `mailcatcher` | declared |
| **Payments** | `inhouse-payments` · `lago` · `killbill` | declared |

Every one of the 27 already carries full catalog metadata — upstream reference, auth scheme
and roles, advertised route prefixes — so `GET /hub/services` is useful before any of them
is built. See [docs/SERVICE_AUTHORING.md](docs/SERVICE_AUTHORING.md) to implement the rest;
`python tools/new_service.py <slug>` scaffolds a working module from the manifest.

---

## Why it is shaped this way

**Lazy loading is enforced by structure, not discipline.** Services are never imported at
boot because nothing imports them: the registry reads TOML, and the mount holds a slug and a
registry reference. There is no "load everything" code path to accidentally take. The test
that would catch a regression is [`test_boot_loads_nothing`](tests/test_lazy_loading.py).

**A `Mount`, not a catch-all handler.** Dispatching by hand would mean re-implementing path
params, method matching, redirects and per-service exception handling — and the service's own
`/openapi.json` and `/docs` would be unreachable. `Mount` is what FastAPI's own `app.mount()`
uses: it rewrites `scope["path"]` and `scope["root_path"]`, so the service sees itself at the
root and still generates correct absolute URLs. Registering 27 of them at boot costs one
small object each and imports nothing.

**Service state is instance-scoped, never module-global.** This is the rule that makes unload
and reset real. A service whose data lives in a module global cannot be reclaimed and cannot
be rewound between benchmark tasks; one whose data lives on the instance can be loaded,
unloaded and reset back to pristine seeds in milliseconds.

**Hub errors and service errors never look alike.** A simulated service answers in its
upstream's own error shape. Anything the *hub* rejects is wrapped in an envelope carrying
`"scope": "hub"`, which no vendor uses — so an agent can tell "the infrastructure said no"
from "the API said no", and a grader can tell a genuine 4xx-under-test from a harness fault.

**One audit trail, not 27.** The recorder sits outside the mounts, so it sees the full path
and every entry already names its service. A grader reads one ordered cross-service timeline
instead of merging logs.

---

## Control plane

| Endpoint | Purpose |
|----------|---------|
| `GET /hub/services` | every service, its descriptor and live state — **loads nothing** |
| `GET /hub/catalog` | the same, grouped by category |
| `GET /hub/services/{slug}` | one service; adds its live route table once loaded |
| `GET /hub/services/{slug}/openapi.json` | that service's schema (loads it — you cannot describe what you have not built) |
| `POST /hub/services/{slug}/load` | pre-warm |
| `POST /hub/services/{slug}/unload` | teardown hook, release the rows |
| `POST /hub/services/{slug}/reload` | back to pristine seeds; also clears a `failed` state |
| `POST /hub/services/{slug}/reset` | rewind data to baseline **without** re-importing — the between-tasks call |
| `POST /hub/reset` | reset every loaded service |
| `GET /hub/health` | aggregate; probes only what is loaded |
| `GET /hub/metrics` | load timings, request counts, RSS |
| `GET /audit/requests` | agent traffic, with `?service=` and `?include_body=false` |

## Configuration

| Variable | Default | Effect |
|----------|---------|--------|
| `HUB_PORT` | `8080` | listen port |
| `HUB_EAGER_SERVICES` | *(none)* | comma-separated slugs to pre-load at startup |
| `HUB_IDLE_TTL` | `0` | unload a service after N idle seconds; `0` disables |
| `HUB_REAPER_INTERVAL` | `30` | how often the idle reaper sweeps |
| `HUB_LOAD_TIMEOUT` | `30` | seconds before a load is abandoned and the service parked |
| `HUB_AUDIT` | `1` | record agent traffic |
| `HUB_EXPOSE_DOCS` | `1` | serve `/docs` and `/<slug>/docs` |
| `HUB_STRICT_DISCOVERY` | `0` | raise on a malformed manifest instead of skipping it |
| `HUB_LOG_LEVEL` | `INFO` | |

---

## Layout

```
service-hub/
├── main.py                     app factory, lifespan, route precedence
├── service_registry.py         catalog + lifecycle + lazy loading
├── router.py                   lazy Mounts, unknown-service handler
├── conftest.py                 shared pytest fixtures
├── Dockerfile                  digest-pinned, hash-verified, non-root
├── docker-compose.yml          one service block, because one container
│
├── hub/
│   ├── base.py                 ServiceModule ABC + ServiceContext + HealthReport
│   ├── manifest.py             service.toml parsing and validation
│   ├── registry glue: config.py, errors.py, control.py, audit.py
│   └── store.py                vendored mutable record store (tables, documents, snapshots)
│
├── services/
│   ├── supabase/               ← the reference implementation
│   │   ├── service.toml        manifest
│   │   ├── service.py          ServiceModule: hooks + wiring
│   │   ├── routes.py           HTTP surface
│   │   ├── data.py             data layer (instance-scoped)
│   │   ├── models.py           request bodies
│   │   ├── openapi.json        exported schema (16 paths / 21 operations)
│   │   ├── README.md           endpoint reference
│   │   ├── examples.md         captured request/response pairs
│   │   └── tests/              70 tests
│   └── <26 more>/service.toml  catalog entries
│
├── data/<slug>/*.json          seed data, one directory per service
├── tests/                      hub tests: registry, lazy loading, router, control plane
├── tools/
│   ├── new_service.py          scaffold a service from its manifest
│   └── export_openapi.py       write/verify committed schemas
└── docs/
    ├── ARCHITECTURE.md         the design, in depth
    ├── SERVICE_AUTHORING.md    how to implement the remaining 26
    └── AGENT_INTEGRATION.md    the agent and harness contract
```

## Tests

```bash
python -m pytest                        # 142 passed
python -m pytest tests/                 # hub: registry, lazy loading, routing, control plane
python -m pytest services/supabase      # the reference service
python tools/export_openapi.py --check  # committed schemas are current
```
