"""Task fixtures for ethara/streak-habit-tracker.

Two rules from PLAN.md 4.4 govern this file:

1. **Implementation agnostic.** Nothing here may assume the agent's framework, file
   layout, ORM or module names. The only things we may assume are the App Contract
   (the app answers at APP_PUBLIC_URL, REST under /api) and whatever instruction.md
   pinned explicitly -- endpoint paths and bodies, the `access_token` login key, the
   seeded account, the three seeded habits, the three collection names.

2. **Provider agnostic.** Domain helpers below are composed from the generic
   `Backend` primitives in capabilities.py, never from a provider SDK. Swapping the
   `backend` slot from pocketbase to another provider replaces the adapter, not
   this file and not a single test.
"""

from __future__ import annotations

import os

import pytest
from _shapes import items
from appclient import client, login, seeded_password
from capabilities import Backend, make_backend

USER_EMAIL = "demo@ethara.ai"


# ----------------------------------------------------------------------- HTTP


@pytest.fixture(scope="session")
def anon_client():
    with client() as c:
        yield c


@pytest.fixture(scope="session")
def user_token() -> str:
    return login(USER_EMAIL, seeded_password("SEED_USER_PASSWORD", "deku-demo-pw-2026"))


@pytest.fixture(scope="session")
def user_client(user_token: str):
    with client(user_token) as c:
        yield c


# ------------------------------------------------- backend slot, domain helpers


class HabitStore:
    """Domain queries for this task, composed from capability primitives.

    Deliberately narrow -- if a substep needs a shape not expressible via
    `count`, `rows`, `one`, the fix is to add a small method here, never to
    reach for a provider SDK in a test file.
    """

    def __init__(self, backend: Backend) -> None:
        self._b = backend

    # -- users -----------------------------------------------------------

    def user_by_email(self, email: str) -> dict | None:
        return self._b.one("users", email=email)

    # -- habits ----------------------------------------------------------

    def count_habits(self, user_id: str, deleted: bool | None = None) -> int:
        where: dict = {"user_id": user_id}
        if deleted is not None:
            where["deleted"] = deleted
        return self._b.count("habits", **where)

    def habits_for(self, user_id: str, deleted: bool | None = None) -> list[dict]:
        where: dict = {"user_id": user_id}
        if deleted is not None:
            where["deleted"] = deleted
        return self._b.rows("habits", limit=200, **where)

    def habit_by_name(self, user_id: str, name: str) -> dict | None:
        return self._b.one("habits", user_id=user_id, name=name)

    def habit_by_id(self, habit_id: str) -> dict | None:
        return self._b.one("habits", id=habit_id)

    # -- completions -----------------------------------------------------

    def count_completions(self, user_id: str, habit_id: str | None = None) -> int:
        where: dict = {"user_id": user_id}
        if habit_id is not None:
            where["habit_id"] = habit_id
        return self._b.count("completions", **where)

    def completions_for_habit(self, habit_id: str) -> list[dict]:
        return self._b.rows("completions", limit=1000, habit_id=habit_id)

    def completion_on(self, habit_id: str, date: str) -> dict | None:
        return self._b.one("completions", habit_id=habit_id, date=date)


@pytest.fixture(scope="session")
def db() -> HabitStore:
    return HabitStore(make_backend())


@pytest.fixture(scope="session")
def user_id(db: HabitStore) -> str:
    record = db.user_by_email(USER_EMAIL)
    assert record is not None, f"seeded user {USER_EMAIL} is missing from the users collection"
    return record["id"]


# ------------------------------------------------------------------ utilities


@pytest.fixture
def unique_habit_name() -> str:
    # Random suffix keeps repeated verifier runs from tripping the uniqueness rule.
    return f"verifier-{os.urandom(4).hex()}"


def new_habit_payload(name: str, color: str = "teal") -> dict:
    return {"name": name, "color": color, "description": "created by the verifier"}


def today_utc() -> str:
    # UTC calendar day matches the server-side "today" the instruction pins.
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).date().isoformat()


def days_ago_utc(offset: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc).date() - timedelta(days=offset)).isoformat()


def future_date_utc(offset: int = 1) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc).date() + timedelta(days=offset)).isoformat()


# ------------------------------------------------- helpers that talk to the app


def find_habit(user_client, name: str) -> dict | None:
    response = user_client.get("/habits")
    assert response.status_code == 200, (
        f"GET /api/habits returned {response.status_code}: {response.text[:400]}"
    )
    for habit in items(response.json()):
        if str(habit.get("name", "")).lower() == name.lower():
            return habit
    return None
