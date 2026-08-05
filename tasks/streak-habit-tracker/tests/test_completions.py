"""Completion-marking substeps.

Asserts the rules on completions from instruction.md: idempotent per (habit, date),
no future-dated marks, un-marking removes the row.
"""

from __future__ import annotations

from conftest import days_ago_utc, find_habit, future_date_utc, today_utc


def test_mark_today_persists_and_streak_updates(user_client, db, user_id):
    """Marking today writes a completion and lifts current_streak to at least one."""
    habit = find_habit(user_client, "Read 20 minutes")
    assert habit is not None, "seeded habit 'Read 20 minutes' is missing from GET /api/habits"
    habit_id = habit["id"]

    before = db.count_completions(user_id, habit_id=habit_id)

    response = user_client.post(f"/habits/{habit_id}/complete", json={"date": today_utc()})
    assert response.status_code in (200, 201), (
        f"POST /api/habits/{{id}}/complete returned {response.status_code}: "
        f"{response.text[:400]}"
    )

    assert db.completion_on(habit_id, today_utc()) is not None, (
        "a completion row was not written for today"
    )
    assert db.count_completions(user_id, habit_id=habit_id) == before + 1, (
        "exactly one completion row should have been added"
    )

    refreshed = find_habit(user_client, "Read 20 minutes")
    assert refreshed is not None
    assert bool(refreshed.get("completed_today")) is True, (
        f"completed_today did not flip to true after marking; got {refreshed}"
    )
    assert int(refreshed.get("current_streak", 0)) >= 1, (
        f"current_streak did not lift to at least 1; got {refreshed}"
    )


def test_unmark_removes_completion_and_recomputes(user_client, db, user_id):
    """Un-marking a day removes the ledger row and the streak recomputes to 0."""
    habit = find_habit(user_client, "Meditate")
    assert habit is not None, "seeded habit 'Meditate' is missing"
    habit_id = habit["id"]

    # Precondition: today is currently marked (seeded current_streak = 5).
    assert db.completion_on(habit_id, today_utc()) is not None, (
        "seeded state assumption failed: today's completion for Meditate should exist"
    )

    response = user_client.request(
        "DELETE", f"/habits/{habit_id}/complete", json={"date": today_utc()}
    )
    assert response.status_code in (200, 202, 204), (
        f"DELETE /api/habits/{{id}}/complete returned {response.status_code}: "
        f"{response.text[:400]}"
    )

    assert db.completion_on(habit_id, today_utc()) is None, (
        "the completion row for today was not removed on un-mark"
    )

    refreshed = find_habit(user_client, "Meditate")
    assert refreshed is not None
    assert bool(refreshed.get("completed_today")) is False, (
        f"completed_today did not flip to false after un-mark; got {refreshed}"
    )
    # Without today's mark the current run to today is broken.
    assert int(refreshed.get("current_streak", -1)) == 0, (
        f"current_streak should recompute to 0 with today missing; got {refreshed}"
    )


def test_duplicate_completion_is_idempotent(user_client, db, user_id):
    """Marking the same habit for the same day twice must not create a second row."""
    from conftest import new_habit_payload

    name = "idempotency-" + today_utc()
    created = user_client.post("/habits", json=new_habit_payload(name, color="slate"))
    assert created.status_code in (200, 201), created.text[:400]
    habit_id = db.habit_by_name(user_id, name)["id"]

    yesterday = days_ago_utc(1)
    first = user_client.post(f"/habits/{habit_id}/complete", json={"date": yesterday})
    assert first.status_code in (200, 201), (
        f"first mark returned {first.status_code}: {first.text[:400]}"
    )
    assert db.count_completions(user_id, habit_id=habit_id) == 1

    second = user_client.post(f"/habits/{habit_id}/complete", json={"date": yesterday})
    # Either accept as no-op or reject as conflict -- both satisfy the rule as long
    # as no duplicate row was written.
    assert second.status_code in (200, 201, 202, 204, 409), (
        f"second mark returned {second.status_code}, expected an idempotent "
        f"success or a 409 conflict: {second.text[:400]}"
    )
    assert db.count_completions(user_id, habit_id=habit_id) == 1, (
        "a duplicate completion row was written for the same (habit, date)"
    )


def test_future_dated_completion_rejected(user_client, db, user_id):
    """A completion cannot be recorded for a date in the future."""
    from conftest import new_habit_payload

    name = "future-check-" + today_utc()
    created = user_client.post("/habits", json=new_habit_payload(name, color="forest"))
    assert created.status_code in (200, 201), created.text[:400]
    habit_id = db.habit_by_name(user_id, name)["id"]

    tomorrow = future_date_utc(1)
    response = user_client.post(f"/habits/{habit_id}/complete", json={"date": tomorrow})
    assert 400 <= response.status_code < 500, (
        f"future-dated mark returned {response.status_code}, expected a 4xx: "
        f"{response.text[:400]}"
    )
    assert db.completion_on(habit_id, tomorrow) is None, (
        "a future-dated completion row was written despite the rejection"
    )
