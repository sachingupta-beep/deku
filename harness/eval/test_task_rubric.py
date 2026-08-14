#!/usr/bin/env python3
"""Self-checks for the task-authored rubric path in run_rubric.py.

    scripts/deku-py harness/eval/test_task_rubric.py

Covers the two things that make a task rubric different from the generic seven
dimensions, both of which are silent if wrong:

  weighting  -- `importance` must actually change a criterion's pull on the
                composite, and the weights must normalise so ANY rubric, of any
                length, still lands in [0, 1].

  polarity   -- `is_positive: false` marks an ANTI-pattern ("presents a retried
                set as a second visible entry"). Grading it like a positive
                criterion rewards the app for exhibiting the defect. The judge is
                instead asked whether the app AVOIDS it, so 1.0 means absent.

No network: these assert on the criteria structure and the arithmetic, which is
where a mistake would quietly skew every rubric score.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_rubric import (  # noqa: E402
    IMPORTANCE_WEIGHT,
    RUBRIC,
    compute_task_rubric_score,
    load_task_rubric,
)

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{label}\n     got  {got!r}\n     want {want!r}")
        print(f"[FAIL] {label}")
    else:
        print(f"[ ok ] {label}")


def write(criteria: list[dict]) -> Path:
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(criteria, fh)
    fh.close()
    return Path(fh.name)


SAMPLE = [
    {"number": "R1", "criterion": "ships a set entry form", "is_positive": True,
     "dimension": "instruction_following", "importance": "critically_important"},
    {"number": "R2", "criterion": "gives each surface an empty state", "is_positive": True,
     "dimension": "ux_flow", "importance": "somewhat_important"},
    {"number": "R3", "criterion": "presents a retried set as a second visible entry",
     "is_positive": False, "dimension": "functionality", "importance": "important"},
]

path = write(SAMPLE)
loaded = load_task_rubric(path)

# ------------------------------------------------------------------ weighting
check("all criteria loaded", len(loaded), 3)
check("weights normalise to 1.0", round(sum(c["weight"] for c in loaded), 6), 1.0)
check(
    "critically_important outweighs somewhat_important",
    loaded[0]["weight"] > loaded[1]["weight"],
    True,
)
check(
    "the 5:1 importance ratio is preserved",
    round(loaded[0]["weight"] / loaded[1]["weight"], 3),
    round(IMPORTANCE_WEIGHT["critically_important"]
          / IMPORTANCE_WEIGHT["somewhat_important"], 3),
)

# An unknown importance must not crash or silently weigh zero.
odd = load_task_rubric(write([
    {"number": "R1", "criterion": "x", "importance": "who_knows"},
    {"number": "R2", "criterion": "y", "importance": "critically_important"},
]))
check("unknown importance still gets a weight", odd[0]["weight"] > 0, True)
check("unknown-importance rubric still normalises",
      round(sum(c["weight"] for c in odd), 6), 1.0)

# ------------------------------------------------------------------- polarity
check("negative criterion is flagged", loaded[2]["is_positive"], False)
check("negative prompt asks the judge to score AVOIDANCE",
      "ANTI-PATTERN" in loaded[2]["asks"], True)
check("negative prompt says a high score means the defect is absent",
      "defect is absent" in loaded[2]["asks"], True)
check("positive prompt carries no anti-pattern framing",
      "ANTI-PATTERN" in loaded[0]["asks"], False)

# ----------------------------------------------------------------- arithmetic
graded_all_pass = {c["key"]: {"score": 1.0} for c in loaded}
check("all criteria met -> 1.0", compute_task_rubric_score(loaded, graded_all_pass), 1.0)

graded_all_fail = {c["key"]: {"score": 0.0} for c in loaded}
check("nothing met -> 0.0", compute_task_rubric_score(loaded, graded_all_fail), 0.0)

# A rogue model returning 1.5 must not inflate past 1.0.
check("out-of-range score is clamped",
      compute_task_rubric_score(loaded, {c["key"]: {"score": 1.5} for c in loaded}), 1.0)

# A criterion the judge never returned counts as 0, not as missing.
check("ungraded criterion counts as zero",
      compute_task_rubric_score(loaded, {}), 0.0)

# Failing ONLY the critically-important one must cost more than failing only the
# somewhat-important one -- otherwise `importance` is decorative.
fail_critical = {**graded_all_pass, loaded[0]["key"]: {"score": 0.0}}
fail_minor = {**graded_all_pass, loaded[1]["key"]: {"score": 0.0}}
check("failing a critical criterion costs more than a minor one",
      compute_task_rubric_score(loaded, fail_critical)
      < compute_task_rubric_score(loaded, fail_minor),
      True)

# ------------------------------------------------------------ malformed input
try:
    load_task_rubric(write([{"number": "R1", "criterion": "   "}]))
    check("empty criterion text is rejected", False, True)
except ValueError:
    check("empty criterion text is rejected", True, True)

# --------------------------------------------------- generic path untouched
check("generic RUBRIC still sums to 1.0", round(sum(w for _, w, _ in RUBRIC), 6), 1.0)
check("generic RUBRIC still has 7 dimensions", len(RUBRIC), 7)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED:")
    for f in FAILURES:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
