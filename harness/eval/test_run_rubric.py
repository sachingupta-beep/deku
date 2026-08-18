#!/usr/bin/env python3
"""Pure-function tests for run_rubric. No browser, no LLM."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_rubric as rr

REPO_ROOT = HERE.parent.parent
STREAK_INSTRUCTION = REPO_ROOT / "tasks" / "streak-habit-tracker" / "instruction.md"


def test_weights_sum_to_one() -> None:
    total = sum(w for _n, w, _a in rr.RUBRIC)
    assert abs(total - 1.0) < 1e-9, f"weights sum to {total}, not 1.0"
    print(f"  weights sum = {total}")


def test_score_all_ones() -> None:
    dims = {name: {"score": 1.0} for name, _, _ in rr.RUBRIC}
    s = rr.compute_judge_score(dims)
    assert s == 1.0, f"all-1.0 gave {s}"
    print(f"  all-1.0 -> {s}")


def test_score_all_zeros() -> None:
    dims = {name: {"score": 0.0} for name, _, _ in rr.RUBRIC}
    s = rr.compute_judge_score(dims)
    assert s == 0.0, f"all-0.0 gave {s}"
    print(f"  all-0.0 -> {s}")


def test_score_mixed_matches_hand_calc() -> None:
    scores = {
        "instruction_following": 0.8,   # 0.8 * 0.30 = 0.24
        "functionality":         0.6,   # 0.6 * 0.25 = 0.15
        "ux_flow":               0.7,   # 0.7 * 0.15 = 0.105
        "ui_visual":             0.5,   # 0.5 * 0.15 = 0.075
        "motion":                0.4,   # 0.4 * 0.05 = 0.02
        "accessibility":         0.3,   # 0.3 * 0.05 = 0.015
        "responsiveness":        0.9,   # 0.9 * 0.05 = 0.045
    }
    expected = round(0.24 + 0.15 + 0.105 + 0.075 + 0.02 + 0.015 + 0.045, 4)
    dims = {k: {"score": v} for k, v in scores.items()}
    got = rr.compute_judge_score(dims)
    assert got == expected, f"expected {expected}, got {got}"
    print(f"  mixed = {got} (expected {expected})")


def test_score_clamps_out_of_range() -> None:
    dims = {name: {"score": 2.5} for name, _, _ in rr.RUBRIC}
    s = rr.compute_judge_score(dims)
    assert s == 1.0, f"clamp failed: {s}"
    dims = {name: {"score": -0.5} for name, _, _ in rr.RUBRIC}
    s = rr.compute_judge_score(dims)
    assert s == 0.0, f"clamp failed: {s}"
    print("  clamps [0,1] correctly")


def test_section_parser_on_real_instruction() -> None:
    assert STREAK_INSTRUCTION.exists(), f"missing fixture: {STREAK_INSTRUCTION}"
    text = STREAK_INSTRUCTION.read_text()
    sections = rr.parse_instruction_sections(text)
    for key in ("core_features", "user_flow", "ui_ux_notes"):
        assert key in sections, f"missing section: {key} (got {list(sections)})"
        body = sections[key]
        assert body.strip(), f"section {key} is empty"
        assert len(body) > 50, f"section {key} suspiciously short: {len(body)} chars"
    print(f"  parsed sections: {sorted(sections)[:8]}...")
    print(f"  core_features   = {len(sections['core_features'])} chars")
    print(f"  user_flow       = {len(sections['user_flow'])} chars")
    print(f"  ui_ux_notes     = {len(sections['ui_ux_notes'])} chars")


def test_safe_dimension_swallows_exception() -> None:
    def boom() -> dict:
        raise RuntimeError("simulated grader crash")
    result = rr.safe_dimension("motion", 0.05,
                               "asks something",
                               boom)
    assert isinstance(result, dict)
    for key in ("score", "weight", "rationale", "evidence", "asks"):
        assert key in result, f"missing key {key}"
    assert result["score"] == 0.0
    assert "simulated grader crash" in result["rationale"]
    assert result["weight"] == 0.05
    assert result["evidence"] == []
    print(f"  exception -> {result['score']}, rationale={result['rationale'][:60]!r}")


def test_safe_dimension_is_binary_and_truncates() -> None:
    """A criterion is satisfied or it is not; `score` is derived, never supplied.

    This test used to feed `score: 1.7` and assert it clamped to 1.0, which was
    the right check while the rubric measured DEGREE. Since 2026-08-17 the judge
    returns `satisfied` and score is 1.0/0.0 derived from it, so an out-of-range
    float is not something the interface can express -- what matters now is that
    a runner supplying no verdict is treated as UNSATISFIED rather than as a pass.
    """
    def big() -> dict:
        return {"satisfied": True, "score": 1.7,
                "rationale": "x" * 5000, "evidence": ["e"] * 50}
    result = rr.safe_dimension("ui_visual", 0.15, "asks", big)
    assert result["satisfied"] is True
    assert result["score"] == 1.0, "a supplied score must not override `satisfied`"

    unsatisfied = rr.safe_dimension("ui_visual", 0.15, "asks",
                                    lambda: {"rationale": "no verdict", "evidence": []})
    assert unsatisfied["satisfied"] is False
    assert unsatisfied["score"] == 0.0, "a missing verdict must not read as a pass"
    assert len(result["rationale"]) <= 2000
    assert len(result["evidence"]) <= 20
    print("  clamps score, truncates rationale + evidence")


def test_parse_viewport_list() -> None:
    got = rr.parse_viewport_list("1920x1200,768x1024,390x844")
    assert got == [(1920, 1200), (768, 1024), (390, 844)], got
    print(f"  parsed viewports: {got}")


def test_works_cap_blocks_pretty_but_broken() -> None:
    """PLAN.md 1.3 mode 1: a beautiful app that does not run must not score well."""
    from run_rubric import RUBRIC, WORKS_HEADROOM, compute_judge_score

    def dims(**override):
        return {n: {"score": override.get(n, 1.0)} for n, _, _ in RUBRIC}

    def plain(d):
        return round(sum(min(1.0, max(0.0, d[n]["score"])) * w for n, w, _ in RUBRIC), 4)

    broken = dims(functionality=0.2)
    capped = compute_judge_score(broken)
    assert capped == round(0.2 + WORKS_HEADROOM, 4), capped
    assert capped < plain(broken), "cap did not bind on a broken-but-pretty app"
    print(f"  pretty-but-broken: plain {plain(broken)} -> capped {capped}")

    # Polish deficits must still cost only their weight -- the cap keys on
    # functionality, so an ugly app that works is untouched by it.
    ugly = dims(ui_visual=0.2, motion=0.2, responsiveness=0.2)
    assert compute_judge_score(ugly) == plain(ugly), "cap wrongly bound on a working app"
    print(f"  ugly-but-working:  unchanged at {compute_judge_score(ugly)}")

    assert compute_judge_score(dims()) == 1.0
    assert compute_judge_score({n: {"score": 0.0} for n, _, _ in RUBRIC}) == 0.0


def main() -> int:
    tests = [
        test_weights_sum_to_one,
        test_score_all_ones,
        test_score_all_zeros,
        test_score_mixed_matches_hand_calc,
        test_score_clamps_out_of_range,
        test_section_parser_on_real_instruction,
        test_safe_dimension_swallows_exception,
        test_safe_dimension_is_binary_and_truncates,
        test_parse_viewport_list,
        test_works_cap_blocks_pretty_but_broken,
    ]
    failed = 0
    for t in tests:
        try:
            print(f"[{t.__name__}]")
            t()
            print(f"  PASS")
        except Exception as exc:
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"  FAIL: {exc}")
    print()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
