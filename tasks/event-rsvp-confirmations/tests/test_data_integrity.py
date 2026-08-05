"""Substeps asserting that what the UI shows is what the database holds."""

from __future__ import annotations

import os

from _shapes import flatten, items
from appclient import client
from conftest import SEEDED_EVENT_TITLE, signup


def test_signup_persists_guest_user(db):
    """Signup writes a real user row with role=guest."""
    email = f"signup-{os.urandom(6).hex()}@ethara.test"
    signup(email, name="Signup Substep")

    user = db.user_by_email(email)
    assert user is not None, f"signed-up user {email!r} was not persisted"
    assert str(user.get("role", "")).lower() == "guest", (
        f"signup created a user with role {user.get('role')!r}, expected 'guest'"
    )
    assert db.count_users_with_email(email) == 1, (
        f"more than one row was written for {email!r}"
    )


def test_new_event_visible_to_guests(organiser_client, db):
    """A published event appears in the guest-visible listing."""
    title = f"Visible {os.urandom(4).hex()}"
    created = organiser_client.post(
        "/events",
        json={
            "title": title,
            "description": "visibility substep",
            "start_time": "2027-08-10T18:00:00Z",
            "location": "Ethara HQ",
            "capacity": 10,
            "status": "published",
        },
    )
    assert created.status_code in (200, 201), (
        f"POST /api/events returned {created.status_code}: {created.text[:400]}"
    )

    # Any guest session can read the public listing.
    guest_email = f"visibility-{os.urandom(4).hex()}@ethara.test"
    guest_token = signup(guest_email)
    with client(guest_token) as c:
        response = c.get("/events")
    assert response.status_code == 200, (
        f"GET /api/events returned {response.status_code}: {response.text[:400]}"
    )

    listed = items(response.json())
    titles = {str(row.get("title", "")) for row in listed}
    assert title in titles, (
        f"newly published event {title!r} did not appear in the guest listing: "
        f"got {sorted(titles)[:15]}..."
    )

    # Also assert the row exists in the database with the right status.
    event = db.event_by_title(title)
    assert event is not None, "created event is missing from the database"
    assert str(event["status"]).lower() == "published", (
        f"created event has status {event['status']!r}, expected 'published'"
    )

    # And the seeded event is still visible alongside it -- the guest listing
    # must not shadow older published events.
    assert SEEDED_EVENT_TITLE in titles, (
        f"seeded event {SEEDED_EVENT_TITLE!r} vanished from the guest listing"
    )
