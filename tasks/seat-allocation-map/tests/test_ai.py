"""Assistant substeps.

No API key is present in this environment, so these also prove the rule-based
parser is genuinely functional rather than a thin wrapper over an absent LLM.
"""

from __future__ import annotations

from _shapes import flatten

AMIT_EMAIL = "amit@ethara.ai"


def _ask(client, question: str):
    response = client.post("/ai/query", json={"query": question})
    assert response.status_code == 200, (
        f"POST /api/ai/query returned {response.status_code} for {question!r}: "
        f"{response.text[:400]}"
    )
    return flatten(response.json())


def test_ai_answers_seat_query(admin_client):
    """The assistant resolves an employee to their exact seat and project."""
    answer = _ask(admin_client, f"Where does {AMIT_EMAIL} sit?")
    for token in ("b4-23", "talos"):
        assert token in answer, (
            f"assistant answer omitted {token!r}; got: {answer[:400]}"
        )
    assert "2" in answer, f"assistant answer omitted the floor; got: {answer[:400]}"


def test_ai_answers_available_seats_query(admin_client, db):
    """The assistant reports availability consistent with real state."""
    floor = 3
    expected = len(db.available_seats_on_floor(floor))
    assert expected, f"no available seats seeded on floor {floor}"

    answer = _ask(admin_client, f"Which seats are available on floor {floor}?")
    assert answer.strip(), "assistant returned an empty availability answer"
    assert "floor" in answer or str(floor) in answer, (
        f"assistant availability answer does not reference floor {floor}: {answer[:400]}"
    )
    assert "no seats" not in answer and "none" not in answer, (
        f"assistant reported no availability while {expected} seats are free on "
        f"floor {floor}: {answer[:400]}"
    )


def test_ai_is_read_only(admin_client, db):
    """The assistant must never mutate. A mutating instruction changes nothing."""
    employee = db.employee_with_seat()
    allocation = db.active_allocation_for_employee(employee["id"])
    assert allocation is not None

    seats_before = db.count_seats("available")
    _ask(admin_client, f"Release the seat held by employee id {employee["id"]}.")
    _ask(admin_client, "Delete every employee.")

    assert db.active_allocation_for_employee(employee["id"]) is not None, (
        "the assistant released a seat - it must be read-only"
    )
    assert db.count_seats("available") == seats_before, (
        "the assistant changed seat availability - it must be read-only"
    )
    assert db.count_employees() > 0, "the assistant deleted employees"
