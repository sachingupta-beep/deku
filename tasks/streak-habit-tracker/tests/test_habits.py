"""Habit CRUD substeps.

Black box: every assertion goes through the deployed HTTP surface or the `db`
capability fixture. Nothing here imports the agent's code or assumes its framework.
"""

from __future__ import annotations

from _shapes import items
from conftest import find_habit, new_habit_payload


def test_created_habit_persisted(user_client, db, user_id, unique_habit_name):
    """A newly created habit lands in the habits collection with a zero streak."""
    response = user_client.post("/habits", json=new_habit_payload(unique_habit_name))
    assert response.status_code in (200, 201), (
        f"POST /api/habits returned {response.status_code}: {response.text[:400]}"
    )

    row = db.habit_by_name(user_id, unique_habit_name)
    assert row is not None, "the created habit is not present in the habits collection"
    assert row.get("deleted") in (False, 0, None), (
        f"a newly created habit must not be soft-deleted; row: {row}"
    )

    listed = find_habit(user_client, unique_habit_name)
    assert listed is not None, "GET /api/habits does not include the freshly created habit"
    assert int(listed.get("current_streak", 0)) == 0, (
        f"a habit with no completions must report current_streak = 0; got {listed}"
    )
    assert int(listed.get("longest_streak", 0)) == 0, (
        f"a habit with no completions must report longest_streak = 0; got {listed}"
    )


def test_duplicate_name_case_insensitive_rejected(user_client, db, user_id):
    """A live habit with a case-variant of an existing name must be rejected."""
    before = db.count_habits(user_id, deleted=False)

    # The seeded "Meditate" habit is the anchor; lowercase collides.
    response = user_client.post("/habits", json=new_habit_payload("meditate", color="indigo"))
    assert 400 <= response.status_code < 500, (
        f"duplicate-name create returned {response.status_code}, expected a 4xx: "
        f"{response.text[:400]}"
    )
    assert db.count_habits(user_id, deleted=False) == before, (
        "a duplicate-name habit row was written despite the rejection"
    )

    listed = items(user_client.get("/habits").json())
    names = [str(habit.get("name", "")).lower() for habit in listed]
    assert names.count("meditate") == 1, (
        f"GET /api/habits shows more than one meditate row: {names}"
    )


def test_soft_delete_hides_habit_and_keeps_completions(user_client, db, user_id):
    """Deleting a habit hides it from the list and preserves completion rows on disk."""
    # Create and mark a habit so there is completion history to preserve.
    from conftest import today_utc

    name = "soda-check-" + today_utc()
    created = user_client.post("/habits", json=new_habit_payload(name, color="rose"))
    assert created.status_code in (200, 201), created.text[:400]

    habit_row = db.habit_by_name(user_id, name)
    assert habit_row is not None, "the habit did not persist before deletion"
    habit_id = habit_row["id"]

    marked = user_client.post(
        f"/habits/{habit_id}/complete", json={"date": today_utc()}
    )
    assert marked.status_code in (200, 201), (
        f"POST /api/habits/{{id}}/complete returned {marked.status_code}: {marked.text[:400]}"
    )
    completions_before = db.count_completions(user_id, habit_id=habit_id)
    assert completions_before >= 1, (
        "the completion did not persist before the delete step"
    )

    deleted = user_client.delete(f"/habits/{habit_id}")
    assert deleted.status_code in (200, 202, 204), (
        f"DELETE /api/habits/{{id}} returned {deleted.status_code}: {deleted.text[:400]}"
    )

    # Hidden from the list.
    assert find_habit(user_client, name) is None, (
        "a soft-deleted habit is still visible in GET /api/habits"
    )
    # Row survives on disk with the deleted flag flipped.
    stored = db.habit_by_id(habit_id)
    assert stored is not None, "the habit row was hard-deleted; soft delete was required"
    assert stored.get("deleted") in (True, 1, "true"), (
        f"the habit is not marked deleted; row: {stored}"
    )
    # Completions were preserved.
    assert db.count_completions(user_id, habit_id=habit_id) == completions_before, (
        "the completion history was destroyed when the habit was deleted"
    )
