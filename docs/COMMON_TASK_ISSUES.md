# Common task issues

Every task authored so far has arrived with the same handful of defects. None are
carelessness — they are properties of how a task package travels. This page is the
checklist for making a new task runnable, and the reasoning behind each item.

> **You will learn**
>
> - The four defects every new task arrives with
> - Why each one is invisible until it costs a run
> - The one-shot fix, in the order it has to happen
> - Which validator complaints are safe to ignore

---

## The state of the corpus

Measured 2026-08-12:

| task | network | init script | test.sh | tests |
|---|---|---|---|---|
| `E_finan_appr_payroll-journal-approval` | public | n/a (`.sql`) | yes | 1 file |
| `athlete-merch-drop` | **allowlist** | **not executable** | yes | 6 files |
| `chess-match-lobby` | public | ok | yes | 4 files |

Ten further directories under `tasks/` have no `task.toml` and an empty `tests/`.
They are shells, not tasks — see [Missing tasks](#missing-tasks).

---

## 1. The seed script is not executable

The single most expensive defect in this project's history.

Postgres **executes** files in `/docker-entrypoint-initdb.d`. A non-executable one
fails:

```
/docker-entrypoint-initdb.d/10-app-role.sh: /bin/sh: bad interpreter: Permission denied
```

…and **the entrypoint does not stop**. The database reports healthy, having skipped
its seed. Every app then connecting as `deku_app` gets:

```
28P01  password authentication failed for user "deku_app"
```

> **Pitfall: the error names the wrong thing**
>
> Postgres returns `28P01` identically for a wrong password and for a role that
> does not exist — deliberately, so the error cannot be used to enumerate users.
>
> So the symptom reads as *"the app got its credentials wrong"* while the cause is
> a file mode in this repo. One full run was lost to it, and an earlier diagnosis
> — *"the app deploys without creating its schema"* — was wrong for the same
> reason: the app could not log in to create anything.

**Fix**

```bash
chmod +x tasks/<task>/environment/*-init.sh
```

**Better fix — design it out.** `payroll-journal-approval` ships
`postgres-init.sql` instead of `.sh`. Postgres runs `.sql` through `psql`, which
needs no executable bit, so the failure mode cannot occur. Prefer `.sql` for new
tasks.

`validate_task.py` check **C14** now fails any task whose `*-init.sh` is not
executable. It has caught this on three consecutive new tasks.

---

## 2. The grader files are stale copies

Each task carries its own copy of the shared grader, because Harbor uploads only
`tests/` when **Harbor** grades.

```
harness/verifier/   →  test.sh  score.py  appclient.py  capabilities.py  _shapes.py  pytest.ini
harness/eval/       →  run_workflows.py  run_rubric.py  grader_compress.py
```

A task authored before a grader fix keeps the old version indefinitely, and
nothing warns you.

> **Pitfall: a wrong score, not an error**
>
> `appclient.py` hardcoded `access_token`. One brief — the only one of nine —
> specifies `{token, user:{…}}`. All 26 pytest checks errored at fixture setup on
> an app whose login worked, and the run published:
>
> ```json
> { "reward": 0.0, "invalid": [] }
> ```
>
> `invalid: []` asserts the measurement was sound. It was not. Re-grading the same
> trial after the fix produced **0.7333**.

**Fix**

```bash
bin/deku-py harness/sync_verifier.py tasks/<task>/
```

**Why it can no longer decide a score.** `eval_fresh.py` assembles `/tests` itself
and overlays all ten shared files straight from `harness/` *after* copying the
task's `tests/`. Whatever the task holds, the container runs the current version:

```
[3/6] copying /app and /tests ...
      overlaid 10 shared grader file(s) from harness/
```

The copies still matter for Harbor's own verifier path, so keep them in sync — but
a stale copy can no longer produce a wrong number.

---

## 3. `network_mode = "allowlist"`

`allowlist` is the **correct** setting. Docker Desktop's LinuxKit kernel lacks
`CONFIG_NFT_FIB_INET`, so Harbor cannot enforce it and refuses the task:

```
ValueError: network_mode='allowlist' is not supported by EnvironmentType.DOCKER
```

This aborts during `Trial.create()` — before the environment is built and before
the agent starts.

**Fix (local development only)**

```toml
# LOCAL-DEV SETTING -- revert to "allowlist" before admission.
network_mode  = "public"
# allowed_hosts = [ ... ]     <- comment out TOGETHER with the mode
```

> **Pitfall: the two lines must move together**
>
> Harbor rejects `allowed_hosts` alongside `network_mode = "public"`, and it
> rejects it by returning `False` from `Task.is_valid_dir()`. The CLI then
> silently reclassifies the directory as a **dataset** and fails with the
> unrelated *"Either datasets or tasks must be provided."*

`validate_task.py` fails every task on `public`. That is not a bug — it is the
reminder to revert before admission.

---

## 4. Slots not surfaced to the verifier

A task declares which backing services it needs:

```toml
[metadata.services]
backend = "postgres"
```

The grader also needs to know, and the only channel into the grader container is
`[verifier].env`:

```toml
[verifier]
env = { DEKU_SERVICE_BACKEND = "postgres", ... }
```

Miss it and the capability adapters cannot tell which backend they are asserting
against. Caught on `chess-match-lobby`.

---

## The one-shot fix

Order matters: generate the compose before syncing, and sync before running.

```bash
TASK=tasks/<new-task>

# 1. seed scripts must be executable
chmod +x $TASK/environment/*-init.sh 2>/dev/null

# 2. generate the compose if services are declared but no compose exists
python3 environment/compose.py --write --task $(basename $TASK)

# 3. refresh the shared grader copies
bin/deku-py harness/sync_verifier.py $TASK/

# 4. network_mode -> "public", commenting out allowed_hosts WITH it
#    and add DEKU_SERVICE_<SLOT> to [verifier].env

# 5. see what is left
bin/deku-py harness/validate_task.py $TASK
```

---

## Complaints that are safe to ignore

Three validator failures are expected on a correct task:

| Complaint | Why it is fine |
|---|---|
| `schema_version is '1.4', expected '1.3'` | the authoring kit emits `1.4`; the validator is pinned to `1.3`. Harbor reads neither — its own template uses `version = "1.0"` |
| `network_mode must not be 'public'` | the deliberate local-dev setting from §3 |
| `difficulty '' not in [...]` | an empty label; affects reporting, not runs |

> **Note**
>
> Everything else in the validator output is real. `[WARN]` lines are heuristic
> and do not set the exit code, but each one has caught a genuine defect.

---

## Two failure modes that are NOT arrival defects {/*not-arrival*/}

These appeared during grading and are worth recognising.

### Tokens that expire mid-session

`conftest` fixtures are session-scoped: they log in once and reuse the token.
Keycloak's default access-token lifespan is **300 seconds**. A pytest session that
runs 533 seconds fails every check after the five-minute mark with:

```
401 {"detail":"Invalid token: Signature has expired."}
```

26 of 38 checks failed this way on an app that was working. **Fix:** pin
`accessTokenLifespan` in `keycloak-realm.json` to something that outlives a
grading session (3600), or refresh tokens per test.

### Checks that assert on consumed seed data

The browser pass runs **before** pytest, by design, so data checks only ever see
state a real user action created. A check that asserts the seed is *untouched*
therefore fails precisely when the browser grader succeeds:

```
browser: "Release that hold and watch free stock return to 18"   PASSED
pytest : "PLT-1001 carries no 'held' reservation"                FAILED
```

Both cannot hold. No application satisfies them. `validate_task.py` now emits a
`[WARN]` for this, matching entity names between `workflows.yaml` and the tests.

---

## Missing tasks {/*missing-tasks*/}

Ten directories under `tasks/` have no `task.toml` and an empty `tests/`. They
were deleted when `tasks/` was added to `.gitignore` and git dropped the tracked
files.

They are recoverable from the commit before that change:

```bash
git ls-tree -r --name-only e589cfcb -- tasks/     # inspect first
```

Restore selectively — a blanket `git checkout` also reverts later edits to the
briefs that survived.

---

## Recap

- **Four defects arrive with every task**: exec bit, stale graders, `allowlist`, unsurfaced slots
- The exec-bit failure is silent and blames the app — prefer `postgres-init.sql`
- Stale graders no longer decide a score, because `eval_fresh` overlays from `harness/`
- `network_mode` and `allowed_hosts` must always change **together**
- Three validator complaints are expected and safe; everything else is real
- When a run fails, assume the harness or the task before the agent — so far it has been every time
