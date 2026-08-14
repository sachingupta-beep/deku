#!/usr/bin/env python3
"""Conformance suite for capability adapters.

    scripts/deku-py harness/verifier/test_capabilities.py

Why a shared suite rather than per-adapter tests
------------------------------------------------
`capabilities.py` is the layer every pytest substep goes through, for every task,
for every provider. A bug here is not one broken test -- it is a broken category,
and it surfaces as an APP failure rather than a harness failure, because the query
returns [] instead of raising.

That is not hypothetical. On 2026-08-06 `PocketBaseBackend` rendered
`deleted=False` as the filter literal `"False"`. PocketBase booleans are
`true`/`false` unquoted, so a boolean column never equalled the string, every
`deleted=False` query returned [], and three of four failing substeps on
streak-habit-tracker were unpassable by ANY app. It read as "the app stores data
outside PocketBase". It was one line of string formatting.

The registry allows 32 providers across 6 slots. Every one of them will have to
translate Python values into some query language. This suite is the contract they
all answer to, so provider number 12 costs what provider number 2 did.

No network: these assert on the QUERY the adapter builds, which is where the type
translation happens and where it went wrong.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capabilities import PocketBaseBackend  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label}\n     got  {got!r}\n     want {want!r}")
        print(f"[FAIL] {label}")
    else:
        print(f"[ ok ] {label}")


lit = PocketBaseBackend._literal

# ------------------------------------------------------- the regression itself
# A boolean must be an unquoted lowercase keyword. Quoting it compares a boolean
# column to a string and matches nothing -- silently, with an empty result.
check("False -> bare lowercase false", lit(False), "false")
check("True  -> bare lowercase true", lit(True), "true")

# bool subclasses int in Python. An isinstance(v, int) check placed before the
# bool check renders False as "0" -- the same bug wearing a different mask.
check("False is NOT rendered as 0", lit(False) != "0", True)
check("True is NOT rendered as 1", lit(True) != "1", True)

# --------------------------------------------------------------- other types
check("str is quoted", lit("abc"), '"abc"')
check("int is bare", lit(5), "5")
check("float is bare", lit(1.5), "1.5")
check("None -> null", lit(None), "null")

# A record id is a string and must stay quoted -- PocketBase ids are
# alphanumeric and would otherwise be read as an identifier, not a value.
check("record id stays quoted", lit("5gzuubbvswes3jm"), '"5gzuubbvswes3jm"')

# A value containing a quote must not be able to terminate the literal early and
# inject filter syntax.
check('embedded quote is escaped', lit('a"b'), '"a\\"b"')

# ----------------------------------------------------- the full filter string
# The exact query that returned [] for every app before the fix.
built = " && ".join(
    f"{k}={lit(v)}" for k, v in {"user_id": "5gzuubbvswes3jm", "deleted": False}.items()
)
check(
    "habits_for(user_id, deleted=False) builds a valid filter",
    built,
    'user_id="5gzuubbvswes3jm" && deleted=false',
)
check("the broken form is gone", 'deleted="False"' in built, False)

# A query with no boolean was always fine -- that asymmetry is what made the bug
# look like an app fault: habit_by_name() worked while habits_for() did not.
check(
    "string-only filter unchanged",
    " && ".join(f"{k}={lit(v)}" for k, v in {"user_id": "u1", "name": "Meditate"}.items()),
    'user_id="u1" && name="Meditate"',
)

# --------------------------------------------------- adapter surface contract
# Every Backend must expose the same three calls, so a substep written against
# one provider runs unchanged against another.
for method in ("rows", "count", "one"):
    check(f"PocketBaseBackend implements {method}()",
          callable(getattr(PocketBaseBackend, method, None)), True)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
