"""Task fixtures for ethara/revenue-report-dashboard.

Implementation-agnostic (J.2): assume only the App Contract, the literals pinned
in instruction.md, and the vendored capability adapters. Nothing here imports a
provider SDK and nothing reads the agent's source. Sign-in goes through the app's
own `POST /api/auth/login`, which appclient owns.
"""

from __future__ import annotations

import time
import uuid

import pytest
from appclient import client, login, seeded_password
from capabilities import Backend, make_backend

# The only sanctioned sleep in the codebase (J.5).
SETTLE_SECONDS = 2.0


def settle(seconds: float = SETTLE_SECONDS) -> None:
    """Give an unwanted async side effect time to land before asserting it did not."""
    time.sleep(seconds)


def poll_deadline(seconds: float = 5.0) -> float:
    """time.monotonic() deadline sized for a bounded poll."""
    return time.monotonic() + seconds + SETTLE_SECONDS


# --------------------------------------------------------------- pinned literals

PASSWORD = "deku-demo-pw-2026"

ANALYST_EMAIL = "analyst@example.com"
MANAGER_NORTH_EMAIL = "manager@example.com"
MANAGER_SOUTH_EMAIL = "manager2@example.com"

ANALYST_NAME = "Dana Okafor"
MANAGER_NORTH_NAME = "Ines Bravo"
MANAGER_SOUTH_NAME = "Rui Santos"

REGION_NORTH = "North"
REGION_SOUTH = "South"
REGION_WEST = "West"
ALL_REGIONS = (REGION_NORTH, REGION_SOUTH, REGION_WEST)

LINE_AURORA = "Aurora"
LINE_BASALT = "Basalt"
ALL_LINES = (LINE_AURORA, LINE_BASALT)

JANUARY_TITLE = "January 2026 Revenue"
JANUARY_START = "2026-01-01"
JANUARY_END = "2026-01-31"

FEBRUARY_TITLE = "February 2026 Revenue"
FEBRUARY_START = "2026-02-01"
FEBRUARY_END = "2026-02-28"

# The figures the January period produces from the seeded ledger.
ANALYST_TOTAL = 415000
NORTH_TOTAL = 195000
SOUTH_TOTAL = 150000
WEST_TOTAL = 70000
AURORA_TOTAL = 325000
BASALT_TOTAL = 90000

REGION_TOTALS = {REGION_NORTH: NORTH_TOTAL, REGION_SOUTH: SOUTH_TOTAL,
                 REGION_WEST: WEST_TOTAL}
LINE_TOTALS = {LINE_AURORA: AURORA_TOTAL, LINE_BASALT: BASALT_TOTAL}

# The seeded ledger, exactly as instruction.md pins it.
SEEDED_TRANSACTIONS = {
    "TX-1001": {"region": REGION_NORTH, "line": LINE_AURORA, "amount": 120000,
                "occurred_on": "2026-01-05", "status": "settled"},
    "TX-1002": {"region": REGION_NORTH, "line": LINE_AURORA, "amount": 45000,
                "occurred_on": "2026-01-18", "status": "settled"},
    "TX-1003": {"region": REGION_NORTH, "line": LINE_BASALT, "amount": 30000,
                "occurred_on": "2026-01-22", "status": "settled"},
    "TX-1004": {"region": REGION_NORTH, "line": LINE_BASALT, "amount": 25000,
                "occurred_on": "2026-01-24", "status": "refunded"},
    "TX-1005": {"region": REGION_SOUTH, "line": LINE_AURORA, "amount": 90000,
                "occurred_on": "2026-01-09", "status": "settled"},
    "TX-1006": {"region": REGION_SOUTH, "line": LINE_BASALT, "amount": 60000,
                "occurred_on": "2026-01-15", "status": "settled"},
    "TX-1007": {"region": REGION_SOUTH, "line": LINE_BASALT, "amount": 15000,
                "occurred_on": "2026-01-30", "status": "void"},
    "TX-1008": {"region": REGION_WEST, "line": LINE_AURORA, "amount": 70000,
                "occurred_on": "2026-01-11", "status": "settled"},
    "TX-1009": {"region": REGION_NORTH, "line": LINE_AURORA, "amount": 99000,
                "occurred_on": "2026-02-02", "status": "settled"},
    "TX-1010": {"region": REGION_SOUTH, "line": LINE_AURORA, "amount": 88000,
                "occurred_on": "2025-12-31", "status": "settled"},
}

NORTH_JANUARY_REFS = ("TX-1001", "TX-1002", "TX-1003")
SOUTH_JANUARY_REFS = ("TX-1005", "TX-1006")
ANALYST_JANUARY_REFS = ("TX-1001", "TX-1002", "TX-1003", "TX-1005",
                        "TX-1006", "TX-1008")
EXCLUDED_REFS = ("TX-1004", "TX-1007", "TX-1009", "TX-1010")

# A period the seeded ledger holds no settled row for.
EMPTY_PERIOD_START = "2026-06-01"
EMPTY_PERIOD_END = "2026-06-30"


# ---------------------------------------------------------------- HTTP clients


@pytest.fixture(scope="session")
def anon_client():
    with client() as c:
        yield c


@pytest.fixture(scope="session")
def analyst_token() -> str:
    return login(ANALYST_EMAIL, seeded_password("SEED_ANALYST_PASSWORD", PASSWORD))


@pytest.fixture(scope="session")
def analyst_client(analyst_token: str):
    with client(analyst_token) as c:
        yield c


@pytest.fixture(scope="session")
def manager_north_token() -> str:
    return login(MANAGER_NORTH_EMAIL,
                 seeded_password("SEED_MANAGER_PASSWORD", PASSWORD))


@pytest.fixture(scope="session")
def manager_north_client(manager_north_token: str):
    with client(manager_north_token) as c:
        yield c


@pytest.fixture(scope="session")
def manager_south_token() -> str:
    return login(MANAGER_SOUTH_EMAIL,
                 seeded_password("SEED_MANAGER2_PASSWORD", PASSWORD))


@pytest.fixture(scope="session")
def manager_south_client(manager_south_token: str):
    with client(manager_south_token) as c:
        yield c


# ----------------------------------------------------- backend domain helpers


class RevenueStore:
    """Provider-agnostic domain queries composed from Backend primitives."""

    def __init__(self, backend: Backend) -> None:
        self._b = backend

    def user_by_email(self, email: str) -> dict | None:
        return self._b.one("users", email=email)

    def region_by_name(self, name: str) -> dict | None:
        return self._b.one("regions", name=name)

    def product_line_by_name(self, name: str) -> dict | None:
        return self._b.one("product_lines", name=name)

    def transaction_by_ref(self, external_ref: str) -> dict | None:
        return self._b.one("transactions", external_ref=external_ref)

    def count_transactions(self, **where) -> int:
        return self._b.count("transactions", **where)

    def report_by_title(self, title: str) -> dict | None:
        return self._b.one("reports", title=title)

    def report_by_id(self, report_id: int) -> dict | None:
        return self._b.one("reports", id=report_id)

    def count_reports(self, **where) -> int:
        return self._b.count("reports", **where)


@pytest.fixture(scope="session")
def db() -> RevenueStore:
    return RevenueStore(make_backend())


# --------------------------------------------------------------- app helpers


def report_id_by_title(app_client, title: str) -> int | None:
    """Find a report id through the app's own list endpoint, not the database."""
    from _shapes import items

    response = app_client.get("/reports")
    assert response.status_code == 200, (
        f"GET /api/reports returned {response.status_code}: {response.text[:400]}"
    )
    for row in items(response.json()):
        if row.get("title") == title:
            return row.get("id")
    return None


def summary_for(app_client, report_id, **params) -> dict:
    response = app_client.get(f"/reports/{report_id}/summary", params=params or None)
    assert response.status_code == 200, (
        f"GET /api/reports/{report_id}/summary returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    return response.json()


def transactions_for(app_client, report_id) -> list[dict]:
    from _shapes import items

    response = app_client.get(f"/reports/{report_id}/transactions")
    assert response.status_code == 200, (
        f"GET /api/reports/{report_id}/transactions returned "
        f"{response.status_code}: {response.text[:400]}"
    )
    return items(response.json())


def breakdown_map(summary: dict, key: str, name_field: str) -> dict:
    entries = summary.get(key)
    assert isinstance(entries, list), (
        f"summary {key!r} is {type(entries).__name__}, expected a list: "
        f"{str(summary)[:300]}"
    )
    out = {}
    for entry in entries:
        assert name_field in entry, (
            f"{key} entry {entry!r} has no {name_field!r} field"
        )
        assert "total" in entry, f"{key} entry {entry!r} has no 'total' field"
        out[entry[name_field]] = int(entry["total"])
    return out


def unique_report_title(prefix: str) -> str:
    """A title no other run can collide with, so reruns stay independent."""
    return f"{prefix} probe {uuid.uuid4().hex[:10]}"


def create_report(analyst_client, title: str, start: str, end: str):
    return analyst_client.post(
        "/reports",
        json={"title": title, "period_start": start, "period_end": end},
    )


def create_published_report(analyst_client, title: str, start: str, end: str) -> int:
    response = create_report(analyst_client, title, start, end)
    assert response.status_code in (200, 201), (
        f"POST /api/reports returned {response.status_code}: {response.text[:400]}"
    )
    report_id = response.json().get("id")
    assert report_id is not None, (
        f"POST /api/reports returned no id: {response.text[:400]}"
    )
    published = analyst_client.post(f"/reports/{report_id}/publish")
    assert published.status_code == 200, (
        f"POST /api/reports/{report_id}/publish returned "
        f"{published.status_code}: {published.text[:400]}"
    )
    return report_id
