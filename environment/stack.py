#!/usr/bin/env python3
"""Bring a task's backing services UP for real -- the answer to "how does the
container come up from a .yaml".

This is Deku's equivalent of WildClawBench's mock_stack.py. It assembles the
sidecar services a task declares (NO `main` -- that's Harbor's agent container),
then runs `docker compose up -d --wait`, so Docker pulls/builds the images and
blocks until every service passes its healthcheck. Use it to boot & smoke-test a
service without running a whole trial.

    python3 environment/stack.py up   --task seat-allocation-map     # boot + wait healthy
    python3 environment/stack.py ps   --task seat-allocation-map     # status
    python3 environment/stack.py down --task seat-allocation-map     # tear down
    python3 environment/stack.py check                               # service.toml <-> registry.json agree?

Pure stdlib; shells out to `docker compose`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import compose  # sibling module: task_services, ordered_providers, REGISTRY, ENV, BANNER

ENV = compose.ENV
REPO = compose.REPO
STACK_FILE = ".deku-stack.yaml"


def read_service_toml(provider: str) -> dict:
    """Flat parse of providers/<p>/service.toml (no tomllib needed)."""
    path = ENV / "providers" / provider / "service.toml"
    out: dict[str, object] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        m = re.match(r'\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*(?:#.*)?$', line)
        if not m or line.strip().startswith("["):
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw.startswith('"'):
            out[key] = raw.strip('"')
        elif raw.isdigit():
            out[key] = int(raw)
        else:
            out[key] = raw
    return out


def sidecar_compose(task: str) -> str:
    """The task's services WITHOUT `main` (main is the agent, Harbor-owned)."""
    providers = compose.ordered_providers(compose.task_services(task))
    parts = [compose.BANNER, "# stack.py standalone bring-up (no `main`).\n", "services:\n"]
    for prov in providers:
        parts.append((ENV / "providers" / prov / "service.yaml").read_text().rstrip("\n") + "\n\n")
    return "".join(parts)


def _write_stack(task: str) -> tuple[Path, str]:
    env_dir = REPO / "tasks" / task / "environment"
    if not env_dir.exists():
        sys.exit(f"no environment/ for task {task!r}")
    compose.copy_assets(task)                     # ensure generic seeds + build assets are present
    stack_path = env_dir / STACK_FILE
    stack_path.write_text(sidecar_compose(task))
    return stack_path, f"deku-stack-{task}"


def _dc(stack: Path, project: str, *args: str) -> int:
    cmd = ["docker", "compose", "-p", project, "-f", str(stack), *args]
    print("+", " ".join(cmd))
    return subprocess.call(cmd)


def cmd_up(task: str, timeout: int) -> int:
    providers = compose.ordered_providers(compose.task_services(task))
    if not providers:
        print(f"{task}: no services declared (frontend-only) -- nothing to bring up")
        return 0
    stack, project = _write_stack(task)
    print(f"bringing up {providers} for {task} ...")
    rc = _dc(stack, project, "up", "-d", "--wait", "--wait-timeout", str(timeout))
    _dc(stack, project, "ps")
    if rc == 0:
        print(f"\n✅ all services healthy for {task}. Tear down with: "
              f"python3 environment/stack.py down --task {task}")
    else:
        print(f"\n❌ services did not all become healthy (rc={rc}). Logs: "
              f"docker compose -p {project} -f {stack} logs", file=sys.stderr)
    return rc


def cmd_ps(task: str) -> int:
    stack, project = REPO / "tasks" / task / "environment" / STACK_FILE, f"deku-stack-{task}"
    return _dc(stack, project, "ps")


def cmd_down(task: str) -> int:
    stack, project = REPO / "tasks" / task / "environment" / STACK_FILE, f"deku-stack-{task}"
    rc = _dc(stack, project, "down", "-v")
    if stack.exists():
        stack.unlink()
    return rc


def cmd_check() -> int:
    """service.toml providers must match registry.json providers (no drift)."""
    toml_ps = {p.parent.name for p in (ENV / "providers").glob("*/service.toml")}
    reg_ps = set(compose.REGISTRY["providers"])
    ok = toml_ps == reg_ps
    print(f"service.toml providers: {sorted(toml_ps)}")
    print(f"registry.json providers: {sorted(reg_ps)}")
    if ok:
        print("✅ in sync")
    else:
        print(f"❌ drift -- only in service.toml: {toml_ps - reg_ps}; "
              f"only in registry: {reg_ps - toml_ps}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["up", "down", "ps", "check"])
    ap.add_argument("--task")
    ap.add_argument("--timeout", type=int, default=180, help="seconds to wait for healthy")
    args = ap.parse_args()
    if args.action == "check":
        return cmd_check()
    if not args.task:
        ap.error("--task is required for up/down/ps")
    return {"up": lambda: cmd_up(args.task, args.timeout),
            "ps": lambda: cmd_ps(args.task),
            "down": lambda: cmd_down(args.task)}[args.action]()


if __name__ == "__main__":
    sys.exit(main())
