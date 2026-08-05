"""Email-integration substeps.

PLAN.md 4.4 pins email delivery to pytest: a browser watching a confirmation
screen cannot distinguish a real send from a setTimeout. Every assertion here
goes through the `inbox` capability fixture, never through smtplib -- the
whole no-mocks guarantee (PLAN.md 4.7) depends on the verifier asking the
mail server rather than the app.
"""

from __future__ import annotations

import os
import time

from appclient import client
from conftest import CONFIRMATION_SUBJECT_PREFIX, SEEDED_EVENT_TITLE, signup


def _wait_for(inbox, to: str, subject_contains: str, timeout: float = 10.0):
    """SMTP delivery is synchronous per the spec, but poll briefly for the
    verifier -> mail-server hop rather than gate on a single instantaneous read.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = inbox.find(to=to, subject_contains=subject_contains)
        if found is not None:
            return found
        time.sleep(0.25)
    return None


def test_rsvp_yes_delivers_confirmation_email(inbox, db, seeded_event):
    """A yes RSVP dispatches a real email to the RSVPing guest."""
    # Fresh per-run guest so inbox assertions cannot collide with seed data
    # or a previous run's messages that are still resident in Mailpit.
    email = f"email-yes-{os.urandom(6).hex()}@ethara.test"
    token = signup(email, name="Email Yes Guest")

    before = inbox.count(to=email)
    assert before == 0, (
        f"unique per-run inbox for {email} is not empty at start: found {before} messages"
    )

    with client(token) as c:
        response = c.post(
            "/rsvps", json={"event_id": seeded_event["id"], "response": "yes"}
        )
    assert response.status_code in (200, 201), (
        f"POST /api/rsvps returned {response.status_code}: {response.text[:400]}"
    )

    message = _wait_for(
        inbox, to=email, subject_contains=CONFIRMATION_SUBJECT_PREFIX
    )
    assert message is not None, (
        f"no confirmation email arrived at {email!r} within the polling window. "
        f"Inbox holds {inbox.count()} total messages; the app claimed the RSVP "
        f"succeeded so a real SMTP send must have happened."
    )

    assert any(email.lower() in addr.lower() for addr in message.to), (
        f"confirmation email is not addressed to the RSVPing guest {email!r}: "
        f"To={message.to}"
    )
    assert message.subject.startswith(CONFIRMATION_SUBJECT_PREFIX), (
        f"subject {message.subject!r} does not start with the pinned prefix "
        f"{CONFIRMATION_SUBJECT_PREFIX!r}"
    )
    assert SEEDED_EVENT_TITLE.lower() in message.subject.lower(), (
        f"subject {message.subject!r} does not include the event title "
        f"{SEEDED_EVENT_TITLE!r}"
    )
    assert message.body and SEEDED_EVENT_TITLE.lower() in message.body.lower(), (
        f"email body does not reference the event title {SEEDED_EVENT_TITLE!r}: "
        f"body={message.body[:200]!r}"
    )


def test_change_to_no_sends_no_email(inbox, seeded_event):
    """Changing an existing yes to no must not dispatch an additional email."""
    email = f"email-flip-{os.urandom(6).hex()}@ethara.test"
    token = signup(email, name="Flip Guest")

    with client(token) as c:
        first = c.post(
            "/rsvps", json={"event_id": seeded_event["id"], "response": "yes"}
        )
        assert first.status_code in (200, 201), (
            f"initial yes returned {first.status_code}: {first.text[:400]}"
        )

    yes_message = _wait_for(inbox, to=email, subject_contains=CONFIRMATION_SUBJECT_PREFIX)
    assert yes_message is not None, (
        f"initial yes did not deliver a confirmation to {email!r} -- unable to "
        f"isolate whether the change-to-no also sent one"
    )
    yes_count = inbox.count(to=email)

    with client(token) as c:
        flip = c.post(
            "/rsvps", json={"event_id": seeded_event["id"], "response": "no"}
        )
        assert flip.status_code in (200, 201), (
            f"change to no returned {flip.status_code}: {flip.text[:400]}"
        )

    # Give any spurious send a chance to arrive.
    time.sleep(2.0)
    after = inbox.count(to=email)
    assert after == yes_count, (
        f"changing yes to no dispatched an additional email to {email!r}: "
        f"count went from {yes_count} to {after}"
    )


def test_capacity_rejection_sends_no_email(inbox, organiser_client, db):
    """A rejected over-capacity RSVP must not dispatch a confirmation."""
    event_title = f"Email Capacity {os.urandom(4).hex()}"
    created = organiser_client.post(
        "/events",
        json={
            "title": event_title,
            "description": "capacity-email substep",
            "start_time": "2028-02-15T18:00:00Z",
            "location": "Ethara HQ",
            "capacity": 1,
            "status": "published",
        },
    )
    assert created.status_code in (200, 201), (
        f"POST /api/events returned {created.status_code}: {created.text[:400]}"
    )
    event_id = created.json().get("id") or db.event_by_title(event_title)["id"]

    # Fill the single seat.
    first_email = f"email-cap-a-{os.urandom(4).hex()}@ethara.test"
    first_token = signup(first_email)
    with client(first_token) as c:
        c.post("/rsvps", json={"event_id": event_id, "response": "yes"})

    # Second guest is over capacity and must not receive a confirmation.
    second_email = f"email-cap-b-{os.urandom(4).hex()}@ethara.test"
    second_token = signup(second_email)
    before = inbox.count(to=second_email)
    with client(second_token) as c:
        rejected = c.post(
            "/rsvps", json={"event_id": event_id, "response": "yes"}
        )
    assert 400 <= rejected.status_code < 500, (
        f"expected 4xx on over-capacity, got {rejected.status_code}: "
        f"{rejected.text[:400]}"
    )

    time.sleep(2.0)
    after = inbox.count(to=second_email)
    assert after == before, (
        f"a rejected over-capacity RSVP delivered a confirmation to "
        f"{second_email!r}: count went from {before} to {after}"
    )
