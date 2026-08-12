# Deku — greenfield spec-to-app harness

A Harbor-format benchmark that measures one capability: **take a written product
brief with no starting codebase and ship a running, multi-tier web application a
stranger can actually use through a browser.**

Spec: [`PLAN.md`](PLAN.md). This README is the operational record — what exists, how
to run it, and what has actually been observed rather than assumed.

---

## Status

| Layer | State |
|---|---|
| 5 authored tasks | built, all pass `validate_task.py` |
| Shared verifier image | `deku-verifier-base:0.2` builds; Chromium runs inside it |
| Binary browser grader | **ran live** — but 17 of 20 substeps were skipped by the rate-limit breaker, not graded (seventh hole) |
| Rubric judge | **ran live**, wrote `judge.json`; every dimension `0.0` on inherited `429` |
| pytest layer | **ran live** — 12 substeps, real per-test diagnostics |
| Reward integrity | `reward.json` is single-key; unobserved runs score `0.0` with `invalid` |
| Verifier mode | `shared` — `separate` cannot grade a live app (see Findings) |
| Trajectory generation | **working end to end** — 11 trajectories across 2 tasks, 2 models |
| Sidecar services | working — PocketBase verified live |
| Claude Code bridge | working — real inference on OAuth subscription |
| Oracle gate | **blocked** — no `solution/app/` in any task |
| Deploy gate | **passes** — `deployed: 1.0` |
| Non-zero reward | not yet — all substeps fail on one seeding/adapter cause |

Nothing below is aspirational. Every number is copied from a real run.

---

## Layout

```
PLAN.md                      the harness spec (source of truth)
SPEC/                        vibecoding docs for the Ethara app (source for task 1)

harness/
  validate_task.py           PLAN.md 2.4 rejection triggers + 3.3 combinatorics guard
  verifier/                  → baked into deku-verifier-base
    Dockerfile               playwright/python:v1.49.1-noble + deps + both graders
    test.sh                  verifier entrypoint: deploy gate → browser → pytest → judge → score
    score.py                 90% + critical rule → reward.json
    capabilities.py          per-slot provider adapters (backend/email/payments/storage)
    appclient.py             authenticated HTTP clients against the App Contract
    _shapes.py, pytest.ini
  eval/                      evaluation, runs SEPARATELY from generation
    run_workflows.py         binary browser grader (agentic loop)
    run_rubric.py            UI/UX + motion + a11y judge (deterministic evidence)
    verify_trajectory.py     PLAN.md 4.9 retention filters
    report.py                reward listing + failed-requirement detail
    test_run_workflows.py    4 self-checks
    test_run_rubric.py       10 self-checks

tasks/<task-id>/
  task.toml                  schema 1.3 config + Deku metadata
  instruction.md             the ONLY thing the agent sees
  environment/Dockerfile     agent runtime
  environment/docker-compose.yaml   sidecar services (when the task needs them)
  tests/                     hidden — baked into the verifier image, never uploaded
  solution/                  held out — oracle agent only

agent/claude_code/           symlink shim so the OAuth bridge imports as agent.claude_code
jobs/                        harbor run output (trajectories, rewards)
logs/                        bridge + run logs
```

---

## The two-signal grading model

Neither grader reads the agent's source. `pytest` here is **not** unit tests over
generated code — architecture is free, so there is nothing stable to import.

```
substep      one atomic, externally observable assertion
             kind: browser | pytest        critical: true | false
workflow     6–23 per task
             passes iff  passing_substeps / total_substeps >= 0.90
             AND every substep marked critical passed
reward       passing_workflows / total_workflows        ∈ [0, 1]
deploy fail  reward = 0  (hard zero, no partial credit)
ungraded     reward = 0  + `invalid` reason  (run did not observe the app)
```

**`reward.json` contains exactly one key.** Harbor promotes *every* top-level key
of that file into its own reward stream
(`VerifierResult.rewards` → `JobResult.reward_stats`), so anything parked next to
`reward` becomes a reward. Diagnostics live in `workflows.json`, which Harbor does
not read.

| file | contents | drives RL? |
|---|---|---|
| `reward.json` | `{"reward": <float>}` — nothing else, ever | **yes** |
| `workflows.json` → `summary` | 15 diagnostics incl. `judge_score`, `invalid` | no |
| `workflows.json` → `workflows[]` | per-workflow, names which requirement failed | no |

`judge_score` isolation is now structural twice over: `score.py` reads `judge.json`
only *after* reward arithmetic is final, **and** the value never enters
`reward.json`. Before, it sat beside `reward` and Harbor registered it as a peer
reward stream — the isolation the docstring claimed was not the isolation the code
delivered.

PLAN.md 1.4 — a judge-only reward is trivially gamed.

### An unobserved run is not a zero

If a workflow declares browser substeps and they were not graded — results file
missing, grader rate-limited, workflow past its deadline — the harness did not look
at the app. Scoring the surviving `pytest` substeps and publishing the ratio would
be a fabrication, and **no workflow in the corpus is browser-only**, so every
workflow would still produce a number.

Such a run scores `0.0` with `summary.invalid` naming the cause:

```
reward.json   {"reward": 0.0}
workflows.json  summary.invalid = ["browser_substeps_ungraded", "grader_unavailable"]
```

Filter on `invalid` before treating any trial as training data. A `0.0` with an
empty `invalid` is an agent failure; a `0.0` with a populated one is a harness
fault wearing the same number.

### Rubric dimensions

| dimension | weight |
|---|---|
| instruction_following | 0.30 |
| functionality | 0.25 |
| ux_flow | 0.15 |
| ui_visual | 0.15 |
| motion | 0.05 |
| accessibility | 0.05 |
| responsiveness | 0.05 |

Weights sum to 1.0, then the composite is **capped at `functionality + 0.15`**.
Without that cap a beautiful app throwing console errors scores ~0.85, which is
exactly PLAN.md 1.3 mode 1 ("builds green, runtime 500"). Measured effect:

```
scenario                             plain  capped  effect
all perfect                            1.0     1.0  -
PRETTY BUT BROKEN (works=0.2)          0.8    0.35  CAPPED
pretty, half-working (works=0.5)     0.875    0.65  CAPPED
ugly but works (visual=0.2)            0.8     0.8  -
```

The judge grades against the **actual `instruction.md`** passed in — the UI/UX
sections pin palette hexes, type scale, radii, `150ms / cubic-bezier(0.16,1,0.3,1)`,
WCAG AA — so `ui_visual` and `motion` check stated spec, not generic taste.
Evidence is objective where possible: `getComputedStyle` samples,
`document.getAnimations()`, a `prefers-reduced-motion` re-capture, Tab focus-walk,
console + failed-request listeners bound at context creation, screenshots at
1920×1200 / 768×1024 / 390×844 sent as multimodal image blocks.

---

## The corpus

| task | sub-cat | diff | slots | wf | browser | pytest | critical | non-happy |
|---|---|---|---|---|---|---|---|---|
| `creator-subscription-billing` | solo_founder | hard | postgres + deku-pay + minio | 14 | 18 | 20 | 17 | 8 |
| `event-rsvp-confirmations` | solo_founder | medium | postgres + mailpit | 12 | 17 | 16 | 12 | 6 |
| `seat-allocation-map` | enterprise | medium | postgres | 12 | 26 | 16 | 9 | 6 |
| `streak-habit-tracker` | individual | easy | pocketbase | 11 | 20 | 12 | 11 | 5 |
| `team-expense-approval` | enterprise | hard | postgres + keycloak | 15 | 21 | 21 | 19 | 10 |

Five distinct archetypes, five slot combinations, zero archetype collisions.
`seat-allocation-map` is derived from [`SPEC/`](SPEC/); the other four were authored
against the same contract.

---

## Setup

Requirements: Python 3.12+, Docker, and either an Anthropic API key or the Claude
Code OAuth bridge.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install harbor fastapi uvicorn httpx
.venv/bin/harbor --version          # 0.20.0
```

Build the shared verifier base (needed before any task image):

```bash
docker build -t deku-verifier-base:0.2 -f harness/verifier/Dockerfile harness
```

### Claude Code bridge (inference on an OAuth subscription)

The bundled `claude_code_bridge.sh` does not work as shipped: it computes
`REPO_ROOT` as its own parent and runs `python -m agent.claude_code`, while the
package sits at `claude_code/`. The `agent/` directory here is a symlink shim that
makes that import path resolve.

```bash
# Bound to 0.0.0.0 so the agent CONTAINER can reach it; a secret is mandatory
# because otherwise any local process can spend the subscription.
SECRET="deku-$(openssl rand -hex 16)"; echo "$SECRET" > .bridge_secret; chmod 600 .bridge_secret
PYTHONPATH=. KAIJU_CC_BRIDGE_SECRET="$SECRET" \
  nohup .venv/bin/python -m agent.claude_code --host 0.0.0.0 --port 8765 > logs/bridge.log 2>&1 &

curl -fsS http://127.0.0.1:8765/healthz            # {"ok":true}
docker run --rm curlimages/curl -sS http://host.docker.internal:8765/healthz   # {"ok":true}
```

Point Harbor at it. **Export both base-URL names** -- which one is read depends
on the agent, and getting it wrong does not fail fast:

| Consumer | Reads |
| --- | --- |
| `claude-code` agent, and the graders (`harness/eval/run_workflows.py`) | `ANTHROPIC_BASE_URL` |
| `openhands` (the DEFAULT agent), via litellm | `ANTHROPIC_API_BASE` |

```bash
export ANTHROPIC_BASE_URL=http://host.docker.internal:8765
export ANTHROPIC_API_BASE=http://host.docker.internal:8765
export ANTHROPIC_API_KEY=$(cat .bridge_secret)
```

Set only one and the other consumer ignores the bridge, dials
`api.anthropic.com` directly, and sends the bridge secret as a real API key. It
surfaces minutes into a paid agent run as `401 invalid x-api-key` buried in a
litellm traceback that names neither the variable nor the bridge.

`bin/deku-run` now mirrors whichever one it finds onto the other, so this cannot
bite you there -- but a bare `harbor run` has no such protection, which is why
both belong in your shell (and in `.env`).

With `ANTHROPIC_BASE_URL` set, Harbor keeps the full model name and aliases every
model tier to it.

---

## End to end

### 1. Validate tasks

```bash
.venv/bin/python harness/validate_task.py tasks/*/
```

```
[PASS] creator-subscription-billing
[PASS] event-rsvp-confirmations
[PASS] seat-allocation-map
[PASS] streak-habit-tracker
[PASS] team-expense-approval
[PASS] combinatorics guard across 5 tasks

not checked here: oracle run (needs a live harbor run) and pytest
implementation-coupling (human review, PLAN.md 4.4)
```

Covers the mechanical PLAN.md 2.4 triggers: schema version, kebab-case naming,
separate verifier mode, healthcheck present, explicit network mode, known slots,
slot→`DEKU_SERVICE_*` plumbing, privileged creds absent from the agent phase,
workflow count 6–23, non-happy-path present, substep↔test id bijection, critical
substep per slot, canary, no provider SDK imported in tests, no substep id leaked
into `instruction.md`, fixture resolution, and the ≤4-variants / ≤80%-overlap
combinatorics guard.

### 2. Generate a trajectory

```bash
.venv/bin/harbor run -p tasks/streak-habit-tracker \
  -a claude-code -m claude-sonnet-4-5-20250929 --n-concurrent-agents 1
```

Cheap pipeline check with no model spend — `nop` builds nothing so it must score 0:

```bash
.venv/bin/harbor run -p tasks/streak-habit-tracker -a nop --n-concurrent-agents 1
```

Artifacts per trial:

```
jobs/<ts>/<task>__<id>/
  agent/trajectory.json                   canonical Harbor ATIF-v1.7
  agent/sessions/projects/-app/*.jsonl    Claude Code session, one object per turn
  agent/claude-code.txt                   raw stream-json
  verifier/reward.json                    the score
  verifier/ctrf.json                      per-test results
  verifier/judge.json                     rubric breakdown
  verifier/shots/                         screenshots
```

### 3. Evaluate — separate from generation

```bash
.venv/bin/python harness/eval/report.py jobs/ --detail
.venv/bin/python harness/eval/verify_trajectory.py jobs/*/
```

Both graders can also run standalone against any deployed app:

```bash
.venv/bin/python harness/eval/run_workflows.py \
  --workflows tasks/seat-allocation-map/tests/workflows.yaml \
  --url http://localhost:4173 --out /tmp/browser_results.json

.venv/bin/python harness/eval/run_rubric.py \
  --instruction tasks/seat-allocation-map/instruction.md \
  --url http://localhost:4173 --out /tmp/judge.json
```

Inside the verifier `test.sh` orders them deliberately: **browser first, pytest
second**, so pytest only ever asserts side effects a real user action caused. The
reverse would assert against seed data — the exploit workflows exist to prevent.
A zero reward is written *before* anything else, because a verifier that exits
without a reward file raises `RewardFileNotFoundError` and the trial is **lost,
not scored 0**.

---

## Run log

Every run performed, with real numbers.

| job | agent | outcome | runtime |
|---|---|---|---|
| `13-04-24` | nop | RuntimeError — pocketbase sidecar unhealthy | 4m41s |
| `13-10-41` | nop | **reward 0.0, 0 exceptions** — pipeline green | 3m15s |
| `13-16-53` | claude-code / sonnet-4.5 | **reward 0.0**, 85 steps, 377 turns | 20m25s |

The real trajectory:

```
prompt tokens      6,127,523
completion tokens     46,026
cached tokens      6,026,267
cost                   $2.88
harbor steps              85
session turns            377
```

Current evaluation state:

```
task                       agent         reward      wf crit brw  steps   cost$ retain
streak-habit-tracker       -                  -       -    -   -      0       - RERUN
streak-habit-tracker       -                  -       -    -   -      0       - RERUN
streak-habit-tracker       -             0.0000       -    -   -      0       - RERUN
streak-habit-tracker       claude-code   0.0000       -    -   -     85    2.88 DISCARD

trials 4 · scored 2 · mean reward 0.0000 · retained 0
```

### Model comparison: Opus 4.5 vs Sonnet 4.5

Two tasks × two models, sequential, same bridge, same scratch config.

| task | model | steps | turns | min | out tok | cost |
|---|---|---|---|---|---|---|
| seat-allocation-map | opus-4-5 | 137 | 136 | 26.8 | 77,502 | $8.90 |
| seat-allocation-map | sonnet-4-5 | 87 | 124 | 19.7 | 58,470 | $3.24 |
| streak-habit-tracker | opus-4-5 | 166 | 173 | 23.1 | 57,978 | $8.35 |
| streak-habit-tracker | sonnet-4-5 | 115 | 126 | 18.1 | 58,266 | $3.80 |

**Rewards are all 0.0 and carry no signal** — every trial died on the separate-mode
teardown above, not on model quality. What is comparable:

| | opus-4-5 | sonnet-4-5 |
|---|---|---|
| cost | **2.4–2.7× higher** | baseline |
| steps | +44% / +57% | baseline |
| wall clock | +26% / +36% | baseline |
| files written (streak / seat) | 26 / 61 | 23 / 56 |
| **self-test curls (streak / seat)** | **108 / 77** | **40 / 13** |

The self-testing gap is the interesting one. PLAN.md 4.9 records browser
self-testing as the strongest single predictor of success (`r = 0.72`). Opus probed
its own app **2.7× more on streak and 5.9× more on seat-allocation**. On the harder
task Sonnet nearly stopped checking its work — 13 probes across 87 steps.

Both models honoured both contract fixes in **all four runs**: `setsid` detached
start YES, pinned password `deku-demo-pw-2026` YES. The fixes work; the zeros are
entirely the harness blocker.

### Self-checks

```
$ .venv/bin/python harness/eval/test_run_workflows.py
[1/4] parse: all 12 workflows have the expected browser substep counts and order
[2/4] round-trip: score.load_browser returns matching per-workflow lengths, all True
[3/4] shell round-trip: lengths align, every substep ungraded (None), not failed
[4/4] rate-limited run: grader_error propagates, substeps ungraded
OK

$ .venv/bin/python harness/eval/test_run_rubric.py
10/10 passed

$ docker run --rm deku-verifier-base:0.2 ...
imports OK
chromium launched, page text: deku
computed color: rgb(79, 70, 229)      ← #4F46E5, the brief's indigo
```

---

## Findings that change PLAN.md

**1.8 is resolved, and the answer kills separate mode.** Sidecars are
`environment/docker-compose.yaml`; the agent container is the `main` compose
service and sidecars share its network namespace, so the app reaches
`pocketbase:8090`. That half works.

The verifier half does not. **Harbor tears down the entire agent environment
before running a `separate` verifier.** A 20-second port watch across a live run:

```
15:49:25  http=200   containers=[__env-main-1, __env-pocketbase-1]   ← app live, serving
15:53:47  http=000   containers=[__verifier__trial-main-1]           ← agent env GONE
16:21:55  http=200   containers=[__env-postgres-1, __env-main-1]     ← next run, live again
```

Confirmed in `harbor/trial/trial.py`: the separate verifier is built with its own
`session_id` (`{trial}__verifier__{key}`), therefore its own compose project and
network, with `extra_docker_compose` stripped — and it receives only
`upload_artifacts(source_artifacts_dir=agent_env_paths.artifacts_dir)`, i.e.
collected files, not a live service.

So `verifier.environment_mode = "separate"` **cannot grade a running app**. The
whole Deku grading design — browser agent plus pytest against a deployed app — is
incompatible with it. This is not a networking problem; two networking fixes were
built and proven before the teardown was found:

```
project B → main:4173                  curl: (6) Could not resolve host: main
project B → host.docker.internal:4173  OK-FROM-APP        (port override applies:
                                                           0.0.0.0:4173->4173/tcp)
```

Neither helps, because by verification time the container no longer exists.

**Shared mode is the required configuration.** `_run_shared_verifier` uses
`self.agent_environment`, so the app is still alive, and `tests/` is uploaded
*inside* `verifier.verify()` — which runs **after** the agent phase. The agent
therefore never sees `workflows.yaml`. PLAN.md 1.8's leak concern is about file
presence; temporally the agent is already finished when the answer key lands.

The real cost of shared mode is different from the one the plan anticipated: the
verifier runs in the *agent's* image, which has none of `score.py`,
`capabilities.py`, `appclient.py`, `_shapes.py` or Playwright — those exist only in
`deku-verifier-base`.

### The migration, and what it produced

| change | why |
|---|---|
| `environment_mode = "shared"` on all 5 tasks | the verifier runs inside the agent env, where the app is still running |
| `[verifier.environment]` removed | Harbor rejects it in shared mode |
| `APP_PUBLIC_URL` → `http://localhost:4173` | the verifier is the same container now, not a peer |
| `harness/sync_verifier.py` | the grader can no longer live in a base image; it ships into each task's `tests/`, with `--check` guarding drift |
| grader deps added to every agent Dockerfile | pytest / httpx / psycopg / pyyaml now run in the agent image |
| `validate_task.py` now **requires** shared | with the rationale inline, so the mode is not "fixed" back to a config that cannot grade |

First run after the migration — the whole pipeline executed for the first time:

```
deployed: 1.0          ← deploy gate PASSED (0.0 on every prior run)
browser_graded: true   ← browser grader RAN, 20 substeps
substeps_total: 32     ← 20 browser + 12 pytest, all evaluated
ctrf.json present      ← pytest RAN
reward: 0.0            ← computed, not the initialisation stub
```

with real per-requirement diagnostics:

```
- dashboard_matches_ledger              0/3 (0%)  CRITICAL
- duplicate_habit_name_rejected         0/3 (0%)  CRITICAL
- duplicate_completion_no_double_count  0/1 (0%)  CRITICAL
- future_dated_completion_rejected      0/1 (0%)
- unauthenticated_access_denied         1/2 (50%)
- cross_user_access_forbidden           0/2 (0%)  CRITICAL
```

### Two further harness bugs the migration exposed

**Harbor validates every `reward.json` key as a numeric reward.**
`VerifierResult.rewards` is `dict[str, float]`, so the `judge_score: null` and the
per-workflow list raised `ValidationError` and the trial was **lost, not scored**.
An earlier comment in `score.py` asserted the opposite ("Harbor ignores keys it
does not know") — that was wrong and cost a trial. Detail now goes to a sibling
`workflows.json`, and the result is checked against Harbor's own model:
`VerifierResult accepts reward.json: True`.

The first fix here was half a fix: it made `reward.json` *valid* but left twelve
diagnostics in it, and Harbor turns every valid key into its own reward stream. See
the seventh hole below — `reward.json` now carries `reward` and nothing else.

**The rubric judge never ran.** It looked for `/app/instruction.md`, but
`TaskPaths.instruction_path` is host-side — Harbor passes the spec to the agent as
a *prompt* and never uploads it. The spec now ships in `tests/` alongside the
graders. No leak: the agent already receives it.

### Playwright had to move into the agent image too

Shared mode means the browser grader runs in the agent's container, and the first
clean trial recorded exactly why it scored nothing:

```
"error": "playwright not installed: No module named 'playwright'"
playwright not installed: No module named 'playwright'; wrote zero-score judge.json
```

Both graders degraded correctly rather than crashing — `run_workflows.py` emitted
its all-fail shell and `run_rubric.py` wrote a zero-score `judge.json` — but that
makes `browser_substeps 0/20` a harness artifact, not a measurement of the app.

`playwright install --with-deps` cannot be used here: the agent images are Debian
trixie, the same fallback-to-Ubuntu failure documented above. Chromium's actual
Debian runtime deps are now installed explicitly and verified by launching it:

```
deps installed
chromium downloaded
LAUNCH OK: deku rgb(79, 70, 229)      ← #4F46E5, the brief's indigo
```

### The third contract hole: agents spawning their own backing service

The first scored run failed every data assertion with:

```
AssertionError: seeded user demo@ethara.ai is missing from the users collection
```

The adapter was exonerated by reproducing it against a live instance —
`count(users) = 1`, `one(users, email=...)` returns the record. The agent was the
cause, and the trajectory says exactly how:

```
http://127.0.0.1:8090   95 mentions
./pocketbase            22 mentions
BACKEND_URL              0 mentions
```

It **downloaded and started its own PocketBase inside the container** and never
touched the provided sidecar. The app wrote to one database; the grader read
another. `BACKEND_URL` was injected correctly — the agent simply never looked.

Same family as the previous two holes: the spec assumed something obvious to its
author. It said "the PocketBase instance at `BACKEND_URL`" but never said *it is
already running, do not start your own*. Added to all five contracts:

> **The backing services are ALREADY RUNNING.** … **Do not download, install,
> compile or start your own copy of any of them.** … The grader inspects the
> service at that address — an app that writes to a different instance scores zero
> no matter how well it works.

Measured effect on the next run:

| | before | after |
|---|---|---|
| `BACKEND_URL` referenced | 0 | **125** |
| `http://pocketbase:8090` | 0 | **83** |
| own instance (`./pocketbase`) | 22 | **0** |

### The fourth: a requirement the agent was forbidden to satisfy

With the sidecar now in use, the failure moved on:

```
AssertionError: PocketBase habits query returned 404
```

`instruction.md` mandates three named collections. Creating a PocketBase
collection requires admin credentials — and `BACKEND_ADMIN_KEY` is withheld from
the agent phase **by design** (PLAN.md 3.4), precisely so an agent cannot satisfy
workflows by writing state directly:

```
agent env keys    : ['APP_PUBLIC_PORT', 'BACKEND_URL']
verifier env keys : ['APP_PUBLIC_URL', 'BACKEND_ADMIN_KEY', 'BACKEND_URL', ...]
```

So the task demanded something the agent was structurally forbidden from doing.
The schema is environment, not agent work: `environment/pocketbase-init.sh` now
creates the superuser **and** the `habits` and `completions` collections at boot.
`datamodel` is already in `spec_sections_given`, so the agent was handed this exact
schema anyway — pre-creating it removes an impossible requirement without removing
any measured work. Verified:

```
created collection
created collection
  users        count=0
  habits       count=0
  completions  count=0
```

**3.6 is unworkable on Apple Silicon.** `allowlist` and `no-network` both gate on
`_enable_egress_control`, which probes with an image pinned to a **linux/amd64**
digest. On arm64 it runs under emulation and exits 1, so `public` is the only
usable mode locally:

```
platform: darwin
probe image: alpine:3.23.4@sha256:5b10f432...
returncode: 1
stderr: WARNING: the requested image's platform (linux/amd64) does not match
        the detected host platform (linux/arm64/v8)
=> egress control available on this host: False
```

The corpus keeps `allowlist` for the Linux/cloud target. This makes 2.5 Phase 7 a
**development** blocker, not just a scaling one.

**4.6.1's token model needs recomputing.** Measured 6.1M prompt tokens of which
6.0M were cache reads, against 46K completion, at $2.88 for one trial. 56,000 trials
is ~$161K driven almost entirely by cache-read pricing — a different cost shape
from the plan's naive per-token projection.

**The App Contract had a hole that made every task unpassable.** See below.

**The `task.toml` healthcheck may be harmful.** It converts "agent failed to
deploy" from a scored 0 into a *lost* trial needing re-run (4.9). `test.sh` already
polls the app for 150s, so the healthcheck adds a failure mode without adding a gate.

**Mode 2 and mode 3 are invisible to any rubric judge.** "Auth works in isolation,
breaks in flow" and "cross-service desync" are pytest-side effects the judge cannot
see from the UI. That is the correct division of labour, and the reason the
two-signal design exists — but nobody should expect `judge_score` to catch a faked
payment.

### The fifth: both graders were denied model access

With the sidecar and schema fixed, `judge.json` came back all zeros:

```
instruction_following  0.0  exception: RuntimeError: ANTHROPIC_API_KEY not set
functionality          0.0  exception: RuntimeError: ANTHROPIC_API_KEY not set
... all 7 dimensions
```

Both graders are model-driven — `run_workflows.py` interprets natural-language
substeps and `run_rubric.py` grades each dimension — but only the *agent* phase
ever received credentials. PLAN.md 3.4 already says `ANTHROPIC_API_KEY` serves
"the agent model **and the browser-grader model**"; the task configs simply never
passed it to the verifier. `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` are now in
`[verifier].env`, which Harbor applies to the verifier exec only.

### The sixth: 429 is the steady state, not an exception

The key error disappeared and became a rate limit:

```
before:  RuntimeError: ANTHROPIC_API_KEY not set
after:   HTTPStatusError: 429 Too Many Requests
```

Grading starts the instant the agent phase ends, on the same account the agent has
just spent millions of tokens against — so 429 is routine here. Without backoff
every substep and all seven dimensions fail for a reason unrelated to the app.
`Anthropic.message()` now honours `Retry-After` with exponential fallback (6
attempts, 15s → 120s cap).

Backoff was necessary and not sufficient. Retrying only changes *how long* the
grader waits before recording a zero — it never changes the fact that a throttled
grader still wrote `passed: false` on a substep it never looked at. That took the
seventh hole to surface, six identical trials later.

The reason it was missing is worth recording: `JudgeAnthropic` had **duplicated**
the entire `message()` method purely to raise `max_tokens`, so it could never
inherit a transport fix. Making `max_tokens` a parameter collapsed the override to
a single `super()` call — 23 lines replaced by 13, and the retry is now inherited
by construction. Duplication is exactly how the judge lost every dimension.

### The grader is a second inference workload, and nobody budgeted for it

Backoff works — the retry ladder fires exactly as designed:

```
workflow user_sees_seeded_streaks (3 browser substeps)
  substep 1/3: Sign in with the credentials documented in /app/USER_README.md
  [retry] HTTP 429, sleeping 15s (1/6)
  [retry] HTTP 429, sleeping 30s (2/6)
  [retry] HTTP 429, sleeping 60s (3/6)
  [retry] HTTP 429, sleeping 120s (4/6)
  [retry] HTTP 429, sleeping 120s (5/6)
```

— and is still not enough. One trial's grading is **20 browser substeps × a
tool-calling loop, plus 7 rubric dimensions**: an inference workload of the same
order as the agent's, issued against the same account seconds after the agent spent
$3.70 on it. A single workflow can burn ~6 minutes purely sleeping.

PLAN.md 4.6.1 budgets agent inference and then declares third-party rate limits
solved by the zero-credential rule. **The grader's own model calls were never in
that budget.** At 7,000 tasks × 8 trials the grading inference is a first-order
cost and capacity dependency in its own right, not a rounding error.

Three remedies, in increasing order of correctness:

1. Sleep between the agent and verifier phases so quota recovers — cheap, slow.
2. **Give grading its own credential.** 3.4 lists `ANTHROPIC_API_KEY` once, serving
   both the agent and the browser grader; they must be distinct accounts.
3. Use an API-tier key for grading rather than an OAuth subscription — subscription
   quotas are far tighter than API limits.

pytest substeps need no model access, so the substantive app diagnostics survive a
rate-limited grader. Only the browser and rubric halves degrade.

### The 429 was largely self-inflicted

The account was not out of quota. The bridge log classifies every one of them:

```
upstream error: status=429 kind=transient_throttle retry_after=None
transient transient_throttle, sleeping 1s (attempt 1/3)
```

`transient_throttle`, not `subscription_cap`. No `Retry-After` header. And the
traffic was mostly succeeding: **336 responses were 200, only 36 were 429.**

The cause was two retry layers multiplying. The bridge retries upstream 3 times
(1s, 2s, 4s) and the grader retried 6 times on top, so a single substep could issue
`4 × 6 = 24` upstream requests — each one refreshing the very throttle it was
waiting on:

```
upstream 429s observed : 325
client-visible 429s    : 36
measured amplification : 9.0x
```

Fixed on both layers, in the right places:

- The **bridge** now absorbs the throttle, because it is closest to upstream and is
  the layer that classifies the error kind: `KAIJU_CC_MAX_INLINE_RETRIES=8`,
  `KAIJU_CC_MAX_INLINE_WAIT=90` (2→90s ladder instead of 1→4s).
- The **grader** stops multiplying: `RETRY_ATTEMPTS` 6 → 2 with a patient 45s base,
  since the bridge only surfaces a 429 after exhausting its own ladder.
- A **circuit breaker** trips after one exhausted ladder, so the remaining substeps
  fail fast instead of each burning the full ~6 minutes. 20 substeps × 6 min of
  sleeping was turning a foregone zero into a two-hour run.

Worst case upstream calls per substep: 24 → 18, and far fewer in practice.

### Multi-account failover does not solve this

The bridge supports an account pool (`KAIJU_CC_ACCOUNT_POOL`, colon-separated file
paths / `keychain:<service>` / `default`), but rotation only triggers on a hard cap:

```python
if classified.kind == ErrorKind.SUBSCRIPTION_CAP:
    provider.mark_account_exhausted(token_used, reset_at)
```

`TRANSIENT_THROTTLE` is retried in place and never fails over, so a second account
sits idle while the first is throttled. A pool is worth configuring for long sweeps
that hit the real 5-hour cap — set `KAIJU_CC_POOL_STATE_PATH` too, or a bridge
restart wipes the cap timers and immediately re-hammers a capped account — but it
is not a remedy for this throttle.

### Absorbing a throttle is not free: the timeout mismatch

Deepening the bridge ladder removed the client-visible 429s completely — 432
upstream throttles, **zero returned to the grader** — but every rubric dimension
then failed with `ReadTimeout`, and the browser substeps timed out at ~360s each.

The arithmetic explains it:

```
bridge worst-case sleep : 306s   (ladder 2,4,8,16,32,64,90,90)
grader HTTP timeout     : 120s (run_workflows) / 180s (run_rubric)
deployed                : 1.0   <- the app WAS reachable
```

The bridge absorbs a throttle by *sleeping*, and it was sleeping longer than the
grader was willing to wait. That converts an absorbed throttle into a client
timeout — the same zero with a different error string, and it looks exactly like
"the app is down" unless you check `deployed`, which was `1.0` throughout.

Any client of an absorbing proxy must have a timeout greater than the proxy's
worst-case absorb time. Both graders now use `LLM_TIMEOUT_SEC = 420`.

### OpenHands needs two fixes before it runs at all

PLAN.md 3.8 pins OpenHands as the agent and 4.6 pins the reference model. Neither
works out of the box.

**1. Harbor's adapter targets an entrypoint current OpenHands no longer has.**

```
ModuleNotFoundError: No module named 'openhands.core'
```

The adapter invokes `/opt/openhands-venv/bin/python -m openhands.core.main`, but an
unpinned `uv pip install openhands-ai` resolves to 1.x, which restructured that
module away. Pin the 0.x line: `--ak version=0.62.0`.

**2. OpenHands sends sampling parameters Anthropic rejects.**

```
opus-4-8: `temperature` is deprecated for this model
opus-4-5: `temperature` and `top_p` cannot both be specified
```

OpenHands 0.62 always sends both, so it died at step 4 on its very first call —
`CodeActAgent RUNNING -> ERROR` — on both Opus models. This is an agent/provider
incompatibility, not a model quirk, and it blocks the exact pairing the plan pins.

Fixed at the bridge, which is the single choke point every agent goes through, as a
sibling to the existing `inject_system_prefix` body transform:

```python
def drop_conflicting_sampling_params(body):
    if "temperature" in body and "top_p" in body:
        body.pop("top_p")
    return body
```

Not configurable — sending both is always an upstream error, so there is no case
where forwarding it unchanged is correct. The transform now runs on every
`v1/messages` POST rather than only when prefix injection is enabled.

With both fixes OpenHands ran a full trajectory: **267 steps, $14.55, 121,479
output tokens, `deployed: 1.0`**, ATIF-v1.5 schema, clean trial.

### OpenHands vs Claude Code, same task

| | claude-code / sonnet-4-5 | openhands / opus-4-5 |
|---|---|---|
| steps | 101 | **267** |
| cost | $3.39 | **$14.55** |
| output tokens | ~50K | **121,479** |
| deployed | 1.0 | 1.0 |
| substeps passed | 1/32 | 1/32 |

OpenHands took 2.6x the steps and 4.3x the cost to reach an identical score. Both
deployed a running app; both failed the same 31 substeps. Harness cost varies far
more by agent scaffold than the resulting capability measurement does — relevant to
4.6.1, which budgets a single per-trial cost.

## Fixes applied — the fairness pass

The user's requirement: *"if its agent written code then its no issues but there should be no environment issues as i want the fair evaluation and every point"* — an agent that writes bad code should lose points, but the environment must never cost it one.

The sections below document every defect found, why it made evaluation unfair, and what was done about it.

---

### A. Environment defects — tasks that were literally unpassable

#### A1. PocketBase collections were superadmin-only

`environment/pocketbase-init.sh` created the `habits` and `completions` collections with no API rules. In PocketBase 0.22 a null rule means superadmin-only access. Every read and write from the agent's user-authenticated app returned HTTP 403, which the app surfaced as 500. The agent could not work around this: `BACKEND_ADMIN_KEY` is deliberately withheld from the agent phase (PLAN.md 3.4), so there was no path to set rules at runtime.

Fixed with owner-scoped rules. The `cross_user_access_forbidden` workflow is preserved — the rules restrict each user to their own records, they do not open the collections to everyone.

```
RED  (null rules)  : user CREATE -> 403 "Only admins can perform this action."
GREEN (owner rules): user CREATE own  -> 200 record created
                     user LIST own    -> totalItems=1
                     spoof other user -> 400 Failed to create record
                     anonymous LIST   -> totalItems=0
```

Two version traps confirmed against the 0.22.21 source: the collection JSON key is `schema` (not `fields`, which is 0.23+), and admin auth is `/api/admins/auth-with-password` (not `/api/collections/_superusers/...`).

#### A2. Missing `description` field

The `habits` collection was missing the `description` field that `instruction.md` requires. The agent was told to build against a schema that did not exist in the environment.

#### A3/A4/A5. Three of five tasks had no `docker-compose.yaml`

`event-rsvp-confirmations` (postgres + mailpit), `team-expense-approval` (postgres + keycloak), and `creator-subscription-billing` (postgres + minio + deku-pay) all declared slots in `task.toml` but had no `environment/docker-compose.yaml`. The sidecars never started. The agent was handed env vars pointing at services that did not exist.

Two additional problems in this group:

- `team-expense-approval`'s `instruction.md` promised a "pre-provisioned" Keycloak realm that nothing provisioned. The agent could not provision it either — `AUTH_ADMIN_TOKEN` is verifier-only. The fix imports a real realm at boot.
- `creator-subscription-billing` told the agent to read deku-pay API docs at `/opt/deku-pay/` that were never written, and `deku-pay` did not exist anywhere in the repo. A working deku-pay service now exists, with its README and OpenAPI spec copied into the agent image.

All three tasks now have real compose files with working sidecars.

`seat-allocation-map` was the only clean task and served as the reference pattern — an unprivileged `deku_app` role for the agent versus a superuser `deku_admin` role for the verifier.

#### A6. Bare `${VAR}` with no fallback

Every service env var in those three tasks was written as `${VAR}` with no `:-` default. When Harbor does not inject a variable the agent receives an empty string rather than a service hostname. All env vars now have `:-` fallbacks pointing at the compose service names.

---

### B. Grader fairness — infrastructure failure billed to the agent

The contract: `score.py` treats a browser substep as UNGRADED (excluded from the ratio, added to `invalid`) if and only if the substep carries an `"error"` key. Without that key, a zero counts as a genuine app failure.

Eleven code paths violated this. Each one could produce a zero that looked like the agent's fault:

| location | what it was |
|---|---|
| `run_substep` generic exception handler | bare exception, no `error` key |
| `run_workflow` generic exception handler | same |
| workflow-crash fallback path | wrote `passed: false`, no `error` key |
| step-cap exhaustion | substeps past the cap marked failed, not ungraded |
| "no tool call from model" | grader gave up, wrote failure |
| initial-navigation failure | page never loaded, substep failed rather than errored |
| `score.py` out-of-range browser index | silently returned `False` |
| deploy-gate early exit | wrote no `workflows.json` at all |
| missing CTRF report | all 12 pytest substeps scored as failures |
| `score.py` crash | left the zero-preamble stub as the final reward |
| `capabilities.py` bare `AssertionError` | raised when a sidecar was down, no error tag |

Each now carries an explicit `error` key or `invalid` marker.

Real-world evidence: in one trial the browser grader graded ZERO of 20 substeps. Workflow 1 burned 308s on rate limiting and tripped a circuit breaker; workflows 2–8 then "failed" in 0.1–0.2s each without ever opening a browser. All 20 were reported as app failures.

---

### C. Defect #17 — the healthcheck that lost the trial

The most severe find, and it affected all six tasks. Harbor runs `[environment.healthcheck]` inside `_prepare()` before the agent phase:

```
_prepare():
    _setup_agent_environment()
    run_healthcheck()        <- agent has not run yet
    _setup_agent()
```

Every task probed `curl -fsS http://localhost:4173/` — the app the agent has not built yet. It can never pass. Harbor cancels the trial: the run is lost entirely rather than scored zero. Earlier runs only survived because local scratch copies happened to strip the healthcheck.

Healthchecks now probe sidecars (`pg_isready`, PocketBase `/api/health`). The smoke task has none because it has no sidecars.

---

### D. The `main` service contract

Harbor merges the task's `docker-compose.yaml` last, so any key set on the `main` service overrides Harbor's own agent container. `image:` and `command:` replace the built agent and its entrypoint; `profiles:` makes compose skip the service entirely so the agent never starts.

Three separate authors introduced this while trying to make `docker compose up` validate standalone. Proven empirically: in a two-service compose, only the non-profiled service started.

All five `main` blocks are now ports-only.

---

### E. Artifacts — the agent's codebase is now captured

`[[artifacts]] source = "/app", destination = "app"` added to every task. Harbor's `ArtifactHandler.download_artifacts()` copies `/app` out of the main container after the agent phase and before the verifier, so it survives verifier failure. Previously `artifacts/` held only an empty convention directory.

Confirmed working in a real run: `artifacts/app/` contained the source.

---

### F. Validator — eleven new mechanical checks (C1–C11)

The recurrence guarantee. Each check was proven with a negative control — a deliberately broken copy that makes it fire.

| check | what it catches |
|---|---|
| C1 | sidecars must exist for every declared slot |
| C2 | grader credentials and `APP_PUBLIC_URL` must be in `[verifier].env` |
| C3 | PocketBase rules must not be null or empty |
| C4 | no bare `${VAR}` without a `:-` fallback in the agent env |
| C5 | `tests/conftest.py` must exist |
| C6 | `solution/solve.sh` must not be an empty skeleton |
| C7 | browser substeps need a `do` field |
| C8 | unknown substep `kind` must fail loudly |
| C9 | `[[artifacts]]` must capture `/app` |
| C10 | a healthcheck must not probe the app; required only when sidecars are declared |
| C11 | the `main` service must not set `image`, `command`, `entrypoint`, or `profiles` |

---

### G. The smoke task

`tasks/smoke-tip-calculator/` — no sidecars, a tiny stdlib HTTP app, 6 workflows (4 browser + 4 pytest substeps), and a real `solution/app/` so Harbor's oracle gate can finally run. The other five tasks all have an empty `solution/app/`, which is exactly why the oracle gate had never run and why every defect in sections A through D shipped undetected.

What its first oracle run proved: `artifacts/app/` captured the source, 4/4 pytest workflows passed, and the fairness marking worked in production:

```
INVALID RUN (browser_substeps_ungraded, grader_unavailable, workflow_timeout):
the app was not fully observed; reward forced to 0.0 and
must not be read as an agent failure
workflows=4/6  critical_failed=0  ungraded_browser=4
```

The browser and rubric graders remain blocked by account-level `transient_throttle` rate limiting — 144 × 429 in one run, only 5 POSTs through, while a probe 30s later returned 3/3 OK. This is an inference-capacity constraint, not a harness defect. A full reward 1.0 oracle score has not yet been demonstrated.

---

### Score ledger

Every zero so far has had a distinct, identified cause, and each was eliminated:

| # | reward | cause of the zero |
|---|---|---|
| 1–6 | 0.0 | verifier never ran — agent env destroyed before it started |
| 7 | 0.0 | trial **lost** to `ValidationError` on a non-numeric reward key |
| 8 | 0.0 | agent ran its own PocketBase instead of the sidecar |
| 9 | 0.0 | `habits` 404 — agent structurally forbidden to create collections |
| 10 | 0.0 | bridge stalled mid-stream at step 31 (`KAIJU_CC_BUFFER_AND_RETRY` off) |
| 11 | 0.0 | graders had no `ANTHROPIC_API_KEY` |
| 12 | 0.0 | graders rate-limited (429, no backoff) |
| 13 | 0.0 | 9x retry amplification — two ladders multiplying to 24 upstream calls/substep |
| 14 | 0.0 | bridge absorbed throttles by sleeping 306s past a 120s client timeout |

Underneath all of it one *genuine* app failure is now visible and correctly
scored: the seeded user has no habits in PocketBase, so every data-dependent
workflow fails. That is a real measurement, not a harness artifact.

---

## Why reward was 0 — and it was not the model

The agent built the app, bound `0.0.0.0:4173`, self-tested with 4 curl probes,
created the PocketBase superuser itself, and reported accurately:

> "The application is now running at `http://localhost:4173`"

Then, **after** the success message:

```
1. result            subtype=success       ← model finished
2. background_tasks_changed
3. task_updated      status=killed         ← server killed AFTER
4. task_notification status=stopped
```

It had started the server as `npm run preview &` — a shell background job inside
the Claude Code session. Session ends → process tree dies → the verifier, running
in a *separate container*, gets `app never became reachable at http://main:4173`.

Root cause was the **App Contract**, which said what to serve and never said the
server must survive the agent phase. Told "serve the app on 4173" in an interactive
session, backgrounding it is the correct move — the model had no way to know
grading happens after its session is destroyed.

Fixed in all five `instruction.md` files:

```
- The server must outlive your session. Grading runs in a separate container
  *after* your session ends. Start the server fully detached, for example
  `setsid nohup <command> > /tmp/app.log 2>&1 < /dev/null &` ...
- Bind to 0.0.0.0, never 127.0.0.1 or localhost ...
- Before you finish, verify persistence yourself ...
```

**Unverified.** It needs a re-run to confirm.

### A second hole, found by auditing that same trajectory

The agent seeded `demo@ethara.ai` / `demo123456`. The verifier expected
`demo@ethara.ai` / `demopassword`. Login fails → every substep fails → reward 0 on
a complete app.

Root cause: `instruction.md` said the password was *"provided via the environment
(see USER_README.md)"* — and no such variable was ever set. `SEED_USER_PASSWORD`
appeared in no `task.toml`. The agent had nothing to go on and invented one.

It was corpus-wide: **16 credential fixtures across 5 tasks, every default
invented, zero instruction.md files pinning a literal.** Several defaults
(`"admin"`, `"guest"`, `"creator"`) would also have failed ordinary password-minimum
validation, including PocketBase's 8-character rule.

Fixed by pinning one fixture password, `deku-demo-pw-2026`, stated in every
`instruction.md` seed section and matched by every verifier default. A validator
check now enforces the agreement in both directions — every email and every
password the verifier uses must appear in the spec:

```
[FAIL] streak-habit-tracker
       - verifier expects seeded password 'demopassword', which instruction.md
         never pins - the agent cannot guess it
```

Nothing else in the pipeline could have caught this: the task validated, the image
built, the agent succeeded, and the trial still scored zero.

---

## The seventh hole: six identical scores that were never measurements

Six consecutive trials — different models, different trajectories, different apps —
produced **bit-identical** reward blocks:

```
17:37  18:24  20:43  21:09  22:37  00:04     all:
reward 0.0 | workflows 0/11 | substeps 1/32
browser 0/20 | pytest 1/12 | critical_failed 10
browser_graded 1 | deployed 1.0 | judge_score 0.0
```

Six independent agents cannot produce the same score. That is a constant, not a
measurement.

The browser executor's own timings gave it away:

```
workflow 1  -> 0/3 passed (309.2s)
workflow 2  -> 0/3 passed (0.2s)
workflow 3  -> 0/3 passed (0.1s)
...
workflow 8  -> 0/1 passed (0.1s)
```

Workflow 1 hit `HTTP 429`, slept 45 s, retried once, exhausted the ladder, and set
the module-global `_RATE_LIMITED`. Workflows 2–8 then raised instantly. **17 of 20
browser substeps were never attempted** — each scored zero in a tenth of a second.
The rubric judge, importing the same client, inherited the tripped breaker and
returned `0.0` on all seven dimensions with `429` quoted in every rationale.

The breaker itself is right: re-running a 90-second ladder for every remaining
substep converts one lost minute into hours of sleeping for the same answer. The
bug was that it **reported its own unavailability as the app's failure**. A verifier
that cannot reach its grader has not graded anything, and must not emit a number
that looks like it did.

`deployed: 1.0` throughout — the apps built and served. The one passing test was
`test_unauthenticated_requests_denied`, which also passes against an empty app.

### What changed

| # | fault | fix |
|---|---|---|
| 1 | 13 numeric keys in `reward.json`; Harbor promoted every one to a reward stream, `judge_score` included | `reward.json` is one key; diagnostics moved to `workflows.json` |
| 2 | Rate-limit exhaustion recorded as `passed: false`, indistinguishable from a broken app | typed `GraderUnavailable` → substep carries `error`, loads as ungraded, run marked `invalid` |
| 3 | Ungraded substeps dropped from *both* sides of the ratio, so a workflow still scored on its `pytest` substeps alone | any ungraded browser substep forces `reward 0.0` + `invalid` |
| 4 | Grading began in the same second the agent stopped, on the same drained account | `DEKU_GRADER_COOLDOWN_SEC` (default 60) before the first grader call |
| 5 | `/app/USER_README.md` — a file `instruction.md` **orders the agent to write** — spliced verbatim into the grader's system prompt | whitelist `key: value` credential lines only, cap 40 |
| 6 | `--timeout-sec` parsed, never used; no per-workflow bound | wired as a real deadline; substeps past it are ungraded, not failed |
| 7 | `pytest` collection failure wrote no CTRF, so every substep failed and the reward looked like an honest zero | `test.sh` checks the report is non-empty and says so |
| 8 | A typo in a substep's `kind` hit `SystemExit`, stranding `test.sh`'s zero preamble as the final reward | fails that substep, keeps scoring, flags the run |

Verified end to end:

```
$ .venv/bin/python harness/eval/test_run_workflows.py
[1/4] parse: all 12 workflows have the expected browser substep counts and order
[2/4] round-trip: score.load_browser returns matching per-workflow lengths, all True
[3/4] shell round-trip: lengths align, every substep ungraded (None), not failed
[4/4] rate-limited run: grader_error propagates, substeps ungraded
OK

A. clean all-pass          reward.json ['reward'] {'reward': 1.0}   invalid []
B. grader rate-limited     reward.json ['reward'] {'reward': 0.0}   invalid ['browser_substeps_ungraded', 'grader_unavailable']
C. browser never launched  reward.json ['reward'] {'reward': 0.0}   invalid ['browser_substeps_ungraded', 'browser_unavailable']
```

B and C previously scored on the surviving `pytest` substeps and published the
result as an ordinary reward.

**Every reward in `jobs/` from `2026-08-03__17-37` onward is invalid** and must not
be read as an agent score. They predate the `invalid` flag, so they carry no marker
— identify them by `browser_substeps_passed: 0` alongside `browser_graded: 1`.

---

## Known gaps

1. **`solution/app/` is empty in all five tasks.** No reference app means
   `harbor run -a oracle` cannot return `1.0`, which is the hard admission gate
   (2.2 step 2). Each `solve.sh` fails loudly rather than half-deploying.
2. **Only `streak-habit-tracker` has a compose file.** The other four declare slots
   (postgres, mailpit, keycloak, deku-pay, minio) with no sidecars behind them.
3. **`deku-pay` does not exist.** 3.3.1 specifies it; nothing implements it.
4. **Neither grader has run against a live app.** Both are contract- and
   unit-verified only.
5. **The grader shares a rate-limit pool with the agent it grades.** The cooldown
   and the `invalid` flag below make the collision visible and non-corrupting, but
   they do not remove it. A separate grader credential is the real fix.
6. **8 GB Docker on this host.** One task declares 8192 MB agent + 4096 MB verifier
   plus sidecars; concurrency above 1 is not viable locally.

## Third-party traps found the hard way

- `python:3.12-slim` is Debian trixie, where `playwright install --with-deps` falls
  back to an Ubuntu package list and dies on missing `ttf-ubuntu-font-family`. The
  vendor image `mcr.microsoft.com/playwright/python:v1.49.1-noble` ships the
  **browsers** at `/ms-playwright` but **not** the Python package.
- PocketBase: the image entrypoint already supplies `serve`, so passing it again
  makes it read `serve` as a hostname and bind `https://serve` with auto-TLS. Its
  `POCKETBASE_ADMIN_*` env vars do **not** create the account, and `admin create`
  requires `migrate up` first. Tokens are minted at runtime and expire, so
  `BACKEND_ADMIN_KEY` holds `email:password` and the adapter exchanges it.
- Harbor prompts interactively about env vars; pipe `yes |` for unattended runs.
