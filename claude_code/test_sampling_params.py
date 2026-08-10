#!/usr/bin/env python3
"""Self-checks for drop_conflicting_sampling_params.

    bin/deku-py claude_code/test_sampling_params.py

Covers the exact upstream 400s observed in jobs/2026-08-04__01-13-28 (opus-4-8,
"`temperature` is deprecated for this model") and the pair rule that opus-4-5
enforces. Case 3 is the regression that matters: it is the one the previous
implementation got wrong, and it cost every opus-4-8 trial its entire run.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.claude_code.bridge import drop_conflicting_sampling_params  # noqa: E402

FAILURES: list[str] = []


def check(label: str, body: dict, expected: dict) -> None:
    got = drop_conflicting_sampling_params(dict(body))
    if got != expected:
        FAILURES.append(f"{label}\n     sent {body}\n     got  {got}\n     want {expected}")
        print(f"[FAIL] {label}")
    else:
        print(f"[ ok ] {label}")


OPUS_45 = "claude-opus-4-5-20251101"
OPUS_48 = "claude-opus-4-8"
SONNET = "claude-sonnet-4-5-20250929"

# 1-2. Pair rule: top_p goes, temperature stays. What OpenHands 0.62 always sends.
check(
    "opus-4-5 + both -> temperature kept, top_p dropped",
    {"model": OPUS_45, "temperature": 0.0, "top_p": 1.0},
    {"model": OPUS_45, "temperature": 0.0},
)
check(
    "sonnet-4-5 + both -> temperature kept, top_p dropped",
    {"model": SONNET, "temperature": 0.7, "top_p": 0.9},
    {"model": SONNET, "temperature": 0.7},
)

# 3. THE REGRESSION -- and a correction to it.
#
# Probed live 2026-08-07: opus-4-8 accepts `temperature` and rejects `top_p`.
# The 2026-08-04 error said the opposite ("temperature is deprecated"), and acting
# on that stripped the wrong parameter -- the request stayed invalid, just for the
# other reason. Assert the probed behaviour, not the error text.
check(
    "opus-4-8 + both -> BOTH dropped",
    {"model": OPUS_48, "temperature": 0.0, "top_p": 1.0},
    {"model": OPUS_48},
)
check(
    "opus-4-8 + top_p alone -> dropped",
    {"model": OPUS_48, "top_p": 1.0},
    {"model": OPUS_48},
)
check(
    "opus-4-8 + temperature alone -> dropped",
    {"model": OPUS_48, "temperature": 0.0},
    {"model": OPUS_48},
)

# 4. Non-conflicting requests pass through untouched.
check(
    "temperature alone on a model that accepts it -> untouched",
    {"model": OPUS_45, "temperature": 0.2},
    {"model": OPUS_45, "temperature": 0.2},
)
check(
    "top_p alone -> untouched",
    {"model": OPUS_45, "top_p": 0.95},
    {"model": OPUS_45, "top_p": 0.95},
)
check("neither -> untouched", {"model": OPUS_45}, {"model": OPUS_45})

# 5. Other body fields survive; a missing model does not crash.
check(
    "unrelated fields preserved",
    {"model": OPUS_45, "temperature": 0.0, "top_p": 1.0, "max_tokens": 4096},
    {"model": OPUS_45, "temperature": 0.0, "max_tokens": 4096},
)
check(
    "absent model -> pair rule only, no crash",
    {"temperature": 0.0, "top_p": 1.0},
    {"temperature": 0.0},
)

# 6. The matcher is env-tunable, and a broken regex degrades to the pair rule
#    rather than taking the bridge down.
os.environ["KAIJU_CC_NO_TEMPERATURE_MODELS"] = r"some-future-model"
check(
    "env can add a temperature-rejecting model",
    {"model": "some-future-model", "temperature": 0.0, "top_p": 1.0},
    {"model": "some-future-model", "top_p": 1.0},
)
os.environ["KAIJU_CC_NO_TEMPERATURE_MODELS"] = "[unclosed"
check(
    "invalid regex falls back to the pair rule",
    {"model": OPUS_45, "temperature": 0.0, "top_p": 1.0},
    {"model": OPUS_45, "temperature": 0.0},
)
del os.environ["KAIJU_CC_NO_TEMPERATURE_MODELS"]

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
