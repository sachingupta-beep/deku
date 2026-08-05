"""Task fixtures for ethara/event-rsvp-confirmations.

Two rules from PLAN.md 4.4 govern this file:

1. **Implementation agnostic.** Nothing here may assume the agent's framework,
   file layout, ORM or module names. The only things we may assume are the App
   Contract (the app answers at APP_PUBLIC_URL, REST under /api), and whatever
   instruction.md pinned explicitly -- endpoint paths and bodies, the
   `access_token` login key, the seeded accounts, the seeded event, the four
   table names, and the confirmation-email subject prefix.

2. **Provider agnostic.** Domain helpers below are composed from the generic
   `Backend` primitives in capabilities.py, never from a provider SDK. The
   email fixture is the shared `Inbox` from capabilities.py. Swapping the
   `backend` slot from postgres, or the `email` slot from mailpit, replaces
   an adapter -- not this file and not a single test.
"""

from __future__ import annotations

import os

import pytest
from _shapes import items
from appclient import client, login, seeded_password
from capabilities import Backend, Inbox, make_backend, make_inbox

ORGANISER_EMAIL = "organiser@ethara.ai"
GUEST_EMAIL = "guest@ethara.ai"
SEEDED_EVENT_TITLE = "Summer Meetup 2026"
CONFIRMATION_SUBJECT_PREFIX = "RSVP confirmed:"


# ----------------------------------------------------------------------- HTTP


@pytest.fixture(scope="session")
def anon_client():
    with client() as c:
        yield c


@pytest.fixture(scope="session")
def organiser_token() -> str:
    return login(
        ORGANISER_EMAIL, seeded_password("SEED_ORGANISER_PASSWORD", "deku-demo-pw-2026")
    )


@pytest.fixture(scope="session")
def organiser_client(organiser_token: str):
    with client(organiser_token) as c:
        yield c


@pytest.fixture(scope="session")
def guest_token() -> str:
    return login(GUEST_EMAIL, seeded_password("SEED_GUEST_PASSWORD", "deku-demo-pw-2026"))


@pytest.fixture(scope="session")
def guest_client(guest_token: str):
    with client(guest_token) as c:
        yield c


# ------------------------------------------------- backend slot, domain helpers


class EventStore:
    """Domain queries for this task, composed from capability primitives."""

    def __init__(self, backend: Backend) -> None:
        self._b = backend

    # -- users ------------------------------------------------------------

    def user_by_email(self, email: str) -> dict | None:
        return self._b.one("users", email=email)

    def count_users_with_email(self, email: str) -> int:
        return self._b.count("users", email=email)

    # -- events -----------------------------------------------------------

    def event_by_title(self, title: str) -> dict | None:
        return self._b.one("events", title=title)

    def event_by_id(self, event_id: int) -> dict | None:
        return self._b.one("events", id=event_id)

    def published_future_events(self) -> list[dict]:
        return self._b.rows("events", status="published")

    # -- rsvps ------------------------------------------------------------

    def rsvp_for(self, event_id: int, user_id: int) -> dict | None:
        return self._b.one("rsvps", event_id=event_id, user_id=user_id)

    def count_yes_rsvps(self, event_id: int) -> int:
        return self._b.count("rsvps", event_id=event_id, response="yes")

    def count_rsvps(self, event_id: int, user_id: int) -> int:
        return self._b.count("rsvps", event_id=event_id, user_id=user_id)

    def yes_rsvps(self, event_id: int) -> list[dict]:
        return self._b.rows("rsvps", event_id=event_id, response="yes")

    # -- email audit ------------------------------------------------------

    def count_email_log(self, recipient: str | None = None) -> int:
        if recipient is None:
            return self._b.count("email_log")
        return self._b.count("email_log", recipient=recipient)


@pytest.fixture(scope="session")
def db() -> EventStore:
    return EventStore(make_backend())


# ---------------------------------------------------- email slot, capability


@pytest.fixture(scope="session")
def inbox() -> Inbox:
    """The mail-server inbox, inspected out of band. Never call smtplib here."""
    return make_inbox()


# ------------------------------------------------------------------ utilities


@pytest.fixture
def unique_email() -> str:
    return f"verifier-{os.urandom(6).hex()}@ethara.test"


@pytest.fixture(scope="session")
def seeded_event(db: EventStore) -> dict:
    event = db.event_by_title(SEEDED_EVENT_TITLE)
    assert event is not None, (
        f"seeded event {SEEDED_EVENT_TITLE!r} is missing from the database"
    )
    return event


def signup(email: str, password: str = "verifier-pw-1", name: str = "Verifier Guest") -> str:
    """Sign up a fresh guest and return their bearer token.

    Uses the pinned /api/auth/signup + /api/auth/login shapes. Kept out of a
    fixture so tests that need multiple fresh guests can call it repeatedly.
    """
    with client() as c:
        response = c.post(
            "/auth/signup",
            json={"email": email, "password": password, "name": name},
        )
        assert response.status_code in (200, 201), (
            f"POST /api/auth/signup returned {response.status_code}: "
            f"{response.text[:400]}"
        )
    return login(email, password)


def new_event_payload(title: str, capacity: int = 5) -> dict:
    return {
        "title": title,
        "description": "Created by the verifier for a substep.",
        "start_time": "2027-09-15T18:00:00Z",
        "location": "Ethara HQ, Bangalore",
        "capacity": capacity,
        "status": "published",
    }
