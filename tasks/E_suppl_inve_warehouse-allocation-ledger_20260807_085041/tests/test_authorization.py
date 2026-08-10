"""Denial at the API.

Hiding a control in the interface is not authorization. Every observation here is
a direct call that bypasses the interface entirely, each one re-reads the target
afterwards to prove the denial changed nothing, and each one is paired with the
same call from a role that may make it, so a denial can never be a dead endpoint
wearing a permission badge.
"""

from __future__ import annotations

from conftest import (
    PLANNER_2_EMAIL,
    PLANNER_EMAIL,
    RESERVATION_COMMITTED,
    ROLE_PLANNER,
    ROLE_STOCK_ADMIN,
    SKU_ADJUSTED,
    SKU_COMMITTED,
    SKU_CONTENDED,
    STATUS_HELD,
    STOCK_ADMIN_EMAIL,
    adjust,
    adjust_ok,
    my_reservations,
    probe_reason,
    release,
    release_ok,
    reserve,
    reserve_ok,
)


def test_stock_admin_cannot_reserve_pallets(admin_client, planner_client, db):
    # cov: C-RL-13, C-RL-14, C-RL-23, C-RL-24, C-RL-25, C-CF-21, C-DC-25,
    # cov: C-DM-01, C-DM-04, C-DM-05, C-DM-06, C-BP-09, C-BP-11
    """The stock admin is denied on the reservation route, and the same call from
    a planner succeeds."""
    planner = db.user_by_email(PLANNER_EMAIL)
    assert planner is not None, "the seeded planner is absent from the users table"
    assert str(planner["role"]) == ROLE_PLANNER, (
        f"{PLANNER_EMAIL!r} carries role {planner['role']!r}, expected "
        f"{ROLE_PLANNER!r}"
    )
    stock_admin = db.user_by_email(STOCK_ADMIN_EMAIL)
    assert stock_admin is not None, (
        f"{STOCK_ADMIN_EMAIL!r} is absent from the users table"
    )
    assert str(stock_admin["role"]) == ROLE_STOCK_ADMIN, (
        f"{STOCK_ADMIN_EMAIL!r} carries role {stock_admin['role']!r}, expected "
        f"{ROLE_STOCK_ADMIN!r}"
    )

    reservations_before = db.count_reservations()
    reserved_before = db.reserved(SKU_CONTENDED)

    denied = reserve(admin_client, SKU_CONTENDED, 1)
    assert denied.status_code in (401, 403), (
        f"POST /api/reservations from a stock admin session returned "
        f"{denied.status_code}, expected 401 or 403. Body was "
        f"{denied.text[:400]}"
    )
    assert db.count_reservations() == reservations_before, (
        f"the denied reservation wrote a row anyway: reservations moved from "
        f"{reservations_before} to {db.count_reservations()}"
    )
    assert db.reserved(SKU_CONTENDED) == reserved_before, (
        f"the denied reservation moved held stock for {SKU_CONTENDED!r} from "
        f"{reserved_before} to {db.reserved(SKU_CONTENDED)}"
    )

    listing = admin_client.get("/reservations")
    assert listing.status_code in (401, 403), (
        f"GET /api/reservations from a stock admin session returned "
        f"{listing.status_code}, expected 401 or 403. The reservation list "
        f"belongs to planners. Body was {listing.text[:400]}"
    )

    # The same call from a planner succeeds, which is what makes the denial a
    # permission boundary rather than a broken endpoint.
    allowed = reserve_ok(planner_client, SKU_CONTENDED, 1)
    release_ok(planner_client, str(allowed["reference"]))


def test_planner_cannot_adjust_on_hand(planner_client, admin_client, db):
    # cov: C-RL-04, C-RL-07, C-RL-15, C-RL-22, C-CF-32, C-CF-42, C-DC-33,
    # cov: C-DC-34, C-DC-43, C-DC-45, C-UF-14, C-UF-16, C-DM-47, C-DM-48
    """A planner calling the adjustment route is denied, on-hand stock does not
    move, and the stock admin makes the same call successfully."""
    on_hand_before = db.on_hand(SKU_ADJUSTED)
    lines_before = db.count_ledger(SKU_ADJUSTED)

    denied = adjust(planner_client, SKU_ADJUSTED, 1, probe_reason("denied"))
    assert denied.status_code in (401, 403), (
        f"POST /api/adjustments from a planner session returned "
        f"{denied.status_code}, expected 401 or 403. Body was "
        f"{denied.text[:400]}"
    )
    assert db.on_hand(SKU_ADJUSTED) == on_hand_before, (
        f"the denied adjustment moved on_hand for {SKU_ADJUSTED!r} from "
        f"{on_hand_before} to {db.on_hand(SKU_ADJUSTED)}"
    )
    assert db.count_ledger(SKU_ADJUSTED) == lines_before, (
        f"the denied adjustment appended a ledger line anyway: {SKU_ADJUSTED!r} "
        f"moved from {lines_before} lines to {db.count_ledger(SKU_ADJUSTED)}"
    )

    adjust_ok(admin_client, SKU_ADJUSTED, 1, probe_reason("allowed"))
    adjust_ok(admin_client, SKU_ADJUSTED, -1, probe_reason("restore"))
    assert db.on_hand(SKU_ADJUSTED) == on_hand_before, (
        f"the paired adjustments left on_hand for {SKU_ADJUSTED!r} at "
        f"{db.on_hand(SKU_ADJUSTED)}, expected the original {on_hand_before}"
    )


def test_auditor_is_denied_every_mutation(auditor_client, db):
    # cov: C-RL-16, C-RL-17, C-RL-18, C-RL-19, C-RL-20, C-RL-21, C-DC-19,
    # cov: C-DM-02, C-DM-03, C-DM-07, C-UF-15, C-UF-04, C-UF-06, C-UF-10
    """The read-only role reaches both reads and is refused on all three
    mutations."""
    reservations_before = db.count_reservations()
    ledger_before = db.count_all_ledger()
    on_hand_before = db.on_hand(SKU_ADJUSTED)

    denied_reserve = reserve(auditor_client, SKU_CONTENDED, 1)
    assert denied_reserve.status_code in (401, 403), (
        f"POST /api/reservations from an auditor session returned "
        f"{denied_reserve.status_code}, expected 401 or 403. Body was "
        f"{denied_reserve.text[:400]}"
    )
    denied_adjust = adjust(auditor_client, SKU_ADJUSTED, 1, probe_reason("auditor"))
    assert denied_adjust.status_code in (401, 403), (
        f"POST /api/adjustments from an auditor session returned "
        f"{denied_adjust.status_code}, expected 401 or 403. Body was "
        f"{denied_adjust.text[:400]}"
    )
    denied_release = release(auditor_client, RESERVATION_COMMITTED)
    assert denied_release.status_code in (401, 403, 404), (
        f"POST /api/reservations/{RESERVATION_COMMITTED}/release from an auditor "
        f"session returned {denied_release.status_code}, expected 401, 403 or "
        f"404. Body was {denied_release.text[:400]}"
    )

    board_read = auditor_client.get("/board")
    assert board_read.status_code == 200, (
        f"GET /api/board from an auditor session returned "
        f"{board_read.status_code}, expected 200. The auditor reads everything. "
        f"Body was {board_read.text[:400]}"
    )
    ledger_read = auditor_client.get("/ledger")
    assert ledger_read.status_code == 200, (
        f"GET /api/ledger from an auditor session returned "
        f"{ledger_read.status_code}, expected 200. Body was "
        f"{ledger_read.text[:400]}"
    )

    assert db.count_reservations() == reservations_before, (
        f"the auditor denials still moved reservations from "
        f"{reservations_before} to {db.count_reservations()}"
    )
    assert db.count_all_ledger() == ledger_before, (
        f"the auditor denials still appended ledger lines: {ledger_before} before, "
        f"{db.count_all_ledger()} after"
    )
    assert db.on_hand(SKU_ADJUSTED) == on_hand_before, (
        f"the auditor denials still moved on_hand for {SKU_ADJUSTED!r} from "
        f"{on_hand_before} to {db.on_hand(SKU_ADJUSTED)}"
    )


def test_planner_cannot_release_another_planners_reservation(planner_client,
                                                             planner2_client, db):
    # cov: C-RL-08, C-RL-29, C-RL-30, C-DC-29, C-DM-21, C-DM-68, C-DM-69,
    # cov: C-UF-07, C-UF-08, C-CF-22
    """A planner aiming a release at somebody else's reservation is denied, and
    the owning planner still reads it."""
    target = db.reservation(RESERVATION_COMMITTED)
    assert target is not None, (
        f"seeded reservation {RESERVATION_COMMITTED!r} is absent from the "
        f"reservations table"
    )
    assert str(target["status"]) == STATUS_HELD, (
        f"seeded reservation {RESERVATION_COMMITTED!r} carries status "
        f"{target['status']!r}, so the cross-planner denial would prove nothing"
    )
    reserved_before = db.reserved(SKU_COMMITTED)

    denied = release(planner_client, RESERVATION_COMMITTED)
    assert denied.status_code in (401, 403, 404), (
        f"POST /api/reservations/{RESERVATION_COMMITTED}/release from a planner "
        f"who does not own it returned {denied.status_code}, expected 401, 403 or "
        f"404. Body was {denied.text[:400]}"
    )
    after = db.reservation(RESERVATION_COMMITTED)
    assert str(after["status"]) == STATUS_HELD, (
        f"the denied release still moved {RESERVATION_COMMITTED!r} to status "
        f"{after['status']!r}"
    )
    assert db.reserved(SKU_COMMITTED) == reserved_before, (
        f"the denied release moved held stock for {SKU_COMMITTED!r} from "
        f"{reserved_before} to {db.reserved(SKU_COMMITTED)}"
    )

    references = [str(r.get("reference")) for r in my_reservations(planner_client)]
    assert RESERVATION_COMMITTED not in references, (
        f"GET /api/reservations returned {RESERVATION_COMMITTED!r} to a planner "
        f"who does not own it: {references!r}"
    )

    owner = db.user_by_email(PLANNER_2_EMAIL)
    assert owner is not None, (
        f"{PLANNER_2_EMAIL!r} is absent from the users table, so nobody owns "
        f"{RESERVATION_COMMITTED!r}"
    )
    owner_references = [str(r.get("reference")) for r in my_reservations(planner2_client)]
    assert RESERVATION_COMMITTED in owner_references, (
        f"the owning planner does not see {RESERVATION_COMMITTED!r} in their own "
        f"list either, so the denial above proves nothing: {owner_references!r}"
    )


def test_unauthenticated_reservation_denied(anon_client, db):
    # cov: C-RL-01, C-RL-09, C-RL-26, C-RL-27, C-RL-28, C-UF-01, C-UF-02,
    # cov: C-UF-11, C-UF-12, C-UF-13, C-TR-14, C-TR-15, C-TR-16, C-TR-17,
    # cov: C-DC-01, C-DC-02, C-DC-03, C-DC-04, C-DC-05, C-DC-06, C-DC-07,
    # cov: C-DC-08, C-DC-09, C-DC-10, C-DC-11, C-DC-12, C-DC-13, C-DC-14,
    # cov: C-DC-15, C-DC-39, C-DC-40, C-BP-01, C-BP-02, C-BP-03, C-BP-04,
    # cov: C-BP-15, C-BP-16, C-DM-49
    """An anonymous caller is denied on every protected route, and the two routes
    that are deliberately open stay open.

    Reaching any of these routes at all is itself an observation. This process
    runs after the agent session has ended, from outside the container, against
    the port the environment published on the origin the environment named. A
    server that died with the session, or bound loopback, or baked in a port of
    its own choosing, answers none of them. The bearer header is observed by
    contrast: the routes that refuse an anonymous caller here are the ones the
    authenticated fixtures reach with a token.
    """
    reservations_before = db.count_reservations()
    ledger_before = db.count_all_ledger()

    denied_reserve = reserve(anon_client, SKU_CONTENDED, 1)
    assert denied_reserve.status_code == 401, (
        f"POST /api/reservations with no bearer token returned "
        f"{denied_reserve.status_code}, expected 401. Body was "
        f"{denied_reserve.text[:400]}"
    )
    denied_adjust = adjust(anon_client, SKU_ADJUSTED, 1, probe_reason("anon"))
    assert denied_adjust.status_code == 401, (
        f"POST /api/adjustments with no bearer token returned "
        f"{denied_adjust.status_code}, expected 401. Body was "
        f"{denied_adjust.text[:400]}"
    )

    for path in ("/board", "/ledger", "/reservations"):
        blocked = anon_client.get(path)
        assert blocked.status_code == 401, (
            f"GET /api{path} with no bearer token returned "
            f"{blocked.status_code}, expected 401. Body was "
            f"{blocked.text[:400]}"
        )

    health = anon_client.get("/health")
    assert health.status_code == 200, (
        f"GET /api/health returned {health.status_code} with no bearer token, "
        f"expected 200. The health route carries no authentication"
    )

    assert db.count_reservations() == reservations_before, (
        f"an anonymous call still created a reservation: reservations moved from "
        f"{reservations_before} to {db.count_reservations()}"
    )
    assert db.count_all_ledger() == ledger_before, (
        f"an anonymous call still appended a ledger line: {ledger_before} before, "
        f"{db.count_all_ledger()} after"
    )
