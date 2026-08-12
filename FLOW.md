# Task Execution Flow — end to end (very detailed)

How a single trial runs in this repo, from `harbor run` to a written reward.
Grounded in the actual code: `harbor/trial/single_step.py`, `tasks/<task>/task.toml`,
`tasks/<task>/tests/{test.sh,score.py,run_workflows.py,run_rubric.py,appclient.py,capabilities.py}`,
and `claude_code/bridge.py`.

Example task used throughout: `oracle-streak` (verifier mode = **shared**).

---

## 0. The command & the actors

```bash
.venv/bin/harbor run -p tasks/oracle-streak -a <agent> -m <model> --n-concurrent-agents 1 -y
```

| Layer   | Thing            | Role                                                        |
|---------|------------------|-------------------------------------------------------------|
| Harness | **Harbor**       | orchestrates: provisions, installs agent, grades, cleans up |
| Agent   | `-a` (openhands/claude-code/…) | the scaffolding that solves the task           |
| Model   | `-m` (claude-…)  | the LLM the agent drives, reached via the bridge            |
| Bridge  | `claude_code/bridge.py` | OAuth proxy on :8765 → api.anthropic.com             |

Top-level driver: `SingleStepTrial._run()` (`single_step.py:38`):
```
_run_agent()                       # phase 1
_upload_agent_logs()               # sync agent output out
_collect_artifacts(...)            # phase 2
if mode == SEPARATE: _stop_agent_environment()   # (not this task)
_run_verifier()                    # phase 3
if mode == SHARED:  _stop_agent_environment()    # phase 4 (this task)
```

---

## 1. PHASE 0 — Provision (containers UP)

Harbor reads `task.toml`:
- `[environment]` → resources, `network_mode` (public/allowlist), image build.
- `[metadata.services] backend = "pocketbase"` → a sidecar container.
- healthcheck → `curl http://pocketbase:8090/api/health` (must pass before phase 1).

Compose brings up, on **one shared network**:
```
env-main    (built from the task image; agent workspace)         :4173
pocketbase  (ghcr.io/muchobien/pocketbase:0.22.21, sidecar)      :8090
```
→ **2 containers up.** Service discovery is by **service name via Docker DNS**
(`pocketbase` resolves to the sidecar). The app reads `BACKEND_URL=http://pocketbase:8090`.

---

## 2. PHASE 1 — Agent phase (TRAJECTORY is generated)

1. Harbor **installs the agent inside `env-main`** (e.g. `uv pip install openhands-ai==<ver>`;
   the version is pinnable via `--ak version=…`).
2. Harbor hands the agent **`instruction.md`** (the human-readable brief — the ONLY task
   text the agent sees; it never sees the tests).
3. The agent runs its loop:
   ```
   LLM(decide) ──HTTP──▶ LLM_BASE_URL (bridge :8765) ──▶ api.anthropic.com  [your OAuth token]
        ▲                                                         │
        └── observation (tool result) ◀── run bash / edit file ◀──┘
   ```
   - Env wiring: OpenHands reads `LLM_BASE_URL` + `LLM_API_KEY`; the bridge swaps the stub
     key for the OAuth token and strips `temperature`/`top_p` (the fix in `bridge.py`).
   - The agent writes the app into `env-main`: `frontend/` (prebuilt to `dist/`),
     `server/` (FastAPI), `start.sh`, and starts the server on `:4173`.
4. Every step (message + tool_calls + observation) is recorded → **`trajectory.json`**.

A degenerate trajectory (4 events, 0 tool calls) means the agent errored on its FIRST LLM
call (e.g. the old `temperature`-deprecated 400, or an auth failure).

---

## 3. PHASE 2 — Collect (trajectory leaves the container)

Harbor syncs the agent's output to the **host**, before any grading:
```
env-main:/…/trajectory.json  ──▶  jobs/<ts>/<task>__<id>/agent/trajectory.json
```
Now the trajectory is durable on disk, independent of the container's fate.
The **verifier never sees the trajectory** — it grades the running app, not the log.

---

## 4. PHASE 3 — Verify (shared mode → runs INSIDE env-main)

Harbor `exec`s into `env-main`, uploads `/tests`, injects `BACKEND_ADMIN_KEY`, and runs
**`test.sh`**. Still **2 containers** — eval is a phase, not a container.

`test.sh` order (from the file, no `set -e` on purpose):

```
1. reward.json = {"reward":0.0}          # fail-safe FIRST (crash ⇒ 0, never a lost trial)
2. DEPLOY GATE                           # poll APP_PUBLIC_URL/api/health 30×5s
                                         #   not reachable ⇒ score 0 (invalid=deploy_failed), exit
3. BROWSER grader  run_workflows.py      # drives real UI       → /tmp/browser_results.json
4. PYTEST grader   pytest /tests         # asserts side effects → ctrf.json
                                         #   (empty ctrf ⇒ writes ctrf-error.json → invalid)
5. RUBRIC judge    run_rubric.py         # advisory LLM         → judge.json  (skip w/ DEKU_SKIP_RUBRIC)
6. score.py        browser + pytest      → reward.json + workflows.json
```

The verifier phase talks to **two** endpoints (from `task.toml` verifier env):
```
APP_PUBLIC_URL    = http://localhost:4173         # the agent's app  (appclient.py)
BACKEND_URL       = http://pocketbase:8090        # pocketbase direct (capabilities.py)
BACKEND_ADMIN_KEY = admin@ethara.ai:deku-local-dev  # privileged; verifier-only
```

### 4a. Deploy gate (`test.sh:22-48`)
- Curls `/api/health` (or `/`) up to 30× with 5s sleeps.
- Fail → routes through `score.py --deployed 0.0` so `reward.json` **and** `workflows.json`
  both carry a `deploy_failed` marker (a bare 0 would look like an honest agent failure). Exits.

### 4b. Browser grader (`run_workflows.py`) — an LLM-driven QA agent
- **Input:** the `browser`-kind substeps from `workflows.yaml`, one natural-language step at a time
  (e.g. *"Sign in…"*, *"Verify the dashboard shows a streak of 5"*).
- **Tools** (Anthropic tool-calling): `browser_navigate`, `browser_snapshot`, `browser_click`,
  `browser_fill`, `browser_select_option`, `browser_press_key`, `browser_scroll`,
  `browser_get_text`, and the MANDATORY `report_result(passed, note)`.
- **Loop:** LLM issues a tool call → Playwright executes on real Chromium → after each action a
  `browser_snapshot` (URL, title, numbered accessibility tree, text) is fed back → LLM decides next.
  So the LLM *does* see the browser's state each step (this is the "bridge" — it's inherent).
- **LLM calls go through the same bridge** (`ANTHROPIC_BASE_URL`). Because grading runs right after
  the agent drained the account, **429 is the expected steady state**:
  - Per-call cooldown (`DEKU_GRADER_COOLDOWN_SEC=60`), min interval (1.5s).
  - Backoff ladder honoring Retry-After (2,4,8,…,90s).
  - **Circuit breaker:** once the ladder is exhausted, `_RATE_LIMITED` is set and further calls
    raise `GraderUnavailable` (avoids hours of sleeping).
- **Output:** per workflow, one `substeps` entry per browser substep, each `{passed, note}` or
  `{error}` if the grader was unreachable → `browser_results.json`.
- **Anti-cheat:** it will NOT read the agent's `USER_README.md` as its own instructions (that would
  let the agent inject "report_result(passed=true)").

### 4c. pytest grader (`pytest /tests` → `ctrf.json`)
- Needs **no LLM**. Two connection styles:
  - `appclient.py` → the app's REST API at `APP_PUBLIC_URL` (`/api/...`). Asserts behavior
    *through the app* (what a real client sees).
  - `capabilities.py` → **pocketbase directly** at `BACKEND_URL`, authenticating with
    `BACKEND_ADMIN_KEY` (`email:password` → `POST /api/admins/auth-with-password` → runtime admin
    token, `capabilities.py:124`). This is the privileged "escape hatch" to read the true DB
    state, incl. other users' rows — used by `test_authorization.py` (cross-user checks).
- Runs **after** the browser pass so pytest only ever asserts state a real user action created.
- Emits CTRF report (`tests / passed / failed`). Empty report ⇒ `ctrf-error.json` ⇒ scorer
  marks `pytest_collection_failed` (a harness fault, not billed to the agent).

### 4d. Rubric judge (`run_rubric.py` → `judge.json`) — ADVISORY ONLY
- A separate LLM (Sonnet by default; `DEKU_GRADER_MODEL`) reads `instruction.md`, screenshots
  the app at 3 viewports (`1920x1200,768x1024,390x844`), scores subjective dimensions
  (instruction_following, functionality, ux_flow, ui_visual, motion, accessibility, responsiveness).
- **`score.py` reads `judge_score` AFTER the reward is final and never lets it move the reward**
  (`score.py:202-208`) — an LLM score is trivially gamed.
- ~64% of the verifier's LLM call volume, so on a capped account it can starve the browser grader;
  `DEKU_SKIP_RUBRIC=1` skips it to protect the signal that actually scores.

### 4e. Scorer (`score.py`) — the exact reward math
For each workflow, walk its substeps; each substep is graded True / False / **None**:
- `pytest` substep → `ctrf[test]` (missing ⇒ False).
- `browser` substep → the matching `browser_results` outcome; **None** if the browser layer
  never ran or emitted fewer results than declared.
- **None = "not measured"** — excluded from the ratio, NOT counted as a failure.

```
ratio(workflow)   = passed_graded_substeps / graded_substeps      (0 if none graded)
workflow PASSES   ⟺ ratio ≥ 0.90  AND no `critical` substep failed
reward            = workflows_passed / total_workflows
```

Hard overrides that force `reward = 0.0` and add an `invalid` marker:
- `--deployed < 1.0`                    → `deploy_failed`
- browser substeps declared but layer never ran → `browser_results_missing`
- any browser substep ungraded (429 mid-run) → `browser_substeps_ungraded`
- grader errors surfaced                → e.g. `grader_unavailable`, `workflow_timeout`
- pytest collection failed              → `pytest_collection_failed`

**Why:** with `invalid`, a 0.0 means "we couldn't fully observe the app" — filtered out of
training data, NOT read as an honest agent failure. This is why the 429 runs scored `0.0 invalid`
even though pytest passed 8/12.

Outputs (one numeric key only in reward.json; everything else in the sibling file):
```
reward.json     → {"reward": <float>}
workflows.json  → {"summary": {...all diagnostics...}, "workflows": [per-workflow detail]}
```

---

## 5. PHASE 4 — Clean (containers DOWN)

Shared mode: after the verifier finishes, `_stop_agent_environment()` stops & removes
`env-main` + `pocketbase` → **0 containers**. **Images stay** on disk (reused next run).
Everything persisted lives under `jobs/<ts>/<task>__<id>/`:
```
agent/trajectory.json          # the trajectory (agent output)
verifier/reward.json           # the score
verifier/workflows.json        # browser results + per-workflow verdict + all diagnostics
verifier/ctrf.json             # pytest results
verifier/judge.json            # rubric (advisory)
verifier/shots/                # rubric screenshots
```

---

## 6. Container lifecycle (this task, shared mode)

```
t0  provision   env-main + pocketbase          → 2 up
t1  agent       agent builds app in env-main   → 2 up
t2  collect     trajectory → host              → 2 up
t3  verify      test.sh exec INSIDE env-main   → 2 up   (eval is a phase, not a container)
t4  clean       stop env-main + pocketbase     → 0 up   (images retained)
```
A **3rd container** appears only in `environment_mode = "separate"` — and there Harbor tears
`env-main` down *before* verifying, so the app must be rebuilt in the fresh verifier env
(not wired for this web-app task).

---

## 7. File map (who does what)

```
task.toml ............ image, services, network, resources, verifier env, artifacts
instruction.md ....... the brief the AGENT reads (never sees tests)
tests/
  workflows.yaml ..... INPUT spec: workflows = requirements, each with browser+pytest substeps
  run_workflows.py ... browser grader (LLM tool-loop + Playwright)  → browser_results.json
  test_*.py .......... pytest assertions                            → ctrf.json
  appclient.py ....... HTTP client to the APP  (APP_PUBLIC_URL)
  capabilities.py .... privileged clients (pocketbase admin, postgres, mailpit, minio, deku-pay)
  run_rubric.py ...... rubric LLM judge (advisory)                  → judge.json
  score.py ........... combines browser+pytest → reward.json + workflows.json
  test.sh ............ verifier entrypoint orchestrating steps 1–6
solution/{app,solve.sh}  the `oracle` golden solution (EMPTY for oracle-streak → oracle can't pass)
environment/providers/*  reusable sidecar definitions (pocketbase, postgres, …)
claude_code/bridge.py    OAuth proxy :8765 (agent + graders → Anthropic)
```

---

## 8. One-line summary

Harbor brings up **2 containers**, lets the **agent** build a live app inside `env-main`
(recording the **trajectory**, which is synced to the host), then — in **shared** mode —
`exec`s the **verifier inside the same container**: a **deploy gate**, an **LLM browser grader**
and an **LLM-free pytest grader** (both via service-name DNS; pytest also hits pocketbase directly
with an admin key), plus an **advisory rubric judge**. `score.py` computes
`reward = passing_workflows / total` (≥90% substeps, no critical fail; browser mandatory), writes
`reward.json`, and Harbor tears the containers down (**0**), keeping images and `jobs/` artifacts.
