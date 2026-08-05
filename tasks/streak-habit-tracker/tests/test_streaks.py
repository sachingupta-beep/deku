"""Streak-computation and dashboard substeps.

Streaks are derived from the completions ledger. The verifier holds the app to
the same computation by reading the ledger through the capability adapter and
comparing against what the app reports.
"""

from __future__ import annotations

from _shapes import flatten, items
from conftest import days_ago_utc, find_habit, today_utc


def _current_streak_from_ledger(dates: set[str]) -> int:
    """Consecutive days ending on today. Zero if today is missing."""
    from datetime import date, timedelta

    if today_utc() not in dates:
        return 0
    streak = 0
    cursor = date.fromisoformat(today_utc())
    while cursor.isoformat() in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _longest_streak_from_ledger(dates: set[str]) -> int:
    from datetime import date, timedelta

    if not dates:
        return 0
    ordered = sorted(date.fromisoformat(d) for d in dates)
    longest = run = 1
    for prev, cur in zip(ordered, ordered[1:]):
        if cur - prev == timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1
    return longest


def test_seeded_streaks_match_ledger(user_client, db, user_id):
    """The seeded streak values agree with what the completions collection holds."""
    expectations = {
        "Meditate": {"current": 5, "longest_at_least": 5},
        "Read 20 minutes": {"current": 0, "longest_at_least": 3},
        "No soda": {"current": 1, "longest_at_least": 1},
    }

    for name, expected in expectations.items():
        habit = find_habit(user_client, name)
        assert habit is not None, f"seeded habit {name!r} is missing from GET /api/habits"

        ledger = {
            str(row["date"])
            for row in db.completions_for_habit(habit["id"])
        }
        assert ledger, f"no completions found for seeded habit {name!r}"

        derived_current = _current_streak_from_ledger(ledger)
        derived_longest = _longest_streak_from_ledger(ledger)

        assert derived_current == expected["current"], (
            f"ledger disagrees with the seeded contract for {name!r}: "
            f"derived current_streak={derived_current}, expected {expected['current']}. "
            f"Seed data is wrong."
        )
        assert derived_longest >= expected["longest_at_least"], (
            f"ledger longest_streak for {name!r} is {derived_longest}, "
            f"expected at least {expected['longest_at_least']}"
        )

        reported_current = int(habit.get("current_streak", -1))
        reported_longest = int(habit.get("longest_streak", -1))
        assert reported_current == derived_current, (
            f"{name!r}: API reported current_streak={reported_current}, "
            f"ledger says {derived_current}. Streak is not derived from completions."
        )
        assert reported_longest == derived_longest, (
            f"{name!r}: API reported longest_streak={reported_longest}, "
            f"ledger says {derived_longest}. Streak is not derived from completions."
        )


def test_dashboard_counts_match_ledger(user_client, db, user_id):
    """Dashboard counters agree with the real state of the collections."""
    response = user_client.get("/dashboard")
    assert response.status_code == 200, (
        f"GET /api/dashboard returned {response.status_code}: {response.text[:400]}"
    )
    payload = response.json()
    flat = flatten(payload)

    expected_total_habits = db.count_habits(user_id, deleted=False)
    expected_total_completions = db.count_completions(user_id)

    # Habits with a current streak of at least one: today is marked.
    today = today_utc()
    active = 0
    for habit_row in db.habits_for(user_id, deleted=False):
        if db.completion_on(habit_row["id"], today) is not None:
            active += 1

    for label, value in (
        ("total_habits", expected_total_habits),
        ("total_completions", expected_total_completions),
        ("habits_with_active_streak", active),
    ):
        assert str(value) in flat, (
            f"dashboard payload is missing the true {label}={value}; "
            f"got {flat[:600]}"
        )

    # habits[] entries must line up with the habits collection.
    dashboard_habits = payload.get("habits") if isinstance(payload, dict) else None
    if dashboard_habits is None:
        # Some implementations expose the array under an envelope key.
        dashboard_habits = items(payload)
    reported_names = {str(h.get("name", "")).lower() for h in dashboard_habits}
    expected_names = {
        str(row["name"]).lower() for row in db.habits_for(user_id, deleted=False)
    }
    assert reported_names == expected_names, (
        f"dashboard habit list disagrees with the habits collection: "
        f"reported {sorted(reported_names)}, expected {sorted(expected_names)}"
    )
