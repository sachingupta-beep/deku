#!/usr/bin/env python3
"""Write `usage.json` and `score.json` into a repackaged run directory.

    python harness/publish_report.py output/<task>/<model>/run_N

Both files are DERIVED: everything here is read back out of artefacts the run
already wrote, so regenerating them is always safe and never re-grades anything.

    usage.json   who spent which tokens, per source
    score.json   the weighted score, with each component shown separately

WHY A SECOND SCORE FILE

`reward.json` stays exactly as it is -- one key, `reward`, the workflow pass
rate -- because Harbor promotes every top-level key it finds there into a reward
stream, and because that number is what trains. `score.json` is a REPORT: a
weighted blend for humans comparing runs, carrying its components so nobody has
to trust a single opaque float.

    workflow  50%   passing workflows / total workflows
    pytest    25%   passing pytest substeps / total pytest substeps
    rubric    25%   the rubric judge's own 0-1 score

CAVEAT ON THE RUBRIC QUARTER

PLAN.md 1.4 keeps `judge_score` out of `reward` on purpose: a model judging
rendered output is trivially gamed, and an agent that learns to please a judge
has not learned to build a working app. Blending it in at 25% here is a
reporting choice made deliberately (2026-08-13). It does NOT touch reward.json,
so nothing that trains is affected -- but a `combined_score` should never be fed
back as a training signal without revisiting that decision.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WEIGHTS = {"workflow": 0.50, "pytest": 0.25, "rubric": 0.25}


def _load(path: Path) -> dict:
    """Parse a JSON artefact, or {} when it is absent or unreadable.

    A missing artefact must degrade one component, never crash the report: a run
    whose browser layer died still has real pytest numbers worth recording.
    """
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _usage_row(usage: dict, model: str = "", calls: int = 0) -> dict:
    """Normalise one evaluator's usage block into the shared row shape.

    Graders speak the Anthropic names (`cache_read_input_tokens`); the agent's
    trajectory speaks its own (`total_prompt_tokens`). Callers map their source
    onto this shape so `sources` is comparable row to row.
    """
    inp = usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    cread = usage.get("cache_read_input_tokens") or 0
    cwrite = usage.get("cache_creation_input_tokens") or 0
    return {
        "model": model or usage.get("model_name") or "",
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": cread,
        "cache_write_tokens": cwrite,
        "total_tokens": inp + out + cread + cwrite,
        "request_count": calls or usage.get("calls") or 0,
    }


def build_usage(run: Path) -> dict:
    """Aggregate token spend across the agent and both graders."""
    sources: dict[str, dict] = {}

    # 1. The agent. Its trajectory reports cumulative totals under its own names,
    #    and it is the only source that carries a real cost figure.
    metrics = (_load(run / "trajectory" / "trajectory.json").get("final_metrics") or {})
    if metrics:
        prompt = metrics.get("total_prompt_tokens") or 0
        cached = metrics.get("total_cached_tokens") or 0
        completion = metrics.get("total_completion_tokens") or 0
        sources["agent"] = {
            "model": _load(run / "manifest.json").get("model", ""),
            # total_prompt_tokens INCLUDES cached reads, so uncached input is the
            # difference. Reporting prompt tokens as `input_tokens` would count
            # the cache twice and inflate the total by ~6.7M on a real run.
            "input_tokens": max(0, prompt - cached),
            "output_tokens": completion,
            "cache_read_tokens": cached,
            "cache_write_tokens": 0,
            "total_tokens": prompt + completion,
            "request_count": 0,
            "cost_usd": metrics.get("total_cost_usd") or 0.0,
        }

    # 2. The browser grader (owns the reward) and 3. the rubric judge (advisory).
    for key, rel in (("browser_grader", "logs/browser_results.json"),
                     ("rubric_judge", "logs/judge.json")):
        meta = _load(run / rel).get("meta") or {}
        usage = meta.get("usage") or {}
        if usage:
            sources[key] = _usage_row(
                usage, model=meta.get("grader_model") or usage.get("model_name", ""))

    totals = {k: sum(s.get(k, 0) for s in sources.values())
              for k in ("input_tokens", "output_tokens", "cache_read_tokens",
                        "cache_write_tokens", "total_tokens", "request_count")}
    totals["cost_usd"] = round(sum(s.get("cost_usd", 0.0) for s in sources.values()), 6)
    totals["sources"] = sources
    return totals


def build_score(run: Path) -> dict:
    """Blend the three graded surfaces into one reported score."""
    summary = (_load(run / "workflows.json").get("summary") or {})
    judge = _load(run / "logs" / "judge.json")

    wf_total = summary.get("workflows_total") or 0
    wf_passed = summary.get("workflows_passed") or 0
    py_total = summary.get("pytest_substeps_total") or 0
    py_passed = summary.get("pytest_substeps_passed") or 0
    rubric = judge.get("judge_score")

    # Criteria the judge could not settle. They are excluded from `rubric` above
    # by run_rubric.py rather than scored, so the number here is what a judge would
    # defend -- and the queue is what a human still has to look at.
    review = judge.get("needs_review") or []

    components = {
        "workflow": {"score": (wf_passed / wf_total) if wf_total else None,
                     "passed": wf_passed, "total": wf_total},
        "pytest": {"score": (py_passed / py_total) if py_total else None,
                   "passed": py_passed, "total": py_total},
        "rubric": {"score": rubric,
                   "criteria": judge.get("criteria_total"),
                   "passed": judge.get("criteria_passed"),
                   "failed": judge.get("criteria_failed"),
                   "needs_human_eval": judge.get("needs_human_eval", len(review)),
                   "council": (judge.get("judge_council") or {}).get("members")},
    }

    # A component with no denominator (no rubric file, no pytest substeps) is
    # ABSENT, not zero -- scoring it 0 would punish a run for a surface the task
    # never declared. Weights are renormalised over what actually graded, and
    # `weights_applied` records what that came to.
    present = {k: v["score"] for k, v in components.items() if v["score"] is not None}
    applied = {k: WEIGHTS[k] for k in present}
    denom = sum(applied.values())
    combined = (sum(present[k] * applied[k] for k in present) / denom) if denom else 0.0

    invalid = summary.get("invalid") or []
    # Written beside score.json so the queue is a file a human can work through,
    # not a field buried in a report they have to go looking for.
    if review:
        (run / "review_queue.json").write_text(
            json.dumps({"threshold_note": "criteria the judge declined to score",
                        "count": len(review), "criteria": review}, indent=2) + "\n")
    return {
        # An invalid run never observed the app, so a blended number would be a
        # fabrication in exactly the way reward.json refuses to be.
        "combined_score": 0.0 if invalid else round(combined, 4),
        "weights": WEIGHTS,
        "weights_applied": applied,
        "components": components,
        "reward": summary.get("reward"),
        "invalid": invalid,
        "degraded": summary.get("degraded") or [],
        "needs_human_review": len(review),
        "note": "combined_score is a report, not a training signal; reward.json "
                "is unchanged and remains the workflow pass rate (PLAN.md 1.4)",
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run", type=Path, nargs="+", help="repackaged run directory")
    args = ap.parse_args(argv[1:])

    for run in args.run:
        if not run.is_dir():
            print(f"not a directory: {run}", file=sys.stderr)
            return 1
        usage = build_usage(run)
        score = build_score(run)
        (run / "usage.json").write_text(json.dumps(usage, indent=2) + "\n")
        (run / "score.json").write_text(json.dumps(score, indent=2) + "\n")
        print(f"{run}\n  usage: {usage['total_tokens']:,} tokens "
              f"across {len(usage['sources'])} source(s), ${usage['cost_usd']:.4f}\n"
              f"  score: {score['combined_score']} "
              f"{ {k: (round(v['score'], 4) if v['score'] is not None else None) for k, v in score['components'].items()} }")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
