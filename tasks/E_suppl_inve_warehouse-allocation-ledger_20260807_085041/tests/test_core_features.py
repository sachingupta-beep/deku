"""The business rules the brief pins.

Reserving holds stock without moving on-hand, releasing gives it back, an
adjustment moves on-hand without touching held stock, and every accepted movement
leaves one ledger line that names its actor and the free count it left behind.

Each grader here restores what it took, so the file is safe to run twice.
"""

from __future__ import annotations

from conftest import (
    KIND_ADJUST,
    KIND_RESERVE,
    PLANNER_EMAIL,
    SKU_ADJUSTED,
    SKU_LIVE,
    STATUS_HELD,
    STATUS_RELEASED,
    adjust_ok,
    board_row,
    ledger,
    probe_reason,
    release_ok,
    reserve_ok,
)


def test_reservation_holds_stock_and_lowers_free(planner_client, db):
    # cov: C-OV-01, C-OV-02, C-OV-03, C-OV-04, C-CF-01, C-CF-02, C-CF-03,
    # cov: C-CF-04, C-CF-05, C-DC-21, C-DC-22, C-DC-26, C-DM-24, C-DM-26,
    # cov: C-CF-56
    """A reservation raises held stock, lowers free stock, and leaves the on-hand
    count exactly where it was.

    The three counts are read from the board and from the database, because the
    interesting failure is a build whose board is honest while its rows are not.
    """
    before = board_row(planner_client, SKU_LIVE)
    on_hand_before = int(before["on_hand"])
    reserved_before = int(before["reserved"])
    free_before = int(before["free"])

    assert free_before >= 3, (
        f"item {SKU_LIVE!r} carries {free_before} free, so a reservation of 3 "
        f"cannot be graded here. The seed opens it at 24 on hand with 6 held"
    )

    created = reserve_ok(planner_client, SKU_LIVE, 3)
    reference = str(created["reference"])
    try:
        assert str(created["status"]) == STATUS_HELD, (
            f"the reservation created on {SKU_LIVE!r} carries status "
            f"{created['status']!r}, expected {STATUS_HELD!r}"
        )
        assert int(created["free_after"]) == free_before - 3, (
            f"POST /api/reservations reported free_after "
            f"{created['free_after']!r} after holding 3 of {SKU_LIVE!r}, expected "
            f"{free_before - 3}"
        )

        after = board_row(planner_client, SKU_LIVE)
        assert int(after["on_hand"]) == on_hand_before, (
            f"a reservation moved on_hand for {SKU_LIVE!r} from {on_hand_before} "
            f"to {after['on_hand']!r}. Reserving commits stock, it does not "
            f"consume it"
        )
        assert int(after["reserved"]) == reserved_before + 3, (
            f"held stock for {SKU_LIVE!r} moved from {reserved_before} to "
            f"{after['reserved']!r} across a reservation of 3"
        )
        assert int(after["free"]) == free_before - 3, (
            f"free stock for {SKU_LIVE!r} moved from {free_before} to "
            f"{after['free']!r} across a reservation of 3"
        )

        assert db.on_hand(SKU_LIVE) == on_hand_before, (
            f"stock_items.on_hand for {SKU_LIVE!r} reads {db.on_hand(SKU_LIVE)}, "
            f"expected {on_hand_before}. The board and the row disagree"
        )
        assert db.reserved(SKU_LIVE) == reserved_before + 3, (
            f"stock_items.reserved for {SKU_LIVE!r} reads "
            f"{db.reserved(SKU_LIVE)}, expected {reserved_before + 3}"
        )

        row = db.reservation(reference)
        assert row is not None, (
            f"the reservation reported as {reference!r} is absent from the "
            f"reservations table"
        )
        assert int(row["quantity"]) == 3, (
            f"reservation {reference!r} stored quantity {row['quantity']!r}, "
            f"expected 3"
        )
        assert str(row["status"]) == STATUS_HELD, (
            f"reservation {reference!r} stored status {row['status']!r}, expected "
            f"{STATUS_HELD!r}"
        )
    finally:
        release_ok(planner_client, reference)


def test_release_returns_stock_to_free(planner_client, db):
    # cov: C-OV-05, C-OV-06, C-CF-22, C-CF-23, C-CF-24, C-CF-25, C-DC-27,
    # cov: C-DC-30, C-DM-27, C-DM-28, C-DM-29, C-DM-30, C-RL-05, C-RL-06
    """Releasing a held reservation returns the stock and marks the reservation
    released, by its pinned reference rather than by any database id."""
    free_before = int(board_row(planner_client, SKU_LIVE)["free"])
    reserved_before = db.reserved(SKU_LIVE)

    created = reserve_ok(planner_client, SKU_LIVE, 2)
    reference = str(created["reference"])
    assert db.reserved(SKU_LIVE) == reserved_before + 2, (
        f"stock_items.reserved for {SKU_LIVE!r} did not rise to "
        f"{reserved_before + 2} before the release under grading"
    )

    released = release_ok(planner_client, reference)
    assert str(released["status"]) == STATUS_RELEASED, (
        f"releasing {reference!r} reported status {released['status']!r}, "
        f"expected {STATUS_RELEASED!r}"
    )
    assert int(released["free_after"]) == free_before, (
        f"releasing {reference!r} reported free_after {released['free_after']!r}, "
        f"expected the {free_before} that stood before the hold"
    )

    assert int(board_row(planner_client, SKU_LIVE)["free"]) == free_before, (
        f"free stock for {SKU_LIVE!r} did not return to {free_before} after "
        f"{reference!r} was released"
    )
    assert db.reserved(SKU_LIVE) == reserved_before, (
        f"stock_items.reserved for {SKU_LIVE!r} reads {db.reserved(SKU_LIVE)} "
        f"after the release, expected {reserved_before}"
    )
    row = db.reservation(reference)
    assert str(row["status"]) == STATUS_RELEASED, (
        f"reservation {reference!r} still stores status {row['status']!r} after a "
        f"release the API reported as successful"
    )


def test_adjustment_raises_on_hand_and_free(admin_client, db):
    # cov: C-OV-07, C-OV-08, C-CF-27, C-CF-28, C-CF-29, C-RL-12, C-CN-01,
    # cov: C-CN-02, C-CN-03, C-DC-31, C-DC-32, C-DC-35, C-DM-46, C-BP-12
    """An adjustment moves on-hand stock, carries its reason into the ledger, and
    leaves held stock untouched. The delta is undone afterwards, so the seeded
    row is exactly where it started."""
    before = board_row(admin_client, SKU_ADJUSTED)
    on_hand_before = int(before["on_hand"])
    reserved_before = int(before["reserved"])
    free_before = int(before["free"])
    reason = probe_reason("recount")

    result = adjust_ok(admin_client, SKU_ADJUSTED, 5, reason)
    try:
        assert int(result["on_hand"]) == on_hand_before + 5, (
            f"POST /api/adjustments reported on_hand {result['on_hand']!r} after "
            f"moving {SKU_ADJUSTED!r} by 5, expected {on_hand_before + 5}"
        )
        assert int(result["free"]) == free_before + 5, (
            f"POST /api/adjustments reported free {result['free']!r} after moving "
            f"{SKU_ADJUSTED!r} by 5, expected {free_before + 5}"
        )
        assert int(result["reserved"]) == reserved_before, (
            f"an adjustment moved held stock for {SKU_ADJUSTED!r} from "
            f"{reserved_before} to {result['reserved']!r}. An adjustment touches "
            f"on-hand stock only"
        )

        assert db.on_hand(SKU_ADJUSTED) == on_hand_before + 5, (
            f"stock_items.on_hand for {SKU_ADJUSTED!r} reads "
            f"{db.on_hand(SKU_ADJUSTED)}, expected {on_hand_before + 5}"
        )
        assert db.reserved(SKU_ADJUSTED) == reserved_before, (
            f"stock_items.reserved for {SKU_ADJUSTED!r} reads "
            f"{db.reserved(SKU_ADJUSTED)}, expected the unchanged {reserved_before}"
        )

        newest = ledger(admin_client, SKU_ADJUSTED)[0]
        assert str(newest["kind"]) == KIND_ADJUST, (
            f"the newest ledger line for {SKU_ADJUSTED!r} carries kind "
            f"{newest['kind']!r}, expected {KIND_ADJUST!r}"
        )
        assert int(newest["quantity_delta"]) == 5, (
            f"the adjustment line for {SKU_ADJUSTED!r} carries quantity_delta "
            f"{newest['quantity_delta']!r}, expected 5"
        )
        assert reason in str(newest.get("reason", "")), (
            f"the adjustment line for {SKU_ADJUSTED!r} carries reason "
            f"{newest.get('reason')!r}, which does not hold the reason the "
            f"request supplied"
        )
    finally:
        adjust_ok(admin_client, SKU_ADJUSTED, -5, probe_reason("restore"))

    assert db.on_hand(SKU_ADJUSTED) == on_hand_before, (
        f"stock_items.on_hand for {SKU_ADJUSTED!r} did not return to "
        f"{on_hand_before} after the opposite adjustment, which is the only "
        f"correction path the brief offers"
    )


def test_ledger_line_records_actor_and_free_after(planner_client, db):
    # cov: C-OV-09, C-OV-15, C-CF-33, C-CF-36, C-CF-37, C-CF-38, C-CF-39,
    # cov: C-CF-40, C-CF-41, C-DC-37, C-DC-38, C-DM-44, C-DM-70, C-UF-09,
    # cov: C-UF-10, C-RL-03
    """One accepted reservation leaves exactly one ledger line, and that line
    names the actor, the signed change in free stock, and the free count it left
    behind."""
    lines_before = db.count_ledger(SKU_LIVE)

    created = reserve_ok(planner_client, SKU_LIVE, 1)
    reference = str(created["reference"])
    try:
        assert db.count_ledger(SKU_LIVE) == lines_before + 1, (
            f"one reservation on {SKU_LIVE!r} moved the ledger from "
            f"{lines_before} lines to {db.count_ledger(SKU_LIVE)}. Exactly one "
            f"line is appended per accepted movement"
        )

        rows = ledger(planner_client, SKU_LIVE)
        assert rows, f"GET /api/ledger returned nothing for {SKU_LIVE!r}"
        newest = rows[0]
        assert str(newest["kind"]) == KIND_RESERVE, (
            f"the newest ledger line for {SKU_LIVE!r} carries kind "
            f"{newest['kind']!r}, expected {KIND_RESERVE!r}. The ledger reads "
            f"newest first"
        )
        assert int(newest["quantity_delta"]) == -1, (
            f"the reserve line for {SKU_LIVE!r} carries quantity_delta "
            f"{newest['quantity_delta']!r}, expected -1. A reservation lowers "
            f"free stock by its quantity"
        )
        assert str(newest["actor_email"]) == PLANNER_EMAIL, (
            f"the reserve line for {SKU_LIVE!r} names actor_email "
            f"{newest['actor_email']!r}, expected {PLANNER_EMAIL!r}"
        )
        assert str(newest["sku"]) == SKU_LIVE, (
            f"the newest ledger line filtered to {SKU_LIVE!r} carries sku "
            f"{newest['sku']!r}"
        )
        assert newest.get("created_at"), (
            f"the reserve line for {SKU_LIVE!r} carries no created_at: {newest!r}"
        )

        free_now = int(board_row(planner_client, SKU_LIVE)["free"])
        assert int(newest["free_after"]) == free_now, (
            f"the reserve line for {SKU_LIVE!r} records free_after "
            f"{newest['free_after']!r} while the board reads {free_now} free"
        )
    finally:
        release_ok(planner_client, reference)
