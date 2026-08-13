# Task input defects

What arrives broken in a task package, why it is invisible until it costs a run,
and what to do about it.

Every defect below was found by running the corpus, not by reading it. Each cost
at least one agent run — between 15 and 35 minutes and $3–7 apiece — and in every
case the symptom pointed somewhere other than the cause.

Audited 2026-08-11 across 13 tasks.

---

## The pattern

**A task is not wrong because someone was careless.** These defects arrive with
the package, and three of the four are things the authoring kit cannot know:

| Defect | Where it comes from |
|---|---|
| `*-init.sh` not executable | git and the kit do not preserve the exec bit |
| grader files stale | they are copies, refreshed only when someone runs the sync |
| `network_mode = "allowlist"` | correct for admission, unenforceable on Docker Desktop |
| packaging text in the brief | correct before 2026-08-10, contradicts the contract after |

They share one property that makes them expensive: **the failure surfaces far
from the cause, and looks like something else.**

---

## 1. `*-init.sh` is not executable

**Status: fixed corpus-wide, and now caught before a run (validator C14).**

The database seed script creates the unprivileged role the app connects as.
Postgres's entrypoint *executes* files in `/docker-entrypoint-initdb.d`, so a
non-executable one fails:

```
/docker-entrypoint-initdb.d/10-app-role.sh: /bin/sh: bad interpreter: Permission denied
```

…and **the entrypoint does not stop.** The database reports healthy, having
skipped its seed. Every app connecting as `deku_app` then gets:

```
28P01  password authentication failed for user "deku_app"
```

Postgres returns `28P01` identically for a wrong password and a role that does
not exist — deliberately, so the error cannot be used to enumerate users. So the
symptom reads as *the app got its credentials wrong*, and the cause is a file
mode in this repo.

**Cost:** one full run on `customer-issue-queue` (35 min), and it is the real
reason `warehouse-allocation-ledger` had never produced a valid score. An earlier
diagnosis recorded in this repo — "the app deploys without creating its schema" —
was wrong: the app could not log in to create anything.

**Spread:** 3 of 7 postgres tasks at the time of discovery. A brand-new task
(`payroll-journal-approval`, authored 2026-08-11) arrived with the same defect,
confirming it is systemic rather than historical.

**Now:** `environment/compose.py` chmods `0755` explicitly instead of inheriting
the mode through `shutil.copy2`, and `validate_task.py` C14 fails any task whose
`*-init.sh` is not executable.

---

## 2. Grader files are stale copies

**Status: in sync across all 13 tasks. Nothing prevents it recurring.**

`harness/verifier/` is the source of truth for five shared files:

```
test.sh   capabilities.py   appclient.py   run_workflows.py   run_rubric.py
```

Harbor uploads a task's `tests/` directory at verification time, so each task
carries **its own copy**. A task authored before a grader fix keeps the old
version indefinitely.

**Cost:** `appclient.py` hardcoded `access_token`. One brief — the only one of
nine — specifies `{token, user:{…}}`. All 26 pytest substeps errored at fixture
setup on an app whose login worked correctly, and the run published:

```json
{ "reward": 0.0, "invalid": [] }
```

`invalid: []` asserts the measurement was sound. It was not. Re-grading the same
trial after the fix produced **0.7333**.

**Now:** the field name is read as either `access_token` or `token`, since it is
the task's contract and one shared file cannot encode one task's wording.
`validate_task.py` already reports drift; run `harness/sync_verifier.py tasks/*/`
before any new task's first run.

---

## 3. `network_mode = "allowlist"`

**Status: all 13 tasks set to `public` locally, original preserved in a comment.**

`allowlist` is the correct setting. Docker Desktop's LinuxKit kernel lacks
`CONFIG_NFT_FIB_INET`, so Harbor cannot enforce it and refuses the task rather
than pretend:

```
ValueError: network_mode='allowlist' is not supported by EnvironmentType.DOCKER
```

This aborts during `Trial.create()` — **before** the environment is built and
before the agent starts.

**Two traps around it, both already paid for:**

- The trial *directory* is created before the failure, so a pipeline that treats
  "directory exists" as "run happened" marches on. `bin/deku-run` crashed in
  `eval_fresh` with a raw `FileNotFoundError` and printed a SCORE table reading
  `(not produced)` — the real error thirty lines up. Now guarded.
- `allowed_hosts` must be commented out *together with* the mode. Harbor rejects
  the pair, and rejects it by returning `False` from `Task.is_valid_dir()`, which
  makes the CLI silently reclassify the directory as a **dataset** and fail with
  the unrelated *"Either datasets or tasks must be provided."*

**Note the tension:** `validate_task.py` fails every task on `public`. That is
not a bug — it is the reminder to revert all 13 before admission.

---

## 4. Packaging instructions in the brief

**Status: 9 of 13 briefs still carry text that contradicts the deployment contract.**

Deployment mechanics moved to `harness/prompt/deployment_contract.j2`, wrapped
around every brief at run time. Briefs authored before that still instruct the
agent to **background** the server:

```
`setsid nohup <command> > /tmp/app.log 2>&1 < /dev/null &`
```

Under a Dockerfile the container's main process **is** the server. Detaching and
exiting stops the container immediately, so this is now precisely backwards.

| Task | Mentions |
|---|---|
| `I_healthf_trac_strength-session-log` | 5 (full `start.sh` clause) |
| `calculator` | 5 (full `start.sh` clause) |
| `streak-habit-tracker` | 5 (full `start.sh` clause) |
| `creator-subscription-billing` | 1 (`setsid nohup`) |
| `event-rsvp-confirmations` | 1 |
| `oracle-streak` | 1 |
| `seat-allocation-map` | 1 |
| `smoke-tip-calculator` | 1 |
| `team-expense-approval` | 1 |

Tasks whose brief still names `start.sh` keep grading through the `start.sh` path
(`eval_fresh.py` reads the brief to decide), so their historic scores stay
comparable. They are not broken — they are inconsistent, and the agent receives
two different deployment instructions.

**Reference:** `customer-issue-queue` and `warehouse-allocation-ledger` have zero
packaging text. The first scored **0.7333**; the second produced the first valid
score in its history.

---

## 5. Checks that assert on consumed seed data

**Status: unfixed. The largest remaining defect in the corpus.**

The browser pass runs **before** pytest by design, so data tests only ever
inspect state a real user action created. Several tasks contain pytest checks
that assert the seed is *untouched* — after the browser pass has legitimately
changed it.

`warehouse-allocation-ledger`, 9 of 18 checks:

```
browser: "Release that hold and watch free stock on PLT-1001 return to 18"   PASSED
pytest : "PLT-1001 carries no 'held' reservation"                            FAILED
```

The app's seed is correct — verified in its own `seed.py`:

```python
("PLT-1001", "Oak Pallet Standard", 24, 6),
("RSV-1002", "PLT-1002", "planner2@example.com", 12),
```

These checks **can only pass when the browser grader fails.** No application can
satisfy both, so they measure nothing about the app.

| Task | Affected |
|---|---|
| `warehouse-allocation-ledger` | 9 of 18 pytest checks |
| `streak-habit-tracker` | 3 checks |
| `customer-issue-queue` | 2 workflows |

Three tasks, one cause. That makes it an authoring hazard, not a slip.

**The rule:** a check must establish its own preconditions — mark today before
testing un-mark, snapshot the count before asserting a delta — or assert only on
data no browser workflow touches.

**It is statically detectable.** The entity ids (`PLT-1001`, `RSV-1002`) appear
in both `workflows.yaml` and the test files. A validator rule flagging any pytest
substep that asserts on a seeded entity a browser workflow also names would have
caught all three before they ever ran.

---

## Preparing a new task

Every new task arrives with defects 1–3. `bundle` and
`payroll-journal-approval` each had all three.

```bash
# 1. seed scripts must be executable
chmod +x tasks/<task>/environment/*-init.sh

# 2. refresh the shared grader copies
bin/deku-py harness/sync_verifier.py tasks/<task>/

# 3. generate the compose if services are declared but no compose exists
python3 environment/compose.py --write --task <task>

# 4. network_mode -> "public", commenting out allowed_hosts WITH it

# 5. confirm what is left
bin/deku-py harness/validate_task.py tasks/<task>
```

Expect three remaining complaints on a correct task, none of them blocking:
`schema_version` (the validator is pinned to `1.3`; the kit now emits `1.4`),
`difficulty` empty, and `network_mode` `public`.

---

## What none of these were

Not one defect in this document was the agent's fault. Across the runs that
exposed them the agent built working applications every time; the harness
either could not deploy them, could not log into them, or checked them against
state something else had already changed.

That distinction is what `invalid` exists to record — and the `access_token`
case is the warning: a run published `reward: 0.0` with `invalid: []`, asserting
a measurement it had not made. The field is only as honest as the checks behind
it.
