#!/usr/bin/env python3
"""Add a dockerd sidecar to a task's compose, in place.

    python3 harness/inject_dockerd.py <task>/environment/docker-compose.yaml

Called by scripts/deku-run under --with-dockerd, which backs the file up first
and restores it on exit. Idempotent: injecting twice is a no-op.

WHY

`harness/prompt/deployment_contract.j2` tells the agent to run `docker info` and,
if a daemon answers, not to finish until it has built its image and confirmed the
health endpoint from it. No task in the corpus ships a dockerd sidecar, so that
branch had never run -- every agent fell through to "no daemon: read your
Dockerfile back carefully".

Reading a Dockerfile does not find what only running one finds. Two runs died on
that gap in two days:

    top-poster    Pydantic EmailStr without the [email] extra   ImportError at start
    seasonal      Prisma without OpenSSL                        engine error at start

Both build cleanly. Both fail on the first `docker run`. Both would have cost the
agent ninety seconds to catch with a daemon, and cost roughly $7 each without one.

ISOLATION

The daemon runs inside the compose network and shares nothing with the host
daemon or the grader. Images the agent builds there are invisible to grading,
which still rebuilds from /app/Dockerfile in a clean container. The agent gains a
way to VERIFY, not a way to smuggle a hand-fixed container past the gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

SERVICE = "dockerd"

# docker:27-dind matches the harness's own Docker major version. TLS is off
# because the daemon is reachable only on the run's private compose network and
# lives for one trial; certificate material would be ceremony, not security.
# `privileged` is not optional -- a Docker daemon cannot manage cgroups,
# namespaces or overlayfs without it, which is the cost of this feature.
DEFINITION = {
    "image": "docker:27-dind",
    "privileged": True,
    "restart": "unless-stopped",
    "environment": {"DOCKER_TLS_CERTDIR": ""},
    "command": ["--host=tcp://0.0.0.0:2375", "--host=unix:///var/run/docker.sock"],
    "healthcheck": {
        "test": ["CMD-SHELL", "docker -H tcp://localhost:2375 info >/dev/null 2>&1"],
        "interval": "5s",
        "timeout": "5s",
        "retries": 30,
        "start_period": "20s",
    },
}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.splitlines()[2].strip(), file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        doc = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        print(f"inject_dockerd: {path} does not parse: {exc}", file=sys.stderr)
        return 1

    services = doc.get("services")
    if not isinstance(services, dict):
        print(f"inject_dockerd: {path} declares no services", file=sys.stderr)
        return 1
    if SERVICE in services:
        return 0  # already there

    services[SERVICE] = dict(DEFINITION)

    # The agent must not start before the daemon is up: `docker info` on a
    # half-started dind answers "cannot connect", and the contract reads that as
    # "this task has no daemon" -- silently returning the agent to the fallback
    # this whole feature exists to replace.
    main_svc = services.get("main")
    if isinstance(main_svc, dict):
        dep = main_svc.get("depends_on")
        if isinstance(dep, dict):
            dep[SERVICE] = {"condition": "service_healthy"}
        elif isinstance(dep, list):
            if SERVICE not in dep:
                dep.append(SERVICE)
        else:
            main_svc["depends_on"] = {SERVICE: {"condition": "service_healthy"}}

    path.write_text(yaml.safe_dump(doc, sort_keys=False, default_flow_style=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
