"""Black-box substep assertions for deku/calculator.

Every test here is referenced by exactly one substep in workflows.yaml, and the
validator rejects the task if that mapping breaks in either direction (a substep
naming a test that does not exist, or a test no substep claims).

Nothing imports the agent's source. Architecture is free -- the only contract is
the HTTP surface pinned in instruction.md.
"""

from __future__ import annotations

TOLERANCE = 1e-6


def calculate(client, expression: str):
    return client.post("/api/calculate", json={"expression": expression})


def history_entries(client) -> list[dict]:
    response = client.get("/api/history")
    assert response.status_code == 200, (
        f"GET /api/history returned {response.status_code}, expected 200"
    )
    body = response.json()
    assert isinstance(body, dict) and "entries" in body, (
        f"GET /api/history must return an object with an 'entries' key, got {body!r}"
    )
    entries = body["entries"]
    assert isinstance(entries, list), f"'entries' must be a list, got {type(entries)}"
    return entries


def assert_result(client, expression: str, expected: float) -> None:
    response = calculate(client, expression)
    assert response.status_code == 200, (
        f"POST /api/calculate {expression!r} returned {response.status_code} "
        f"({response.text[:200]!r}), expected 200"
    )
    body = response.json()
    assert set(body) == {"expression", "result"}, (
        f"response for {expression!r} must have exactly the keys "
        f"'expression' and 'result', got {sorted(body)}"
    )
    assert body["expression"] == expression, (
        f"expression must be echoed back unchanged: sent {expression!r}, "
        f"got {body['expression']!r}"
    )
    actual = body["result"]
    assert isinstance(actual, (int, float)) and not isinstance(actual, bool), (
        f"result for {expression!r} must be a JSON number, got {actual!r}"
    )
    assert abs(actual - expected) < TOLERANCE, (
        f"{expression!r} evaluated to {actual}, expected {expected}"
    )


# --------------------------------------------------------------- deploy + math

def test_health_endpoint_returns_200(client):
    """The healthcheck target answers, which is what gates every other substep."""
    response = client.get("/api/health")
    assert response.status_code == 200, (
        f"GET /api/health returned {response.status_code}, expected 200"
    )
    response.json()  # body must be valid JSON; its shape is the agent's choice


def test_calculate_respects_operator_precedence(client):
    """`*` and `/` bind tighter than `+` and `-`.

    Left-to-right evaluation is the classic wrong answer here: it gives 51 for
    the first case instead of 27, which is why the same numbers appear in the
    spec's worked table.
    """
    assert_result(client, "12+5*3", 27)
    assert_result(client, "20-2*5", 10)
    assert_result(client, "8/4+1", 3)


def test_calculate_handles_parentheses_and_negatives(client):
    """Parentheses override precedence; unary minus parses leading and nested.

    `7/2` and `1/3` also pin real division against integer division and the
    6-decimal half-up rounding rule.
    """
    assert_result(client, "(12+5)*3", 51)
    assert_result(client, "2*(3+4)-10", 4)
    assert_result(client, "-5+2", -3)
    assert_result(client, "(-5)*2", -10)
    assert_result(client, "7/2", 3.5)
    assert_result(client, "1/3", 0.333333)


# -------------------------------------------------------------------- history

def test_history_records_calculation(client, clean_history):
    """A calculation is recorded server-side, readable by a separate client.

    This is the substep that distinguishes a real backend from a page that keeps
    its history in browser memory -- these assertions run from a different HTTP
    client than the one that made the calculation.
    """
    assert_result(client, "6*7", 42)

    entries = history_entries(client)
    assert len(entries) == 1, (
        f"after one calculation the history must hold exactly 1 entry, got {len(entries)}"
    )
    entry = entries[0]
    assert set(entry) == {"expression", "result"}, (
        f"a history entry must have exactly the keys 'expression' and 'result', "
        f"got {sorted(entry)}"
    )
    assert entry["expression"] == "6*7"
    assert abs(entry["result"] - 42) < TOLERANCE


def test_history_is_newest_first_and_capped(client, clean_history):
    """Newest-first ordering, and the oldest entry falls off the end at 20."""
    for n in range(1, 22):  # 21 calculations against a cap of 20
        assert_result(client, f"{n}+0", n)

    entries = history_entries(client)
    assert len(entries) == 20, (
        f"the history caps at 20 entries; after 21 calculations it holds "
        f"{len(entries)}"
    )
    assert entries[0]["expression"] == "21+0", (
        f"the history is newest-first, so the most recent calculation '21+0' must "
        f"be first; got {entries[0]['expression']!r}"
    )
    recorded = {e["expression"] for e in entries}
    assert "1+0" not in recorded, (
        "the oldest calculation '1+0' must be dropped once the 21st is recorded"
    )
    assert "2+0" in recorded, (
        "only the single oldest entry should be dropped, but '2+0' is missing too"
    )


def test_history_clear_empties_the_log(client):
    """DELETE empties the history server-side, not just in the page."""
    assert_result(client, "2+2", 4)
    assert history_entries(client), "precondition failed: history is empty before the clear"

    response = client.delete("/api/history")
    assert response.status_code in (200, 204), (
        f"DELETE /api/history returned {response.status_code}, expected 200 or 204"
    )

    entries = history_entries(client)
    assert entries == [], f"history must be empty after a clear, got {entries!r}"


# ---------------------------------------------------------------- non-happy

def assert_rejected(client, expression: str) -> None:
    response = calculate(client, expression)
    assert response.status_code == 400, (
        f"{expression!r} returned {response.status_code} "
        f"({response.text[:200]!r}), expected 400"
    )
    body = response.json()
    assert "error" in body, (
        f"a rejected expression must return {{'error': ...}}, got {response.text[:200]!r}"
    )
    assert isinstance(body["error"], str) and body["error"].strip(), (
        f"the error field for {expression!r} must be a non-empty human-readable string"
    )


# NOTE: no @pytest.mark.parametrize anywhere in this file, deliberately.
# score.py maps a substep to a ctrf entry by exact test id, and a parametrized
# test reports as `test_name[param]` -- one row per case, none of them matching
# the id workflows.yaml names. Every substep would score as a missing test rather
# than a pass or a fail. Cases are looped inside a single test instead, so one
# test id produces one ctrf row.

def test_division_by_zero_returns_400(client):
    """Dividing by zero is a client error, not a 500, an Infinity, or a NaN."""
    for expression in ("1/0", "5/(3-3)", "10/(2*0)"):
        assert_rejected(client, expression)


def test_invalid_expression_returns_400(client):
    """Malformed and non-arithmetic input is rejected with a JSON error.

    The `__import__` case is the one that matters most: an app that reaches for a
    language-level eval answers 200 here (or crashes), which the spec forbids
    explicitly.
    """
    cases = (
        "2+",                 # trailing operator
        "2++3",               # two operators in a row
        "(2+3",               # unbalanced parenthesis
        "2+3)",               # unbalanced the other way
        "",                   # empty
        "   ",                # whitespace only
        "__import__('os')",   # not arithmetic, and a live eval would run it
        "2 + banana",         # not arithmetic
    )
    for expression in cases:
        assert_rejected(client, expression)


def test_rejected_expression_is_not_recorded(client, clean_history):
    """A 400 leaves the history untouched.

    Recording failures alongside successes is the plausible-looking bug this
    catches: the endpoint rejects correctly but appends anyway, so the user's
    history fills with input that never evaluated.
    """
    for expression in ("1/0", "2+", "2 + banana"):
        assert calculate(client, expression).status_code == 400

    entries = history_entries(client)
    assert entries == [], (
        f"rejected expressions must not reach the history, but it holds {entries!r}"
    )
