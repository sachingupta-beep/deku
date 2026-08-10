# Agent and harness integration

The contract between the hub, the agent under evaluation, and the harness running the
benchmark.

---

## The flow

```
  1. harness starts the container          docker run -p 8080:8080 service-hub:v1
                                           27 services discovered, 0 loaded, ~46 MB

  2. harness pre-warms (optional)          POST /hub/services/supabase/load
                                           only for tasks where cold-start latency
                                           would pollute a timing measurement

  3. agent starts                          told one thing: the hub's base URL

  4. agent discovers                       GET /hub/services      ← loads nothing
                                           GET /hub/services/keycloak/openapi.json

  5. agent works                           GET  /supabase/rest/v1/documents?status=eq.draft
                                           POST /mailpit/api/v1/search
                                           ...  service loads on the first call to it

  6. harness grades                        GET /audit/requests?service=supabase
                                           GET /supabase/rest/v1/... (assert final state)

  7. harness resets                        POST /hub/reset          ← ~1 ms per service
                                           GET  /audit/requests/clear
                                           next task starts from pristine seeds

  8. teardown                              docker stop
```

No additional containers at any step.

---

## What the agent needs to be told

One environment variable:

```bash
SERVICE_HUB_URL=http://service-hub:8080
```

Everything else is discoverable. That is the design intent: the prompt should not have to
enumerate which services are up, because the enumeration would go stale and because an agent
that can discover its environment is the more interesting thing to evaluate.

If your harness prefers per-service variables — to match an existing task format, or because
a task should not know the whole fleet exists — derive them:

```python
services = requests.get(f"{HUB}/hub/services").json()["services"]
env = {f"{s['slug'].upper().replace('-', '_')}_API_URL": f"{HUB}{s['base_path']}"
       for s in services}
# SUPABASE_API_URL=http://service-hub:8080/supabase
# ORY_KRATOS_API_URL=http://service-hub:8080/ory-kratos
```

Injecting only the subset a task needs is a legitimate way to scope what the agent can see.

---

## Discovery

### `GET /hub/services`

The orientation call. Loads nothing.

```json
{
  "total": 27,
  "services": [
    {
      "slug": "supabase",
      "name": "Supabase (self-host)",
      "category": "backend",
      "summary": "Self-hosted Supabase data plane: PostgREST at /rest/v1 with ...",
      "status": "implemented",
      "state": "discovered",
      "base_path": "/supabase",
      "health_path": "/supabase/health",
      "openapi_path": "/supabase/openapi.json",
      "docs_path": "/supabase/docs",
      "route_prefixes": ["/supabase/rest/v1", "/supabase/storage/v1/bucket", "..."],
      "auth": {
        "scheme": "apikey",
        "roles": ["anon", "authenticated", "service_role"],
        "description": "The `apikey` header selects the Postgres role that RLS is ..."
      },
      "load_ms": null,
      "request_count": 0
    }
  ]
}
```

Two fields that are easy to confuse:

- **`status`** — `implemented` or `declared`. A property of the repository: is there a module
  behind this entry at all?
- **`state`** — `discovered` / `ready` / `failed` / `unloaded` / `declared`. A property of
  this process right now.

An agent should filter on `status`. A harness watches `state`.

Filters: `?category=email`, `?status=implemented`, `?state=ready`, `?loaded=true`.

### `GET /hub/catalog`

The same data grouped by category — better when the agent's next decision is "which kind of
service do I need".

### `GET /hub/services/{slug}/openapi.json`

One service's full schema. **This one loads the service** — you cannot describe a surface you
have not built. To check existence without loading, use `GET /hub/services/{slug}`.

---

## Auto-loading

The agent never manages loading. Calling an endpoint loads its service:

```
GET /lago/api/v1/invoices
  └─ Mount /lago matches
     └─ registry.acquire("lago")  →  import, construct, on_startup, build app   (~90 ms)
        └─ request proceeds
```

Subsequent calls skip all of that. Concurrent first calls collapse into one load.

The two responses an agent can get *instead*:

```jsonc
// 501 — the catalog knows this service, but nobody has built it
{"error": {"scope": "hub", "code": "service_not_implemented", "service": "keycloak",
           "hint": "docs/SERVICE_AUTHORING.md walks through adding it"}}

// 503 — the module exists but failed to load; it is parked until a reload
{"error": {"scope": "hub", "code": "service_load_failed", "service": "lago",
           "error_type": "CoerceError",
           "hint": "POST /hub/services/lago/reload to retry after fixing it"}}
```

Both carry `"scope": "hub"`. An agent seeing that knows the *infrastructure* refused, not the
simulated API — so retrying against a different endpoint of the same service is pointless.

---

## Lifecycle control (harness only)

| Call | When | Cost |
|------|------|------|
| `POST /hub/services/{slug}/load` | before a timed task, to keep import cost out of the measurement | ~90 ms |
| `POST /hub/services/{slug}/reset` | **between tasks** — rows back to baseline | ~1 ms |
| `POST /hub/reset` | between tasks, every loaded service | ~1 ms each |
| `POST /hub/services/{slug}/reload` | after a task corrupted a service, or to clear `failed` | ~90 ms |
| `POST /hub/services/{slug}/unload` | when a batch moves to a different service mix | — |
| `POST /hub/reap` | force an idle sweep now | — |

`reset` versus `reload` matters at scale. Reloading between every task in a thousand-task
batch spends real wall-clock re-importing code that never changed; `reset` restores the
snapshot taken at load time and is two orders of magnitude cheaper.

---

## Grading

### Traffic

```bash
GET /audit/requests                          # everything, oldest first
GET /audit/requests?service=supabase         # one service
GET /audit/requests?include_body=false       # metadata only — the default dump is large
GET /audit/summary                           # counts by service and by endpoint
GET /audit/requests/clear                    # between tasks
```

Every entry carries `service`, `method`, `path`, `query_params`, `request_body`,
`status_code`, `response_body` and `duration_ms`. Because the recorder sits outside the
mounts, one call gives an ordered cross-service timeline — you can see that the agent read
Supabase, then checked Mailpit, then called Lago, in that order, without merging logs.

Not recorded: `/hub/*`, `/audit/*`, `*/health`, docs and schema routes. Harness bookkeeping
stays out of the agent's trail.

### Final state

Read it back through the API with a privileged credential:

```python
docs = get(f"{HUB}/supabase/rest/v1/documents?status=eq.published",
           headers={"apikey": SERVICE_KEY}).json()
assert any(d["id"] == 503 for d in docs)      # the agent published it
```

Two assertions worth combining: **did the state change** (above) and **did the agent get
there legitimately** (`/audit/requests` shows the call it made, rather than a lucky guess at
a URL).

---

## Deployment notes

**Concurrency.** One uvicorn worker. Multiple workers would give each its own registry and
its own in-memory data, so an agent's write could land in a different process than its read.
If you need throughput, run several containers with the tasks partitioned across them — the
hub is small enough that this is cheap.

**Persistence.** None, by design. Every load reads the seeds fresh; a restart is a reset.
Reproducibility comes from the seeds being immutable in the image.

**Task fixtures.** Bind-mount a `.csv` over a service's data directory to shadow the baked
`.json` — `hub.store.read_seed_with_ctx` prefers a sibling `.csv`:

```yaml
volumes:
  - ./task-042/supabase/documents.csv:/app/data/supabase/documents.csv:ro
```

Then `POST /hub/services/supabase/reload` to pick it up.

**Health.** `GET /health` is O(1) and never loads a service — that is what Docker's
healthcheck polls. `GET /hub/health` probes the loaded services and is what a harness polls.

**Sizing.** ~46 MB cold. Each loaded service adds its data: Supabase is ~3.4 MB. A task
touching three services runs in well under 100 MB, against roughly 1.2 GB for 27 idle
containers.
