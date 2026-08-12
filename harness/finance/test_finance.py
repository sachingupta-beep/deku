#!/usr/bin/env python3
"""Tests for the finance trajectory-usage record.

    .venv/bin/pytest harness/finance/test_finance.py

The subject is a payload posted into an accounting system, so the tests target
the failure modes that are expensive precisely because they are silent: a
budget record that contradicts the doc's rules, a cost computed from a rate
nobody has for that model, and a warning-free record that is actually missing
its attribution.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pricing  # noqa: E402
import usage  # noqa: E402


# ----------------------------------------------------------------- fixtures
@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """A minimal repackaged run: manifest + trajectory + both grader outputs."""
    run = tmp_path / "streak-habit-tracker" / "claude-opus-4-8" / "run_1"
    (run / "trajectory").mkdir(parents=True)
    (run / "logs").mkdir()

    (run / "manifest.json").write_text(json.dumps({
        "task": "streak-habit-tracker",
        "model": "claude-opus-4-8",
        "trial_id": "streak-habit-tracker__jZiMs3R",
        "reward": 0.9,
        "deployed": 1.0,
        "invalid": [],
        "finished_at": "2026-08-04T11:28:00Z",
        "graded_by": "verifier",
    }))
    (run / "trajectory" / "trajectory.json").write_text(json.dumps({
        "final_metrics": {
            "total_prompt_tokens": 7211997,
            "total_completion_tokens": 71071,
            "total_cached_tokens": 7102131,
            "total_cost_usd": 6.014226749999995,
        }
    }))
    (run / "logs" / "browser_results.json").write_text(json.dumps({
        "meta": {"grader_model": "claude-sonnet-4-6", "usage": {
            "model_name": "claude-sonnet-4-6", "provider": "anthropic",
            "calls": 40, "input_tokens": 200_000, "output_tokens": 20_000,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100_000,
        }}
    }))
    (run / "logs" / "judge.json").write_text(json.dumps({
        "meta": {"grader_model": "claude-sonnet-4-6", "usage": {
            "model_name": "claude-sonnet-4-6", "provider": "anthropic",
            "calls": 7, "input_tokens": 50_000, "output_tokens": 5_000,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
        }}
    }))
    return run


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("DEKU_PROJECT_ID", "DEKU_PROJECT_TYPE", "DEKU_TEAM_TYPE",
                 "DEKU_TASK_ID", "DEKU_BUDGET_TYPE", "DEKU_RFP_SUB_TYPE",
                 "DEKU_PRODUCTION_MODE", "DEKU_MODEL_PRICES"):
        monkeypatch.delenv(name, raising=False)
    # Never touch the keychain or the network from a test.
    monkeypatch.setenv("DEKU_SUBSCRIPTION_ID", "SUB-TEST")


def rfp(monkeypatch):
    monkeypatch.setenv("DEKU_PROJECT_ID", "PRJ-512")
    monkeypatch.setenv("DEKU_BUDGET_TYPE", "RFP")
    monkeypatch.setenv("DEKU_RFP_SUB_TYPE", "Testing")


# ------------------------------------------------------------------ pricing
def test_dated_snapshot_resolves_to_its_family_rate():
    assert pricing.rates("claude-opus-4-8-20260101") == (5.00, 25.00)


def test_unknown_model_is_unpriced_not_guessed():
    # The whole point: no rate must never become a plausible-looking number.
    assert pricing.rates("some-future-model") is None
    assert pricing.cost_usd("some-future-model", {"input_tokens": 1_000_000}) is None


def test_cache_tokens_are_cheaper_than_fresh_input():
    fresh = pricing.cost_usd("claude-sonnet-4-6", {"input_tokens": 1_000_000})
    cached = pricing.cost_usd("claude-sonnet-4-6",
                              {"cache_read_input_tokens": 1_000_000})
    written = pricing.cost_usd("claude-sonnet-4-6",
                               {"cache_creation_input_tokens": 1_000_000})
    assert fresh == 3.0
    assert cached == pytest.approx(0.30)     # 0.10x input
    assert written == pytest.approx(3.75)    # 1.25x input


def test_price_override_file_wins(tmp_path, monkeypatch):
    override = tmp_path / "prices.json"
    override.write_text(json.dumps({"claude-opus-4-8": [1.0, 2.0]}))
    monkeypatch.setenv("DEKU_MODEL_PRICES", str(override))
    assert pricing.rates("claude-opus-4-8") == (1.0, 2.0)


def test_unreadable_override_is_ignored_not_fatal(monkeypatch):
    monkeypatch.setenv("DEKU_MODEL_PRICES", "/nonexistent/prices.json")
    assert pricing.rates("claude-opus-4-8") == (5.00, 25.00)


# ------------------------------------------------------------ budget rules
def test_rfp_blanks_production_mode_and_is_never_phase_based(monkeypatch):
    rfp(monkeypatch)
    monkeypatch.setenv("DEKU_PRODUCTION_MODE", "Multiphase")  # contradictory
    fields = usage.budget_fields([])
    assert fields == {"budget_type": "RFP", "rfp_sub_type": "Testing",
                      "production_mode": "", "is_phase_based": False}


def test_is_phase_based_is_derived_from_the_mode(monkeypatch):
    monkeypatch.setenv("DEKU_BUDGET_TYPE", "Production")
    monkeypatch.setenv("DEKU_PRODUCTION_MODE", "Multiphase")
    assert usage.budget_fields([])["is_phase_based"] is True
    monkeypatch.setenv("DEKU_PRODUCTION_MODE", "Singlephase")
    assert usage.budget_fields([])["is_phase_based"] is False


def test_missing_budget_type_warns(monkeypatch):
    warnings = []
    usage.budget_fields(warnings)
    assert any("DEKU_BUDGET_TYPE" in w for w in warnings)


# ---------------------------------------------------------------- payload
def test_complete_run_produces_a_postable_record(run_dir, monkeypatch):
    rfp(monkeypatch)
    payload = usage.build_payload(run_dir)

    assert payload["_diagnostics"]["blockers"] == []
    assert payload["_diagnostics"]["warnings"] == []
    assert payload["_diagnostics"]["postable"] is True
    assert payload["trajectory_id"] == "streak-habit-tracker__jZiMs3R"
    assert payload["task_id"] == "streak-habit-tracker"
    assert payload["subscription_id"] == "SUB-TEST"
    assert payload["trajectory_input_tokens"] == 7211997
    assert payload["trajectory_input_cache_tokens"] == 7102131
    assert payload["trajectory_cost_usd"] == pytest.approx(6.0142267)
    # generated_at must carry an offset -- the finance doc requires it.
    assert payload["generated_at"].endswith("+00:00")


def test_both_graders_become_separate_judge_lines(run_dir, monkeypatch):
    rfp(monkeypatch)
    lines = usage.build_payload(run_dir)["judge_lines"]
    assert len(lines) == 2, "browser grader and rubric judge are separate lines"
    browser, judge = lines
    assert browser["judge_input_tokens"] == 200_000
    assert browser["judge_input_cache_tokens"] == 100_000
    # 200k in @ $3 + 20k out @ $15 + 100k cache-read @ $0.30 = 0.6 + 0.3 + 0.03
    assert browser["judge_cost_usd"] == pytest.approx(0.93)
    assert judge["judge_cost_usd"] == pytest.approx(0.225)


def test_workflows_json_usage_wins_over_the_graders_own_file(run_dir, monkeypatch):
    """workflows.json is the path that survives Harbor's in-place collection.

    browser_results.json is never collected on the primary grading path, so
    score.py copies both graders' usage into workflows.json. When both exist
    (an eval_fresh regrade), the summary must win -- it is the one score.py
    actually computed for this grading run.
    """
    rfp(monkeypatch)
    (run_dir / "workflows.json").write_text(json.dumps({"summary": {"grader_usage": {
        "browser": {"model_name": "claude-sonnet-4-6", "calls": 1,
                    "input_tokens": 1_000_000, "output_tokens": 0,
                    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
    }}}))
    lines = usage.build_payload(run_dir)["judge_lines"]
    assert lines[0]["judge_input_tokens"] == 1_000_000, "summary must win"
    assert lines[0]["judge_cost_usd"] == pytest.approx(3.0)
    # The rubric has no summary entry, so it still falls back to judge.json.
    assert lines[1]["judge_input_tokens"] == 50_000


def test_grader_that_never_ran_is_omitted_not_zeroed(run_dir, monkeypatch):
    """DEKU_SKIP_RUBRIC leaves no usage -- an all-zero line would claim it ran free."""
    rfp(monkeypatch)
    (run_dir / "logs" / "judge.json").write_text(json.dumps(
        {"meta": {"skipped": "DEKU_SKIP_RUBRIC"}}))
    payload = usage.build_payload(run_dir)
    assert len(payload["judge_lines"]) == 1
    assert payload["_diagnostics"]["postable"] is True


def test_unpriced_grader_model_nulls_the_cost_and_blocks(run_dir, monkeypatch):
    rfp(monkeypatch)
    (run_dir / "logs" / "judge.json").write_text(json.dumps({
        "meta": {"usage": {"model_name": "gpt-5-turbo", "calls": 3,
                           "input_tokens": 1000, "output_tokens": 100}}}))
    payload = usage.build_payload(run_dir)
    assert payload["judge_lines"][-1]["judge_cost_usd"] is None
    assert payload["_diagnostics"]["postable"] is False
    assert any("no price" in b for b in payload["_diagnostics"]["blockers"])


def test_missing_project_id_makes_the_record_unpostable(run_dir, monkeypatch):
    monkeypatch.setenv("DEKU_BUDGET_TYPE", "RFP")
    monkeypatch.setenv("DEKU_RFP_SUB_TYPE", "Testing")
    payload = usage.build_payload(run_dir)
    assert payload["_diagnostics"]["postable"] is False
    assert any("DEKU_PROJECT_ID" in b for b in payload["_diagnostics"]["blockers"])


def test_task_trajectory_mismatch_blocks(run_dir, monkeypatch):
    """The stale-artifact trap: a variant task filed under the task it varies.

    Found on a real published run -- output/streak-habit-tracker/.../run_1
    carries trial_id oracle-streak__DYAyEJm, because it was repackaged before
    repackage.py derived the task from the trial directory. Posting that pair
    bills oracle-streak's spend to streak-habit-tracker.
    """
    rfp(monkeypatch)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    manifest["trial_id"] = "oracle-streak__DYAyEJm"
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    payload = usage.build_payload(run_dir)
    assert payload["_diagnostics"]["postable"] is False
    assert any("does not match trajectory" in b
               for b in payload["_diagnostics"]["blockers"])


def test_missing_trial_id_blocks_a_non_unique_trajectory_id(run_dir, monkeypatch):
    """trajectory_id must not degrade to "run_1", which repeats under every task."""
    rfp(monkeypatch)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    del manifest["trial_id"]
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    payload = usage.build_payload(run_dir)
    assert payload["_diagnostics"]["postable"] is False
    assert any("not unique" in b for b in payload["_diagnostics"]["blockers"])


def test_missing_finished_at_blocks_rather_than_dating_to_now(run_dir, monkeypatch):
    """generated_at buckets the spend; today's date on an old run is silent rot."""
    rfp(monkeypatch)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    del manifest["finished_at"]
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    payload = usage.build_payload(run_dir)
    assert payload["_diagnostics"]["postable"] is False
    assert any("finished_at" in b for b in payload["_diagnostics"]["blockers"])


def test_deploy_failed_run_still_bills(run_dir, monkeypatch):
    """A zero-reward trial consumed a paid trajectory -- it must still post.

    No grader ever ran, so empty judge_lines is the truth rather than a gap.
    That is a warning, and warnings do not block: refusing to bill these would
    quietly drop every failed trial's agent spend from the ledger.
    """
    rfp(monkeypatch)
    (run_dir / "logs" / "browser_results.json").unlink()
    (run_dir / "logs" / "judge.json").unlink()
    payload = usage.build_payload(run_dir)
    assert payload["trajectory_cost_usd"] > 0
    assert payload["judge_lines"] == []
    assert any("no grader usage" in w
               for w in payload["_diagnostics"]["warnings"])
    assert payload["_diagnostics"]["blockers"] == []
    assert payload["_diagnostics"]["postable"] is True


def test_wire_payload_strips_local_only_keys(run_dir, monkeypatch):
    rfp(monkeypatch)
    wire = usage.wire_payload(usage.build_payload(run_dir))
    assert "_diagnostics" not in wire
    assert set(wire) == {
        "project_id", "project_type", "task_id", "trajectory_id", "team_type",
        "budget_type", "rfp_sub_type", "production_mode", "is_phase_based",
        "generated_at", "model_name", "trajectory_input_tokens",
        "trajectory_output_tokens", "trajectory_input_cache_tokens",
        "trajectory_output_cache_tokens", "trajectory_cost_usd",
        "subscription_id", "judge_lines",
    }, "wire payload must match the finance doc's field list exactly"
