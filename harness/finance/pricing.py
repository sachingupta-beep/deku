#!/usr/bin/env python3
"""Model list prices, for costing the grader/judge calls the harness makes.

Pure stdlib, py3.9-compatible -- imported by repackage.py, which runs on the
system python3.

Rates are USD per MILLION tokens, from platform.claude.com/docs/en/pricing.
Cache rates are derived, not quoted separately, because that is how Anthropic
publishes them:
    cache WRITE = 1.25x input   (5-minute TTL; the 1h TTL is 2x, unused here)
    cache READ  = 0.10x input

WHY A TABLE AT ALL: the finance record wants `judge_cost_usd` per evaluator
model, and nothing upstream computes it. Harbor costs the AGENT trajectory
(trajectory.json:final_metrics.total_cost_usd), but the browser grader and the
rubric judge are separate paid calls the harness itself makes, and their token
counts reach us raw. This turns those into money.

WHY UNKNOWN MODELS RETURN None RATHER THAN A GUESS: a wrong number in a finance
system is worse than a missing one -- it reconciles silently and nobody ever
looks again. An unpriced model surfaces as `cost_usd: null` plus a `pricing`
warning on the record, which is visible and fixable. Add the rate here (or via
DEKU_MODEL_PRICES) rather than letting an estimate through.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# USD per 1M tokens: model prefix -> (input, output).
#
# Keyed by PREFIX so dated snapshots resolve without a new entry every release:
# "claude-opus-4-5-20251101" matches "claude-opus-4-5". Longest prefix wins, so
# a more specific key can always override a family default.
PRICES = {
    "claude-fable-5":   (10.00, 50.00),
    "claude-mythos-5":  (10.00, 50.00),
    "claude-opus-5":    (5.00, 25.00),
    "claude-opus-4-8":  (5.00, 25.00),
    "claude-opus-4-7":  (5.00, 25.00),
    "claude-opus-4-6":  (5.00, 25.00),
    "claude-sonnet-5":  (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # DELIBERATELY ABSENT, and this WILL block every record until resolved:
    #   claude-sonnet-4-5  -- DEFAULT_GRADER_MODEL (run_workflows.py:42) AND
    #                         DEFAULT_JUDGE_MODEL  (run_rubric.py:66)
    #   claude-opus-4-5    -- appears in output/ as an agent model
    # Both are legacy models whose rates are not in the pricing reference this
    # table was built from, so a number here would be invention. Every trial
    # graded at the defaults therefore reports `no price for browser grader
    # model` and refuses to post -- a loud, safe failure rather than an invoice
    # line built on a guess. Confirm the real per-MTok rates against an actual
    # invoice, then add them here (or via DEKU_MODEL_PRICES).
}

CACHE_WRITE_MULTIPLIER = 1.25   # 5-minute TTL
CACHE_READ_MULTIPLIER = 0.10


def _overrides() -> dict:
    """Extra/replacement rates from DEKU_MODEL_PRICES (a path to a JSON file).

    Shape: {"<model-prefix>": [input_per_mtok, output_per_mtok], ...}

    This is the escape hatch for a model this file has not caught up with, and
    for orgs billed at negotiated rather than list rates. Unreadable or
    malformed file -> ignored, because a broken override must not take the
    whole finance record down with it.
    """
    path = os.environ.get("DEKU_MODEL_PRICES", "").strip()
    if not path:
        return {}
    try:
        raw = json.loads(Path(path).read_text())
        return {str(k): (float(v[0]), float(v[1])) for k, v in raw.items()}
    except Exception:
        return {}


def rates(model: str):
    """(input, output) USD per 1M tokens for `model`, or None if unpriced."""
    if not model:
        return None
    table = dict(PRICES)
    table.update(_overrides())
    name = model.strip()
    # Longest matching prefix, so "claude-opus-4-8-20260101" prefers an exact
    # "claude-opus-4-8-20260101" entry over the "claude-opus-4-8" family rate.
    best = None
    for prefix, price in table.items():
        if name.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, price)
    return best[1] if best else None


def cost_usd(model: str, usage: dict):
    """Cost of one usage block, or None when the model has no known rate.

    `usage` uses the Anthropic names, which is what run_workflows normalises
    both providers into:
        input_tokens, output_tokens,
        cache_creation_input_tokens, cache_read_input_tokens
    """
    price = rates(model)
    if price is None:
        return None
    inp, out = price
    million = 1_000_000.0
    return round(
        (usage.get("input_tokens") or 0) / million * inp
        + (usage.get("output_tokens") or 0) / million * out
        + (usage.get("cache_creation_input_tokens") or 0) / million
        * inp * CACHE_WRITE_MULTIPLIER
        + (usage.get("cache_read_input_tokens") or 0) / million
        * inp * CACHE_READ_MULTIPLIER,
        6,
    )
