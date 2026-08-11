#!/usr/bin/env python3
"""Work out how to build and run an app the harness was never told about.

    plan = plan_app(staged_app_dir)          # inspect
    write_build_files(staged_app_dir, plan)  # emit Dockerfile + .dockerignore

Why this exists
---------------
Grading redeploys the agent's app into a clean container. Something has to turn a
directory of source into a running server, and there are only two places that
knowledge can live:

  in the task spec   -- "write /app/start.sh, it must install deps, migrate, and
                        start detached". This is what we did, and it is a tax on
                        every task and every run. It also leaks: the moment the
                        spec explains HOW to package an app, a packaging mistake
                        stops being the agent's and starts being ours, and each
                        new trap found (`.venv`, then `node_modules`) has to be
                        written into eleven briefs by hand.

  in the harness     -- here. The spec goes back to describing the PRODUCT, and
                        the harness reads the app the way a deployment platform
                        does: find the manifest, install from it, run the start
                        script it declares.

The second is what Heroku, Railway, Fly and Cloud Run all do, and it works for
the same reason it works for them: a project's manifest already states how to
build and start it. `package.json` has `scripts.start`. That is not a convention
we are imposing, it is one npm imposed in 2010.

The portability traps disappear as a side effect rather than as a rule anyone has
to remember. `.dockerignore` is written HERE, so `node_modules` and `.venv` never
enter the build context no matter what the agent committed -- there is no stale
tree to copy over a clean install, because there is no stale tree.

What this cannot do
-------------------
Guess. If an app declares no manifest this module returns no plan, and the caller
must record that as a HARNESS fault (`invalid`), never as an agent score of 0.
Being unable to observe something is not evidence the something was absent.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Never enter the build context. Two reasons, and the second is the load-bearing
# one:
#   1. they are large and slow to send to the daemon
#   2. they are machine-specific. A virtualenv records absolute interpreter paths;
#      node_modules/.bin holds symlinks into a tree that no longer exists after a
#      copy. Both produce failures that read like application bugs -- "cannot
#      execute binary file", "Cannot find module '../lib/tsc.js'" -- and both cost
#      this project a full run before the cause was found.
#
# Every pattern is `**/`-prefixed on purpose. .dockerignore anchors to the CONTEXT
# ROOT, so a bare `node_modules` matches /app/node_modules and nothing else --
# and agents overwhelmingly build client/ + server/ layouts where the trees are
# one level down. Verified 2026-08-10: with the unprefixed list the build context
# was 88MB of the very node_modules this is meant to exclude, npm found every
# package already present, installed nothing, and the broken tree shipped intact.
# The bug is silent: the image builds, and the failure surfaces later as an
# application error.
IGNORE = [
    "**/node_modules", "**/.venv", "**/venv",
    "**/__pycache__", "**/*.pyc",
    "**/.pytest_cache", "**/.mypy_cache", "**/.ruff_cache",
    "**/.git", "**/.DS_Store", "**/*.log",
    ".browser_screenshots", ".downloads",
]

# Directory names that are never an application package, so a manifest inside one
# is a fixture or a vendored copy rather than the thing to run.
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git",
             "dist", "build", "out", ".next", "coverage", "tests", "test"}

# Preferred names when several packages could be the server. Ordered.
SERVER_HINTS = ("server", "api", "backend", "app", "src")


@dataclass
class Step:
    """One build command, run at image build time."""
    workdir: str          # relative to /app
    shell: str            # the command line


@dataclass
class Plan:
    kind: str                          # "node" | "python"
    steps: list[Step] = field(default_factory=list)
    start_workdir: str = "."
    start_shell: str = ""
    migrate_workdir: str = ""
    migrate_shell: str = ""
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ discovery
def _manifests(app_dir: Path, name: str, max_depth: int = 3) -> list[Path]:
    """Every `name` under app_dir, skipping vendored and output directories."""
    found = []
    for path in app_dir.rglob(name):
        rel = path.relative_to(app_dir)
        if len(rel.parts) > max_depth:
            continue
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        found.append(path)
    # shallowest first: a root manifest outranks a nested one
    return sorted(found, key=lambda p: (len(p.relative_to(app_dir).parts), str(p)))


def _rank_server(rel_dir: str) -> int:
    """Lower is more likely to be the server package."""
    name = Path(rel_dir).name.lower()
    for i, hint in enumerate(SERVER_HINTS):
        if name == hint:
            return i
    return len(SERVER_HINTS)


def _plan_node(app_dir: Path) -> Plan | None:
    """Read package.json the way a PaaS does: build what declares a build, start
    what declares a start.

    Handles the single-package layout and the client/ + server/ split that agents
    reach for unprompted -- in the latter there is no root package.json at all,
    so "just run npm start in /app" finds nothing.
    """
    pkgs = []
    for path in _manifests(app_dir, "package.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        rel = str(path.parent.relative_to(app_dir)) or "."
        pkgs.append((rel, data.get("scripts") or {}, path.parent))
    if not pkgs:
        return None

    plan = Plan(kind="node")

    # Install every package that has a manifest; `npm ci` when a lockfile is
    # present (exact, reproducible), `npm install` when it is not. `ci` FAILS
    # rather than falling back if the lockfile is out of sync with package.json,
    # which is a real defect worth surfacing -- so the fallback is explicit and
    # logged rather than silent.
    for rel, scripts, pdir in pkgs:
        has_lock = (pdir / "package-lock.json").exists()
        install = ("npm ci --no-audit --no-fund" if has_lock
                   else "npm install --no-audit --no-fund")
        if has_lock:
            install += " || npm install --no-audit --no-fund"
        plan.steps.append(Step(rel, install))
        if not has_lock:
            plan.notes.append(f"{rel}: no package-lock.json, using npm install")

    # Build anything that declares a build. Frontends must be built before the
    # server starts, because the server serves their output.
    for rel, scripts, _ in pkgs:
        if "build" in scripts:
            plan.steps.append(Step(rel, "npm run build"))

    # The server is the package declaring a start-like script.
    candidates = [(rel, scripts) for rel, scripts, _ in pkgs
                  if any(k in scripts for k in ("start", "serve", "preview"))]
    if not candidates:
        return None
    candidates.sort(key=lambda c: _rank_server(c[0]))
    rel, scripts = candidates[0]
    script = next(k for k in ("start", "serve", "preview") if k in scripts)
    plan.start_workdir = rel
    plan.start_shell = f"npm run {script}" if script != "start" else "npm start"
    if len(candidates) > 1:
        plan.notes.append(
            f"{len(candidates)} packages declare a start script "
            f"({', '.join(c[0] for c in candidates)}); chose {rel}")

    # A declared migrate script runs at container start, not at build time: no
    # database is reachable during `docker build`.
    if "migrate" in scripts:
        plan.migrate_workdir = rel
        plan.migrate_shell = "npm run migrate"
    return plan


def _plan_python(app_dir: Path) -> Plan | None:
    """An entry point is required; a manifest is not.

    Requiring requirements.txt first was wrong. A stdlib-only `server.py` is a
    complete, runnable Python app and needs no dependencies at all -- 28 of this
    corpus's collected apps are exactly that (smoke-tip-calculator, calculator),
    and every one of them was reported as an unidentifiable stack. Install from a
    manifest when there is one, and run the app either way.
    """
    plan = Plan(kind="python")
    reqs = _manifests(app_dir, "requirements.txt")
    pyproject = _manifests(app_dir, "pyproject.toml")
    for path in reqs:
        rel = str(path.parent.relative_to(app_dir)) or "."
        plan.steps.append(Step(rel, "pip install --no-cache-dir --break-system-packages "
                                    "-r requirements.txt || "
                                    "pip install --no-cache-dir -r requirements.txt"))
    for path in pyproject:
        rel = str(path.parent.relative_to(app_dir)) or "."
        if not any(s.workdir == rel for s in plan.steps):
            plan.steps.append(Step(rel, "pip install --no-cache-dir --break-system-packages . "
                                        "|| pip install --no-cache-dir ."))

    for entry in ("server.py", "main.py", "app.py", "wsgi.py", "asgi.py", "manage.py"):
        hits = _manifests(app_dir, entry)
        if not hits:
            continue
        rel = str(hits[0].parent.relative_to(app_dir)) or "."
        plan.start_workdir = rel
        if entry == "manage.py":
            plan.start_shell = "python manage.py runserver 0.0.0.0:${APP_PUBLIC_PORT}"
        else:
            plan.start_shell = f"python -u {entry}"   # -u: unbuffered, so the
            # container log shows the app's own output as it happens rather than
            # only when a buffer fills, which matters when it dies at startup.
        if not plan.steps:
            plan.notes.append("no manifest found; assuming stdlib-only")
        return plan
    return None


def plan_app(app_dir: Path) -> Plan | None:
    """The plan for this app, or None if its stack cannot be identified.

    None is not a failing grade. The caller records it as `invalid` -- the
    harness could not observe the app, which says nothing about the app.
    """
    return _plan_node(app_dir) or _plan_python(app_dir)


# -------------------------------------------------------------- emit the files
# @@TOKEN@@ substitution rather than str.format: these are shell scripts, and
# every `${VAR:-default}` in them is a brace str.format would try to interpret.
ENTRYPOINT = """#!/usr/bin/env bash
# GENERATED by harness/app_image.py -- not written by the agent.
set -u
export APP_PUBLIC_PORT="${APP_PUBLIC_PORT:-4173}"
export PORT="${PORT:-$APP_PUBLIC_PORT}"
export HOST="${HOST:-0.0.0.0}"
@@MIGRATE@@
cd "/app/@@START_WORKDIR@@" || exit 1
echo "[deku] starting: @@START_SHELL@@  (cwd /app/@@START_WORKDIR@@)"
# exec, so the server becomes PID 1. A backgrounded server would let this script
# exit, and the container would stop the instant it did.
exec @@START_SHELL@@
"""

MIGRATE_BLOCK = """
cd "/app/@@WORKDIR@@" || exit 1
echo "[deku] migrating: @@SHELL@@"
# Not fatal. Some apps provision their schema on first request instead, and a
# migrate step that fails is better surfaced by the health gate and the pytest
# pass than by refusing to start the app at all.
@@SHELL@@ || echo "[deku] migrate step failed (continuing)" >&2
"""


def render_dockerfile(base_image: str, plan: Plan, port: str = "4173") -> str:
    lines = [
        "# GENERATED by harness/app_image.py at grading time -- not written by the agent,",
        "# and not present during the agent phase.",
        "#",
        f"# Base is the task's own environment image, so the app is built against exactly",
        "# the runtimes the task declares (node, python, build tools) and nothing has to be",
        "# guessed about the stack.",
        f"FROM {base_image}",
        "WORKDIR /app",
        "",
        "# .dockerignore keeps node_modules/.venv out of this COPY, so the install steps",
        "# below cannot be overwritten by a tree built for another machine.",
        "COPY . /app",
        "",
    ]
    for step in plan.steps:
        wd = "/app" if step.workdir == "." else f"/app/{step.workdir}"
        # `set -eu` first: without it a failed `cd` leaves the next command to run
        # in whatever directory the shell happened to be in, which installs the
        # wrong package and reports success.
        lines.append(f"RUN set -eu; cd {wd}; {step.shell}")
    lines += [
        "",
        f"ENV APP_PUBLIC_PORT={port} PORT={port} HOST=0.0.0.0",
        f"EXPOSE {port}",
        "COPY .deku-entrypoint.sh /deku-entrypoint.sh",
        "RUN chmod +x /deku-entrypoint.sh",
        'CMD ["/deku-entrypoint.sh"]',
        "",
    ]
    return "\n".join(lines)


def write_build_files(app_dir: Path, plan: Plan, base_image: str,
                      port: str = "4173") -> Path:
    """Write .dockerignore, .deku-entrypoint.sh and Dockerfile into the staged app.

    Into the STAGING copy, never the trial's artifacts -- the agent's output is
    evidence and stays exactly as it was left.
    """
    (app_dir / ".dockerignore").write_text("\n".join(IGNORE) + "\n")

    migrate = ""
    if plan.migrate_shell:
        migrate = (MIGRATE_BLOCK
                   .replace("@@WORKDIR@@", plan.migrate_workdir)
                   .replace("@@SHELL@@", plan.migrate_shell))
    (app_dir / ".deku-entrypoint.sh").write_text(
        ENTRYPOINT
        .replace("@@MIGRATE@@", migrate)
        .replace("@@START_WORKDIR@@", plan.start_workdir)
        .replace("@@START_SHELL@@", plan.start_shell)
    )

    dockerfile = app_dir / "Dockerfile"
    dockerfile.write_text(render_dockerfile(base_image, plan, port))
    return dockerfile


def describe(plan: Plan) -> str:
    """One block of human-readable text for the run log and the debug bundle."""
    out = [f"stack detected : {plan.kind}"]
    for step in plan.steps:
        out.append(f"  build       : ({step.workdir}) {step.shell}")
    if plan.migrate_shell:
        out.append(f"  migrate     : ({plan.migrate_workdir}) {plan.migrate_shell}")
    out.append(f"  start       : ({plan.start_workdir}) {plan.start_shell}")
    for note in plan.notes:
        out.append(f"  note        : {note}")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        sys.exit("usage: app_image.py <app-dir>   # print the detected plan")
    p = plan_app(Path(sys.argv[1]).resolve())
    if p is None:
        sys.exit("no plan: could not identify the stack")
    print(describe(p))
    print()
    print(render_dockerfile("<task-env-image>", p))
