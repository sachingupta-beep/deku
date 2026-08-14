#!/usr/bin/env python3
"""Make ONE real grader call and print exactly what came back.

    scripts/deku-py harness/eval/probe_grader.py

Exists because a grader fault inside a trial costs ~14 minutes and ~$1 to
reproduce, and until the browser results file was collected it surfaced only as
a bare reason code (`grader_llm_error`) with the exception text discarded. This
runs the same client, the same tool schema and the same auth resolution as
run_workflows.py, outside Docker, in about a second.

It deliberately does NOT go through the retry ladder or the cooldown: the point
is to see the first error immediately, not to survive it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_workflows as rw  # noqa: E402


def _host_side(url: str) -> str:
    """Rewrite container-only hostnames so the probe works from the host.

    `host.docker.internal` is how a CONTAINER reaches a service on the host, and
    it is the correct value in task.toml -- but it does not resolve on the host
    itself, where this probe runs. Without this the probe reports
    `ConnectError: nodename nor servname provided` and looks like a broken
    bridge when the configuration is in fact correct.
    """
    for container_name in ("host.docker.internal", "gateway.docker.internal"):
        if container_name in url:
            rewritten = url.replace(container_name, "localhost")
            print(f"note     : rewrote {container_name} -> localhost "
                  f"(container-only name; the trial itself still uses the original)")
            return rewritten
    return url


def main() -> int:
    model = os.environ.get("DEKU_GRADER_MODEL", rw.DEFAULT_GRADER_MODEL)
    provider = rw._resolve_provider(model)

    for var in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL"):
        if os.environ.get(var):
            os.environ[var] = _host_side(os.environ[var])

    print(f"model    : {model}")
    print(f"provider : {provider}")
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        print(f"base_url : {os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')}")
        print(f"api_key  : {'set (' + key[:7] + '...)' if key else '*** NOT SET ***'}")
    else:
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        print(f"base_url : {os.environ.get('ANTHROPIC_BASE_URL', 'https://api.anthropic.com')}")
        print(f"api_key  : {'set (' + key[:7] + '...)' if key else '*** NOT SET ***'}")
    print()

    # Skip the 60s cooldown and the pacing gap -- we want the first error now.
    rw.GRADER_COOLDOWN_SEC = 0.0
    rw.MIN_CALL_INTERVAL_SEC = 0.0
    rw.RETRY_ATTEMPTS = 1

    llm = rw.make_llm(model)
    try:
        resp = llm.message(
            system="You are a QA browser agent. Answer with a tool call.",
            messages=[{"role": "user",
                       "content": "Substep: confirm the page loaded. "
                                  "Call report_result with passed=true and a short note."}],
            tools=rw.TOOLS,
            max_tokens=256,
        )
    except Exception as exc:
        print(f"FAILED: {exc.__class__.__name__}: {exc}")
        body = getattr(getattr(exc, "response", None), "text", None)
        if body:
            print(f"\nupstream body:\n{body[:2000]}")
        print("\nThis is the error the grader hits on every substep.")
        return 1
    finally:
        llm.close()

    print("OK -- the grader can reach its model and returned a usable response.\n")
    print(f"stop_reason : {resp.get('stop_reason')}")
    for block in resp.get("content", []):
        if block.get("type") == "tool_use":
            print(f"tool_use    : {block.get('name')}  input={json.dumps(block.get('input'))}")
        elif block.get("type") == "text":
            print(f"text        : {block.get('text', '')[:200]}")

    if not resp.get("content"):
        print("\nWARNING: empty content. The loop would treat this as a no-tool-call "
              "substep and score it UNGRADED, not failed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
