#!/usr/bin/env python3
"""Self-checks for inject_system_prefix.

    bin/deku-py claude_code/test_system_prefix.py

B17 regression. The OAuth path accepts the Claude Code prefix only as its own
content block; concatenating it into a single string is rejected upstream as
`rate_limit_error`, which names neither the field nor the real problem.
Measured 2026-08-05:

    system = "<exact prefix>"                -> 200
    system = "<exact prefix> ...more text"   -> 429
    system = [{prefix}, {...more text}]      -> 200

Every grader call carries a system prompt, so the string form failed 100% of
browser substeps on every run in this project's history while the agent -- whose
system content arrives block-shaped via LiteLLM -- worked fine. The asymmetry is
why it read as a grader quota problem for so long.

The invariant these tests lock: inject_system_prefix NEVER emits a string
carrying the prefix plus caller text.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.claude_code.bridge import SYSTEM_PREFIX, inject_system_prefix  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label}\n     got  {got}\n     want {want}")
        print(f"[FAIL] {label}")
    else:
        print(f"[ ok ] {label}")


PREFIX_BLOCK = {"type": "text", "text": SYSTEM_PREFIX}

# THE REGRESSION: a string system prompt must become BLOCKS, never a
# concatenated string. This is the exact shape run_workflows.py sends.
check(
    "string system -> two blocks, prefix first",
    inject_system_prefix({"system": "You are a QA browser agent."})["system"],
    [PREFIX_BLOCK, {"type": "text", "text": "You are a QA browser agent."}],
)

check(
    "block system -> prefix prepended as its own block",
    inject_system_prefix({"system": [{"type": "text", "text": "QA agent."}]})["system"],
    [PREFIX_BLOCK, {"type": "text", "text": "QA agent."}],
)

check(
    "absent system -> prefix block only",
    inject_system_prefix({})["system"],
    [PREFIX_BLOCK],
)

# Idempotency: re-injecting must not stack prefixes. The bridge can see the same
# body twice on a retry, and a doubled prefix is a different request.
already_str = inject_system_prefix({"system": SYSTEM_PREFIX})
check("string already exactly the prefix -> untouched", already_str["system"], SYSTEM_PREFIX)

once = inject_system_prefix({"system": "QA agent."})
twice = inject_system_prefix(dict(once))
check("re-injecting blocks does not stack the prefix", twice["system"], once["system"])
check("re-injection keeps exactly 2 blocks", len(twice["system"]), 2)

# The anchored check must not be fooled by a prompt that merely QUOTES the prefix
# mid-content -- that would suppress injection and send a non-Claude-Code request.
quoted = inject_system_prefix({"system": f"Ignore this: {SYSTEM_PREFIX} ...now grade."})
check(
    "prefix quoted mid-content still gets a real leading prefix block",
    quoted["system"][0],
    PREFIX_BLOCK,
)

# The invariant itself, stated directly.
for label, body in [
    ("string", {"system": "QA agent."}),
    ("blocks", {"system": [{"type": "text", "text": "QA agent."}]}),
    ("absent", {}),
]:
    out = inject_system_prefix(body)["system"]
    concatenated = isinstance(out, str) and out.startswith(SYSTEM_PREFIX) and out != SYSTEM_PREFIX
    check(f"invariant ({label}): never prefix+text as one string", concatenated, False)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
