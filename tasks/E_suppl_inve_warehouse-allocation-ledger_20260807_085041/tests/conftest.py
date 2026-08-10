"""Task fixtures for ethara/warehouse-allocation-ledger.

Three rules govern this file.

1. **Implementation agnostic (INV6, G23).** Nothing here may assume the agent's
   framework, file layout, ORM, module names or id type. The only things assumed
   are the App Contract, whatever instruction.md pinned literally -- routes,
   field names, status codes, table and column names, seeded accounts, the pallet
   skus, the reservation references -- and the generic backend primitives in
   capabilities.py. Note in particular that a reservation is always addressed by
   its pinned `reference`, never by a database id: the id type is exactly the
   kind of thing a black-box grader may not assume.

2. **Provider agnostic (INV5).** Domain queries are composed from the generic
   `Backend` primitives, never from a provider SDK. Swapping postgres for another
   backend replaces the adapter, never this file and never a single assertion.

3. **Restorative.** Every helper that takes stock also gives it back, and every
   grader that uses one releases what it reserved. The suite has to run twice in
   a row against a live database and reach the same verdict, because that is
   exactly what the oracle gate asks of it.

`settle()` is the only sanctioned sleep in the whole grader layer (G31), and the
only clock read lives in a function here rather than at module level, so no
assertion can bake a stale timestamp at import.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pytest
from appclient import client, login, seeded_password
from capabilities import Backend, make_backend
from _shapes import items

# ------------------------------------------------------------- seeded accounts
# instruction.md > Data model > Seed data.

PLANNER_EMAIL = "planner@example.com"
PLANNER_2_EMAIL = "planner2@example.com"
STOCK_ADMIN_EMAIL = "stock_admin@example.com"
AUDITOR_EMAIL = "auditor@example.com"
SEEDED_PASSWORD = "deku-demo-pw-2026"

PLANNER_NAME = "Dana Ryecroft"
PLANNER_2_NAME = "Marek Toll"
STOCK_ADMIN_NAME = "Ivo Bell"
AUDITOR_NAME = "Sofia Crane"

ROLE_PLANNER = "planner"
ROLE_STOCK_ADMIN = "stock_admin"
ROLE_AUDITOR = "auditor"

# ---------------------------------------------------------------- pinned items
# Each sku has one job in this suite, so no two graders contend for the same row.
#
#   PLT-1001  free stock plus a live seeded hold -- reserve, release, ledger, and
#             the adjustment that is refused from below
#   PLT-1002  fully committed at zero free      -- the oversell refusal, and the
#             cross-planner release denial on RSV-1002
#   PLT-1003  the contention subject
#   PLT-1004  the adjustment subject, the duplicate release, the zero quantity
#   PLT-1005  the zero row, never mutated

SKU_LIVE = "PLT-1001"
SKU_COMMITTED = "PLT-1002"
SKU_CONTENDED = "PLT-1003"
SKU_ADJUSTED = "PLT-1004"
SKU_EMPTY = "PLT-1005"

SEEDED_SKUS = (SKU_LIVE, SKU_COMMITTED, SKU_CONTENDED, SKU_ADJUSTED, SKU_EMPTY)

SEEDED_ITEM_NAMES = {
    SKU_LIVE: "Oak Pallet Standard",
    SKU_COMMITTED: "Steel Cage Pallet",
    SKU_CONTENDED: "Euro Pallet Light",
    SKU_ADJUSTED: "Chill Pallet Insulated",
    SKU_EMPTY: "Drum Cradle Pallet",
}

RESERVATION_LIVE = "RSV-1001"
RESERVATION_COMMITTED = "RSV-1002"

UNKNOWN_SKU = "PLT-9999"

# --------------------------------------------------------------- pinned values
# instruction.md > Core features, Data model, Deployment contract.

STATUS_HELD = "held"
STATUS_RELEASED = "released"

KIND_RESERVE = "reserve"
KIND_RELEASE = "release"
KIND_ADJUST = "adjust"

REFUSAL_FIELD = "free_quantity"

# A reservation and an adjustment are both synchronous, so nothing here polls for
# a side effect. The one bounded wait is between the two contending threads and
# their joined result, which the executor already owns.
SETTLE_INTERVAL_S = 0.5
POLL_TIMEOUT_S = 15.0


def settle(seconds: float = SETTLE_INTERVAL_S) -> None:
    """The only sanctioned sleep in the grader layer.

    Used between polls so a bounded wait for something that SHOULD happen does
    not spin. A bare sleep before asserting that something DID happen is always
    wrong and appears nowhere in this suite.
    """
    time.sleep(seconds)


def utc_now() -> datetime:
    """The single clock read, and it lives here rather than in a grader.

    Read inside a function, never at module import, so two graders in one run
    cannot share a frozen value. No assertion compares against this directly; it
    exists so a helper can bound a poll.
    """
    return datetime.now(timezone.utc)


def poll_until(getter, predicate, timeout: float = POLL_TIMEOUT_S):
    """Poll `getter()` to a deadline until `predicate` holds. Returns the last
    value seen either way, so a caller can report what it actually saw rather
    than a bare timeout."""
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = getter()
        if latest is not None and predicate(latest):
            return latest
        settle()
    return latest


def probe_reason(tag: str) -> str:
    """A unique per-run adjustment reason, so a line this run wrote can never be
    confused with one an earlier run left behind."""
    return f"{tag} probe {os.urandom(6).hex()}"


# --------------------------------------------------------------------- clients


@pytest.fixture(scope="session")
def anon_client():
    with client() as c:
        yield c


@pytest.fixture(scope="session")
def planner_client():
    token = login(PLANNER_EMAIL, seeded_password("SEED_PLANNER_PASSWORD", SEEDED_PASSWORD))
    with client(token) as c:
        yield c


@pytest.fixture(scope="session")
def planner2_client():
    token = login(PLANNER_2_EMAIL, seeded_password("SEED_PLANNER2_PASSWORD", SEEDED_PASSWORD))
    with client(token) as c:
        yield c


@pytest.fixture(scope="session")
def admin_client():
    token = login(STOCK_ADMIN_EMAIL, seeded_password("SEED_STOCK_ADMIN_PASSWORD",
                                                     SEEDED_PASSWORD))
    with client(token) as c:
        yield c


@pytest.fixture(scope="session")
def auditor_client():
    token = login(AUDITOR_EMAIL, seeded_password("SEED_AUDITOR_PASSWORD", SEEDED_PASSWORD))
    with client(token) as c:
        yield c


# ------------------------------------------------------ backend domain helpers


class YardStore:
    """Domain queries for this task, composed from the generic `count`, `rows`,
    `one` primitives. Table and column names are the ones instruction.md pins."""

    def __init__(self, backend: Backend) -> None:
        self._b = backend

    # -- users ------------------------------------------------------------

    def user_by_email(self, email: str) -> dict | None:
        return self._b.one("users", email=email)

    def count_users(self, **where) -> int:
        return self._b.count("users", **where)

    # -- stock items ------------------------------------------------------

    def item(self, sku: str) -> dict | None:
        return self._b.one("stock_items", sku=sku)

    def all_items(self) -> list[dict]:
        return self._b.rows("stock_items", limit=200)

    def on_hand(self, sku: str) -> int:
        row = self.item(sku)
        assert row is not None, f"seeded item {sku!r} is absent from stock_items"
        return int(row["on_hand"])

    def reserved(self, sku: str) -> int:
        row = self.item(sku)
        assert row is not None, f"seeded item {sku!r} is absent from stock_items"
        return int(row["reserved"])

    def free(self, sku: str) -> int:
        row = self.item(sku)
        assert row is not None, f"seeded item {sku!r} is absent from stock_items"
        return int(row["on_hand"]) - int(row["reserved"])

    # -- reservations -----------------------------------------------------

    def reservation(self, reference: str) -> dict | None:
        return self._b.one("reservations", reference=reference)

    def reservations_for_item(self, item_id) -> list[dict]:
        return self._b.rows("reservations", limit=500, stock_item_id=item_id)

    def count_reservations(self, **where) -> int:
        return self._b.count("reservations", **where)

    def held_total(self, sku: str) -> int:
        """The sum of `quantity` over an item's `held` reservations, which the
        brief makes equal to `stock_items.reserved`."""
        row = self.item(sku)
        assert row is not None, f"seeded item {sku!r} is absent from stock_items"
        return sum(int(r["quantity"]) for r in self.reservations_for_item(row["id"])
                   if str(r["status"]) == STATUS_HELD)

    # -- ledger -----------------------------------------------------------

    def ledger_rows(self, sku: str) -> list[dict]:
        # The limit is deliberately far above anything a graded run produces. The
        # ledger is append-only and every oracle run adds to it, so a limit sized
        # to one run would start truncating counts on a corpus that keeps its
        # database, and a truncated count reads as a real defect.
        row = self.item(sku)
        assert row is not None, f"seeded item {sku!r} is absent from stock_items"
        return self._b.rows("ledger_entries", limit=100000, stock_item_id=row["id"])

    def count_ledger(self, sku: str, kind: str | None = None) -> int:
        rows = self.ledger_rows(sku)
        if kind is None:
            return len(rows)
        return len([r for r in rows if str(r["kind"]) == kind])

    def count_all_ledger(self) -> int:
        return self._b.count("ledger_entries")


@pytest.fixture(scope="session")
def db() -> YardStore:
    return YardStore(make_backend())


# ------------------------------------------------------------- API helpers


def board(client_) -> list[dict]:
    response = client_.get("/board")
    assert response.status_code == 200, (
        f"GET /api/board returned {response.status_code}, expected 200. Body was "
        f"{response.text[:400]}"
    )
    return items(response.json())


def board_row(client_, sku: str) -> dict:
    for row in board(client_):
        if str(row.get("sku")) == sku:
            return row
    raise AssertionError(
        f"seeded item {sku!r} is absent from GET /api/board; the board carried "
        f"{[r.get('sku') for r in board(client_)]!r}"
    )


def board_free(client_, sku: str) -> int:
    return int(board_row(client_, sku)["free"])


def reserve(client_, sku: str, quantity: int):
    """File a reservation and hand back the raw response. Asserts nothing, so a
    caller can grade a refusal with the same helper it grades a success with."""
    return client_.post("/reservations", json={"sku": sku, "quantity": quantity})


def reserve_ok(client_, sku: str, quantity: int) -> dict:
    response = reserve(client_, sku, quantity)
    assert response.status_code in (200, 201), (
        f"POST /api/reservations for {quantity} of {sku!r} returned "
        f"{response.status_code}, expected 200 or 201. Body was {response.text[:400]}"
    )
    body = response.json()
    assert body.get("reference"), (
        f"the created reservation for {sku!r} carries no reference: "
        f"{response.text[:400]}"
    )
    return body


def release(client_, reference: str):
    """Release by the pinned public handle. The route never names a database id,
    so nothing here assumes one."""
    return client_.post(f"/reservations/{reference}/release")


def release_ok(client_, reference: str) -> dict:
    response = release(client_, reference)
    assert response.status_code in (200, 201), (
        f"POST /api/reservations/{reference}/release returned "
        f"{response.status_code}, expected 200. Body was {response.text[:400]}"
    )
    return response.json()


def my_reservations(client_) -> list[dict]:
    response = client_.get("/reservations")
    assert response.status_code == 200, (
        f"GET /api/reservations returned {response.status_code}, expected 200. "
        f"Body was {response.text[:400]}"
    )
    return items(response.json())


def release_every_hold(client_, sku: str) -> None:
    """Hand back everything this caller still holds on one item.

    Restorative setup, not a teardown: it is what lets the contention grader make
    an exact claim about the last pallets without assuming the run history."""
    for row in my_reservations(client_):
        if str(row.get("sku")) == sku and str(row.get("status")) == STATUS_HELD:
            release_ok(client_, str(row["reference"]))


def adjust(client_, sku: str, delta: int, reason: str):
    return client_.post("/adjustments", json={"sku": sku, "delta": delta,
                                              "reason": reason})


def adjust_ok(client_, sku: str, delta: int, reason: str) -> dict:
    response = adjust(client_, sku, delta, reason)
    assert response.status_code in (200, 201), (
        f"POST /api/adjustments moving {sku!r} by {delta} returned "
        f"{response.status_code}, expected 200 or 201. Body was {response.text[:400]}"
    )
    return response.json()


def ledger(client_, sku: str | None = None) -> list[dict]:
    params = {"sku": sku} if sku else None
    response = client_.get("/ledger", params=params)
    assert response.status_code == 200, (
        f"GET /api/ledger for {sku!r} returned {response.status_code}, expected "
        f"200. Body was {response.text[:400]}"
    )
    return items(response.json())


def refusal_body(response) -> dict:
    """A refusal must be a JSON object. Parsing it here keeps the message shape
    identical across the four graders that read one."""
    try:
        body = response.json()
    except ValueError as exc:
        raise AssertionError(
            f"the refusal returned a body that is not JSON: {response.text[:400]}"
        ) from exc
    assert isinstance(body, dict), (
        f"the refusal body is not a JSON object: {response.text[:400]}"
    )
    return body
