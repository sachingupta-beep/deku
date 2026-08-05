"""Task fixtures for ethara/seat-allocation-map.

Two rules from PLAN.md 4.4 govern this file:

1. **Implementation agnostic.** Nothing here may assume the agent's framework, file
   layout, ORM or module names. The only things we may assume are the App Contract
   (the app answers at APP_PUBLIC_URL, REST under /api) and whatever instruction.md
   pinned explicitly -- endpoint paths and bodies, the `access_token` login key, the
   seeded accounts, the canonical Amit record, the five table names.

2. **Provider agnostic.** Domain helpers below are composed from the generic
   `Backend` primitives in capabilities.py, never from a provider SDK. Swapping the
   `backend` slot from postgres to another provider replaces the adapter, not this
   file and not a single test.
"""

from __future__ import annotations

import os

import pytest
from _shapes import items
from appclient import client, login, seeded_password
from capabilities import Backend, make_backend

ADMIN_EMAIL = "admin@ethara.ai"
EMPLOYEE_EMAIL = "amit@ethara.ai"


# ----------------------------------------------------------------------- HTTP


@pytest.fixture(scope="session")
def anon_client():
    with client() as c:
        yield c


@pytest.fixture(scope="session")
def admin_token() -> str:
    return login(ADMIN_EMAIL, seeded_password("SEED_ADMIN_PASSWORD", "deku-demo-pw-2026"))


@pytest.fixture(scope="session")
def admin_client(admin_token: str):
    with client(admin_token) as c:
        yield c


@pytest.fixture(scope="session")
def employee_client():
    token = login(EMPLOYEE_EMAIL, seeded_password("SEED_EMPLOYEE_PASSWORD", "deku-demo-pw-2026"))
    with client(token) as c:
        yield c


# ------------------------------------------------- backend slot, domain helpers


class SeatStore:
    """Domain queries for this task, composed from capability primitives."""

    def __init__(self, backend: Backend) -> None:
        self._b = backend

    # -- seats ------------------------------------------------------------

    def count_seats(self, status: str | None = None) -> int:
        return self._b.count("seats", **({"status": status} if status else {}))

    def seat_by_number(self, seat_number: str) -> dict | None:
        return self._b.one("seats", seat_number=seat_number)

    def seat_by_id(self, seat_id: int) -> dict | None:
        return self._b.one("seats", id=seat_id)

    def pick_seat(self, status: str, floor: int | None = None) -> dict:
        where: dict = {"status": status}
        if floor is not None:
            where["floor"] = floor
        found = self._b.rows("seats", limit=1, **where)
        assert found, f"no seat with status={status!r} floor={floor!r} in the seed data"
        return found[0]

    def available_seats_on_floor(self, floor: int) -> list[dict]:
        return self._b.rows("seats", status="available", floor=floor)

    # -- employees --------------------------------------------------------

    def count_employees(self, status: str | None = None) -> int:
        return self._b.count("employees", **({"status": status} if status else {}))

    def employee_by_email(self, email: str) -> dict | None:
        return self._b.one("employees", email=email)

    def count_employees_with_email(self, email: str) -> int:
        return self._b.count("employees", email=email)

    def employee_without_seat(self, exclude: set[int] | None = None) -> dict:
        excluded = exclude or set()
        for employee in self._b.rows("employees", limit=400, status="pending"):
            if employee["id"] not in excluded:
                return employee
        raise AssertionError("no unseated employee in the seed data")

    def employee_with_seat(self) -> dict:
        for allocation in self._b.rows(
            "seat_allocations", limit=50, allocation_status="active"
        ):
            employee = self._b.one("employees", id=allocation["employee_id"])
            if employee:
                return employee
        raise AssertionError("no seated employee in the seed data")

    # -- allocations ------------------------------------------------------

    def active_allocation_for_employee(self, employee_id: int) -> dict | None:
        return self._b.one(
            "seat_allocations", employee_id=employee_id, allocation_status="active"
        )

    def count_active_allocations_for_seat(self, seat_id: int) -> int:
        return self._b.count(
            "seat_allocations", seat_id=seat_id, allocation_status="active"
        )

    def released_allocation_for_seat(self, seat_id: int) -> dict | None:
        return self._b.one(
            "seat_allocations", seat_id=seat_id, allocation_status="released"
        )


@pytest.fixture(scope="session")
def db() -> SeatStore:
    return SeatStore(make_backend())


# ------------------------------------------------------------------ utilities


@pytest.fixture
def unique_email() -> str:
    return f"verifier-{os.urandom(6).hex()}@ethara.ai"


@pytest.fixture(scope="session")
def any_project_id(admin_client) -> int:
    response = admin_client.get("/projects")
    assert response.status_code == 200, (
        f"GET /api/projects returned {response.status_code}: {response.text[:400]}"
    )
    projects = items(response.json())
    assert projects, "GET /api/projects returned no projects"
    return projects[0]["id"]


def new_employee_payload(email: str, project_id: int) -> dict:
    return {
        "name": "Verifier Joiner",
        "email": email,
        "department": "Engineering",
        "role": "Engineer",
        "joining_date": "2026-08-03",
        "project_id": project_id,
    }
