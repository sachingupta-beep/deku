#!/usr/bin/env python3
"""Grade a finished trial by REDEPLOYING its app into a clean container.

    bin/deku-py harness/eval_fresh.py jobs/<ts>/<task>__<id>
    bin/deku-py harness/eval_fresh.py jobs/<ts>/<task>__<id> --keep   # debug

Why this exists
---------------
Under `verifier.environment_mode = "shared"` the graders run inside the very
container the agent worked in, against the process the agent left running. That
grades *the app the agent left running*, which is a weaker claim than *the app
the agent built*:

  - the running server was started by hand and never proven to survive a cold start
  - caches are warm (node_modules, __pycache__, an already-JIT'd runtime)
  - background processes the agent started are still up
  - state the agent created by hand is still in memory
  - /tests -- the answer key -- lands in the agent's own filesystem

This redeploys instead: fresh container from the same image, the collected /app
copied in, `start.sh` run from cold, then the SAME graders. An app that only
worked because of its warm container fails here, which is the point.

Harbor cannot do this itself. `environment_mode="separate"` gives a fresh
container but strips the sidecars, builds from tests/ rather than environment/,
and tears the agent env down first -- so there is no app left to grade.

Contract with the task
----------------------
None. The task brief describes the product; it says nothing about packaging.
harness/app_image.py reads the app's own manifests -- `package.json`,
`requirements.txt`, `pyproject.toml` -- and generates the Dockerfile, exactly as a
deployment platform does. An agent that ships its own `/app/Dockerfile` has that
honoured instead; a task whose spec still asks for `/app/start.sh` still works.

If none of the three is available the run is NOT scored 0. `invalid` records
which of the three cases applies -- the agent crashed, it built nothing, or the
harness does not recognise the stack -- because "we could not measure it" and
"it failed" are different claims.

Pure stdlib + the docker CLI, same as repackage.py.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HEALTH_TIMEOUT_SEC = 180
START_TIMEOUT_SEC = 600
DEFAULT_PORT = "4173"

# Caches the agent warmed. Copying these forward would defeat the purpose: a
# stale .pyc can keep an app running whose source no longer imports.
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def must(cmd: list[str], what: str) -> str:
    r = run(cmd)
    if r.returncode != 0:
        sys.exit(f"{what} failed:\n  $ {' '.join(cmd)}\n{r.stderr.strip()[:1500]}")
    return r.stdout.strip()


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------- task config
def missing_required(spec: dict, host_env: dict) -> list[str]:
    """Names declared as a bare ``${VAR}`` (no default) that the host cannot supply.

    task.toml distinguishes these deliberately: ``${VAR:-fallback}`` is optional,
    a bare ``${VAR}`` is mandatory -- Harbor itself refuses to start a run when one
    is unset. Running eval_fresh without that check spends the full image build,
    cold start and browser pass before the grader reports `ANTHROPIC_API_KEY not
    set`, which has now cost two ~20-minute runs. Fail in a second instead.
    """
    bare = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
    missing = []
    for raw in (spec or {}).values():
        if isinstance(raw, str):
            m = bare.match(raw.strip())
            if m and not host_env.get(m.group(1)):
                missing.append(m.group(1))
    return sorted(set(missing))


def resolve_env(spec: dict, host_env: dict) -> dict:
    """Expand task.toml's ``${VAR}`` / ``${VAR:-default}`` against the host env.

    Same substitution Harbor performs, reimplemented here because we are running
    the verifier ourselves rather than through Harbor's trial machinery.
    """
    out: dict[str, str] = {}
    pattern = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*))?\}$", re.S)
    for key, raw in (spec or {}).items():
        if not isinstance(raw, str):
            out[key] = str(raw)
            continue
        m = pattern.match(raw.strip())
        if m:
            var, default = m.group(1), m.group(2)
            out[key] = host_env.get(var) or (default if default is not None else "")
        else:
            out[key] = raw
    return out


def load_task(trial: Path) -> tuple[Path, dict]:
    config = json.loads((trial / "config.json").read_text())
    raw = (config.get("task") or {}).get("path") or ""
    task_dir = Path(raw)
    if not task_dir.is_absolute():
        task_dir = REPO / task_dir
    if not task_dir.exists():
        # The trial may have run from a scratch copy (/tmp/...). Fall back to the
        # task of the same name in this repo so a moved job is still gradable.
        guess = REPO / "tasks" / trial.name.split("__")[0]
        if not guess.exists():
            sys.exit(f"cannot locate the task dir for {trial.name} (tried {task_dir}, {guess})")
        log(f"note: {task_dir} is gone; using {guess.relative_to(REPO)}")
        task_dir = guess

    try:
        import tomllib
        cfg = tomllib.loads((task_dir / "task.toml").read_text())
    except Exception as exc:
        sys.exit(f"could not read {task_dir}/task.toml: {exc}")
    return task_dir, cfg


# ----------------------------------------------------------------- sidecars
# Services that exist for the AGENT phase and must not be part of grading.
#
#   main    -- Harbor's agent container. The task compose only overrides it (a
#              ports block, no image), so starting it here fails on a service
#              with nothing to run. We supply our own app container instead.
#   dockerd -- a nested Docker daemon some tasks give the agent so it can test
#              the /app/Dockerfile it was asked to write. Grading builds that
#              Dockerfile itself, on the host daemon, from source. Starting a
#              privileged daemon during grading would burn ~400MB and a
#              privileged container for something nothing in the grader uses --
#              and would let a `deploy` step in the app reach a daemon, which no
#              graded app should ever have.
AGENT_ONLY_SERVICES = {"main", "dockerd"}


def sidecar_services(compose_file: Path) -> list[str]:
    """Backing services in the task's compose, minus the agent-only helpers."""
    if not compose_file.exists():
        return []
    names, inside = [], False
    for line in compose_file.read_text().splitlines():
        if re.match(r"^services:\s*$", line):
            inside = True
            continue
        if inside and re.match(r"^\S", line):      # dedent -> left the block
            inside = False
        if inside and re.match(r"^  [A-Za-z0-9_.-]+:\s*$", line):
            names.append(line.strip().rstrip(":"))
    return [n for n in names if n not in AGENT_ONLY_SERVICES]


def sidecars_only_compose(compose_file: Path, dest: Path) -> Path:
    """Write a copy of the task compose with the agent-only blocks removed.

    Compose validates EVERY service in the file, not just the ones named on the
    command line. The task's `main` block is a partial override of Harbor's agent
    container -- a bare `ports:` with no image and no build context -- so asking
    compose to start only `pocketbase` still fails with:

        service "main" has neither an image nor a build context specified

    Harbor never hits this because it merges the task compose over its own base,
    which supplies main's image. We supply our own app container instead, so main
    is simply dropped.
    """
    drop = re.compile(r"^  (%s):\s*$" % "|".join(sorted(AGENT_ONLY_SERVICES)))
    out, skipping = [], False
    for line in compose_file.read_text().splitlines():
        if drop.match(line):
            skipping = True
            continue
        if skipping:
            # Stay in skip mode through the block's body; stop at the next service
            # key (2-space indent) or any dedent to column 0.
            if re.match(r"^  \S", line) or re.match(r"^\S", line):
                skipping = False
                if drop.match(line):     # two agent-only blocks back to back
                    skipping = True
                    continue
            else:
                continue
        out.append(line)
    dest.write_text("\n".join(out) + "\n")
    return dest


def compose_cmd(compose_file: Path, project: str, task_env_dir: Path) -> list[str]:
    # --project-directory pins relative mounts (./pocketbase-init.sh) to the
    # task's environment/ dir, so the filtered copy can live anywhere.
    return ["docker", "compose", "-p", project, "-f", str(compose_file),
            "--project-directory", str(task_env_dir)]


def start_sidecars(compose_file: Path, project: str, services: list[str],
                   task_env_dir: Path) -> None:
    """Bring the backing services up on their own project, from empty.

    A brand-new compose project means brand-new anonymous volumes, so the
    database starts EMPTY and is populated only by the task's seed script -- the
    "wipe and reseed" behaviour, achieved by never reusing the agent phase's
    services rather than by scrubbing them. Nothing the agent wrote survives
    into grading, so a row it inserted by hand cannot satisfy a workflow.
    """
    log(f"      starting {len(services)} sidecar(s) and waiting for health ...")
    cmd = compose_cmd(compose_file, project, task_env_dir)
    r = run(cmd + ["up", "-d", "--wait", *services])
    if r.returncode != 0:
        # --wait fails the command if a healthcheck never goes green; retry
        # without it so a service lacking a healthcheck is not fatal.
        r2 = run(cmd + ["up", "-d", *services])
        if r2.returncode != 0:
            sys.exit("sidecar startup failed:\n" + (r.stderr or r2.stderr)[:1500])
        log("      (started without --wait; a service declares no healthcheck)")


def stop_sidecars(compose_file: Path, project: str, task_env_dir: Path) -> None:
    """Tear down the services AND their volumes.

    `-v` matters: without it the anonymous volumes survive and the next run's
    database is not actually fresh.
    """
    run(compose_cmd(compose_file, project, task_env_dir) + ["down", "-v", "--remove-orphans"])


# ------------------------------------------------------------------ staging
def stage_app(trial: Path, staging: Path) -> Path:
    """Copy the collected /app artifact, dropping warmed caches."""
    src = trial / "artifacts" / "app"
    if not src.is_dir():
        sys.exit(f"no /app artifact at {src} -- was the trial run with artifact collection?")
    dst = staging / "app"
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(*CACHE_DIRS),
    )
    dropped = sum(1 for p in src.rglob("*") if p.is_dir() and p.name in CACHE_DIRS)
    if dropped:
        log(f"  dropped {dropped} warmed cache dir(s) — a cold container has none")
    return dst


# ---------------------------------------------------------------- the deploy
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trial", type=Path, help="jobs/<ts>/<task>__<id>")
    ap.add_argument("--keep", action="store_true",
                    help="leave the container running for inspection")
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--generate-dockerfile", action="store_true",
                    help="if the agent wrote no /app/Dockerfile, derive one from the "
                         "app's manifests (harness/app_image.py) instead of scoring "
                         "the run a deploy failure. For trials that predate the "
                         "deployment contract; off by default, because the contract "
                         "asks the agent for a Dockerfile and writing one for it "
                         "would grade an artifact the agent never produced")
    ap.add_argument("--repackage", action="store_true",
                    help="on success, publish the result to output/<task>/<model>/run_N/ "
                         "via harness/repackage.py --verifier-dir verifier_fresh")
    args = ap.parse_args()

    trial = args.trial.resolve()
    if not trial.is_dir():
        sys.exit(f"trial not found: {trial}")

    task_dir, cfg = load_task(trial)
    task = task_dir.name
    # Docker rejects any uppercase in a repository name ("repository name must be
    # lowercase"), and task codes from the authoring kit carry capitals
    # (I_healthf_trac_strength-session-log_...). Normalise both names the same way
    # so a task's own naming scheme cannot break the build.
    slug = re.sub(r"[^a-z0-9._-]", "-", task.lower()).strip("-.") or "task"
    tag = f"deku-fresh-{slug}:latest"
    cname = re.sub(r"[^a-z0-9._-]", "-", f"deku-fresh-{trial.name.lower()}").strip("-.")
    out_dir = trial / "verifier_fresh"
    out_dir.mkdir(exist_ok=True)

    log(f"task      : {task}")
    log(f"trial     : {trial.name}")
    log(f"container : {cname}")

    missing = missing_required((cfg.get("verifier") or {}).get("env") or {},
                               dict(__import__("os").environ))
    if missing:
        log("")
        log(f"MISSING REQUIRED ENV: {', '.join(missing)}")
        log("")
        log("task.toml declares these as bare ${VAR} with no default, so the grader")
        log("would start with an empty value and fail after the full build + cold")
        log("start. Export them and re-run:")
        log("")
        log('  SECRET="$(cat .bridge_secret)"')
        log("  export ANTHROPIC_API_KEY=\"$SECRET\"")
        log("  export ANTHROPIC_BASE_URL=http://host.docker.internal:8765")
        return 2

    compose_file = task_dir / "environment" / "docker-compose.yaml"
    sidecars = sidecar_services(compose_file)
    project = f"dekufresh-{re.sub(r'[^a-z0-9]', '', trial.name.lower())}"
    network = f"{project}_default"
    if sidecars:
        log(f"sidecars  : {', '.join(sidecars)}  (project {project})")

    # --- staging: exactly what a cold deploy gets --------------------------
    staging = trial / ".fresh_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    app_dir = stage_app(trial, staging)

    # --- how do we deploy this app? ---------------------------------------
    # THE AGENT PACKAGES ITS OWN APP. The deployment contract
    # (harness/prompt/deployment_contract.j2, wrapped around every brief by
    # bin/deku-run) asks for /app/Dockerfile, and that file is what gets built.
    #
    # Measured 2026-08-11 on customer-issue-queue, opus-4-8: the agent's own
    # Dockerfile scored 0.7333 -- identical to the harness-generated one on the
    # same task and model -- while being a better artifact: multi-stage, dev
    # dependencies excluded from the runtime image, correct layer ordering, and a
    # `**/node_modules` .dockerignore it worked out unprompted. Same 14-minute
    # agent phase. There was no measurable cost, so there is no reason for the
    # harness to second-guess it.
    #
    # Order:
    #   1. /app/Dockerfile           -- the contract. What is graded.
    #   2. /app/start.sh             -- tasks whose brief still asks for one, so
    #                                   their historic scores stay comparable.
    #   3. nothing                   -- scored failure; the contract was explicit.
    #
    # app_image.py is NOT used by default. It stays for --generate-dockerfile, a
    # deliberate opt-in for grading a trial that predates this contract.
    spec = (task_dir / "instruction.md")
    spec_wants_start_sh = spec.is_file() and "start.sh" in spec.read_text()

    plan = None
    dockerfile = app_dir / "Dockerfile"
    start_sh = app_dir / "start.sh"
    if dockerfile.is_file():
        deploy_mode = "dockerfile"
        log("deploy    : the agent's own /app/Dockerfile")
    elif spec_wants_start_sh and start_sh.is_file():
        deploy_mode = "start.sh"
        log("deploy    : /app/start.sh (this task's brief still requires it)")
    elif args.generate_dockerfile:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from app_image import plan_app, write_build_files, describe  # noqa: E402
        plan = plan_app(app_dir)
        if plan is not None:
            deploy_mode = "dockerfile"
            log("deploy    : Dockerfile generated by the harness (--generate-dockerfile)")
            for line in describe(plan).splitlines():
                log(f"  {line}")
        elif start_sh.is_file():
            deploy_mode = "start.sh"
            log("deploy    : /app/start.sh")
        else:
            deploy_mode = "none"
            log("deploy    : NONE -- no Dockerfile, no manifest, no start.sh")
    elif start_sh.is_file():
        deploy_mode = "start.sh"
        log("deploy    : /app/start.sh (no Dockerfile was written)")
    else:
        deploy_mode = "none"
        log("deploy    : NONE -- the agent wrote no /app/Dockerfile")

    if deploy_mode == "none":
        # WHY it is missing decides whether this is the agent's fault.
        #
        # An agent that ran to completion and never wrote start.sh ignored the
        # contract -- that is a scored failure. An agent that CRASHED partway
        # never reached the point of writing it, and billing that to the agent
        # invents a capability judgement from an infrastructure fault. Both
        # produced `no_start_script` before this check, so a 132-step OpenHands
        # 500 was indistinguishable from an agent that simply did not bother
        # (2026-08-07, both seen within an hour).
        result = json.loads((trial / "result.json").read_text()) if (
            trial / "result.json").exists() else {}
        exc = (result.get("exception_info") or {}).get("exception_type")
        exc_msg = str((result.get("exception_info") or {}).get("exception_message") or "")
        # exit 137 = SIGKILL (usually the OOM killer), 143 = SIGTERM.
        signal_hint = next((s for s in ("exit 137", "exit 143") if s in exc_msg), "")

        # result.json is NOT sufficient on its own. OpenHands' wrapper exits 0 even
        # when its own agent controller dies -- on 2026-08-07 an internal 500
        # ("name 'unicode' is not defined", a Python 2 builtin in its error path)
        # drove AgentState.RUNNING -> ERROR at 132 steps, and Harbor still recorded
        # `exception_info: null` and "Exceptions: 0". At Harbor's level a crashed
        # agent and a finished one look identical, so ask the agent's own log too.
        if not exc:
            for log_name in ("openhands.txt", "claude-code.txt"):
                log_path = trial / "agent" / log_name
                if log_path.exists():
                    try:
                        tail = log_path.read_text(errors="replace")[-200000:]
                    except OSError:
                        continue
                    if "AgentState.ERROR" in tail:
                        exc = "AgentStateError"
                        exc_msg = next(
                            (ln.strip() for ln in reversed(tail.splitlines())
                             if "Error" in ln or "Exception" in ln), ""
                        )[:200]
                        break

        # Did the agent build anything at all? The two answers point in opposite
        # directions and must not share a reason code.
        # MISSING.txt is Harbor's placeholder for an artifact it could not collect.
        # Counting it as "the agent built something" turns a collection failure into
        # `harness_could_not_identify_stack`, which points the reader at app_image.py
        # for a problem that happened two stages earlier.
        reserved = {".browser_screenshots", ".downloads", "USER_README.md",
                    "MISSING.txt"}
        built = [p for p in app_dir.rglob("*")
                 if p.is_file() and p.relative_to(app_dir).parts[0] not in reserved]

        if exc:
            reason = ["agent_crashed_before_finishing"]
            note = (f"the agent phase ended in {exc}"
                    f"{' (' + signal_hint + ')' if signal_hint else ''}, so it never "
                    f"reached a deployable state. Not scored as an agent failure -- "
                    f"the run did not complete.")
            log(f"\nFLAGGED: nothing to deploy, and the agent phase ended in {exc}.")
            log("         Treating this as an incomplete run, not an agent failure.")
        elif built and args.generate_dockerfile:
            # --generate-dockerfile was asked for and app_image.py still could not
            # identify the stack. That is OUR limitation, and scoring it 0 would
            # publish a capability judgement the harness never earned the right to
            # make.
            reason = ["harness_could_not_identify_stack"]
            note = (f"the agent left {len(built)} file(s) under /app but no manifest "
                    f"harness/app_image.py recognises (package.json, requirements.txt, "
                    f"pyproject.toml) and no start.sh. This is a harness gap, not an "
                    f"agent failure -- extend app_image.py rather than reading this "
                    f"as a score.")
            log(f"\nFLAGGED: {len(built)} file(s) under /app, but no recognised manifest.")
            log("         Recorded as a HARNESS gap, not scored against the agent.")
            log("         Extend harness/app_image.py to cover this stack.")
        elif built:
            # The app exists but was not packaged. `invalid` stays EMPTY: the
            # deployment contract asks for /app/Dockerfile in plain terms and the
            # agent had a daemon to test it with, so this is a scored failure to
            # meet the contract, not a measurement the harness failed to take.
            reason = []
            note = (f"the agent left {len(built)} file(s) under /app but no "
                    f"/app/Dockerfile, which the deployment contract requires, and no "
                    f"/app/start.sh. There is nothing to build. Re-grade an older "
                    f"trial with --generate-dockerfile if it predates this contract.")
            log(f"\nFAIL: {len(built)} file(s) under /app, but no /app/Dockerfile.")
            log("      The deployment contract requires one. Scored as an agent failure.")
            log("      (For a trial predating the contract: --generate-dockerfile)")
        else:
            reason = ["no_app_built"]
            note = ("the agent phase completed but left nothing under /app beyond the "
                    "reserved directories. There is no application to deploy.")
            log("\nFAIL: the agent completed but built nothing under /app.")

        (out_dir / "reward.json").write_text(json.dumps({"reward": 0.0}, indent=2) + "\n")
        (out_dir / "workflows.json").write_text(json.dumps(
            {"summary": {"reward": 0.0, "invalid": reason, "note": note}},
            indent=2) + "\n")
        shutil.rmtree(staging, ignore_errors=True)
        return 1

    # --- image -------------------------------------------------------------
    log(f"\n[1/6] building a clean image from {task_dir.name}/environment ...")
    must(["docker", "build", "-q", "-t", tag, str(task_dir / "environment")],
         "image build")

    if plan is not None:
        # Base the app image on the task's OWN environment image. It already
        # carries the runtimes the task declares -- node, python, build tools --
        # so nothing about the stack has to be guessed, and it is the same
        # baseline the agent worked against.
        #
        # Written into the STAGING copy. trial/artifacts/app is evidence and is
        # never modified.
        write_build_files(app_dir, plan, base_image=tag, port=args.port)
        shutil.copy2(app_dir / "Dockerfile", out_dir / "generated.Dockerfile")
        (out_dir / "generated.plan.txt").write_text(describe(plan) + "\n")
        log("      generated Dockerfile + .dockerignore "
            "(copies in verifier_fresh/generated.*)")

    # --- container ---------------------------------------------------------
    run(["docker", "rm", "-f", cname])
    verifier_env = resolve_env((cfg.get("verifier") or {}).get("env") or {},
                               dict(__import__("os").environ))
    agent_env = resolve_env((cfg.get("environment") or {}).get("env") or {},
                            dict(__import__("os").environ))
    env_flags: list[str] = []
    for k, v in {**agent_env, **verifier_env}.items():
        env_flags += ["-e", f"{k}={v}"]
    env_flags += ["-e", f"APP_PUBLIC_PORT={args.port}"]

    app_cname = f"{cname}-app"
    app_tag = f"deku-fresh-app-{slug}:latest"
    if deploy_mode == "dockerfile":
        # The app is a SEPARATE container, so it is not on the grader's localhost.
        # Both sit on one user-defined network, where Docker's embedded DNS
        # resolves container names -- the default bridge does not, which is why a
        # network is created below even when the task declares no sidecars.
        app_url = f"http://{app_cname}:{args.port}"
    else:
        # The verifier is INSIDE this container, so the app is on its own localhost.
        app_url = f"http://localhost:{args.port}"
    env_flags += ["-e", f"APP_PUBLIC_URL={app_url}"]

    log(f"[2/6] starting a fresh container ...")
    net_flags: list[str] = []
    owned_network = ""
    if sidecars:
        filtered = sidecars_only_compose(compose_file, staging / "sidecars.yaml")
        start_sidecars(filtered, project, sidecars, compose_file.parent)
        # Same network as the services, so the app resolves them by name exactly
        # as it did during the agent phase (BACKEND_URL=http://pocketbase:8090).
        net_flags = ["--network", network]
    elif deploy_mode == "dockerfile":
        owned_network = f"{project}_net"
        run(["docker", "network", "rm", owned_network])
        must(["docker", "network", "create", owned_network], "network create")
        net_flags = ["--network", owned_network]
    must(["docker", "run", "-d", "--name", cname,
          *net_flags,
          "--add-host", "host.docker.internal:host-gateway",
          *env_flags, tag, "sleep", "infinity"], "container start")

    try:
        # --- copy the app + the graders in ---------------------------------
        log("[3/6] copying /app (built by the agent) and /tests (the answer key) ...")
        must(["docker", "exec", cname, "mkdir", "-p", "/app", "/tests",
              "/logs/verifier"], "mkdir")
        must(["docker", "cp", f"{app_dir}/.", f"{cname}:/app"], "copy app")
        must(["docker", "cp", f"{task_dir / 'tests'}/.", f"{cname}:/tests"], "copy tests")
        run(["docker", "exec", cname, "chmod", "-R", "+x", "/tests"])
        run(["docker", "exec", cname, "chmod", "+x", "/app/start.sh"])

        # --- cold start ----------------------------------------------------
        if deploy_mode == "dockerfile":
            log("[4/6] building /app/Dockerfile and running it as its own container ...")
            # --no-cache and --pull for the same reason the container is fresh: a
            # layer cached from an earlier grading run is carried-over state, and
            # it can hide the failure we are here to detect. A `RUN npm ci` that
            # succeeded last week replays from cache today even if the registry is
            # unreachable or the lockfile now resolves differently, and the run
            # would score as though the build worked. --pull does the same for the
            # base image, so a stale local `node:20` cannot stand in for the one
            # the Dockerfile actually names.
            #
            # Cost is a full dependency install per grading. That is the honest
            # price of the claim "this builds from source, today, on a machine
            # that has never seen it".
            # --pull ONLY for an agent-written Dockerfile, whose FROM names a
            # public image that could be stale locally. A generated Dockerfile is
            # based on the task environment image built moments ago in [1/6] and
            # existing nowhere else, so --pull sends docker to the registry for a
            # repository that does not exist:
            #   pull access denied, repository does not exist ... insufficient_scope
            pull = [] if plan is not None else ["--pull"]
            b = subprocess.run(
                ["docker", "build", "--no-cache", *pull, "-t", app_tag, str(app_dir)],
                capture_output=True, text=True, timeout=START_TIMEOUT_SEC,
            )
            (out_dir / "app_build.log").write_text(
                f"exit={b.returncode}\n\n--- stdout ---\n{b.stdout}\n--- stderr ---\n{b.stderr}\n"
            )
            log(f"      docker build exit={b.returncode} (log: verifier_fresh/app_build.log)")
            if b.returncode != 0:
                # A build failure is the agent's -- the Dockerfile is theirs, and it
                # is the artifact the contract asks for. Scored 0 with `deployed`
                # 0.0, NOT invalidated: the harness observed exactly what it set
                # out to observe.
                tail = (b.stderr or b.stdout or "").strip().splitlines()[-15:]
                log("\nFAIL: /app/Dockerfile does not build.")
                for line in tail:
                    log(f"      {line}")
                (out_dir / "reward.json").write_text(
                    json.dumps({"reward": 0.0}, indent=2) + "\n")
                (out_dir / "workflows.json").write_text(json.dumps(
                    {"summary": {"reward": 0.0, "invalid": [], "deployed": 0.0,
                                 "note": "the agent's /app/Dockerfile failed to build in a "
                                         "clean context; see verifier_fresh/app_build.log"}},
                    indent=2) + "\n")
                return 1

            run(["docker", "rm", "-f", app_cname])
            must(["docker", "run", "-d", "--name", app_cname,
                  *net_flags,
                  "--add-host", "host.docker.internal:host-gateway",
                  *env_flags, app_tag], "app container start")
            log(f"      app container {app_cname} started from {app_tag}")
        else:
            log("[4/6] running /app/start.sh from cold ...")
            r = subprocess.run(
                ["docker", "exec", "-w", "/app", cname, "bash", "/app/start.sh"],
                capture_output=True, text=True, timeout=START_TIMEOUT_SEC,
            )
            (out_dir / "start_sh.log").write_text(
                f"exit={r.returncode}\n\n--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}\n"
            )
            log(f"      start.sh exit={r.returncode} (log: verifier_fresh/start_sh.log)")

        # --- health gate ---------------------------------------------------
        # Probed from INSIDE the grader container against the same APP_PUBLIC_URL
        # the graders will use, so the gate cannot pass on a URL the graders
        # cannot reach (in dockerfile mode those are different machines).
        log(f"[5/6] waiting for the app at {app_url} ...")
        deadline = time.time() + HEALTH_TIMEOUT_SEC
        healthy = False
        while time.time() < deadline:
            # Gate on /api/health returning 200, not on "something answered".
            # The old `|| curl /` fallback passed an app that was returning 503 on
            # /api/health for the whole wait while its static frontend served fine
            # (2026-08-07) -- 45 substeps were then graded against an app that had
            # told us it was not ready.
            probe = run(["docker", "exec", cname, "sh", "-c",
                         f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 "
                         f"{app_url}/api/health"])
            health_code = (probe.stdout or "").strip()
            if health_code == "200":
                healthy = True
                break
            # Only a genuinely absent endpoint (404) justifies falling back to `/`.
            # A 5xx is the app reporting its own failure.
            if health_code == "404":
                alt = run(["docker", "exec", cname, "sh", "-c",
                           f"curl -fsS --max-time 5 {app_url}/"])
                if alt.returncode == 0:
                    log("      no /api/health (404); accepted GET / instead")
                    healthy = True
                    break
            time.sleep(3)

        if not healthy:
            log(f"\nFAIL: the app never became healthy in a clean container.")
            log(f"      /api/health last returned: {health_code or 'no response'}")
            if deploy_mode == "dockerfile":
                # The app is in its own container, so its stdout is NOT in
                # start_sh.log and is lost the moment the container is removed.
                lg = run(["docker", "logs", "--tail", "200", app_cname])
                (out_dir / "app_container.log").write_text(
                    f"--- stdout ---\n{lg.stdout}\n--- stderr ---\n{lg.stderr}\n")
                log("      app container output: verifier_fresh/app_container.log")
                for line in (lg.stderr or lg.stdout or "").strip().splitlines()[-10:]:
                    log(f"      {line}")
            if health_code and health_code.startswith("5"):
                log("      That is the app reporting its OWN failure -- it started but")
                log("      could not reach something it needs (commonly the database).")
            (out_dir / "reward.json").write_text(json.dumps({"reward": 0.0}, indent=2) + "\n")
            (out_dir / "workflows.json").write_text(json.dumps(
                {"summary": {"reward": 0.0, "invalid": [],
                             "deployed": 0.0,
                             "note": "start.sh did not bring the app up from cold; "
                                     "this is a scored agent failure, not a harness fault"}},
                indent=2) + "\n")
            return 1
        log("      app is up")

        if deploy_mode == "dockerfile":
            # The browser grader reads its credentials from /app/USER_README.md in
            # ITS OWN container (run_workflows.py DEFAULT_CREDENTIALS_PATH), and the
            # app now runs somewhere else. Apps write that file at boot -- this
            # task's does, from the same seed routine that creates the accounts --
            # so the grader would be reading the agent's pre-run copy while the
            # live database was seeded from the app's post-boot one.
            #
            # Here the spec pins the passwords, so the two agree and nothing breaks.
            # An app that minted credentials at startup would be unloggable-into
            # with no indication why. Under start.sh both were literally the same
            # file; carrying it across restores that.
            probe = run(["docker", "exec", app_cname, "cat", "/app/USER_README.md"])
            if probe.returncode == 0 and probe.stdout.strip():
                staged = (app_dir / "USER_README.md")
                before = staged.read_text() if staged.is_file() else ""
                if probe.stdout != before:
                    log("      note: the app rewrote USER_README.md at boot; "
                        "using the live version for grading")
                    (out_dir / "USER_README.boot.md").write_text(probe.stdout)
                tmp = staging / "USER_README.live.md"
                tmp.write_text(probe.stdout)
                # Deliberately NOT must(): the staged copy is a working fallback,
                # and aborting a completed deploy over a file sync would throw away
                # a gradable run to fix a problem that may not exist.
                cp = run(["docker", "cp", str(tmp), f"{cname}:/app/USER_README.md"])
                if cp.returncode != 0:
                    log("      warn: could not sync USER_README.md from the app "
                        "container; grading with the agent's staged copy")

        # --- grade ---------------------------------------------------------
        log("[6/6] running the graders (deploy gate -> browser -> pytest -> score) ...")
        r = subprocess.run(["docker", "exec", "-w", "/app", cname, "bash", "/tests/test.sh"],
                           text=True)
        run(["docker", "cp", f"{cname}:/logs/verifier/.", str(out_dir)])
        if deploy_mode == "dockerfile":
            # Kept on success as well: an app that serves /api/health but errors on
            # every real request leaves its only explanation here.
            lg = run(["docker", "logs", "--tail", "500", app_cname])
            (out_dir / "app_container.log").write_text(
                f"--- stdout ---\n{lg.stdout}\n--- stderr ---\n{lg.stderr}\n")

        reward_path = out_dir / "reward.json"
        if reward_path.exists():
            reward = json.loads(reward_path.read_text()).get("reward")
            log(f"\nFRESH-CONTAINER REWARD: {reward}")
            old = trial / "verifier" / "reward.json"
            if old.exists():
                log(f"shared-container reward: {json.loads(old.read_text()).get('reward')}")
                log("(a gap between them is how much the old score leaned on the warm container)")
        else:
            log("\nno reward.json produced -- see verifier_fresh/ for logs")
        log(f"\nresults: {out_dir.relative_to(REPO)}")

        if args.repackage:
            # Publish the FRESH grading, not Harbor's in-place one. Both sets live
            # under the same trial, so passing the wrong dir here would silently
            # republish the shared-container score under a fresh-eval banner.
            log("\npublishing to output/ ...")
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from repackage import repackage as _repackage  # noqa: E402
            dest = _repackage(trial, verifier_dir="verifier_fresh")
            log(f"  -> {dest.relative_to(REPO)}  (manifest.graded_by = verifier_fresh)")
        return 0

    finally:
        if args.keep:
            log(f"\n--keep: container left running. Inspect with:\n"
                f"  docker exec -it {cname} bash\n"
                f"  docker rm -f {cname}   # when done")
            if deploy_mode == "dockerfile":
                log(f"  docker logs -f {app_cname}   # the app itself\n"
                    f"  docker rm -f {app_cname}")
            if sidecars:
                log(f"  docker compose -p {project} down -v   # and the sidecars")
        else:
            run(["docker", "rm", "-f", cname])
            if deploy_mode == "dockerfile":
                run(["docker", "rm", "-f", app_cname])
            if sidecars:
                stop_sidecars(staging / "sidecars.yaml", project, compose_file.parent)
            if owned_network:
                run(["docker", "network", "rm", owned_network])
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
