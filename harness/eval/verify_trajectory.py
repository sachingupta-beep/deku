#!/usr/bin/env python3
"""Apply PLAN.md 4.9's quality filters to generated trajectories.

    python harness/eval/verify_trajectory.py jobs/2026-08-03__13-16-53
    python harness/eval/verify_trajectory.py jobs/*/            --json

Runs SEPARATELY from generation, over trajectories already on disk.

Three verdicts, and the distinction between the last two is the point (PLAN.md 4.9):

  KEEP     Retained. A run that finished and scored 0 is a NEGATIVE EXAMPLE, not
           waste -- on a task the model nearly solves, those are the runs RL
           learns from.
  DISCARD  A quality filter tripped. The trajectory is unusable as training data.
  RERUN    The trial never produced a score (harness-level loss). It must be
           re-run so the task still has a full N, because a sweep that silently
           drops trials yields pass_rate values with different denominators and
           breaks comparability.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MAX_SINGLE_CALL_INPUT_TOKENS = 50_000

HARNESS_LOSS_SIGNATURES = (
    "RewardFileNotFoundError",
    "sandbox crash",
    "provider timeout",
    "ContainerError",
    "EnvironmentError",
)

UNKNOWN_TOOL_SIGNATURES = (
    "no such tool",
    "unknown tool",
    "tool not found",
    "is not a valid tool",
    "unrecognized tool",
)

COMPACTION_SIGNATURES = (
    "conversation compacted",
    "context compacted",
    "previous conversation summarized",
    "compact_boundary",
)


class Finding(dict):
    def __init__(self, verdict: str, rule: str, detail: str) -> None:
        super().__init__(verdict=verdict, rule=rule, detail=detail)


def steps_of(trajectory: dict) -> list[dict]:
    return trajectory.get("steps") or []


def check_call_size(steps: list[dict]) -> list[Finding]:
    """Client requirement: no single call may exceed 50K input tokens.

    Both figures are reported because the threshold's meaning is a policy choice
    the harness owner must make explicitly, and the two answers differ by an
    order of magnitude on cache-heavy agents:

      total    prompt + cache_read -- the whole context the model attended to
      uncached prompt only         -- what was freshly sent on the wire

    Counting total is the literal reading, and under it a long-horizon agent
    fails on essentially every call once its context is warm.
    """
    worst_total = worst_uncached = 0
    offenders_total = offenders_uncached = 0
    for step in steps:
        metrics = step.get("metrics") or {}
        uncached = metrics.get("prompt_tokens") or 0
        total = uncached + (metrics.get("cached_tokens") or 0)
        worst_total = max(worst_total, total)
        worst_uncached = max(worst_uncached, uncached)
        offenders_total += total > MAX_SINGLE_CALL_INPUT_TOKENS
        offenders_uncached += uncached > MAX_SINGLE_CALL_INPUT_TOKENS
    if not offenders_total:
        return []
    return [Finding(
        "DISCARD", "single-call-input-tokens",
        f"{offenders_total}/{len(steps)} calls over {MAX_SINGLE_CALL_INPUT_TOKENS:,} "
        f"total input (worst {worst_total:,}); "
        f"{offenders_uncached} over on uncached alone (worst {worst_uncached:,})",
    )]


def check_hallucinated_tools(steps: list[dict]) -> list[Finding]:
    """A tool call the runtime rejected as unknown.

    Detected from the observation's error text rather than a per-agent tool
    registry: the registry would need maintaining for every agent in the matrix
    and would go stale silently, whereas the rejection message is produced by
    the runtime itself.
    """
    findings = []
    for step in steps:
        observation = str(step.get("observation") or "").lower()
        for signature in UNKNOWN_TOOL_SIGNATURES:
            if signature in observation:
                names = [
                    tc.get("function_name")
                    for tc in (step.get("tool_calls") or [])
                    if isinstance(tc, dict)
                ]
                findings.append(Finding(
                    "DISCARD", "hallucinated-tool-call",
                    f"step {step.get('step_id')}: runtime rejected {names or '<unnamed>'} "
                    f"({signature!r})",
                ))
                break
    return findings


def check_compaction(steps: list[dict], instruction: str | None) -> list[Finding]:
    """Context summarization that corrupted the agent's grasp of instruction.md.

    Compaction itself is normal and not disqualifying. What PLAN.md 4.9 rejects
    is compaction that DAMAGED the requirements -- and instruction.md is now the
    only document, so there is no redundant copy to recover from. Whether the
    understanding actually broke is a judgement call, so this reports for review
    instead of auto-discarding.
    """
    events = 0
    for step in steps:
        blob = f"{step.get('message')} {step.get('observation')}".lower()
        if any(signature in blob for signature in COMPACTION_SIGNATURES):
            events += 1
    if not events:
        return []
    return [Finding(
        "REVIEW", "context-compaction",
        f"{events} compaction event(s); confirm instruction.md requirements survived",
    )]


def check_harness_loss(trial_dir: Path) -> list[Finding]:
    """A trial that errored at the harness level is LOST, not failed."""
    exception_file = trial_dir / "exception.txt"
    if exception_file.exists():
        text = exception_file.read_text(errors="replace")
        matched = next((s for s in HARNESS_LOSS_SIGNATURES if s.lower() in text.lower()), None)
        tail = text.strip().splitlines()[-1][:160] if text.strip() else "empty"
        return [Finding(
            "RERUN", "harness-level-error",
            f"{matched or 'trial raised'}: {tail}",
        )]
    return []


def check_scored(trial_dir: Path) -> tuple[float | None, list[Finding]]:
    reward_file = trial_dir / "verifier" / "reward.json"
    if not reward_file.exists():
        return None, [Finding(
            "RERUN", "no-reward-file",
            "verifier wrote no reward.json - trial produced no score",
        )]
    try:
        reward = float(json.loads(reward_file.read_text()).get("reward"))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return None, [Finding("RERUN", "unreadable-reward", f"{type(exc).__name__}: {exc}")]
    return reward, []


def verdict_of(findings: list[Finding]) -> str:
    for level in ("RERUN", "DISCARD"):
        if any(f["verdict"] == level for f in findings):
            return level
    return "KEEP"


def inspect_trial(trial_dir: Path) -> dict:
    trajectory_file = trial_dir / "agent" / "trajectory.json"
    record: dict = {
        "trial": trial_dir.name,
        "path": str(trial_dir),
        "reward": None,
        "steps": 0,
        "findings": [],
    }

    findings: list[Finding] = []
    findings += check_harness_loss(trial_dir)
    reward, reward_findings = check_scored(trial_dir)
    findings += reward_findings
    record["reward"] = reward

    if trajectory_file.exists():
        trajectory = json.loads(trajectory_file.read_text())
        steps = steps_of(trajectory)
        record["steps"] = len(steps)
        record["agent"] = (trajectory.get("agent") or {}).get("name")
        record["model"] = (trajectory.get("agent") or {}).get("model_name")
        record["final_metrics"] = trajectory.get("final_metrics") or {}
        findings += check_call_size(steps)
        findings += check_hallucinated_tools(steps)
        findings += check_compaction(steps, None)
    else:
        findings.append(Finding(
            "RERUN", "no-trajectory",
            "agent/trajectory.json absent - nothing to retain",
        ))

    record["findings"] = findings
    record["verdict"] = verdict_of(findings)
    return record


def find_trials(target: Path) -> list[Path]:
    if (target / "agent").is_dir() or (target / "verifier").is_dir():
        return [target]
    return sorted(
        child for child in target.iterdir()
        if child.is_dir() and ((child / "agent").is_dir() or (child / "verifier").is_dir())
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("targets", nargs="+", type=Path,
                        help="job directories or a single trial directory")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv[1:])

    records = []
    for target in args.targets:
        if not target.exists():
            print(f"no such path: {target}", file=sys.stderr)
            continue
        for trial in find_trials(target):
            records.append(inspect_trial(trial))

    if not records:
        print("no trials found", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(records, indent=2, default=str))
        return 0

    print(f"{'verdict':<8} {'reward':>7} {'steps':>6}  trial")
    print("-" * 78)
    for record in records:
        reward = "-" if record["reward"] is None else f"{record['reward']:.4f}"
        print(f"{record['verdict']:<8} {reward:>7} {record['steps']:>6}  {record['trial']}")
        for finding in record["findings"]:
            print(f"         [{finding['verdict']}] {finding['rule']}: {finding['detail']}")

    counts: dict[str, int] = {}
    for record in records:
        counts[record["verdict"]] = counts.get(record["verdict"], 0) + 1
    print("-" * 78)
    print("  ".join(f"{verdict}={count}" for verdict, count in sorted(counts.items())))
    if counts.get("RERUN"):
        print(f"\n{counts['RERUN']} trial(s) must be RE-RUN to restore the sweep's N "
              f"(PLAN.md 4.9) - they are lost, not failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
