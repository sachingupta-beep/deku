"""Task fixtures for ethara/team-expense-approval.

Two rules from PLAN.md 4.4 govern this file:

1. **Implementation agnostic.** Nothing here may assume the agent's framework, file
   layout, ORM or module names. The only things we may assume are the App Contract
   (the app answers at APP_PUBLIC_URL, REST under /api, POST /api/auth/login
   returns access_token) and whatever instruction.md pinned explicitly -- endpoint
   paths and bodies, the seeded users, the four table names.

2. **Provider agnostic.** Domain helpers below are composed from the generic
   `Backend` primitives in capabilities.py, never from a provider SDK. Swapping the
   `backend` slot from postgres to another provider replaces the adapter, not this
   file and not a single test.

Auth is Keycloak (real OIDC), but every substep authenticates through the app's
own /api/auth/login endpoint (see appclient.py). Talking through the app's session
surface is what keeps the substeps implementation-agnostic -- a test that spoke
Keycloak's admin API directly would break the moment auth was swapped for Zitadel.
"""

from __future__ import annotations

import os

import pytest
from _shapes import items
from appclient import client, login, seeded_password
from capabilities import Backend, make_backend

FINANCE_EMAIL = "finance@ethara.ai"
MIA_EMAIL = "mia.manager@ethara.ai"
MARK_EMAIL = "mark.manager@ethara.ai"
ELLEN_EMAIL = "ellen@ethara.ai"      # reports to Mia
EVAN_EMAIL = "evan@ethara.ai"        # reports to Mia
ETHAN_EMAIL = "ethan@ethara.ai"      # reports to Mark
EMMA_EMAIL = "emma@ethara.ai"        # reports to Mark


# ------------------------------------------------------------------------ HTTP
#
# One client per role, plus a second employee under a different manager and a
# second manager, so cross-team isolation can be proven directly.


@pytest.fixture(scope="session")
def anon_client():
    with client() as c:
        yield c


def _authed(email: str, env_var: str, default: str):
    token = login(email, seeded_password(env_var, default))
    return client(token)


@pytest.fixture(scope="session")
def finance_client():
    with _authed(FINANCE_EMAIL, "SEED_FINANCE_PASSWORD", "deku-demo-pw-2026") as c:
        yield c


@pytest.fixture(scope="session")
def mia_client():
    with _authed(MIA_EMAIL, "SEED_MIA_PASSWORD", "deku-demo-pw-2026") as c:
        yield c


@pytest.fixture(scope="session")
def mark_client():
    with _authed(MARK_EMAIL, "SEED_MARK_PASSWORD", "deku-demo-pw-2026") as c:
        yield c


@pytest.fixture(scope="session")
def ellen_client():
    with _authed(ELLEN_EMAIL, "SEED_ELLEN_PASSWORD", "deku-demo-pw-2026") as c:
        yield c


@pytest.fixture(scope="session")
def evan_client():
    with _authed(EVAN_EMAIL, "SEED_EVAN_PASSWORD", "deku-demo-pw-2026") as c:
        yield c


@pytest.fixture(scope="session")
def ethan_client():
    with _authed(ETHAN_EMAIL, "SEED_ETHAN_PASSWORD", "deku-demo-pw-2026") as c:
        yield c


# ---------------------------------------------- backend slot, domain helpers


class ExpenseStore:
    """Domain queries for this task, composed from capability primitives."""

    def __init__(self, backend: Backend) -> None:
        self._b = backend

    # -- employees --------------------------------------------------------

    def employee_by_email(self, email: str) -> dict | None:
        return self._b.one("employees", email=email)

    def reports_of(self, manager_id: int) -> list[dict]:
        return self._b.rows("employees", manager_id=manager_id)

    # -- claims -----------------------------------------------------------

    def claim_by_id(self, claim_id: int) -> dict | None:
        return self._b.one("claims", id=claim_id)

    def count_claims(self, **where) -> int:
        return self._b.count("claims", **where)

    def claims_for_employee(self, employee_id: int, state: str | None = None) -> list[dict]:
        where: dict = {"employee_id": employee_id}
        if state:
            where["state"] = state
        return self._b.rows("claims", **where)

    def pick_claim(self, state: str, employee_id: int | None = None) -> dict:
        where: dict = {"state": state}
        if employee_id is not None:
            where["employee_id"] = employee_id
        found = self._b.rows("claims", limit=1, **where)
        assert found, f"no claim with state={state!r} employee_id={employee_id!r} in the seed data"
        return found[0]

    def any_submitted_from_report(self, manager_id: int) -> dict:
        reports = self.reports_of(manager_id)
        assert reports, f"manager {manager_id} has no direct reports in the seed data"
        for report in reports:
            claim = self._b.one("claims", employee_id=report["id"], state="submitted")
            if claim:
                return claim
        raise AssertionError(
            f"no submitted claim from any direct report of manager {manager_id}"
        )

    # -- events -----------------------------------------------------------

    def events_for_claim(self, claim_id: int) -> list[dict]:
        return self._b.rows("claim_events", claim_id=claim_id)


@pytest.fixture(scope="session")
def db() -> ExpenseStore:
    return ExpenseStore(make_backend())


# ------------------------------------------------------------------ utilities


@pytest.fixture
def unique_description() -> str:
    return f"verifier-{os.urandom(6).hex()}"


def submit_claim_payload(description: str, amount_cents: int = 1500) -> dict:
    return {
        "amount_cents": amount_cents,
        "currency": "USD",
        "category": "meals",
        "description": description,
        "expense_date": "2026-08-03",
    }


def me(client_) -> dict:
    """Resolve the caller's identity through the app's own /api/me endpoint.

    Employee ids and roles are the app's concern, not Keycloak's -- reading them
    through /api/me keeps the substeps agnostic to how the app stores them.
    """
    response = client_.get("/me")
    assert response.status_code == 200, (
        f"GET /api/me returned {response.status_code}: {response.text[:400]}"
    )
    return response.json()


@pytest.fixture(scope="session")
def mia_employee_id(mia_client) -> int:
    return me(mia_client)["employee_id"]


@pytest.fixture(scope="session")
def mark_employee_id(mark_client) -> int:
    return me(mark_client)["employee_id"]


@pytest.fixture(scope="session")
def ellen_employee_id(ellen_client) -> int:
    return me(ellen_client)["employee_id"]


@pytest.fixture(scope="session")
def ethan_employee_id(ethan_client) -> int:
    return me(ethan_client)["employee_id"]
