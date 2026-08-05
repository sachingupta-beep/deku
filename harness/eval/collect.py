#!/usr/bin/env python3
"""Flatten every trial on disk into one table plus a CSV.

    python harness/eval/collect.py                 # table to stdout
    python harness/eval/collect.py --csv out.csv   # also write CSV

Reads config.json (agent + model, written at trial start), trajectory.json
(effort and cost) and verifier/reward.json (the score). Trials missing any of
those are still listed, with blanks, so a lost or aborted run stays visible
rather than silently vanishing from the comparison.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

FIELDS = [
    "job", "task", "agent", "model", "steps", "cost_usd", "out_tokens",
    "reward", "deployed", "substeps_passed", "substeps_total",
    "browser_passed", "browser_total", "pytest_passed", "pytest_total",
    "judge_score",
]


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def collect(jobs_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for job in sorted(jobs_dir.iterdir()):
        if not job.is_dir():
            continue
        for trial in sorted(job.glob("*__*")):
            agent_cfg = (read_json(trial / "config.json").get("agent") or {})
            traj = read_json(trial / "agent" / "trajectory.json")
            metrics = traj.get("final_metrics") or {}
            reward = read_json(trial / "verifier" / "reward.json")
            rows.append({
                "job": job.name,
                "task": trial.name.rsplit("__", 1)[0],
                "agent": agent_cfg.get("name") or "",
                "model": agent_cfg.get("model_name") or "",
                "steps": len(traj.get("steps") or []),
                "cost_usd": metrics.get("total_cost_usd") or 0.0,
                "out_tokens": metrics.get("total_completion_tokens") or 0,
                "reward": reward.get("reward"),
                "deployed": reward.get("deployed"),
                "substeps_passed": reward.get("substeps_passed"),
                "substeps_total": reward.get("substeps_total"),
                "browser_passed": reward.get("browser_substeps_passed"),
                "browser_total": reward.get("browser_substeps_total"),
                "pytest_passed": reward.get("pytest_substeps_passed"),
                "pytest_total": reward.get("pytest_substeps_total"),
                "judge_score": reward.get("judge_score"),
            })
    return rows


def fmt(value, spec: str = "", dash: str = "-") -> str:
    return dash if value is None else format(value, spec)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jobs", type=Path, default=Path("jobs"))
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args()

    rows = collect(args.jobs)
    if not rows:
        print("no trials found")
        return 1

    header = (f"{'started':<18}{'agent':<12}{'model':<26}{'steps':>6}"
              f"{'cost$':>8}{'reward':>7}{'dep':>5}{'subs':>8}")
    print(header)
    print("-" * len(header))
    for r in rows:
        subs = ("-" if r["substeps_total"] is None
                else f"{r['substeps_passed']}/{r['substeps_total']}")
        print(f"{r['job'][:18]:<18}{(r['agent'] or '-')[:12]:<12}"
              f"{(r['model'] or '-')[:26]:<26}{r['steps']:>6}"
              f"{r['cost_usd']:>8.2f}{fmt(r['reward'], '.4f'):>7}"
              f"{fmt(r['deployed'], '.0f'):>5}{subs:>8}")

    scored = [r for r in rows if r["reward"] is not None]
    print("-" * len(header))
    print(f"trials {len(rows)} · scored {len(scored)} · "
          f"total spend ${sum(r['cost_usd'] for r in rows):.2f}")

    if args.csv:
        with args.csv.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"csv -> {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
