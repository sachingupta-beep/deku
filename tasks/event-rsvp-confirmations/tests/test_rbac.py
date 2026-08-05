"""Authorization substeps.

PLAN.md 4.7: hiding a button is not a permission. Every assertion here goes to
the API directly, because that is the only place authorization can actually be
proven.
"""

from __future__ import annotations

import os

from appclient import client
from conftest import new_event_payload, signup


def test_guest_cannot_edit_other_guest_rsvp(guest_client, db, seeded_event):
    """A guest session cannot flip another guest's RSVP.

    Modelled at the API surface: the seeded guest holds a session and tries to
    POST an RSVP body naming a different user. If the app trusts a client-set
    user id, this will succeed and leak cross-tenant writes -- that is exactly
    the failure mode this substep must reject.
    """
    # A fresh guest with their own row we can attempt to hijack.
    victim_email = f"victim-{os.urandom(4).hex()}@ethara.test"
    victim_token = signup(victim_email, name="Victim Guest")
    with client(victim_token) as c:
        c.post("/rsvps", json={"event_id": seeded_event["id"], "response": "no"})
    victim = db.user_by_email(victim_email)
    assert victim is not None, "signed-up victim not found in the database"

    before = db.rsvp_for(seeded_event["id"], victim["id"])

    # The seeded guest attempts to modify the victim's RSVP by naming their id.
    hijack = guest_client.post(
        "/rsvps",
        json={
            "event_id": seeded_event["id"],
            "response": "yes",
            "user_id": victim["id"],
        },
    )
    # Accept either an outright forbid (the safe branch) or a 4xx/2xx where the
    # server correctly ignored the injected user_id and applied the change to
    # the caller. What must NEVER hold is the victim's row being mutated.
    after = db.rsvp_for(seeded_event["id"], victim["id"])
    if before is None:
        assert after is None or after["response"] == "no", (
            f"another guest's RSVP was created/mutated via injected user_id "
            f"(status {hijack.status_code}): {after}"
        )
    else:
        assert after is not None and after["response"] == before["response"], (
            f"another guest's RSVP response flipped from {before['response']!r} "
            f"to {after['response'] if after else None!r} via a hijack attempt "
            f"(status {hijack.status_code})"
        )


def test_guest_create_event_denied_at_api(guest_client, db):
    """A guest session cannot create events."""
    title = f"guest-should-not-create-{os.urandom(4).hex()}"
    response = guest_client.post("/events", json=new_event_payload(title))
    assert response.status_code in (401, 403), (
        f"guest POST /api/events returned {response.status_code}, expected 401/403: "
        f"{response.text[:400]}"
    )
    assert db.event_by_title(title) is None, (
        "a guest-initiated event create reached the database"
    )


def test_guest_read_organiser_guest_list_denied(guest_client, seeded_event):
    """A guest cannot read the organiser-only per-event guest list."""
    response = guest_client.get(f"/events/{seeded_event['id']}/rsvps")
    assert response.status_code in (401, 403), (
        f"guest GET /api/events/{seeded_event['id']}/rsvps returned "
        f"{response.status_code}, expected 401/403: {response.text[:400]}"
    )


def test_unauthenticated_requests_denied(anon_client, seeded_event):
    """Anonymous callers are rejected on reads and mutations alike."""
    protected_reads = [
        "/rsvps/me",
        f"/events/{seeded_event['id']}/rsvps",
    ]
    for path in protected_reads:
        response = anon_client.get(path)
        assert response.status_code in (401, 403), (
            f"anonymous GET /api{path} returned {response.status_code}, "
            f"expected 401/403: {response.text[:400]}"
        )

    mutations = [
        ("POST", "/events", new_event_payload(f"anon-{os.urandom(4).hex()}")),
        (
            "POST",
            "/rsvps",
            {"event_id": seeded_event["id"], "response": "yes"},
        ),
    ]
    for method, path, body in mutations:
        response = anon_client.request(method, path, json=body)
        assert response.status_code in (401, 403), (
            f"anonymous {method} /api{path} returned {response.status_code}, "
            f"expected 401/403: {response.text[:400]}"
        )
