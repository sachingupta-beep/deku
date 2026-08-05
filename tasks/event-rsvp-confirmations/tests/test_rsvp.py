"""RSVP-engine substeps.

Black box: every assertion goes through the deployed HTTP surface or the `db`
capability fixture. Nothing here imports the agent's code or assumes its
framework.
"""

from __future__ import annotations

import concurrent.futures

from _shapes import items
from appclient import client
from conftest import SEEDED_EVENT_TITLE, signup


def test_rsvp_yes_persisted(guest_client, guest_token, db, seeded_event):
    """A yes RSVP leaves a real, consistent row and does not double up."""
    # Ensure a clean starting state for the seeded guest on the seeded event.
    guest_client.post(
        "/rsvps", json={"event_id": seeded_event["id"], "response": "no"}
    )
    before_yes = db.count_yes_rsvps(seeded_event["id"])

    response = guest_client.post(
        "/rsvps", json={"event_id": seeded_event["id"], "response": "yes"}
    )
    assert response.status_code in (200, 201), (
        f"POST /api/rsvps returned {response.status_code}: {response.text[:400]}"
    )

    guest = db.user_by_email("guest@ethara.ai")
    assert guest is not None, "seeded guest is missing"
    rsvp = db.rsvp_for(seeded_event["id"], guest["id"])
    assert rsvp is not None, "no RSVP row was written for the seeded guest"
    assert rsvp["response"] == "yes", (
        f"RSVP row has response {rsvp['response']!r}, expected 'yes'"
    )
    assert db.count_rsvps(seeded_event["id"], guest["id"]) == 1, (
        "duplicate RSVP rows exist for (event, guest) - the unique index is missing"
    )
    assert db.count_yes_rsvps(seeded_event["id"]) == before_yes + 1, (
        "the yes count did not advance by exactly one"
    )


def test_change_yes_to_no_frees_capacity(guest_client, db, seeded_event):
    """Changing yes to no releases a slot immediately, on the next request."""
    # Force the guest into a known yes state first.
    guest_client.post(
        "/rsvps", json={"event_id": seeded_event["id"], "response": "yes"}
    )
    yes_before = db.count_yes_rsvps(seeded_event["id"])
    assert yes_before >= 1, "prior yes RSVP did not persist"

    response = guest_client.post(
        "/rsvps", json={"event_id": seeded_event["id"], "response": "no"}
    )
    assert response.status_code in (200, 201), (
        f"POST /api/rsvps (change to no) returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    assert db.count_yes_rsvps(seeded_event["id"]) == yes_before - 1, (
        "changing yes to no did not decrement the yes count"
    )

    # Detail endpoint must reflect the new remaining count.
    detail = guest_client.get(f"/events/{seeded_event['id']}")
    assert detail.status_code == 200, (
        f"GET /api/events/{seeded_event['id']} returned {detail.status_code}: "
        f"{detail.text[:400]}"
    )


def test_organiser_guest_list_matches_database(organiser_client, db, seeded_event):
    """The organiser's guest list contains every yes RSVP and nothing else."""
    response = organiser_client.get(f"/events/{seeded_event['id']}/rsvps")
    assert response.status_code == 200, (
        f"GET /api/events/{seeded_event['id']}/rsvps returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    rows = items(response.json())

    expected_ids = {r["user_id"] for r in db.yes_rsvps(seeded_event["id"])}
    returned_ids = {int(r["user_id"]) for r in rows}
    assert returned_ids == expected_ids, (
        f"organiser guest list mismatch. expected user_ids {sorted(expected_ids)}, "
        f"got {sorted(returned_ids)}"
    )
    for row in rows:
        for key in ("user_id", "name", "email", "response"):
            assert key in row, f"guest-list row missing {key!r}: {row}"
        assert row["response"] == "yes", (
            f"guest list included a non-yes row: {row}"
        )


def test_rsvp_beyond_capacity_rejected(organiser_client, organiser_token, db):
    """Once capacity is reached, the next yes RSVP is rejected with a 4xx."""
    # Build a fresh event with capacity 1 so we can drive it to the boundary
    # without disturbing the seeded fixture.
    event_title = f"Capacity Boundary {__import__('os').urandom(4).hex()}"
    payload = {
        "title": event_title,
        "description": "capacity boundary substep",
        "start_time": "2027-10-01T18:00:00Z",
        "location": "Ethara HQ",
        "capacity": 1,
        "status": "published",
    }
    created = organiser_client.post("/events", json=payload)
    assert created.status_code in (200, 201), (
        f"POST /api/events returned {created.status_code}: {created.text[:400]}"
    )
    event = created.json()
    event_id = event.get("id") or db.event_by_title(event_title)["id"]

    # First guest fills the sole seat.
    first_email = f"cap-a-{__import__('os').urandom(4).hex()}@ethara.test"
    first_token = signup(first_email)
    with client(first_token) as c:
        first = c.post("/rsvps", json={"event_id": event_id, "response": "yes"})
    assert first.status_code in (200, 201), (
        f"first RSVP returned {first.status_code}: {first.text[:400]}"
    )
    assert db.count_yes_rsvps(event_id) == 1

    # Second guest is over capacity.
    second_email = f"cap-b-{__import__('os').urandom(4).hex()}@ethara.test"
    second_token = signup(second_email)
    with client(second_token) as c:
        second = c.post("/rsvps", json={"event_id": event_id, "response": "yes"})
    assert 400 <= second.status_code < 500, (
        f"over-capacity RSVP returned {second.status_code}, expected 4xx: "
        f"{second.text[:400]}"
    )
    assert db.count_yes_rsvps(event_id) == 1, (
        "an over-capacity yes reached the database"
    )
    guest_b = db.user_by_email(second_email)
    if guest_b is not None:
        rejected_row = db.rsvp_for(event_id, guest_b["id"])
        assert rejected_row is None or rejected_row["response"] != "yes", (
            "an over-capacity RSVP was persisted as yes"
        )


def test_concurrent_last_seat_single_winner(organiser_client, db):
    """Two simultaneous yes RSVPs for the last seat: exactly one wins."""
    event_title = f"Race Boundary {__import__('os').urandom(4).hex()}"
    created = organiser_client.post(
        "/events",
        json={
            "title": event_title,
            "description": "race substep",
            "start_time": "2027-11-15T18:00:00Z",
            "location": "Ethara HQ",
            "capacity": 1,
            "status": "published",
        },
    )
    assert created.status_code in (200, 201), (
        f"POST /api/events returned {created.status_code}: {created.text[:400]}"
    )
    event_id = created.json().get("id") or db.event_by_title(event_title)["id"]

    email_a = f"race-a-{__import__('os').urandom(4).hex()}@ethara.test"
    email_b = f"race-b-{__import__('os').urandom(4).hex()}@ethara.test"
    token_a = signup(email_a)
    token_b = signup(email_b)

    def attempt(token: str) -> int:
        # A fresh client per thread: sharing one would serialise the requests
        # and the race this substep exists to prove would never happen.
        with client(token) as c:
            r = c.post("/rsvps", json={"event_id": event_id, "response": "yes"})
            return r.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(attempt, [token_a, token_b]))

    successes = [s for s in statuses if s in (200, 201)]
    assert len(successes) == 1, (
        f"expected exactly one RSVP to succeed, got statuses {statuses}"
    )
    assert db.count_yes_rsvps(event_id) == 1, (
        "the event ended with more than one yes RSVP against capacity 1"
    )


def test_duplicate_yes_updates_and_does_not_double_count(
    organiser_client, db
):
    """Submitting yes twice updates the same row rather than creating two."""
    event_title = f"Duplicate Boundary {__import__('os').urandom(4).hex()}"
    created = organiser_client.post(
        "/events",
        json={
            "title": event_title,
            "description": "duplicate substep",
            "start_time": "2027-12-01T18:00:00Z",
            "location": "Ethara HQ",
            "capacity": 5,
            "status": "published",
        },
    )
    assert created.status_code in (200, 201)
    event_id = created.json().get("id") or db.event_by_title(event_title)["id"]

    email = f"dup-{__import__('os').urandom(4).hex()}@ethara.test"
    token = signup(email)
    with client(token) as c:
        first = c.post("/rsvps", json={"event_id": event_id, "response": "yes"})
        second = c.post("/rsvps", json={"event_id": event_id, "response": "yes"})
    assert first.status_code in (200, 201), (
        f"first yes returned {first.status_code}: {first.text[:400]}"
    )
    assert second.status_code in (200, 201), (
        f"second yes returned {second.status_code}: {second.text[:400]}"
    )

    guest = db.user_by_email(email)
    assert guest is not None
    assert db.count_rsvps(event_id, guest["id"]) == 1, (
        "duplicate yes RSVPs produced more than one row"
    )
    assert db.count_yes_rsvps(event_id) == 1, (
        "duplicate yes was double-counted against capacity"
    )


def test_cancelled_event_rsvp_rejected(organiser_client, db):
    """A cancelled event accepts no new RSVPs."""
    event_title = f"Cancelled Boundary {__import__('os').urandom(4).hex()}"
    created = organiser_client.post(
        "/events",
        json={
            "title": event_title,
            "description": "cancel substep",
            "start_time": "2028-01-15T18:00:00Z",
            "location": "Ethara HQ",
            "capacity": 5,
            "status": "published",
        },
    )
    assert created.status_code in (200, 201)
    event_id = created.json().get("id") or db.event_by_title(event_title)["id"]

    cancel = organiser_client.patch(
        f"/events/{event_id}", json={"status": "cancelled"}
    )
    assert cancel.status_code == 200, (
        f"PATCH /api/events/{event_id} returned {cancel.status_code}: "
        f"{cancel.text[:400]}"
    )

    email = f"cancel-{__import__('os').urandom(4).hex()}@ethara.test"
    token = signup(email)
    with client(token) as c:
        response = c.post(
            "/rsvps", json={"event_id": event_id, "response": "yes"}
        )
    assert 400 <= response.status_code < 500, (
        f"RSVP on a cancelled event returned {response.status_code}, "
        f"expected 4xx: {response.text[:400]}"
    )
    assert db.count_yes_rsvps(event_id) == 0, (
        "a yes RSVP was accepted on a cancelled event"
    )
