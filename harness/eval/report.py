#!/usr/bin/env python3
"""List rewards across generated trials, with the requirements each one missed.

    python harness/eval/report.py jobs/
    python harness/eval/report.py jobs/2026-08-03__13-16-53 --detail
    python harness/eval/report.py jobs/ --json

Runs SEPARATELY from generation, over jobs already on disk. Reads each trial's
`verifier/reward.json` and `agent/trajectory.json`, and reuses
`verify_trajectory` for the PLAN.md 4.9 retention verdict so one trial never
gets two different answers.

The `--detail` view answers the question the aggregate cannot: WHICH task
requirement failed. That needs the per-workflow block `score.py` writes into
reward.json; trials scored before that field existed show as unavailable rather
than silently empty.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_trajectory import find_trials, inspect_trial  # noqa: E402


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def collect(trial_dir: Path) -> dict:
    reward = load_json(trial_dir / "verifier" / "reward.json")
    trajectory = load_json(trial_dir / "agent" / "trajectory.json")
    audit = inspect_trial(trial_dir)
    metrics = trajectory.get("final_metrics") or {}
    agent = trajectory.get("agent") or {}

    return {
        "trial": trial_dir.name,
        "task": trial_dir.name.rsplit("__", 1)[0],
        "agent": agent.get("name") or "-",
        "model": agent.get("model_name") or "-",
        "reward": reward.get("reward"),
        "deployed": reward.get("deployed"),
        "workflows_passed": reward.get("workflows_passed"),
        "workflows_total": reward.get("workflows_total"),
        "critical_failed": reward.get("critical_substeps_failed"),
        "browser_graded": reward.get("browser_graded"),
        "browser": (reward.get("browser_substeps_passed"), reward.get("browser_substeps_total")),
        "pytest": (reward.get("pytest_substeps_passed"), reward.get("pytest_substeps_total")),
        "detail": (load_json(trial_dir / "verifier" / "workflows.json").get("workflows")
                   or reward.get("workflows")),
        "steps": metrics.get("total_steps") or audit.get("steps") or 0,
        "cost_usd": metrics.get("total_cost_usd"),
        "prompt_tokens": metrics.get("total_prompt_tokens"),
        "completion_tokens": metrics.get("total_completion_tokens"),
        "verdict": audit["verdict"],
    }


def fmt(value, spec: str = "", dash: str = "-") -> str:
    return dash if value is None else format(value, spec)


def print_table(rows: list[dict]) -> None:
    header = (f"{'task':<26} {'agent':<12} {'reward':>7} {'wf':>7} {'crit':>4} "
              f"{'brw':>3} {'steps':>6} {'cost$':>7} {'retain':<8}")
    print(header)
    print("-" * len(header))
    for row in rows:
        wf = (f"{row['workflows_passed']}/{row['workflows_total']}"
              if row["workflows_total"] is not None else "-")
        brw = "y" if row["browser_graded"] else ("n" if row["browser_graded"] is not None else "-")
        print(f"{row['task'][:26]:<26} {row['agent'][:12]:<12} "
              f"{fmt(row['reward'], '.4f'):>7} {wf:>7} "
              f"{fmt(row['critical_failed'], 'd'):>4} {brw:>3} "
              f"{row['steps']:>6} {fmt(row['cost_usd'], '.2f'):>7} {row['verdict']:<8}")


def print_detail(rows: list[dict]) -> None:
    for row in rows:
        print()
        print(f"=== {row['trial']}")
        print(f"    agent {row['agent']} · model {row['model']} · reward "
              f"{fmt(row['reward'], '.4f')} · retain {row['verdict']}")
        if row["browser_graded"] is False:
            print("    browser substeps UNGRADED - reward reflects pytest substeps only")
        bp, bt = row["browser"]
        pp, pt = row["pytest"]
        print(f"    substeps: browser {fmt(bp)}/{fmt(bt)} · pytest {fmt(pp)}/{fmt(pt)}")

        detail = row["detail"]
        if detail is None:
            print("    per-workflow detail unavailable (trial predates score.py's "
                  "`workflows` block)")
            continue
        failed = [w for w in detail if not w["passed"]]
        if not failed:
            print("    every workflow passed")
            continue
        print(f"    {len(failed)} requirement(s) unmet:")
        for workflow in failed:
            flag = " CRITICAL" if workflow["critical_failed"] else ""
            print(f"      - {workflow['id']}  "
                  f"{workflow['substeps_passed']}/{workflow['substeps_graded']} substeps "
                  f"({workflow['ratio']:.0%}){flag}")
            if workflow.get("purpose"):
                print(f"          {workflow['purpose']}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", type=Path)
    parser.add_argument("--detail", action="store_true",
                        help="list the workflows each trial failed")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv[1:])

    trials: list[Path] = []
    for target in args.targets:
        if not target.exists():
            print(f"no such path: {target}", file=sys.stderr)
            continue
        if target.name == "jobs" or (target / "result.json").exists() is False:
            for job in sorted(p for p in target.iterdir() if p.is_dir()):
                trials.extend(find_trials(job))
        else:
            trials.extend(find_trials(target))

    trials = [t for t in dict.fromkeys(trials)]
    if not trials:
        print("no trials found", file=sys.stderr)
        return 2

    rows = [collect(trial) for trial in trials]

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0

    print_table(rows)
    if args.detail:
        print_detail(rows)

    scored = [r["reward"] for r in rows if r["reward"] is not None]
    if scored:
        print()
        print(f"trials {len(rows)} · scored {len(scored)} · "
              f"mean reward {sum(scored) / len(scored):.4f} · "
              f"retained {sum(r['verdict'] == 'KEEP' for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
