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
The agent must leave an executable `/app/start.sh` that brings the app up from a
cold filesystem (see the Deployment Contract in instruction.md). Without it there
is nothing to redeploy, and the run scores 0 with `invalid: ["no_start_script"]`
-- a task fault surfaced honestly, not silently billed to the agent.

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
def sidecar_services(compose_file: Path) -> list[str]:
    """Service names in the task's compose, EXCLUDING `main`.

    `main` is Harbor's agent container, and the task's compose only overrides it
    (a ports block, no image). We bring up the real backing services and supply
    our own app container in main's place, so starting `main` here would fail on
    a service with nothing to run.
    """
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
    return [n for n in names if n != "main"]


def sidecars_only_compose(compose_file: Path, dest: Path) -> Path:
    """Write a copy of the task compose with the `main` block removed.

    Compose validates EVERY service in the file, not just the ones named on the
    command line. The task's `main` block is a partial override of Harbor's agent
    container -- a bare `ports:` with no image and no build context -- so asking
    compose to start only `pocketbase` still fails with:

        service "main" has neither an image nor a build context specified

    Harbor never hits this because it merges the task compose over its own base,
    which supplies main's image. We supply our own app container instead, so main
    is simply dropped.
    """
    out, skipping = [], False
    for line in compose_file.read_text().splitlines():
        if re.match(r"^  main:\s*$", line):
            skipping = True
            continue
        if skipping:
            # Stay in skip mode through main's body; stop at the next service
            # key (2-space indent) or any dedent to column 0.
            if re.match(r"^  \S", line) or re.match(r"^\S", line):
                skipping = False
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
    ap.add_argument("--repackage", action="store_true",
                    help="on success, publish the result to output/<task>/<model>/run_N/ "
                         "via harness/repackage.py --verifier-dir verifier_fresh")
    args = ap.parse_args()

    trial = args.trial.resolve()
    if not trial.is_dir():
        sys.exit(f"trial not found: {trial}")

    task_dir, cfg = load_task(trial)
    task = task_dir.name
    tag = f"deku-fresh-{task}:latest"
    cname = f"deku-fresh-{trial.name.lower()}"
    out_dir = trial / "verifier_fresh"
    out_dir.mkdir(exist_ok=True)

    log(f"task      : {task}")
    log(f"trial     : {trial.name}")
    log(f"container : {cname}")

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

    start_sh = app_dir / "start.sh"
    if not start_sh.is_file():
        log("\nFAIL: the agent left no /app/start.sh, so the app cannot be redeployed.")
        (out_dir / "reward.json").write_text(json.dumps({"reward": 0.0}, indent=2) + "\n")
        (out_dir / "workflows.json").write_text(json.dumps(
            {"summary": {"reward": 0.0, "invalid": ["no_start_script"],
                         "note": "fresh-container eval requires /app/start.sh "
                                 "(see the Deployment Contract in instruction.md)"}},
            indent=2) + "\n")
        shutil.rmtree(staging, ignore_errors=True)
        return 1

    # --- image -------------------------------------------------------------
    log(f"\n[1/6] building a clean image from {task_dir.name}/environment ...")
    must(["docker", "build", "-q", "-t", tag, str(task_dir / "environment")],
         "image build")

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
    # The verifier is INSIDE this container, so the app is on its own localhost.
    env_flags += ["-e", f"APP_PUBLIC_URL=http://localhost:{args.port}"]

    log(f"[2/6] starting a fresh container ...")
    net_flags: list[str] = []
    if sidecars:
        filtered = sidecars_only_compose(compose_file, staging / "sidecars.yaml")
        start_sidecars(filtered, project, sidecars, compose_file.parent)
        # Same network as the services, so the app resolves them by name exactly
        # as it did during the agent phase (BACKEND_URL=http://pocketbase:8090).
        net_flags = ["--network", network]
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
        log(f"[5/6] waiting for the app on localhost:{args.port} ...")
        deadline = time.time() + HEALTH_TIMEOUT_SEC
        healthy = False
        while time.time() < deadline:
            probe = run(["docker", "exec", cname, "sh", "-c",
                         f"curl -fsS --max-time 5 http://localhost:{args.port}/api/health "
                         f"|| curl -fsS --max-time 5 http://localhost:{args.port}/"])
            if probe.returncode == 0:
                healthy = True
                break
            time.sleep(3)

        if not healthy:
            log("\nFAIL: the app never came up in a clean container.")
            log("      The agent's app worked only in its own warm container.")
            (out_dir / "reward.json").write_text(json.dumps({"reward": 0.0}, indent=2) + "\n")
            (out_dir / "workflows.json").write_text(json.dumps(
                {"summary": {"reward": 0.0, "invalid": [],
                             "deployed": 0.0,
                             "note": "start.sh did not bring the app up from cold; "
                                     "this is a scored agent failure, not a harness fault"}},
                indent=2) + "\n")
            return 1
        log("      app is up")

        # --- grade ---------------------------------------------------------
        log("[6/6] running the graders (deploy gate -> browser -> pytest -> score) ...")
        r = subprocess.run(["docker", "exec", "-w", "/app", cname, "bash", "/tests/test.sh"],
                           text=True)
        run(["docker", "cp", f"{cname}:/logs/verifier/.", str(out_dir)])

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
            if sidecars:
                log(f"  docker compose -p {project} down -v   # and the sidecars")
        else:
            run(["docker", "rm", "-f", cname])
            if sidecars:
                stop_sidecars(staging / "sidecars.yaml", project, compose_file.parent)
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
