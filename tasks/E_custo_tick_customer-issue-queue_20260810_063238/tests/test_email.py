"""The email slot: delivery observed at the mail server, never in the UI.

A browser looking at a confirmation screen cannot tell a real send from a
setTimeout, so every assertion here reads the inbox through the capability
adapter. This is the notification half of the pattern's critical focus --
assignment persisted AND notification delivered.
"""

from __future__ import annotations

from conftest import (
    AGENT2_EMAIL,
    AGENT_EMAIL,
    ASSIGNMENT_SUBJECT_PREFIX,
    CUSTOMER_EMAIL,
    claim_ticket,
    reassign_ticket,
    resolve_ticket,
    settle,
    user_by_email,
)


def test_claim_delivers_one_email_to_raising_customer(agent_client, inbox, fresh_ticket):
    # cov: C-CF-32, C-CF-33, C-OV-04, C-DM-12
    before = inbox.count(CUSTOMER_EMAIL)

    r = claim_ticket(agent_client, fresh_ticket["id"])
    assert r.status_code in (200, 201), (
        f"POST claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{r.status_code}; body: {r.text[:200]}"
    )

    delivered = settle(lambda: inbox.count(CUSTOMER_EMAIL) > before)
    assert delivered, (
        f"claiming ticket {fresh_ticket['title']!r} returned {r.status_code} but no new "
        f"message reached {CUSTOMER_EMAIL} at the mail server "
        f"(count stayed at {before})"
    )

    after = inbox.count(CUSTOMER_EMAIL)
    assert after == before + 1, (
        f"claiming ticket {fresh_ticket['title']!r} delivered {after - before} messages "
        f"to {CUSTOMER_EMAIL}, expected exactly 1"
    )


def test_assignment_email_subject_carries_prefix_and_title(agent_client, inbox,
                                                           fresh_ticket):
    # cov: C-CF-37, C-CF-38, C-CF-39
    title = fresh_ticket["title"]
    expected_subject = f"{ASSIGNMENT_SUBJECT_PREFIX}{title}"

    r = claim_ticket(agent_client, fresh_ticket["id"])
    assert r.status_code in (200, 201), (
        f"POST claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{r.status_code}; body: {r.text[:200]}"
    )

    msg = settle(lambda: inbox.find(CUSTOMER_EMAIL, subject_contains=expected_subject))
    assert msg is not None, (
        f"no message to {CUSTOMER_EMAIL} carries the subject {expected_subject!r} after "
        f"ticket {title!r} was claimed; the subject must begin "
        f"{ASSIGNMENT_SUBJECT_PREFIX!r} followed by the ticket title"
    )

    body = (getattr(msg, "body", "") or "")
    assert body.strip(), (
        f"the assignment message to {CUSTOMER_EMAIL} for ticket {title!r} has an empty "
        f"body; it must name the ticket title and the assigned agent"
    )


def test_reassign_delivers_second_email_to_raising_customer(agent_client,
                                                            supervisor_client, backend,
                                                            inbox, fresh_ticket):
    # cov: C-CF-32, C-CF-34, C-CF-35, C-CF-36
    claimed = claim_ticket(agent_client, fresh_ticket["id"])
    assert claimed.status_code in (200, 201), (
        f"setup claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{claimed.status_code}; body: {claimed.text[:200]}"
    )
    after_claim = settle(lambda: inbox.count(CUSTOMER_EMAIL))

    agent2 = user_by_email(backend, AGENT2_EMAIL)
    assert agent2 is not None, (
        f"seeded account {AGENT2_EMAIL!r} is missing from the users table"
    )

    r = reassign_ticket(supervisor_client, fresh_ticket["id"], agent2["id"])
    assert r.status_code in (200, 201), (
        f"POST reassign on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{r.status_code}; body: {r.text[:200]}"
    )

    delivered = settle(lambda: inbox.count(CUSTOMER_EMAIL) > after_claim)
    assert delivered, (
        f"reassigning ticket {fresh_ticket['title']!r} returned {r.status_code} but no "
        f"further message reached {CUSTOMER_EMAIL}; every persisted assignment change "
        f"notifies the raising customer"
    )


def test_resolution_delivers_no_email(agent_client, inbox, fresh_ticket):
    # cov: C-CF-41, C-CF-40
    claimed = claim_ticket(agent_client, fresh_ticket["id"])
    assert claimed.status_code in (200, 201), (
        f"setup claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{claimed.status_code}; body: {claimed.text[:200]}"
    )
    after_claim = settle(lambda: inbox.count(CUSTOMER_EMAIL))

    r = resolve_ticket(agent_client, fresh_ticket["id"])
    assert r.status_code in (200, 201), (
        f"POST resolve on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{r.status_code}; body: {r.text[:200]}"
    )

    settle(lambda: False, timeout=3.0)
    assert inbox.count(CUSTOMER_EMAIL) == after_claim, (
        f"resolving ticket {fresh_ticket['title']!r} delivered mail to {CUSTOMER_EMAIL}; "
        f"resolution is not an assignment change and sends nothing"
    )


def test_refused_reassign_delivers_no_email(agent_client, supervisor_client, backend,
                                            inbox, fresh_ticket):
    # cov: C-CF-42, C-CF-29
    claimed = claim_ticket(agent_client, fresh_ticket["id"])
    assert claimed.status_code in (200, 201), (
        f"setup claim on ticket {fresh_ticket['id']}: expected 200 or 201, observed "
        f"{claimed.status_code}; body: {claimed.text[:200]}"
    )
    after_claim = settle(lambda: inbox.count(CUSTOMER_EMAIL))

    holder = user_by_email(backend, AGENT_EMAIL)
    assert holder is not None, (
        f"seeded account {AGENT_EMAIL!r} is missing from the users table"
    )

    r = reassign_ticket(supervisor_client, fresh_ticket["id"], holder["id"])
    assert r.status_code == 409, (
        f"reassigning ticket {fresh_ticket['id']} to the agent who already holds it: "
        f"expected 409, observed {r.status_code}; body: {r.text[:200]}"
    )

    settle(lambda: False, timeout=3.0)
    assert inbox.count(CUSTOMER_EMAIL) == after_claim, (
        f"a refused reassign on ticket {fresh_ticket['title']!r} delivered mail to "
        f"{CUSTOMER_EMAIL}; a rejected change notifies nobody"
    )


def test_concurrent_claims_deliver_exactly_one_email(agent_client, agent2_client, inbox,
                                                     fresh_ticket):
    # cov: C-OV-06, C-CF-24
    from concurrent.futures import ThreadPoolExecutor

    before = inbox.count(CUSTOMER_EMAIL)
    ticket_id = fresh_ticket["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(claim_ticket, agent_client, ticket_id),
            pool.submit(claim_ticket, agent2_client, ticket_id),
        ]
        results = [f.result() for f in futures]

    codes = sorted(r.status_code for r in results)
    delivered = settle(lambda: inbox.count(CUSTOMER_EMAIL) > before)
    assert delivered, (
        f"two simultaneous claims on ticket {ticket_id} returned {codes} but no message "
        f"reached {CUSTOMER_EMAIL}; the winning claim notifies the raising customer"
    )

    after = inbox.count(CUSTOMER_EMAIL)
    assert after == before + 1, (
        f"two simultaneous claims on ticket {ticket_id} delivered {after - before} "
        f"messages to {CUSTOMER_EMAIL}, expected exactly 1 (statuses {codes})"
    )
