"""Persistence and reconciliation at the declared backend.

The `db` slot's observation obligation lives here: every grader in this file
reads the allocation tables through the backend capability adapter and holds them
against what the application publishes. A board that agrees with itself proves
nothing; a board that agrees with the rows behind it is the whole point.
"""

from __future__ import annotations

from conftest import (
    KIND_RELEASE,
    KIND_RESERVE,
    SEEDED_ITEM_NAMES,
    SEEDED_SKUS,
    SKU_LIVE,
    STATUS_HELD,
    board,
    ledger,
    release_ok,
    reserve_ok,
)


def test_board_reconciles_with_stock_rows(planner_client, db):
    # cov: C-CF-04, C-CF-06, C-CF-07, C-CF-48, C-CF-49, C-CF-50, C-CF-51,
    # cov: C-CF-52, C-DC-16, C-DC-17, C-DC-48, C-DC-49, C-DM-08, C-DM-09,
    # cov: C-DM-11, C-DM-12, C-DM-14, C-DM-18, C-DM-57, C-DM-59, C-DM-61,
    # cov: C-DM-63, C-DM-65, C-TR-18, C-TR-19, C-RL-02, C-DM-10, C-DM-17
    """Every board row agrees with the stock_items row behind it, and free stock
    is the difference rather than a stored number.

    This is the grader that would catch a cached counter: a build that keeps its
    own free column drifts from `on_hand` minus `reserved` the first time the two
    writers disagree, and nothing on screen says so.
    """
    rows = board(planner_client)
    by_sku = {str(r["sku"]): r for r in rows}

    for sku in SEEDED_SKUS:
        assert sku in by_sku, (
            f"seeded item {sku!r} is absent from GET /api/board, which carried "
            f"{sorted(by_sku)!r}"
        )

    for sku in SEEDED_SKUS:
        row = by_sku[sku]
        stored = db.item(sku)
        assert stored is not None, (
            f"seeded item {sku!r} is absent from the stock_items table"
        )
        assert str(row.get("name")) == SEEDED_ITEM_NAMES[sku], (
            f"the board names {sku!r} {row.get('name')!r}, expected "
            f"{SEEDED_ITEM_NAMES[sku]!r}"
        )
        assert int(row["on_hand"]) == int(stored["on_hand"]), (
            f"the board reports on_hand {row['on_hand']!r} for {sku!r} while "
            f"stock_items holds {stored['on_hand']!r}"
        )
        assert int(row["reserved"]) == int(stored["reserved"]), (
            f"the board reports reserved {row['reserved']!r} for {sku!r} while "
            f"stock_items holds {stored['reserved']!r}"
        )
        assert int(row["free"]) == int(stored["on_hand"]) - int(stored["reserved"]), (
            f"the board reports free {row['free']!r} for {sku!r}, which is not "
            f"on_hand {stored['on_hand']!r} minus reserved {stored['reserved']!r}. "
            f"Free stock is derived on every read, never stored"
        )
        assert int(stored["reserved"]) >= 0, (
            f"stock_items.reserved for {sku!r} reads {stored['reserved']!r}, below "
            f"the floor the check constraint holds"
        )
        assert int(stored["reserved"]) <= int(stored["on_hand"]), (
            f"stock_items.reserved for {sku!r} reads {stored['reserved']!r} against "
            f"on_hand {stored['on_hand']!r}. Free stock has gone negative, which "
            f"the check constraint exists to make impossible"
        )


def test_reserved_column_matches_held_reservations(db):
    # cov: C-CF-03, C-CF-24, C-DM-31, C-DM-19, C-DM-20, C-DM-22, C-DM-23,
    # cov: C-DM-25, C-DM-71, C-DM-72, C-DM-73, C-DM-74, C-BP-05, C-BP-07
    """For every item, the held counter equals the sum of its live reservations.

    The counter and the reservation rows are two independent writers of the same
    fact. A build that updates one without the other reads correctly on the board
    and oversells at the constraint, or refuses stock nobody is holding.
    """
    for sku in SEEDED_SKUS:
        stored = db.item(sku)
        assert stored is not None, (
            f"seeded item {sku!r} is absent from the stock_items table"
        )
        counted = db.held_total(sku)
        assert int(stored["reserved"]) == counted, (
            f"stock_items.reserved for {sku!r} reads {stored['reserved']!r} while "
            f"its {STATUS_HELD!r} reservations sum to {counted}. The counter and "
            f"the reservation rows have drifted apart"
        )

    live = db.item(SKU_LIVE)
    held_rows = [r for r in db.reservations_for_item(live["id"])
                 if str(r["status"]) == STATUS_HELD]
    assert held_rows, (
        f"item {SKU_LIVE!r} carries no {STATUS_HELD!r} reservation, so the seeded "
        f"hold that every other observation leans on is missing"
    )
    for row in held_rows:
        assert int(row["quantity"]) >= 1, (
            f"reservation {row['reference']!r} stores quantity "
            f"{row['quantity']!r}, below the floor of 1 the brief pins"
        )


def test_ledger_survives_release_and_reread(planner_client, db):
    # cov: C-OV-10, C-OV-11, C-OV-12, C-OV-13, C-CF-34, C-CF-43, C-CF-44,
    # cov: C-CF-45, C-CF-46, C-CF-47, C-DM-45, C-DC-50, C-UF-24, C-UF-25,
    # cov: C-UX-53
    """A release appends its own line rather than removing the line that created
    the hold, and both survive a fresh read.

    Append-only is asserted the only way a black-box grader can assert it: the
    reserve lines for an item never go down.
    """
    lines_before = db.count_ledger(SKU_LIVE)
    reserves_before = db.count_ledger(SKU_LIVE, KIND_RESERVE)
    releases_before = db.count_ledger(SKU_LIVE, KIND_RELEASE)

    created = reserve_ok(planner_client, SKU_LIVE, 4)
    reference = str(created["reference"])

    assert db.count_ledger(SKU_LIVE, KIND_RESERVE) == reserves_before + 1, (
        f"a reservation on {SKU_LIVE!r} moved the reserve-line count from "
        f"{reserves_before} to {db.count_ledger(SKU_LIVE, KIND_RESERVE)}"
    )

    release_ok(planner_client, reference)

    assert db.count_ledger(SKU_LIVE, KIND_RESERVE) == reserves_before + 1, (
        f"releasing {reference!r} moved the reserve-line count for {SKU_LIVE!r} "
        f"to {db.count_ledger(SKU_LIVE, KIND_RESERVE)}. A release appends a line, "
        f"it never withdraws one"
    )
    assert db.count_ledger(SKU_LIVE, KIND_RELEASE) == releases_before + 1, (
        f"releasing {reference!r} left the release-line count for {SKU_LIVE!r} at "
        f"{db.count_ledger(SKU_LIVE, KIND_RELEASE)}, expected "
        f"{releases_before + 1}"
    )
    assert db.count_ledger(SKU_LIVE) == lines_before + 2, (
        f"one reservation with one release moved the ledger for {SKU_LIVE!r} from "
        f"{lines_before} lines to {db.count_ledger(SKU_LIVE)}, expected "
        f"{lines_before + 2}"
    )

    rows = ledger(planner_client, SKU_LIVE)
    kinds = [str(r["kind"]) for r in rows[:2]]
    assert kinds[0] == KIND_RELEASE, (
        f"the newest line for {SKU_LIVE!r} carries kind {kinds[0]!r} after a "
        f"release, expected {KIND_RELEASE!r}"
    )
    assert kinds[1] == KIND_RESERVE, (
        f"the line under the release for {SKU_LIVE!r} carries kind {kinds[1]!r}, "
        f"expected the {KIND_RESERVE!r} line that created the hold to still be "
        f"standing"
    )
    assert int(rows[0]["quantity_delta"]) == 4, (
        f"the release line for {SKU_LIVE!r} carries quantity_delta "
        f"{rows[0]['quantity_delta']!r}, expected 4. A release raises free stock "
        f"by the released quantity"
    )
    assert int(rows[1]["quantity_delta"]) == -4, (
        f"the reserve line under it carries quantity_delta "
        f"{rows[1]['quantity_delta']!r}, expected -4"
    )
