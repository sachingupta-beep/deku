"""Persistence, reconciliation and seeded state.

These tests read the datastore through the capability adapter and check that
what the API reported is what actually landed, and that the seeded corpus
matches the brief exactly.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from conftest import (
    AGENT2_EMAIL,
    AGENT_EMAIL,
    CUSTOMER2_EMAIL,
    CUSTOMER_EMAIL,
    ROLE_AGENT,
    ROLE_CUSTOMER,
    ROLE_SUPERVISOR,
    SEEDED_ASSIGNED_TICKET,
    SEEDED_OPEN_TICKET,
    SEEDED_OPEN_TICKET_2,
    STATUS_ASSIGNED,
    STATUS_OPEN,
    SUPERVISOR_EMAIL,
    TICKETS_TABLE,
    USERS_TABLE,
    api,
    claim_ticket,
    reassign_ticket,
    settle,
    ticket_by_title,
    user_by_email,
)


def test_health_endpoint_returns_200(anon_client):
    # cov: C-TR-04, C-DC-05, C-DC-01, C-DC-04
    r = anon_client.get(api("/health"))
    assert r.status_code == 200, (
        f"GET /api/health: expected 200 once the app is ready, observed "
        f"{r.status_code}; body: {r.text[:200]}"
    )


def test_raised_ticket_records_raising_customer(backend, fresh_ticket):
    # cov: C-CF-10, C-DM-07
    raiser = user_by_email(backend, CUSTOMER_EMAIL)
    assert raiser is not None, (
        f"seeded account {CUSTOMER_EMAIL!r} is missing from the {USERS_TABLE} table"
    )
    assert str(fresh_ticket.get("customer_id")) == str(raiser["id"]), (
        f"ticket {fresh_ticket['title']!r} stores customer_id "
        f"{fresh_ticket.get('customer_id')!r}, expected the raising customer "
        f"{raiser['id']!r}"
    )


def test_rejected_claim_leaves_assignee_unchanged(agent_client, agent2_client, backend,
                                                  fresh_ticket):
    # cov: C-CF-20, C-TR-10, C-TR-11
    winner = user_by_email(backend, AGENT_EMAIL)
    assert winner is not None, (
        f"seeded account {AGENT_EMAIL!r} is missing from the {USERS_TABLE} table"
    )

    first = claim_ticket(agent_client, fresh_ticket["id"])
    assert first.status_code in (200, 201), (
        f"first claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{first.status_code}; body: {first.text[:200]}"
    )

    second = claim_ticket(agent2_client, fresh_ticket["id"])
    assert second.status_code == 409, (
        f"second claim on ticket {fresh_ticket['id']}: expected 409, observed "
        f"{second.status_code}; body: {second.text[:200]}"
    )

    row = ticket_by_title(backend, fresh_ticket["title"])
    assert str(row.get("assignee_id")) == str(winner["id"]), (
        f"after a refused second claim, ticket {fresh_ticket['title']!r} stores "
        f"assignee_id {row.get('assignee_id')!r}; the first claimant "
        f"{winner['id']!r} keeps it"
    )


def test_concurrent_claims_store_single_assignee(agent_client, agent2_client, backend,
                                                 fresh_ticket):
    # cov: C-CF-23, C-DM-09
    ticket_id = fresh_ticket["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(claim_ticket, agent_client, ticket_id),
            pool.submit(claim_ticket, agent2_client, ticket_id),
        ]
        results = [f.result() for f in futures]

    codes = sorted(r.status_code for r in results)
    row = settle(
        lambda: (ticket_by_title(backend, fresh_ticket["title"]) or {}).get("assignee_id")
        and ticket_by_title(backend, fresh_ticket["title"])
    )
    assert row, (
        f"two simultaneous claims on ticket {ticket_id} returned {codes} but no "
        f"assignee_id was persisted"
    )

    agent = user_by_email(backend, AGENT_EMAIL)
    agent2 = user_by_email(backend, AGENT2_EMAIL)
    assert str(row.get("assignee_id")) in (str(agent["id"]), str(agent2["id"])), (
        f"ticket {fresh_ticket['title']!r} stores assignee_id {row.get('assignee_id')!r}, "
        f"which is neither claiming agent ({agent['id']!r}, {agent2['id']!r})"
    )
    assert row.get("status") == STATUS_ASSIGNED, (
        f"ticket {fresh_ticket['title']!r} has an assignee but stores status "
        f"{row.get('status')!r}, expected {STATUS_ASSIGNED!r}"
    )


def test_forbidden_reassign_leaves_assignee_unchanged(agent_client, backend):
    # cov: C-CF-31, C-RL-18
    target = ticket_by_title(backend, SEEDED_ASSIGNED_TICKET)
    assert target is not None, (
        f"seeded ticket {SEEDED_ASSIGNED_TICKET!r} is missing from the "
        f"{TICKETS_TABLE} table"
    )
    before = target.get("assignee_id")

    agent2 = user_by_email(backend, AGENT2_EMAIL)
    assert agent2 is not None, (
        f"seeded account {AGENT2_EMAIL!r} is missing from the {USERS_TABLE} table"
    )

    r = reassign_ticket(agent_client, target["id"], agent2["id"])
    assert r.status_code in (401, 403), (
        f"POST reassign on ticket {target['id']} as an agent: expected 401 or 403, "
        f"observed {r.status_code}; body: {r.text[:200]}"
    )

    after = ticket_by_title(backend, SEEDED_ASSIGNED_TICKET)
    assert after.get("assignee_id") == before, (
        f"a forbidden reassign changed assignee_id on {SEEDED_ASSIGNED_TICKET!r} from "
        f"{before!r} to {after.get('assignee_id')!r}; a rejected call changes no row"
    )


def test_seeded_accounts_match_brief(backend):
    # cov: C-DM-17, C-RL-22, C-RL-23, C-RL-24, C-RL-25, C-RL-26, C-DM-04, C-DM-05, C-CF-04, C-DM-02
    expected = {
        CUSTOMER_EMAIL: ROLE_CUSTOMER,
        CUSTOMER2_EMAIL: ROLE_CUSTOMER,
        AGENT_EMAIL: ROLE_AGENT,
        AGENT2_EMAIL: ROLE_AGENT,
        SUPERVISOR_EMAIL: ROLE_SUPERVISOR,
    }
    for email, role in expected.items():
        row = user_by_email(backend, email)
        assert row is not None, (
            f"seeded account {email!r} is missing from the {USERS_TABLE} table; the "
            f"brief seeds five accounts"
        )
        assert row.get("role") == role, (
            f"seeded account {email!r} carries role {row.get('role')!r}, expected "
            f"{role!r}"
        )


def test_seeded_tickets_match_brief(backend):
    # cov: C-DM-16, C-DM-14, C-DM-15, C-DM-06, C-DM-01
    open_titles = (SEEDED_OPEN_TICKET, SEEDED_OPEN_TICKET_2)
    for title in open_titles:
        row = ticket_by_title(backend, title)
        assert row is not None, (
            f"seeded ticket {title!r} is missing from the {TICKETS_TABLE} table"
        )
        assert row.get("status") == STATUS_OPEN, (
            f"seeded ticket {title!r} carries status {row.get('status')!r}, expected "
            f"{STATUS_OPEN!r}"
        )
        assert not row.get("assignee_id"), (
            f"seeded ticket {title!r} is {STATUS_OPEN!r} but carries assignee_id "
            f"{row.get('assignee_id')!r}"
        )

    assigned = ticket_by_title(backend, SEEDED_ASSIGNED_TICKET)
    assert assigned is not None, (
        f"seeded ticket {SEEDED_ASSIGNED_TICKET!r} is missing from the "
        f"{TICKETS_TABLE} table"
    )
    assert assigned.get("status") == STATUS_ASSIGNED, (
        f"seeded ticket {SEEDED_ASSIGNED_TICKET!r} carries status "
        f"{assigned.get('status')!r}, expected {STATUS_ASSIGNED!r}"
    )
    holder = user_by_email(backend, AGENT_EMAIL)
    assert str(assigned.get("assignee_id")) == str(holder["id"]), (
        f"seeded ticket {SEEDED_ASSIGNED_TICKET!r} stores assignee_id "
        f"{assigned.get('assignee_id')!r}, expected {AGENT_EMAIL} ({holder['id']!r})"
    )


def test_seeding_is_idempotent(backend):
    # cov: C-DM-18
    for email in (CUSTOMER_EMAIL, AGENT_EMAIL, SUPERVISOR_EMAIL):
        n = backend.count(USERS_TABLE, email=email)
        assert n == 1, (
            f"the {USERS_TABLE} table holds {n} rows for {email!r}, expected exactly 1; "
            f"seeding must not duplicate rows when the app restarts"
        )
    for title in (SEEDED_OPEN_TICKET, SEEDED_OPEN_TICKET_2, SEEDED_ASSIGNED_TICKET):
        n = backend.count(TICKETS_TABLE, title=title)
        assert n == 1, (
            f"the {TICKETS_TABLE} table holds {n} rows titled {title!r}, expected "
            f"exactly 1; seeding must not duplicate rows when the app restarts"
        )
