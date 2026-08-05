# `environment/` — central service catalog

One generic, shared source of truth for every backing service, used by all tasks
**as per need**. Replaces the per-task duplication of `docker-compose.yaml` +
`postgres-init.sh` (which was copy-pasted identically across tasks).

## The model

```
environment/
├── registry.json                 # slot -> allowed providers; provider -> {image, ports, seeds, deps}
├── providers/
│   ├── postgres/{service.yaml, init.sh}      # init.sh is GENERIC (same everywhere)
│   ├── pocketbase/service.yaml               # seed is TASK-SPECIFIC (stays in task)
│   ├── minio/service.yaml
│   ├── mailpit/service.yaml
│   ├── keycloak/service.yaml                 # realm is TASK-SPECIFIC (stays in task)
│   └── deku-pay/service.yaml
└── compose.py                    # generator: task [metadata.services] -> tasks/<t>/environment/docker-compose.yaml
```

A task only declares **what it needs**, in `task.toml`:

```toml
[metadata.services]
backend = "postgres"
storage = "minio"
```

`compose.py` assembles that task's `docker-compose.yaml` from the fragments —
the same "central source → generated per-task copy" pattern as `sync_verifier.py`
for grader files.

## Generic vs. task-specific (the split)

| Kind | Example | Lives where |
|------|---------|-------------|
| Generic infra | postgres image + `deku_app` role init | `environment/providers/` (centralized) |
| Task seed | pocketbase collections, keycloak realm | `tasks/<t>/environment/` (task owns it) |

## How a container actually comes up

Two kinds of provider, per `service.toml`'s `kind`:

- **`kind = "image"`** (postgres, minio, mailpit, keycloak, pocketbase) — a real
  public image. The `.yaml` fragment is enough: `docker compose up` pulls and runs it.
- **`kind = "build"`** (deku-pay) — an **in-house** service with no public image;
  it carries its own build context (`build/`: Dockerfile + app.py) in the provider
  dir, exactly like a WildClawBench mock. The `.yaml` alone can't start it — the
  build context must exist, which is why it lives here and `compose.py` copies it
  into the task.

Inside a trial, **Harbor** merges the task's `docker-compose.yaml` and runs it. To
boot a task's services **standalone** (no trial) for smoke-testing, use `stack.py`
— Deku's equivalent of WildClawBench's `mock_stack.py`:

```bash
python3 environment/stack.py up   --task <name>   # docker compose up -d --wait (boots + healthchecks)
python3 environment/stack.py ps   --task <name>
python3 environment/stack.py down --task <name>
python3 environment/stack.py check                # service.toml <-> registry.json in sync
```

## Usage (compose generator)

```bash
python3 environment/compose.py --check                 # generated vs current, all tasks (CI gate)
python3 environment/compose.py --task <name>           # print a task's generated compose
python3 environment/compose.py --write --task <name>   # write it + copy generic seeds/assets
```

## Provider ladders (PLAN §3.3)

`registry.json` lists each slot's provider ladder (easiest → hardest), e.g.
`db: sqlite → postgres → mysql → cockroachdb`. Only providers actually in use are
implemented today (postgres, pocketbase, minio, mailpit, keycloak, deku-pay); the
rest are declared in the ladder and added on demand.
