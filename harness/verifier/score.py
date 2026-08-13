#!/usr/bin/env python3
"""Aggregate both graders into the Harbor reward (PLAN.md 4.5).

    workflow_pass = passing_substeps / total_substeps >= 0.90
                    AND no substep marked `critical` failed
    reward        = passing_workflows / total_workflows

Browser results are NOT optional. If a workflow declares browser substeps and
they were not graded -- no results file, grader rate-limited, workflow timed out --
the run did not observe the app, and a number derived from the surviving pytest
substeps would be a fabrication. Such a run scores 0.0 with `invalid` naming the
reason, so it can be excluded from training data rather than read as a failure.

reward.json carries exactly one key. Harbor promotes every top-level key to a
reward stream, so all diagnostics live in workflows.json instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

PASS_THRESHOLD = 0.90


def load_ctrf(path: Path) -> dict[str, bool]:
    """Map `<file>::<test>` -> passed, from a CTRF report."""
    if not path.exists():
        return {}
    report = json.loads(path.read_text())
    results = {}
    for test in report.get("results", {}).get("tests", []):
        name = test.get("name", "")
        status = test.get("status", "")
        if not name:
            continue
        results[name] = status == "passed"
        # CTRF names arrive as a full node id; index the short form too so
        # workflows.yaml can reference `file.py::test_name`.
        results[name.split("/")[-1]] = status == "passed"
    return results


def load_browser(path: Path) -> tuple[dict[str, list[bool | None]], bool, list[str]]:
    """Map workflow id -> ordered browser substep outcomes.

    A substep carrying `error` (grader unreachable, workflow timeout) is None, not
    False: the app was never observed, so calling it a failure is a measurement the
    harness did not make. The returned error list is what makes the whole run
    refuse to publish as an ordinary score.
    """
    if not path.exists():
        return {}, False, []
    payload = json.loads(path.read_text())
    outcomes = {
        entry["id"]: [None if step.get("error") else bool(step.get("passed"))
                      for step in entry.get("substeps", [])]
        for entry in payload.get("workflows", [])
    }
    errors = payload.get("meta", {}).get("grader_error") or []
    return outcomes, True, sorted(errors)


def substep_passed(
    substep: dict,
    workflow_id: str,
    browser_index: int,
    pytest_results: dict[str, bool],
    browser_results: dict[str, list[bool | None]],
    browser_graded: bool,
) -> bool | None:
    """True/False, or None when the substep was not graded at all."""
    kind = substep.get("kind")
    if kind == "pytest":
        return pytest_results.get(substep["test"], False)
    if kind == "browser":
        if not browser_graded:
            return None
        outcomes = browser_results.get(workflow_id, [])
        # Missing outcome = the grader emitted fewer results than the workflow
        # declares. That's a harness alignment fault, not an app verdict.
        return outcomes[browser_index] if browser_index < len(outcomes) else None
    # A typo in one substep's `kind` used to SystemExit here, which left the zero
    # preamble from test.sh in place and shipped an infrastructure fault as an
    # ordinary reward:0.0. Fail the substep, keep scoring the rest, and let the
    # invalid-kind count force the run to be flagged rather than silently zeroed.
    print(f"unknown substep kind {kind!r} in workflow {workflow_id!r}; failing it",
          file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflows", type=Path, required=True)
    parser.add_argument("--pytest", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--deployed", type=float, default=1.0)
    parser.add_argument("--judge", type=Path, default=None,
                        help="optional judge.json; its score is copied in as an "
                             "advisory field and never affects reward")
    args = parser.parse_args()

    workflows = yaml.safe_load(args.workflows.read_text())
    pytest_results = load_ctrf(args.pytest)
    browser_results, browser_graded, grader_errors = load_browser(args.browser)

    browser_declared = sum(
        1 for w in workflows for s in w["substeps"] if s.get("kind") == "browser"
    )
    ungraded_browser = 0
    workflows_passed = 0
    substeps_total = substeps_passed = 0
    browser_total = browser_passed = 0
    pytest_total = pytest_passed = 0
    critical_failed = 0
    detail: list[dict] = []

    for workflow in workflows:
        graded: list[bool] = []
        workflow_critical_failed = False
        browser_index = 0

        for substep in workflow["substeps"]:
            outcome = substep_passed(
                substep,
                workflow["id"],
                browser_index,
                pytest_results,
                browser_results,
                browser_graded,
            )
            if substep.get("kind") == "browser":
                browser_index += 1
                if outcome is None:
                    ungraded_browser += 1
                else:
                    browser_total += 1
                    browser_passed += int(outcome)
            else:
                pytest_total += 1
                pytest_passed += int(bool(outcome))

            if outcome is None:
                continue  # ungraded: excluded from the ratio, not counted as a failure

            graded.append(outcome)
            if substep.get("critical") and not outcome:
                workflow_critical_failed = True
                critical_failed += 1

        substeps_total += len(graded)
        substeps_passed += sum(graded)

        ratio = (sum(graded) / len(graded)) if graded else 0.0
        passed = ratio >= PASS_THRESHOLD and not workflow_critical_failed
        workflows_passed += passed

        # Which requirement failed, not just how many: "8/12" without the ids is
        # not actionable for a reviewer. Written to workflows.json rather than
        # reward.json, which Harbor requires to be strictly numeric.
        detail.append({
            "id": workflow["id"],
            "purpose": workflow.get("purpose", ""),
            "passed": passed,
            "substeps_passed": sum(graded),
            "substeps_graded": len(graded),
            "ratio": round(ratio, 4),
            "critical_failed": workflow_critical_failed,
        })

    total = len(workflows)
    reward = (workflows_passed / total) if total else 0.0
    if args.deployed < 1.0:
        reward = 0.0  # deploy failure is a hard zero, no partial credit

    # An ungraded substep used to be dropped from BOTH sides of the ratio, so a
    # browser layer that never ran left the workflow scored on its pytest substeps
    # alone -- and since no workflow in the corpus is browser-only, every workflow
    # still produced a number. That silently converts "we could not measure this"
    # into "the agent scored X". Any ungraded browser substep now invalidates the
    # run: reward 0.0 plus an explicit reason, so it can be filtered out of
    # training data instead of being mistaken for an honest failure.
    # An ungraded substep is a hole in the observation, and a run full of holes
    # cannot be scored. But ALL-OR-NOTHING was too blunt: on 2026-08-13 one
    # substep of 27 came back without a verdict -- the grader model was cut off
    # mid-sentence by max_tokens and replied with prose instead of a tool call --
    # and the run was discarded. It had passed 10 of 11 workflows and 35 of 37
    # pytest checks. A $5.65 agent phase produced nothing.
    #
    # So: tolerate a small fraction, and never let tolerance flatter the app.
    # A workflow holding an ungraded substep is counted as FAILED (already true
    # above, since an ungraded substep is not a passing one), so the reward can
    # only be dragged down by the hole, never lifted by it. Above the threshold
    # the run is invalid exactly as before.
    UNGRADED_TOLERANCE = 0.10
    ungraded_ratio = (ungraded_browser / browser_declared) if browser_declared else 0.0

    invalid: list[str] = []
    if browser_declared and not browser_graded:
        invalid.append("browser_results_missing")
    degraded: list[str] = []
    over_tolerance = ungraded_ratio > UNGRADED_TOLERANCE

    if ungraded_browser and over_tolerance:
        invalid.append("browser_substeps_ungraded")

    # grader_error names the KIND of fault behind those same ungraded substeps
    # (grader_no_tool_call, grader_step_cap, ...), so it has to follow the same
    # rule. Extending `invalid` unconditionally would keep voiding the run for a
    # single tolerated hole and make the tolerance above meaningless.
    #
    # `browser_results_missing` is deliberately NOT subject to this: nothing was
    # observed at all, and there is no ratio to be lenient about.
    if grader_errors:
        (invalid if over_tolerance else degraded).extend(grader_errors)

    # A fault under the tolerance is recorded rather than voiding the run, so the
    # hole is never invisible: the number is publishable, and a reader can still
    # see it was taken with something unobserved.
    if ungraded_browser and not over_tolerance:
        degraded.append(
            f"browser_substeps_ungraded={ungraded_browser}/{browser_declared} "
            f"({ungraded_ratio:.0%} <= {UNGRADED_TOLERANCE:.0%} tolerance); the "
            f"workflows holding them are counted as failed, so the reward is a "
            f"lower bound"
        )
    # test.sh drops ctrf-error.json alongside a missing/empty ctrf.json when pytest
    # collection failed. Without this, all pytest substeps score False and the
    # harness fault bills the agent.
    if (not pytest_results) and (args.pytest.parent / "ctrf-error.json").exists():
        invalid.append("pytest_collection_failed")
    if invalid:
        reward = 0.0

    # Read AFTER reward is final. PLAN.md 1.4: judge_score is recorded but never
    # drives training, because a judge-only reward is trivially gamed. Keeping the
    # read below the arithmetic makes that impossible to violate by accident.
    judge_score = None
    if args.judge and args.judge.exists():
        try:
            judge_score = json.loads(args.judge.read_text()).get("judge_score")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"judge.json unreadable, continuing without it: {exc}", file=sys.stderr)

    # Harbor turns EVERY top-level key of reward.json into a reward stream
    # (VerifierResult.rewards -> JobResult.reward_stats). Twelve diagnostics next
    # to `reward` therefore shipped twelve rewards, and judge_score -- documented
    # above as advisory and trivially gamed -- was registered as a peer of the real
    # one. reward.json is now exactly one key; every diagnostic lives in the
    # sibling file, which Harbor does not interpret.
    summary = {
        "reward": round(reward, 4),
        "invalid": invalid,
        "workflows_total": total,
        "workflows_passed": workflows_passed,
        "substeps_total": substeps_total,
        "substeps_passed": substeps_passed,
        "browser_substeps_declared": browser_declared,
        "browser_substeps_total": browser_total,
        "browser_substeps_passed": browser_passed,
        "browser_substeps_ungraded": ungraded_browser,
        "pytest_substeps_total": pytest_total,
        "pytest_substeps_passed": pytest_passed,
        "critical_substeps_failed": critical_failed,
        "browser_graded": browser_graded,
        "degraded": degraded,
        "deployed": args.deployed,
        "judge_score": judge_score,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    (args.out.parent / "workflows.json").write_text(
        json.dumps({"summary": summary, "workflows": detail}, indent=2) + "\n"
    )
    args.out.write_text(json.dumps({"reward": round(reward, 4)}, indent=2) + "\n")

    if invalid:
        print(f"INVALID RUN ({', '.join(invalid)}): the app was not fully observed; "
              f"reward forced to 0.0 and must not be read as an agent failure",
              file=sys.stderr)
    print(f"reward={reward:.4f} workflows={workflows_passed}/{total} "
          f"critical_failed={critical_failed} browser_graded={browser_graded} "
          f"ungraded_browser={ungraded_browser}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
