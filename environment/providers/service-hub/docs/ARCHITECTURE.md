# Architecture

How the hub is put together, and why each piece is the shape it is.

---

## 1. The problem

An agent benchmark needs an agent to face realistic services: a real auth flow, a real
mail inbox, a real billing API with real error codes. The obvious way to get that is one
container per service. For 27 services that means 27 images to build, 27 uvicorn processes
to schedule, 27 ports to allocate, and — the part that actually hurts — every one of them
resident for the whole run even though a given task touches two or three.

The hub keeps the realism and drops the multiplication. One process, one port, one image.
Each service is a module that is imported the first time somebody calls it.

The constraint that shapes everything below: **discovering that a service exists must not
load it.** If it did, an agent orienting itself with `GET /hub/services` would pull all 27
into memory and the design would be a per-container fleet with extra steps.

---

## 2. Layered view

```
        ┌───────────────────────────────────────────────────────────────┐
   L4   │  services/<pkg>/     ServiceModule subclass                   │
        │                      data.py · routes.py · models.py          │
        ├───────────────────────────────────────────────────────────────┤
   L3   │  hub/base.py         ServiceModule ABC · ServiceContext       │
        │                      lifecycle hooks · create_app()           │
        ├───────────────────────────────────────────────────────────────┤
   L2   │  service_registry.py catalog · state machine · lazy load      │
        │  router.py           Mount dispatch · unknown-service         │
        │  hub/control.py      /hub/*        hub/audit.py  /audit/*     │
        ├───────────────────────────────────────────────────────────────┤
   L1   │  main.py             app factory · lifespan · precedence      │
        │  hub/config.py       HUB_* environment                        │
        ├───────────────────────────────────────────────────────────────┤
   L0   │  hub/store.py        Table · Document · Store · snapshots     │
        │  data/<slug>/*.json  seeds                                    │
        └───────────────────────────────────────────────────────────────┘
```

Dependencies point downward only. **L4 never imports L2** — a service reaches the hub solely
through the `ServiceContext` it is handed, and reaches other services not at all. That is
what "logically isolated" means here: two services share a process and still have no path to
each other's rows except HTTP, exactly as if they were separate containers.

---

## 3. Service registry

[`service_registry.py`](../service_registry.py)

### Descriptor vs record

Two objects per service, split by lifetime:

- **`ServiceDescriptor`** (frozen) — parsed from `service.toml`. Identity, wiring, advertised
  surface. Never changes after discovery.
- **`ServiceRecord`** (mutable) — state, the live module and app, error text, load timings,
  request counts. One per service for the process lifetime, regardless of how many times the
  service is loaded and unloaded.

Keeping them apart is what lets `GET /hub/services` answer completely for an unloaded
service: the descriptor holds everything except what only exists once the module is running.

### State machine

```
   DECLARED ──────────────────────────────▶ 501, forever (no module behind it)

   DISCOVERED ──acquire()──▶ LOADING ──ok───▶ READY ──unload()──▶ UNLOADED
                                │                                    │
                                └──raise──▶ FAILED ◀──────reload()───┘
                                              │
                                              └── acquire() re-raises, does not retry
```

`FAILED` is **sticky**, and that is a decision worth defending. A service that raised on
import will raise identically on the next request, so retrying per-request converts one
clear failure into an unbounded stream of them, floods the logs, and makes run timings
nondeterministic — the last thing a benchmark wants. Recovery is explicit:
`POST /hub/services/<slug>/reload`.

### Discovery cost

Discovery parses 27 TOML files with `tomllib` and constructs 27 frozen dataclasses. No
imports, no seed reads, no filesystem beyond the manifests. It is the only work the hub does
before it starts serving.

---

## 4. Lazy loading

### The four steps

```python
service_class = await run_in_threadpool(_resolve_module, descriptor)  # 1. import
module        = service_class(ctx)                                    # 2. construct
await _maybe_await(module.on_startup())                               # 3. startup hook
app           = await run_in_threadpool(module.create_app)            # 4. build the app
ctx.store.capture_baseline()                                          #    snapshot the seeds
```

Details that matter:

**Import runs in the threadpool.** `importlib.import_module` hits the filesystem, and for a
data-heavy service that can take long enough to matter. Doing it on the event loop would
stall requests already in flight for *other* services — the one way a shared process could
be worse than separate containers. Router construction goes to the threadpool for the same
reason: it is arbitrary user code.

**`on_startup` runs before `build_router`.** Routes close over the data layer, so the data
layer has to exist first.

**The baseline is captured at load, not at first reset.** Capturing lazily would snapshot
whatever the task had already mutated, making reset a no-op exactly when it is needed.

**Hooks may be sync or async.** `_maybe_await` inspects the return value, so a service that
has nothing to await can write `def on_startup(self)` without ceremony.

### The lock

```python
if record.ready:                      # fast path: no lock, no await
    record.touch()
    return record

async with self._lock_for(slug):      # slow path: one loader, everyone else waits
    if record.ready:                  # re-check — someone may have loaded it
        return record
    await asyncio.wait_for(self._load(record), timeout=...)
```

Double-checked locking, per slug. Twelve simultaneous cold requests produce **one** import,
not twelve; and because the lock is per slug, a slow Supabase load never blocks a Keycloak
request. The fast path costs a dict lookup and a boolean, which is what every request after
the first pays.

Covered by [`test_concurrent_first_requests_load_exactly_once`](../tests/test_lazy_loading.py).

### Unloading

`unload` awaits `on_shutdown`, drops the module and app references, and calls
`drop_store(slug)`. The imported Python module deliberately stays in `sys.modules`: code is
kilobytes and re-importing it buys nothing. What unloading reclaims is the **seeded rows**,
which is where a service's memory actually lives. `reload(reimport=True)` purges
`sys.modules` too, for development.

Measured on the shipped image: **46 MB cold, +3.4 MB for Supabase**. Twenty-seven separate
uvicorn containers cost roughly 27 × 45 MB before a single row is loaded.

### Idle eviction

With `HUB_IDLE_TTL` set, a background task unloads services idle longer than the TTL.
Services named in `HUB_EAGER_SERVICES` are exempt — pinning one is a statement of intent.
Off by default (`0`), because on a short run eviction only adds reload latency.

---

## 5. Dynamic router

[`router.py`](../router.py)

### Why `Mount`

The tempting implementation is a catch-all:

```python
@app.api_route("/{service}/{path:path}", methods=[...])
async def dispatch(service: str, path: str, request: Request): ...
```

It looks simpler and is not. Re-dispatching by hand means re-implementing path parameters,
method matching, trailing-slash redirects, and per-service exception handling — and the
service's own `/openapi.json` and `/docs` become unreachable, so an agent cannot discover
one service's surface without the hub proxying every schema route too.

`Mount` is what FastAPI's own `app.mount()` uses. It strips the matched prefix from
`scope["path"]` and appends it to `scope["root_path"]`, so the sub-app sees itself at the
root while still generating correct absolute URLs. Everything above comes for free, across
Starlette versions, without the hub knowing anything about the service's routes.

### Where the laziness lives

Not in the route table — in the mounted app:

```python
class LazyServiceMount:
    __slots__ = ("_registry", "_slug")

    async def __call__(self, scope, receive, send):
        record = await self._registry.acquire(self._slug)   # imports on first call only
        await record.app(scope, receive, send)
```

Twenty-seven of these cost twenty-seven two-slot objects. Registering them at boot is what
lets Starlette do the prefix matching while the *modules* stay unimported.

### Precedence

Registration order is match order, so `main.py` installs in this sequence:

```
/health, /                    hub liveness and index
/audit/*                      request log
/hub/*                        control plane
/docs, /openapi.json          the hub's own schema
/<slug>/*                     the 27 lazy mounts
/{service}/{path:path}        "no such service", registered last
```

Belt and braces: [`hub/manifest.py`](../hub/manifest.py) refuses `hub`, `audit`, `health`,
`docs` and friends as slugs at discovery time, so a service cannot claim a control-plane path
even by accident.

The catch-all matters more than it looks. Without it, an agent that writes `/keyclock/...`
gets FastAPI's bare `{"detail":"Not Found"}` and no way to tell a mistyped *service* from a
mistyped *endpoint*. With it:

```json
{"error": {"scope": "hub", "code": "service_not_found",
           "hint": "did you mean 'keycloak'?", "available": ["appwrite", "..."]}}
```

That is the difference between an agent recovering in one turn and burning its budget
guessing.

---

## 6. Service base class

[`hub/base.py`](../hub/base.py)

```python
class ServiceModule(ABC):
    @abstractmethod
    def build_router(self) -> APIRouter: ...     # the routes

    def configure_app(self, app) -> None: ...    # optional middleware/handlers
    async def on_startup(self) -> None: ...      # build data layers, load seeds
    async def on_shutdown(self) -> None: ...     # release them
    def health(self) -> HealthReport: ...        # cheap probe

    def create_app(self) -> FastAPI:             # final — do not override
```

`build_router` returns an `APIRouter`; the base class wraps it into the `FastAPI` app. That
split is deliberate. It is what guarantees the invariants the hub advertises — every service
has a health endpoint at its declared path, its own isolated OpenAPI document, its own docs
page, a title and version taken from the manifest — **without 27 authors each remembering to
add them**. `/health` is registered before the router so a service's catch-all route can
never shadow it.

### `ServiceContext`

The only object a service receives, and its entire view of the hub:

```python
ctx.seed("profiles.json", "profiles")        # read a seed, CSV-overlay aware
ctx.register_table("profiles", "id", loader) # declare a table (loader runs later)
ctx.register_document("settings", loader)    # declare a JSON blob
ctx.eager_load()                             # force all loaders to run now
ctx.table("profiles") / ctx.document("settings")
ctx.data_dir · ctx.config · ctx.logger · ctx.descriptor
```

`ctx.store` is a **fresh** `Store` per load. Not memoized — memoizing is right in the fleet,
where the store dies with the container, and wrong here, where a reload would silently hand
the new instance the old one's mutated rows.

### The rule that makes it work

> **All service state lives on the instance. Never at module scope.**

Module-level state cannot be reclaimed on unload, cannot be rewound between tasks, and is
shared between two hub instances in one process — which is exactly what the test suite
builds. [`test_reload_returns_to_pristine_seeds`](../tests/test_lazy_loading.py) is the test
that catches a violation.

---

## 7. Data and reset

[`hub/store.py`](../hub/store.py) is vendored from the mock-API fleet: `Table` (rows with a
declared primary key, insertion order preserved, reads return deep copies), `Document` (a
single JSON blob), snapshots, and a drift log. Two functions were added for the hub —
`new_store` and `drop_store` — for the reload reason above.

Seeds are flat JSON rows with string cells, so a bind-mounted `profiles.csv` shadows the
baked `profiles.json` with no code change. That is how a benchmark task ships its own
fixtures without a fork.

Three levels of reset, cheapest first:

| Call | Cost | What it rewinds |
|------|------|-----------------|
| `POST /hub/services/<slug>/reset` | ~1 ms | rows → post-seed baseline |
| `POST /hub/services/<slug>/reload` | ~90 ms | rows + re-runs the hooks |
| `POST /hub/services/<slug>/reload?reimport=true` | ~150 ms | the above + re-imports the code |

`reset` is the between-tasks call. Reloading between every task in a thousand-task batch
would spend real wall-clock on nothing.

---

## 8. Audit

[`hub/audit.py`](../hub/audit.py) is raw ASGI, not `BaseHTTPMiddleware`. The latter runs each
request in a nested task and buffers the response through an anyio stream, which adds latency
to every call and interacts poorly with mounted sub-apps. Here `receive` and `send` are
wrapped; a non-recorded path costs one string compare.

Because the recorder sits *outside* the mounts it sees the full path, so every entry already
names its service. One ordered cross-service timeline, rather than 27 logs to merge:

```json
{"service": "supabase", "method": "GET", "path": "/supabase/rest/v1/projects",
 "status_code": 200, "duration_ms": 1.84, "request_body": null, "response_body": "[...]"}
```

Skipped: `/hub/*`, `/audit/*`, `*/health`, docs and schema routes. `/admin/` paths **are**
recorded — in the fleet `/admin` was the out-of-band drift plane and had to stay invisible,
but here the harness surface is `/hub/*` and `/admin/` belongs to the simulated products
(Keycloak's `/admin/realms/{realm}/users` is ordinary agent traffic).

---

## 9. Errors

Two error vocabularies, never confusable:

```jsonc
// the simulated service said no — upstream's own shape, whatever that is
{"code": "42501", "message": "new row violates row-level security policy ...",
 "hint": "Send an apikey header with a writable role."}

// the hub said no — an envelope no vendor uses
{"error": {"scope": "hub", "code": "service_not_implemented", "service": "keycloak",
           "hint": "docs/SERVICE_AUTHORING.md walks through adding it"}}
```

`"scope": "hub"` is the discriminator. An agent that sees it knows retrying against a
different endpoint is pointless. A grader can tell a genuine 4xx-under-test from a harness
fault — without which every failed task needs a human to classify it.

---

## 10. Failure containment

| Failure | Blast radius |
|---------|--------------|
| Malformed `service.toml` | that service is skipped, listed at `/hub/problems`; the other 26 serve |
| Service raises in `on_startup` | that service is `failed`; hub health reports `degraded`; others unaffected |
| Load exceeds `HUB_LOAD_TIMEOUT` | that service is parked with a timeout error |
| `on_shutdown` raises | logged; the unload completes anyway |
| Unknown eager service | logged; the hub still boots |
| `health()` raises | that service reports `status: error`; the route still answers 200 |

The through-line: one broken service must never cost the other 26. In a single-process design
that is not automatic — it is the reason every one of those paths catches.

---

## 11. What one process costs

Honest trade-offs of collapsing 27 containers into one:

- **No per-service resource limits.** A service that allocates without bound takes the
  process down. Separate containers would cap it with cgroups. Mitigation: seeds are bounded
  and loaded at startup where a bad one fails loudly.
- **No per-service crash isolation.** An unhandled exception in a route is contained by
  FastAPI's handler, but a segfault in a C extension is not. The hub's dependency surface is
  two packages and the standard library, largely for this reason.
- **Shared GIL.** Simulators are I/O-trivial and CPU-cheap, so this is theoretical at
  benchmark concurrency — but it is real, and a service doing heavy computation would need
  to be pushed to the threadpool.
- **Shared Python version.** Every service runs on the container's interpreter. Two services
  needing incompatible versions of a library would be a genuine problem; the two-dependency
  policy is what keeps that from arising.

What is *not* given up: services remain independently developed, independently tested,
independently loaded, and reachable at stable URLs. Moving one back into its own container
means running its `ServiceModule` under a thin `main.py` — the module boundary is already
the container boundary.
