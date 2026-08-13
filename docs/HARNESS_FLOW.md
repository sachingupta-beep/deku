# The Deku harness, end to end

Deku measures whether an AI agent can build a working web application from a
written brief. This page traces one run from input to published score.

> **You will learn**
>
> - What a task package contains and who owns each file
> - The three phases of a run, and why grading uses a fresh container
> - The three grading signals and what each one can prove
> - Exactly how the reward is calculated
> - The mechanism that separates "the app failed" from "we never looked"

---

## The problem this solves

An agent that builds an app can always make it *look* finished. It can start a
server by hand, insert rows directly, or return a status badge the UI draws for
itself.

The harness answers a stricter question:

> Can a stranger open this app in a browser, complete a real task, and does the
> underlying data actually change?

Everything below exists to make that answerable without trusting either the agent
or the app.

---

## Input: the task package

A task is a directory:

```
tasks/<task>/
  task.toml                 config: services, timeouts, env, artifacts
  instruction.md            the brief — describes the PRODUCT, nothing else
  environment/
    Dockerfile              the agent's runtime image
    docker-compose.yaml     backing services (Postgres, Keycloak, Mailpit, …)
    postgres-init.sql       seeds the unprivileged role the app connects as
  tests/
    workflows.yaml          the user journeys, and which check proves each step
    conftest.py             fixtures + the seeded constants
    test_<task>.py          the assertions
    rubric.json             design criteria for the advisory judge
```

### Ownership

| Owned by the task | Owned by the harness |
|---|---|
| `instruction.md`, `workflows.yaml`, `conftest.py`, `test_*.py`, `rubric.json` | `test.sh`, `score.py`, `appclient.py`, `capabilities.py`, `run_workflows.py`, `run_rubric.py` |

The harness files are **overlaid into the container at grading time** from
`harness/verifier/` and `harness/eval/`. A task cannot grade with an outdated
copy, because its own copy never executes.

---

## Phase 1: the agent builds the app

```bash
bin/deku-run tasks/<task> -m <model>
```

Harbor starts the backing services, builds the agent image, and runs the agent
inside it with the brief as its prompt.

**The agent never sees the answer key.** The run passes
`--disable-verification`, so `tests/` is never uploaded into the agent's
container at all.

### The deployment contract

Briefs describe the product. How the app is packaged and deployed is identical
across every task, so it lives in one file and is wrapped around each brief at
run time:

```
harness/prompt/deployment_contract.j2
```

It asks the agent for `/app/Dockerfile`, states that grading rebuilds from source
into a clean container with an empty database, and tells the agent where it can
test its image.

> **Note**
>
> Keeping packaging out of the briefs means a change to the deployment rules is
> one edit, not one per task — and a brief stays a description of the product.

---

## Phase 2: grading in a clean container

Grading does **not** run in the agent's container.

```
[1/6]  build a clean image from the task's environment/
[2/6]  start fresh backing services — new volumes, empty DB, re-seeded
[3/6]  copy in /app (the agent's source) and /tests (the answer key)
       overlay the current grader from harness/
[4/6]  docker build /app/Dockerfile  →  run it as its own container
[5/6]  wait for GET /api/health to return 200
[6/6]  run the graders
```

### Why a fresh container

Grading in the agent's own container measures **the process it left running**,
not **the app it built**. Those differ:

```
warm caches            a stale .pyc can keep an app running whose source no longer imports
hand-started servers   never proven to survive a cold start
rows created by hand   a workflow satisfied without the feature existing
```

A brand-new compose project means brand-new volumes, so the database starts empty
and is populated only by the task's seed script. Nothing the agent wrote by hand
survives into grading.

The app image is built with `--no-cache`: a layer cached from an earlier grading
run is carried-over state, and can hide the very failure the fresh container
exists to detect.

### Three containers, one network

```
APP        the agent's Dockerfile, built from source
GRADER     Chromium + pytest; reaches the app over the network
SERVICES   Postgres / Keycloak / Mailpit — fresh, re-seeded
```

The app and the grader are separate machines. The grader reaches the app at
`http://<app-container>:4173` — the same way a real user's browser would, rather
than sharing a filesystem with it.

---

## The three grading signals

| Signal | Question | Mechanism |
|---|---|---|
| **Deploy gate** | Does it run at all? | HTTP probe against `/api/health` |
| **Browser** | *Can a person do this?* | An LLM drives real Chromium — signs in, clicks, reads the screen |
| **pytest** | *Did it actually happen?* | Queries the database **directly**, bypassing the app |
| **Rubric judge** | Is it well made? | LLM scores screenshots against the task's criteria — **advisory only** |

### The deploy gate is absolute

The gate polls `GET /api/health` and requires `200`. A `404` falls back to `GET /`
— the only case where the endpoint genuinely may not exist. A `5xx` is the app
reporting its own failure and is never read as deployed.

A failed deploy is a hard zero with no partial credit.

### Why pytest is hard to fake

The tests open the database with an admin credential the agent never holds and
count the rows themselves. The app has no say in it.

That is what makes this answerable:

> Did clicking "Approve" write the row — or did the UI just draw a badge?

### Why the browser runs first

pytest runs **after** the browser, so data assertions only ever inspect state a
real user action created.

### Why the judge doesn't count

`judge_score` is recorded and never contributes to the reward. It is an LLM's
opinion of screenshots, which is trivially gamed. Aesthetic judgement is
diagnostics, not score.

---

## How the reward is calculated

Two steps. **No weights.**

**Step 1 — each workflow passes or fails:**

```
ratio = passing_substeps / total_substeps  ≥  0.90
AND    no substep marked `critical` failed
```

**Step 2 — the reward is the fraction of workflows that passed:**

```
reward = passing_workflows / total_workflows
```

### Why 0.90 rather than 1.00

A workflow may carry a substep that is genuinely unobservable in a given
environment. The 10% slack absorbs that without letting a broken journey through:
at 10 substeps exactly one may fail; at 3, none can.

### Why `critical` exists on top of the ratio

In a 10-substep journey, "the money actually moved" failing gives 9/10 = 0.90 —
a pass under the ratio alone. Marking it `critical` makes it a veto rather than a
weight.

---

## The integrity mechanism

`reward.json` carries exactly one key: the reward itself.

Harbor promotes every top-level key to a reward stream, so diagnostics live in
`workflows.json` instead — and this is the field that decides whether the number
means anything:

```
invalid: []       every declared check was really observed
invalid: [...]    the harness could not measure — discard the run
```

> **This is the most important guarantee in the system.**
>
> `reward: 0.0` with a populated `invalid` is **not a failing app**. It is a
> failed measurement, and the run is excluded rather than recorded.

Cases that produce `invalid` rather than a score:

```
the agent crashed before finishing
the grader could not reach its LLM
the browser pass hit its step cap without a verdict
the app never became healthy
```

### Where the honesty is enforced

- A pytest failure is a **score**; the script keeps going. Only a dead app aborts.
- `test.sh` writes `reward 0.0` **before** anything else, so a crash still leaves
  an interpretable result rather than no file at all.
- A missing `/app/Dockerfile` is checked against the agent's own log: if the agent
  crashed, the run is flagged incomplete rather than billed to the agent.

---

## Output

```
output/<task>/<model>/run_N/
  reward.json          the score, one key
  workflows.json       per-workflow verdicts, deployed, invalid
  manifest.json        provenance
  app/                 the source the agent wrote — evidence, never modified
  logs/
    browser_results.json   per-substep verdicts AND why each failed
    pytest_ctrf.json       per-test results
    judge.json             the weighted rubric (advisory)
    app_build.log          the image build
    app_container.log      the app's own output
  screenshots/         what the browser grader saw
  trajectory/          every step the agent took
  services/            which service images this run was graded against
```

The manifest carries provenance: the task and model, the reward, `deployed`,
`invalid`, `graded_by`, a task checksum, the agent version and cost, and the
duration of each stage.

`task_checksum` pins which version of the task produced the score. `graded_by`
records that it came from the clean-container path rather than in-place grading.
