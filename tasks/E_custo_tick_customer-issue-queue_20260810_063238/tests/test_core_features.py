"""Business rules and the ticket state machine, as pinned by instruction.md.

Every assertion here observes an externally visible effect: an HTTP status, or
a row the backend adapter can read. Nothing inspects the agent's source (INV6).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from conftest import (
    SEEDED_OPEN_TICKET,
    SEEDED_ASSIGNED_TICKET,
    STATUS_ASSIGNED,
    STATUS_OPEN,
    STATUS_RESOLVED,
    claim_ticket,
    find_ticket,
    list_tickets,
    reassign_ticket,
    resolve_ticket,
    settle,
    ticket_by_title,
    unique_suffix,
    user_by_email,
    AGENT_EMAIL,
    AGENT2_EMAIL,
    raise_ticket,
)


def test_raised_ticket_persists_open_and_unassigned(fresh_ticket):
    # cov: C-CF-09, C-CF-08, C-OV-01, C-RL-02, C-DM-09
    assert fresh_ticket.get("status") == STATUS_OPEN, (
        f"ticket {fresh_ticket.get('title')!r} was raised but its stored status is "
        f"{fresh_ticket.get('status')!r}, expected {STATUS_OPEN!r}"
    )
    assert not fresh_ticket.get("assignee_id"), (
        f"ticket {fresh_ticket.get('title')!r} is {STATUS_OPEN!r} but carries "
        f"assignee_id {fresh_ticket.get('assignee_id')!r}; an open ticket has no assignee"
    )


def test_claim_persists_assignee_and_status(agent_client, backend, fresh_ticket):
    # cov: C-CF-17, C-CF-16, C-CF-18, C-OV-02, C-RL-06, C-RL-07
    agent = user_by_email(backend, AGENT_EMAIL)
    assert agent is not None, (
        f"seeded account {AGENT_EMAIL!r} is missing from the users table"
    )

    r = claim_ticket(agent_client, fresh_ticket["id"])
    assert r.status_code in (200, 201), (
        f"POST claim on ticket {fresh_ticket['id']} as {AGENT_EMAIL}: expected "
        f"200 or 201, observed {r.status_code}; body: {r.text[:200]}"
    )

    row = settle(
        lambda: (ticket_by_title(backend, fresh_ticket["title"]) or {}).get("assignee_id")
        and ticket_by_title(backend, fresh_ticket["title"])
    )
    assert row, (
        f"claim on ticket {fresh_ticket['title']!r} returned {r.status_code} but no "
        f"assignee_id was persisted"
    )
    assert str(row.get("assignee_id")) == str(agent["id"]), (
        f"ticket {fresh_ticket['title']!r} stores assignee_id {row.get('assignee_id')!r}, "
        f"expected the claiming agent {agent['id']!r}"
    )
    assert row.get("status") == STATUS_ASSIGNED, (
        f"ticket {fresh_ticket['title']!r} was claimed but stores status "
        f"{row.get('status')!r}, expected {STATUS_ASSIGNED!r}"
    )


def test_claim_on_assigned_ticket_returns_409(agent2_client, agent_client, backend,
                                              fresh_ticket):
    # cov: C-CF-19, C-DM-10
    first = claim_ticket(agent_client, fresh_ticket["id"])
    assert first.status_code in (200, 201), (
        f"first claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{first.status_code}; body: {first.text[:200]}"
    )

    second = claim_ticket(agent2_client, fresh_ticket["id"])
    assert second.status_code == 409, (
        f"second claim on the already-assigned ticket {fresh_ticket['id']} as "
        f"{AGENT2_EMAIL}: expected 409, observed {second.status_code}; "
        f"body: {second.text[:200]}"
    )


def test_concurrent_claims_produce_one_success_and_one_409(agent_client, agent2_client,
                                                           fresh_ticket):
    # cov: C-CF-21, C-CF-22, C-OV-05, C-DM-11
    ticket_id = fresh_ticket["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(claim_ticket, agent_client, ticket_id),
            pool.submit(claim_ticket, agent2_client, ticket_id),
        ]
        results = [f.result() for f in futures]

    codes = sorted(r.status_code for r in results)
    successes = [c for c in codes if c in (200, 201)]
    conflicts = [c for c in codes if c == 409]

    assert len(successes) == 1 and len(conflicts) == 1, (
        f"two simultaneous claims on ticket {ticket_id} returned {codes}; expected "
        f"exactly one success (200 or 201) and exactly one 409. Bodies: "
        f"{[r.text[:120] for r in results]}"
    )


def test_reassign_persists_new_assignee(supervisor_client, agent_client, backend,
                                        fresh_ticket):
    # cov: C-CF-26, C-CF-27, C-OV-03, C-RL-14, C-RL-12
    claimed = claim_ticket(agent_client, fresh_ticket["id"])
    assert claimed.status_code in (200, 201), (
        f"setup claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{claimed.status_code}; body: {claimed.text[:200]}"
    )

    agent2 = user_by_email(backend, AGENT2_EMAIL)
    assert agent2 is not None, (
        f"seeded account {AGENT2_EMAIL!r} is missing from the users table"
    )

    r = reassign_ticket(supervisor_client, fresh_ticket["id"], agent2["id"])
    assert r.status_code in (200, 201), (
        f"POST reassign on ticket {fresh_ticket['id']} as the supervisor: expected "
        f"200 or 201, observed {r.status_code}; body: {r.text[:200]}"
    )

    row = settle(
        lambda: (ticket_by_title(backend, fresh_ticket["title"]) or {}).get("assignee_id")
        == agent2["id"]
        and ticket_by_title(backend, fresh_ticket["title"])
    )
    assert row, (
        f"reassign of ticket {fresh_ticket['title']!r} returned {r.status_code} but the "
        f"stored assignee_id never became {agent2['id']!r}"
    )
    assert row.get("status") == STATUS_ASSIGNED, (
        f"ticket {fresh_ticket['title']!r} stores status {row.get('status')!r} after a "
        f"reassign, expected it to stay {STATUS_ASSIGNED!r}"
    )


def test_resolve_persists_terminal_status(agent_client, backend, fresh_ticket):
    # cov: C-CF-43, C-DM-13, C-RL-05
    claimed = claim_ticket(agent_client, fresh_ticket["id"])
    assert claimed.status_code in (200, 201), (
        f"setup claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{claimed.status_code}; body: {claimed.text[:200]}"
    )

    r = resolve_ticket(agent_client, fresh_ticket["id"])
    assert r.status_code in (200, 201), (
        f"POST resolve on ticket {fresh_ticket['id']} as the assignee: expected 200 "
        f"or 201, observed {r.status_code}; body: {r.text[:200]}"
    )

    row = settle(
        lambda: (ticket_by_title(backend, fresh_ticket["title"]) or {}).get("status")
        == STATUS_RESOLVED
        and ticket_by_title(backend, fresh_ticket["title"])
    )
    assert row, (
        f"resolve of ticket {fresh_ticket['title']!r} returned {r.status_code} but the "
        f"stored status never became {STATUS_RESOLVED!r}"
    )


def test_ticket_list_returns_array_newest_first(agent_client, customer_client):
    # cov: C-CF-15, C-CF-14, C-DC-16, C-DM-15
    first_title = f"Probe ordering A {unique_suffix()}"
    second_title = f"Probe ordering B {unique_suffix()}"

    for title in (first_title, second_title):
        r = raise_ticket(customer_client, title)
        assert r.status_code in (200, 201), (
            f"POST /api/tickets while raising {title!r}: expected 200 or 201, observed "
            f"{r.status_code}; body: {r.text[:200]}"
        )

    listing = list_tickets(agent_client)
    assert isinstance(listing, list), (
        f"GET /api/tickets did not yield a list of ticket objects; observed "
        f"{type(listing).__name__}"
    )

    titles = [t.get("title") for t in listing]
    assert first_title in titles and second_title in titles, (
        f"the queue omits one of the two tickets just raised; expected both "
        f"{first_title!r} and {second_title!r} among {titles[:10]}"
    )
    assert titles.index(second_title) < titles.index(first_title), (
        f"GET /api/tickets is not newest-first: {second_title!r} was raised after "
        f"{first_title!r} but appears later in the list"
    )
    assert SEEDED_OPEN_TICKET in titles, (
        f"the seeded unowned ticket {SEEDED_OPEN_TICKET!r} is absent from the queue an "
        f"agent reads; observed {titles[:10]}"
    )
    assert SEEDED_ASSIGNED_TICKET not in [
        t.get("title") for t in listing if not t.get("assignee_id")
    ], (
        f"the seeded ticket {SEEDED_ASSIGNED_TICKET!r} already has an assignee but is "
        f"listed as unowned"
    )
