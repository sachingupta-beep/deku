#!/usr/bin/env python3
"""Build the finance trajectory-usage record for one repackaged run.

Pure stdlib, py3.9-compatible -- repackage.py imports this and runs on the
system python3.

Target payload: POST <base>/ethara_project/trajectory_usage/create, per the
Finance API doc. One record per TRAJECTORY (one trial), carrying the agent
model's token/cost totals plus a `judge_lines` entry for every evaluator model
the harness billed while grading it.

Where each number comes from:

    trajectory_*        agent/trajectory.json -> final_metrics
                        (Harbor's own accounting of the agent phase)
    judge_lines[]       logs/browser_results.json -> meta.usage   (browser grader)
                        logs/judge.json          -> meta.usage    (rubric judge)
                        costed here via pricing.py -- nothing upstream prices them
    subscription_id     claude_account.py (the OAuth account that paid)
    trajectory_id       the trial directory name, e.g. streak-habit-tracker__jZiMs3R
    task_id             the task name

The classification fields (project, team, budget) cannot be derived from a run
-- they are how finance wants the spend attributed, not a property of the
trial -- so they come from DEKU_* environment variables. See ENV below.

Anything the harness could not determine is reported under `_diagnostics` --
split into `blockers` (would make the record wrong; refuse to post) and
`warnings` (incomplete but true; post anyway) -- rather than guessed.
post_usage.py strips `_`-prefixed keys before POSTing, so the file on disk is
both the exact wire payload and its own audit trail.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pricing  # noqa: E402
from claude_account import get_claude_account_info, subscription_id  # noqa: E402

# --- ENV ---------------------------------------------------------------------
# DEKU_PROJECT_ID        finance project, e.g. "PRJ-512"        (required)
# DEKU_PROJECT_TYPE      default "Technical"
# DEKU_TEAM_TYPE         default "Projects"
# DEKU_TASK_ID           default: the task name from the run
# DEKU_BUDGET_TYPE       "RFP" | "Production"                   (required)
# DEKU_RFP_SUB_TYPE      "Testing" | "Sampling"   (RFP only)
# DEKU_PRODUCTION_MODE   "Singlephase" | "Multiphase" (Production only)
# DEKU_SUBSCRIPTION_ID   override the Claude account UUID
# DEKU_MODEL_PRICES      path to a JSON rate override (see pricing.py)

BUDGET_RFP = "RFP"
BUDGET_PRODUCTION = "Production"
RFP_SUB_TYPES = ("Testing", "Sampling")
PRODUCTION_MODES = ("Singlephase", "Multiphase")


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def iso8601(value, blockers: list) -> str:
    """Normalise a timestamp to ISO 8601 WITH an offset.

    The finance doc is explicit that `generated_at` must carry timezone
    information. Harbor writes UTC (often 'Z'-suffixed), which Odoo may or may
    not accept; emitting an explicit +00:00 offset removes the question.

    Falling back to now() is a BLOCKER, not a warning: `generated_at` is what
    finance buckets spend by, so a run from last month stamped with today's
    date silently lands in the wrong period and reconciles against nothing.
    """
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat(timespec="seconds")
        except ValueError:
            blockers.append("unparseable timestamp {!r}; the record would be "
                            "dated to the current time".format(value))
    else:
        blockers.append("run has no finished_at; the record would be dated to "
                        "the current time")
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def budget_fields(blockers: list) -> dict:
    """The four budget/mode fields, with the doc's rules enforced.

    The doc states them as prose ("leave empty for Production", "true for
    Multiphase"), which means a caller can produce a record that is accepted
    and wrong -- RFP with a production_mode set, or Multiphase with
    is_phase_based false. Deriving is_phase_based rather than reading it from
    env, and blanking the field that does not apply, makes that unrepresentable.
    """
    budget = _env("DEKU_BUDGET_TYPE")
    if budget not in (BUDGET_RFP, BUDGET_PRODUCTION):
        blockers.append(
            "DEKU_BUDGET_TYPE is {!r}; expected 'RFP' or 'Production'".format(
                budget or "unset"))

    if budget == BUDGET_RFP:
        sub = _env("DEKU_RFP_SUB_TYPE")
        if sub not in RFP_SUB_TYPES:
            blockers.append(
                "budget_type=RFP needs DEKU_RFP_SUB_TYPE in {}; got {!r}".format(
                    list(RFP_SUB_TYPES), sub or "unset"))
        if _env("DEKU_PRODUCTION_MODE"):
            blockers.append("DEKU_PRODUCTION_MODE ignored: it must be empty "
                            "when budget_type is RFP")
        return {"budget_type": budget, "rfp_sub_type": sub,
                "production_mode": "", "is_phase_based": False}

    mode = _env("DEKU_PRODUCTION_MODE")
    if budget == BUDGET_PRODUCTION and mode not in PRODUCTION_MODES:
        blockers.append(
            "budget_type=Production needs DEKU_PRODUCTION_MODE in {}; "
            "got {!r}".format(list(PRODUCTION_MODES), mode or "unset"))
    if _env("DEKU_RFP_SUB_TYPE"):
        blockers.append("DEKU_RFP_SUB_TYPE ignored: it must be empty when "
                        "budget_type is Production")
    return {"budget_type": budget, "rfp_sub_type": "", "production_mode": mode,
            # Derived, never read from env: the doc ties it to the mode, so a
            # separate switch could only ever contradict it.
            "is_phase_based": mode == "Multiphase"}


def judge_line(source: str, meta: dict, blockers: list):
    """One `judge_lines` entry from a grader's `meta.usage` block.

    Returns None when the grader made no billable calls (skipped, or the trial
    deploy-failed before grading) -- an all-zero line would misreport a grader
    that never ran as one that ran free.
    """
    usage = (meta or {}).get("usage") or {}
    if not usage.get("calls"):
        return None
    model = usage.get("model_name") or (meta or {}).get("grader_model") or ""
    cost = pricing.cost_usd(model, usage)
    if cost is None:
        blockers.append(
            "no price for {} grader model {!r}; judge_cost_usd would be null. "
            "Add a rate to harness/finance/pricing.py or set DEKU_MODEL_PRICES."
            .format(source, model))
    return {
        "model_name": model,
        "judge_input_tokens": usage.get("input_tokens", 0),
        "judge_output_tokens": usage.get("output_tokens", 0),
        "judge_input_cache_tokens": usage.get("cache_read_input_tokens", 0),
        "judge_output_cache_tokens": usage.get("cache_creation_input_tokens", 0),
        "judge_cost_usd": cost,
    }


def build_payload(run_dir: Path) -> dict:
    """The finance record for one repackaged run (output/<task>/<model>/run_N).

    Two severities, because they need different answers:

      blockers  the record would be WRONG if posted -- misattributed, mispriced,
                or dated to the wrong period. post_usage.py refuses to send it.
      warnings  the record is right but incomplete. It still posts, because the
                alternative is never billing a trajectory that genuinely cost
                money. The canonical case is a deploy-failed trial: the agent
                phase ran and was paid for, grading never happened, so there
                are no judge lines and that is the truth, not a gap.
    """
    run_dir = Path(run_dir)
    blockers: list = []
    warnings: list = []

    manifest = _load(run_dir / "manifest.json")
    metrics = (_load(run_dir / "trajectory" / "trajectory.json")
               .get("final_metrics") or {})

    # Grader usage, preferring workflows.json.
    #
    # score.py copies both graders' usage into workflows.json specifically
    # because that file survives collection on both grading paths, while
    # browser_results.json does not survive Harbor's in-place collection. The
    # graders' own files are the fallback: they are present on an eval_fresh
    # regrade (which docker-cps the whole verifier directory), and reading them
    # keeps this working if score.py is ever run without the summary field.
    summary_usage = ((_load(run_dir / "workflows.json").get("summary") or {})
                     .get("grader_usage") or {})
    browser_meta = ({"usage": summary_usage["browser"]} if "browser" in summary_usage
                    else _load(run_dir / "logs" / "browser_results.json").get("meta") or {})
    judge_meta = ({"usage": summary_usage["rubric"]} if "rubric" in summary_usage
                  else _load(run_dir / "logs" / "judge.json").get("meta") or {})

    if not manifest:
        blockers.append("no manifest.json in {} -- run repackage.py first"
                        .format(run_dir))
    if not metrics:
        blockers.append("trajectory has no final_metrics, so every token count "
                        "and the cost would post as 0")

    task = manifest.get("task") or run_dir.parts[-3]
    model = manifest.get("model") or run_dir.parts[-2]
    trial_id = manifest.get("trial_id") or run_dir.name

    # `trajectory_id` is finance's per-trajectory key, so it has to be globally
    # unique. Without a trial_id it degrades to the directory name -- "run_2",
    # which repeats under every task/model pair and would collide across
    # unrelated trajectories. (26 of the 28 currently-published runs predate
    # manifest.json entirely and are already blocked above; this catches the
    # narrower case of a manifest that exists but omits the field.)
    if not manifest.get("trial_id"):
        blockers.append(
            "manifest has no trial_id, so trajectory_id would fall back to "
            "{!r} -- not unique across tasks. Re-run repackage.py for this "
            "trial.".format(run_dir.name))

    # A trial directory is "<task>__<suffix>", so the two fields must agree.
    # They disagree on runs published before repackage.py started deriving the
    # task from the trial directory: a variant task (tasks/oracle-streak,
    # which declares the name "ethara/streak-habit-tracker") was filed under
    # the task it is a variant OF. Posting that pair bills one task's spend to
    # another, which is exactly the misattribution finance would never catch.
    if "__" in trial_id and trial_id.rsplit("__", 1)[0] != task:
        blockers.append(
            "task {!r} does not match trajectory {!r}; this run was published "
            "before repackage.py derived the task from the trial directory. "
            "Re-run repackage.py for this trial before billing it."
            .format(task, trial_id))

    sub_id = subscription_id()
    if not sub_id:
        account = get_claude_account_info()
        blockers.append(
            "no subscription_id: {}. Set DEKU_SUBSCRIPTION_ID to attribute this "
            "record.".format(account.get("error") or "account lookup returned "
                                                     "no uuid"))

    project_id = _env("DEKU_PROJECT_ID")
    if not project_id:
        blockers.append("DEKU_PROJECT_ID is unset; finance cannot attribute "
                        "this record to a project")

    # Harbor already costs the agent phase; do not recompute it here. Its number
    # is derived from the per-step usage the agent actually consumed, which this
    # module never sees, and two sources of truth for one field is how finance
    # records start disagreeing with the platform bill.
    trajectory_cost = metrics.get("total_cost_usd")
    if trajectory_cost is None and metrics:
        blockers.append("trajectory has no total_cost_usd; it would post as 0")

    lines = []
    for source, meta in (("browser", browser_meta), ("rubric", judge_meta)):
        # A judge COUNCIL bills two models, and each must be priced separately:
        # `usage.model_name` is a comma-joined label ("opus-5, sonnet-4-6") that
        # pricing.py cannot resolve, and an unpriced model blocks the WHOLE
        # record -- agent cost included. `per_member` carries each model's own
        # totals, so emit one judge_line per member.
        per_member = ((meta or {}).get("usage") or {}).get("per_member") or {}
        if len(per_member) > 1:
            for label, snap in per_member.items():
                line = judge_line(f"{source}:{label}", {"usage": snap}, blockers)
                if line is not None:
                    lines.append(line)
            continue
        line = judge_line(source, meta, blockers)
        if line is not None:
            lines.append(line)
    if not lines:
        # Warning, not a blocker -- see the docstring. Empty judge_lines is the
        # honest answer for a trial that never reached grading, and for trials
        # published before graders were instrumented the numbers are simply
        # unrecoverable; refusing to bill those forever loses real spend.
        warnings.append("no grader usage recorded; this trial predates grader "
                        "token accounting, or it never reached grading "
                        "(deploy failure). judge_lines is empty.")

    payload = {
        "project_id": project_id,
        "project_type": _env("DEKU_PROJECT_TYPE", "Technical"),
        "task_id": _env("DEKU_TASK_ID") or task,
        # The trial directory name is the harness's unique per-trajectory id
        # (task__<8-char suffix>), and it is what every artifact on disk is
        # filed under -- so a finance row can always be traced back to a run.
        "trajectory_id": manifest.get("trial_id") or run_dir.name,
        "team_type": _env("DEKU_TEAM_TYPE", "Projects"),
        "generated_at": iso8601(manifest.get("finished_at"), blockers),
        "model_name": model,
        "trajectory_input_tokens": metrics.get("total_prompt_tokens", 0),
        "trajectory_output_tokens": metrics.get("total_completion_tokens", 0),
        # Harbor reports one cache figure (`total_cached_tokens`) and it counts
        # cache READS. There is no cache-creation figure in final_metrics, so
        # the output-cache field is 0 rather than a fabricated split.
        "trajectory_input_cache_tokens": metrics.get("total_cached_tokens", 0),
        "trajectory_output_cache_tokens": 0,
        "trajectory_cost_usd": trajectory_cost or 0,
        "subscription_id": sub_id,
        "judge_lines": lines,
    }
    payload.update(budget_fields(blockers))

    payload["_diagnostics"] = {
        "run_dir": str(run_dir),
        "reward": manifest.get("reward"),
        "deployed": manifest.get("deployed"),
        "invalid": manifest.get("invalid") or [],
        "graded_by": manifest.get("graded_by"),
        "blockers": blockers,
        "warnings": warnings,
        "postable": not blockers,
    }
    return payload


def wire_payload(payload: dict) -> dict:
    """The payload as it goes on the wire: local-only `_` keys removed."""
    return {k: v for k, v in payload.items() if not k.startswith("_")}
