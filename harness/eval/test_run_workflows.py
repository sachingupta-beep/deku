#!/usr/bin/env python3
"""Static self-check for run_workflows.py.

Proves, without a browser or an LLM, that:
  1. Parsing tasks/seat-allocation-map/tests/workflows.yaml yields exactly the
     browser substeps per workflow, in order.
  2. The results structure we build round-trips through score.py::load_browser
     and produces a per-workflow substep-outcome list whose length equals the
     number of browser substeps in that workflow.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "harness" / "verifier"))

from run_workflows import browser_substeps, build_results_shell, load_workflows  # noqa: E402
import score  # noqa: E402

WORKFLOWS = REPO / "tasks" / "seat-allocation-map" / "tests" / "workflows.yaml"

# Expected per PLAN.md 4.4 + hand count of workflows.yaml.
EXPECTED = [
    ("employee_finds_own_seat", 3),
    ("hr_onboards_new_joiner", 4),
    ("hr_releases_leaver_seat", 3),
    ("dashboard_matches_reality", 3),
    ("available_seats_filtered_by_floor", 3),
    ("assistant_answers_natural_language", 3),
    ("employee_cannot_mutate", 2),
    ("unauthenticated_access_denied", 1),
    ("concurrent_allocation_single_winner", 0),
    ("employee_holds_at_most_one_seat", 0),
    ("non_available_seat_rejected", 2),
    ("duplicate_employee_email_rejected", 2),
]


def main() -> int:
    workflows = load_workflows(WORKFLOWS)
    assert [w["id"] for w in workflows] == [e[0] for e in EXPECTED], \
        f"workflow ids drift: got {[w['id'] for w in workflows]}"

    for w, (wid, expected_count) in zip(workflows, EXPECTED):
        b = browser_substeps(w)
        assert len(b) == expected_count, \
            f"{wid}: {len(b)} browser substeps, expected {expected_count}"
        # Order preserved and pytest substeps excluded.
        raw_browser = [s for s in w["substeps"] if s.get("kind") == "browser"]
        assert b == raw_browser, f"{wid}: order drift"

    print("[1/4] parse: all 12 workflows have the expected browser substep counts and order")

    # Build a synthetic all-pass results file and round-trip through score.load_browser.
    shell = build_results_shell(workflows)
    # Flip every emitted substep to passed=True.
    for entry in shell["workflows"]:
        for s in entry["substeps"]:
            s.pop("error", None)  # a real graded pass carries no error marker
            s["passed"] = True
            s["note"] = "synthetic pass for round-trip test"

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(shell, f)
        results_path = Path(f.name)

    loaded, graded, errors = score.load_browser(results_path)
    assert graded is True
    assert errors == [], f"clean run should carry no grader errors, got {errors}"
    for wid, expected_count in EXPECTED:
        got = loaded.get(wid, [])
        assert len(got) == expected_count, \
            f"round-trip {wid}: score.load_browser returned {len(got)} outcomes, expected {expected_count}"
        assert all(o is True for o in got), f"{wid}: expected all True after synthetic all-pass"
    print("[2/4] round-trip: score.load_browser returns matching per-workflow lengths, all True")

    # A browser that never launched observed nothing. Every substep must load as
    # None (ungraded), never False -- False would let score.py grade the workflow
    # on its surviving pytest substeps and publish a number for an unmeasured app.
    fail_shell = build_results_shell(workflows)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(fail_shell, f)
        fail_path = Path(f.name)
    loaded_f, _, _ = score.load_browser(fail_path)
    for wid, expected_count in EXPECTED:
        got = loaded_f.get(wid, [])
        assert len(got) == expected_count
        assert all(o is None for o in got), \
            f"{wid}: browser-unavailable substeps must be ungraded (None), got {got}"
    print("[3/4] shell round-trip: lengths align, every substep ungraded (None), not failed")

    # The regression that produced six identical reward:0.0 trials: a rate-limited
    # grader marked substeps failed, and because no workflow is browser-only every
    # workflow still scored. Ungraded substeps must now invalidate the run.
    rate_limited = build_results_shell(workflows)
    for entry in rate_limited["workflows"]:
        for s in entry["substeps"]:
            s["error"] = "grader_unavailable"
    rate_limited["meta"] = {"grader_error": ["grader_unavailable"]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(rate_limited, f)
        rl_path = Path(f.name)
    _, rl_graded, rl_errors = score.load_browser(rl_path)
    assert rl_graded is True, "a results file exists, so browser_graded stays true"
    assert rl_errors == ["grader_unavailable"], \
        f"grader_error must survive into score.py, got {rl_errors}"
    print("[4/4] rate-limited run: grader_error propagates, substeps ungraded")

    # SKIPPED substeps -- never attempted because an earlier substep consumed the
    # workflow budget (steps_used=0) -- are genuinely unobserved and must load as
    # None. A substep that EXHAUSTED the cap while driving the app is different
    # and is asserted separately below.
    step_cap_stub = {"passed": False, "error": "grader_step_cap",
                     "note": "skipped: workflow step cap already hit",
                     "do": "x", "steps_used": 0}
    no_tool_stub = {"passed": False, "error": "grader_no_tool_call",
                    "note": "no tool call; model said: ''",
                    "do": "x", "steps_used": 0}
    infra_payload = {"workflows": [
        {"id": "employee_finds_own_seat",
         "substeps": [step_cap_stub, no_tool_stub, step_cap_stub]},
    ]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(infra_payload, f)
        infra_path = Path(f.name)
    infra_loaded, _, _ = score.load_browser(infra_path)
    assert infra_loaded["employee_finds_own_seat"] == [None, None, None], \
        f"step-cap and no-tool-call must load as None, got {infra_loaded['employee_finds_own_seat']}"
    print("[5/6] SKIPPED step-cap and no-tool-call substeps load as None (ungraded)")

    # ...but a substep that burned its whole allowance while driving the app is a
    # FAILURE, not an unobserved substep. The grader looked -- for 100 steps -- and
    # never reached a verdict, and the commonest cause is a control that does
    # nothing. Treating it as unobserved invalidated an entire run that had really
    # scored 7/9 (strength-session-log, 2026-08-06), publishing 0.0 instead of 0.78.
    exhausted_stub = {"passed": False, "reason": "cap_exhausted",
                      "note": "step cap hit (100 steps used) without reaching a verdict; "
                              "scored as a failure, not as unobserved",
                      "do": "x", "steps_used": 100}
    exhausted_payload = {"workflows": [
        {"id": "employee_finds_own_seat", "substeps": [exhausted_stub]},
    ]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(exhausted_payload, f)
        exhausted_path = Path(f.name)
    ex_loaded, _, ex_errors = score.load_browser(exhausted_path)
    assert ex_loaded["employee_finds_own_seat"] == [False], \
        f"an exhausted-cap substep must load as False (failed), got {ex_loaded['employee_finds_own_seat']}"
    assert not ex_errors, \
        f"an exhausted-cap substep must NOT invalidate the run, got errors {ex_errors}"
    print("[5b/6] cap-EXHAUSTED substep loads as False (failed) and does not invalidate")

    # Workflow-crash results must carry error='grader_workflow_crash' so score.py
    # excludes them from the ratio instead of billing the app.
    from run_workflows import browser_substeps as _bs
    sample_wf = workflows[0]
    b_subs = _bs(sample_wf)
    crash_results = [{"passed": False, "do": s.get("do", ""), "steps_used": 0,
                      "error": "grader_workflow_crash",
                      "note": "workflow crash: RuntimeError: boom"}
                     for s in b_subs]
    for r in crash_results:
        assert r.get("error") == "grader_workflow_crash", \
            f"workflow-crash results must carry grader_workflow_crash, got {r}"
    crash_payload = {"workflows": [{"id": sample_wf["id"], "substeps": crash_results}]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(crash_payload, f)
        crash_path = Path(f.name)
    crash_loaded, _, _ = score.load_browser(crash_path)
    assert all(o is None for o in crash_loaded[sample_wf["id"]]), \
        "workflow-crash substeps must load as None (ungraded)"
    print("[6/6] workflow-crash results carry 'error' key and load as ungraded")

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
