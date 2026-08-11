"""Task fixtures for ethara/customer-issue-queue.

Two rules govern this file:

1. **Implementation agnostic** (INV6, G23). Nothing here may assume the agent's
   framework, file layout, ORM or module names. The only assumable things are
   the App Contract (the app answers at APP_PUBLIC_URL, REST under /api), and
   whatever instruction.md pinned explicitly -- endpoint paths and bodies, the
   seeded accounts, the seeded tickets, the two table names, the status enum,
   and the assignment-email subject prefix.

2. **Provider agnostic.** Domain helpers below are composed from the generic
   `Backend` and `Inbox` primitives in capabilities.py, never from a provider
   SDK (G10). Swapping the `backend` slot away from postgres, or the `email`
   slot away from mailpit, replaces an adapter -- not this file, not one test.

No test_* function lives here (G10).
"""

from __future__ import annotations

import os
import time

import pytest
from _shapes import items
from appclient import api_base, client, login, seeded_password
from capabilities import Backend, Inbox, make_backend, make_inbox

# --------------------------------------------------------------- pinned literals
# Every value below appears verbatim in instruction.md and in the Literals
# Ledger. A value that is not pinned there may not be asserted here (G6).

CUSTOMER_EMAIL = "customer@example.com"
CUSTOMER2_EMAIL = "customer2@example.com"
AGENT_EMAIL = "agent@example.com"
AGENT2_EMAIL = "agent2@example.com"
SUPERVISOR_EMAIL = "supervisor@example.com"

CUSTOMER_NAME = "Dana Reyes"
CUSTOMER2_NAME = "Priya Shah"
AGENT_NAME = "Marco Ruiz"
AGENT2_NAME = "Lena Fischer"
SUPERVISOR_NAME = "Ada Whitfield"

SEEDED_OPEN_TICKET = "Payment page returns 500"
SEEDED_OPEN_TICKET_2 = "Export CSV missing columns"
SEEDED_ASSIGNED_TICKET = "Login loop on mobile"

ASSIGNMENT_SUBJECT_PREFIX = "Ticket assigned: "

STATUS_OPEN = "open"
STATUS_ASSIGNED = "assigned"
STATUS_RESOLVED = "resolved"

ROLE_CUSTOMER = "customer"
ROLE_AGENT = "agent"
ROLE_SUPERVISOR = "supervisor"

USERS_TABLE = "users"
TICKETS_TABLE = "tickets"

# Bounded settle window for the SMTP round trip. The only sanctioned sleep in
# the suite (G31) -- test files never call time.sleep directly.
SETTLE_TIMEOUT_SEC = 20.0
SETTLE_INTERVAL_SEC = 0.5


def settle(predicate, timeout: float = SETTLE_TIMEOUT_SEC,
           interval: float = SETTLE_INTERVAL_SEC):
    """Poll `predicate` until it returns a truthy value or the window closes.

    Returns the truthy value, or the last falsy one. Never swallows an
    exception: a raising predicate propagates immediately, because a probe that
    hides a failure is worse than no probe (G31).
    """
    deadline = time.monotonic() + timeout
    result = predicate()
    while not result and time.monotonic() < deadline:
        time.sleep(interval)
        result = predicate()
    return result


def unique_suffix() -> str:
    """Unique per-run token so a re-run never collides with its own leftovers."""
    return os.urandom(6).hex()


# ------------------------------------------------------------------------ HTTP


@pytest.fixture(scope="session")
def anon_client():
    with client() as c:
        yield c


def _token(email: str) -> str:
    return login(email, seeded_password("SEED_PASSWORD", "deku-demo-pw-2026"))


@pytest.fixture(scope="session")
def customer_client():
    with client(_token(CUSTOMER_EMAIL)) as c:
        yield c


@pytest.fixture(scope="session")
def customer2_client():
    with client(_token(CUSTOMER2_EMAIL)) as c:
        yield c


@pytest.fixture(scope="session")
def agent_client():
    with client(_token(AGENT_EMAIL)) as c:
        yield c


@pytest.fixture(scope="session")
def agent2_client():
    with client(_token(AGENT2_EMAIL)) as c:
        yield c


@pytest.fixture(scope="session")
def supervisor_client():
    with client(_token(SUPERVISOR_EMAIL)) as c:
        yield c


# ------------------------------------------------------------------- providers


@pytest.fixture(scope="session")
def backend() -> Backend:
    return make_backend()


@pytest.fixture(scope="session")
def inbox() -> Inbox:
    return make_inbox()


# --------------------------------------------------------------- domain helpers


def api(path: str) -> str:
    return f"{api_base()}{path}"


def ticket_rows(backend: Backend, **where) -> list[dict]:
    return backend.rows(TICKETS_TABLE, **where)


def ticket_by_title(backend: Backend, title: str) -> dict | None:
    return backend.one(TICKETS_TABLE, title=title)


def user_by_email(backend: Backend, email: str) -> dict | None:
    return backend.one(USERS_TABLE, email=email)


def list_tickets(http_client) -> list[dict]:
    """GET /api/tickets as a list, tolerant of an envelope the spec never pinned."""
    r = http_client.get(api("/tickets"))
    assert r.status_code == 200, (
        f"GET /api/tickets: expected 200, observed {r.status_code}; "
        f"body: {r.text[:200]}"
    )
    return items(r.json())


def find_ticket(http_client, title: str) -> dict | None:
    for t in list_tickets(http_client):
        if t.get("title") == title:
            return t
    return None


def raise_ticket(http_client, title: str, body: str = "Reported by the customer.",
                 urgency: str = "high"):
    """Create a ticket. `priority` is the field name instruction.md pins."""
    return http_client.post(
        api("/tickets"), json={"title": title, "body": body, "priority": urgency}
    )


def ticket_path(ticket_id, action: str = "") -> str:
    """Build a per-ticket path from the pinned `/api/tickets` collection route.

    Composed here so no test file carries a partial route in an f-string: the
    only route literal in the suite is the one the ledger pins.
    """
    suffix = f"/{action}" if action else ""
    return api("/tickets") + f"/{ticket_id}{suffix}"


def claim_ticket(http_client, ticket_id):
    return http_client.post(ticket_path(ticket_id, "claim"))


def reassign_ticket(http_client, ticket_id, assignee_id):
    return http_client.post(
        ticket_path(ticket_id, "reassign"), json={"assignee_id": assignee_id}
    )


def resolve_ticket(http_client, ticket_id):
    return http_client.post(ticket_path(ticket_id, "resolve"))


def assignment_mail_count(inbox: Inbox, to: str, title: str) -> int:
    """Messages to `to` whose subject carries the pinned prefix plus `title`."""
    subject = f"{ASSIGNMENT_SUBJECT_PREFIX}{title}"
    matches = 0
    for _ in range(1):
        msg = inbox.find(to, subject_contains=subject)
        if msg is not None:
            matches = max(matches, 1)
    return matches


@pytest.fixture
def fresh_ticket(customer_client, backend):
    """A ticket raised by CUSTOMER_EMAIL, unique per run, left `open`.

    Self-seeding: no test depends on another test having run (G31).
    """
    title = f"Probe issue {unique_suffix()}"
    r = raise_ticket(customer_client, title)
    assert r.status_code in (200, 201), (
        f"POST /api/tickets while raising {title!r}: expected 200 or 201, "
        f"observed {r.status_code}; body: {r.text[:200]}"
    )
    row = settle(lambda: ticket_by_title(backend, title))
    assert row is not None, (
        f"ticket {title!r} was accepted over HTTP but no row with that title is "
        f"readable in the {TICKETS_TABLE} table"
    )
    return row
