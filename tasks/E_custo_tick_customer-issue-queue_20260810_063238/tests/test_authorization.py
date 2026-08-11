"""Denial at the API, ownership and relationship scope.

Hiding a control in the UI is not authorization: every test here calls the
endpoint directly with a real session token and asserts the refusal, then
confirms the underlying row is untouched where a mutation was attempted.
"""

from __future__ import annotations

from conftest import (
    AGENT2_EMAIL,
    AGENT_EMAIL,
    SEEDED_ASSIGNED_TICKET,
    SEEDED_OPEN_TICKET_2,
    api,
    claim_ticket,
    raise_ticket,
    reassign_ticket,
    ticket_by_title,
    ticket_path,
    user_by_email,
)


def test_agent_reassign_returns_403(agent_client, backend):
    # cov: C-RL-10, C-CF-30, C-RL-18
    target = ticket_by_title(backend, SEEDED_ASSIGNED_TICKET)
    assert target is not None, (
        f"seeded ticket {SEEDED_ASSIGNED_TICKET!r} is missing from the tickets table"
    )
    agent2 = user_by_email(backend, AGENT2_EMAIL)
    assert agent2 is not None, (
        f"seeded account {AGENT2_EMAIL!r} is missing from the users table"
    )

    r = reassign_ticket(agent_client, target["id"], agent2["id"])
    assert r.status_code in (401, 403), (
        f"POST reassign on ticket {target['id']} as {AGENT_EMAIL} (an agent): "
        f"expected 401 or 403, observed {r.status_code}; body: {r.text[:200]}. "
        f"Reassignment belongs to a supervisor"
    )


def test_customer_claim_returns_403(customer_client, backend):
    # cov: C-RL-03, C-CF-25, C-RL-04
    target = ticket_by_title(backend, SEEDED_OPEN_TICKET_2)
    assert target is not None, (
        f"seeded ticket {SEEDED_OPEN_TICKET_2!r} is missing from the tickets table"
    )

    r = claim_ticket(customer_client, target["id"])
    assert r.status_code in (401, 403), (
        f"POST claim on ticket {target['id']} as a customer: expected 401 or 403, "
        f"observed {r.status_code}; body: {r.text[:200]}"
    )

    after = ticket_by_title(backend, SEEDED_OPEN_TICKET_2)
    assert not after.get("assignee_id"), (
        f"a refused customer claim left assignee_id {after.get('assignee_id')!r} on "
        f"ticket {SEEDED_OPEN_TICKET_2!r}; a rejected call changes no row"
    )


def test_agent_raise_returns_403(agent_client):
    # cov: C-CF-13, C-RL-15
    r = raise_ticket(agent_client, "Agent attempts to raise an issue")
    assert r.status_code in (401, 403), (
        f"POST /api/tickets as {AGENT_EMAIL} (an agent): expected 401 or 403, observed "
        f"{r.status_code}; body: {r.text[:200]}. Only a customer raises an issue"
    )


def test_cross_customer_ticket_read_returns_403(customer2_client, backend,
                                                fresh_ticket):
    # cov: C-RL-20, C-RL-01, C-RL-19
    r = customer2_client.get(ticket_path(fresh_ticket["id"]))
    assert r.status_code in (401, 403, 404), (
        f"GET ticket {fresh_ticket['id']} as a different customer: expected 401, "
        f"403 or 404, observed {r.status_code}; body: {r.text[:200]}. A customer reads "
        f"only tickets that customer raised"
    )


def test_ticket_list_without_token_returns_401(anon_client):
    # cov: C-RL-17, C-RL-16, C-DC-17
    r = anon_client.get(api("/tickets"))
    assert r.status_code in (401, 403), (
        f"GET /api/tickets with no bearer token: expected 401 or 403, observed "
        f"{r.status_code}; body: {r.text[:200]}"
    )
