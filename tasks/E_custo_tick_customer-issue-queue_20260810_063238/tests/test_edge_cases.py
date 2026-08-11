"""Boundary, validation and state-machine refusals.

Each test drives the endpoint to a state the spec forbids and asserts the exact
rejection status the brief pins.
"""

from __future__ import annotations

from conftest import (
    AGENT_EMAIL,
    SEEDED_OPEN_TICKET_2,
    api,
    claim_ticket,
    reassign_ticket,
    resolve_ticket,
    ticket_by_title,
    unique_suffix,
    user_by_email,
)


def test_resolve_open_ticket_returns_409(agent_client, backend):
    # cov: C-CF-44, C-DM-13
    target = ticket_by_title(backend, SEEDED_OPEN_TICKET_2)
    assert target is not None, (
        f"seeded ticket {SEEDED_OPEN_TICKET_2!r} is missing from the tickets table"
    )

    r = resolve_ticket(agent_client, target["id"])
    assert r.status_code == 409, (
        f"POST resolve on ticket {target['id']} on a ticket with no assignee: "
        f"expected 409, observed {r.status_code}; body: {r.text[:200]}. Only an "
        f"assigned ticket can be resolved"
    )


def test_transition_out_of_resolved_returns_409(agent_client, fresh_ticket):
    # cov: C-CF-45, C-CN-02, C-CN-03
    claimed = claim_ticket(agent_client, fresh_ticket["id"])
    assert claimed.status_code in (200, 201), (
        f"setup claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{claimed.status_code}; body: {claimed.text[:200]}"
    )
    resolved = resolve_ticket(agent_client, fresh_ticket["id"])
    assert resolved.status_code in (200, 201), (
        f"setup resolve on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{resolved.status_code}; body: {resolved.text[:200]}"
    )

    again = resolve_ticket(agent_client, fresh_ticket["id"])
    assert again.status_code == 409, (
        f"POST resolve on ticket {fresh_ticket['id']} on an already-resolved ticket: "
        f"expected 409, observed {again.status_code}; body: {again.text[:200]}. "
        f"Resolution is terminal"
    )


def test_empty_title_returns_422(customer_client):
    # cov: C-CF-11
    r = customer_client.post(
        api("/tickets"),
        json={"title": "", "body": "The body is present.", "priority": "normal"},
    )
    assert r.status_code == 422, (
        f"POST /api/tickets with an empty title: expected 422, observed "
        f"{r.status_code}; body: {r.text[:200]}"
    )


def test_empty_body_returns_422(customer_client):
    # cov: C-CF-12
    r = customer_client.post(
        api("/tickets"),
        json={
            "title": f"Probe missing body {unique_suffix()}",
            "body": "",
            "priority": "normal",
        },
    )
    assert r.status_code == 422, (
        f"POST /api/tickets with an empty body: expected 422, observed "
        f"{r.status_code}; body: {r.text[:200]}"
    )


def test_reassign_to_current_holder_returns_409(agent_client, supervisor_client, backend,
                                                fresh_ticket):
    # cov: C-CF-28
    claimed = claim_ticket(agent_client, fresh_ticket["id"])
    assert claimed.status_code in (200, 201), (
        f"setup claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{claimed.status_code}; body: {claimed.text[:200]}"
    )

    holder = user_by_email(backend, AGENT_EMAIL)
    assert holder is not None, (
        f"seeded account {AGENT_EMAIL!r} is missing from the users table"
    )

    r = reassign_ticket(supervisor_client, fresh_ticket["id"], holder["id"])
    assert r.status_code == 409, (
        f"POST reassign on ticket {fresh_ticket['id']} naming the agent who already "
        f"holds it: expected 409, observed {r.status_code}; body: {r.text[:200]}. "
        f"A reassign moves a ticket to a different agent"
    )
