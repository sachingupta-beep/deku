"""Contention, boundary, validation refusal and empty state.

The pattern's critical focus lives here: an oversell denied under contention, at
the database rather than in application code. Everything else in this file is one
of the boundaries around it.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from conftest import (
    KIND_RELEASE,
    REFUSAL_FIELD,
    SKU_ADJUSTED,
    SKU_COMMITTED,
    SKU_CONTENDED,
    SKU_EMPTY,
    SKU_LIVE,
    STATUS_RELEASED,
    UNKNOWN_SKU,
    adjust,
    board_row,
    ledger,
    probe_reason,
    refusal_body,
    release,
    release_every_hold,
    release_ok,
    reserve,
    reserve_ok,
)


def test_reservation_beyond_free_refused_with_free_quantity(planner_client, db):
    # cov: C-OV-14, C-OV-16, C-CF-08, C-CF-09, C-CF-10, C-CF-11, C-CF-12,
    # cov: C-DC-23, C-DC-41, C-DC-42, C-DC-44, C-DC-46, C-DC-47, C-TR-06,
    # cov: C-TR-07, C-TR-08, C-UF-30, C-UF-32, C-UF-33, C-DM-60, C-DM-62
    """A reservation against a fully committed item is refused with the quantity
    still free, and nothing anywhere moves."""
    row = board_row(planner_client, SKU_COMMITTED)
    assert int(row["free"]) == 0, (
        f"item {SKU_COMMITTED!r} reads {row['free']!r} free, but the seed commits "
        f"all 12 of its pallets so that a refusal can be graded here"
    )

    reservations_before = db.count_reservations()
    lines_before = db.count_ledger(SKU_COMMITTED)
    reserved_before = db.reserved(SKU_COMMITTED)

    refused = reserve(planner_client, SKU_COMMITTED, 1)
    assert refused.status_code == 409, (
        f"POST /api/reservations for 1 of {SKU_COMMITTED!r} with nothing free "
        f"returned {refused.status_code}, expected 409. Body was "
        f"{refused.text[:400]}"
    )
    body = refusal_body(refused)
    assert REFUSAL_FIELD in body, (
        f"the refusal for {SKU_COMMITTED!r} carries no {REFUSAL_FIELD} field, so "
        f"a planner is never told how much is still free. Body was {body!r}"
    )
    assert int(body[REFUSAL_FIELD]) == 0, (
        f"the refusal for {SKU_COMMITTED!r} reports {body[REFUSAL_FIELD]!r} still "
        f"free, expected 0"
    )

    assert db.count_reservations() == reservations_before, (
        f"the refused reservation wrote a row anyway: reservations moved from "
        f"{reservations_before} to {db.count_reservations()}"
    )
    assert db.count_ledger(SKU_COMMITTED) == lines_before, (
        f"the refused reservation appended a ledger line: {SKU_COMMITTED!r} moved "
        f"from {lines_before} lines to {db.count_ledger(SKU_COMMITTED)}"
    )
    assert db.reserved(SKU_COMMITTED) == reserved_before, (
        f"the refused reservation moved held stock for {SKU_COMMITTED!r} from "
        f"{reserved_before} to {db.reserved(SKU_COMMITTED)}"
    )


def test_concurrent_reservations_cannot_oversell(planner_client, planner2_client, db):
    # cov: C-CF-13, C-CF-14, C-CF-15, C-CF-16, C-CF-17, C-CF-18, C-CF-19,
    # cov: C-CF-20, C-TR-01, C-TR-02, C-TR-03, C-TR-04, C-TR-05, C-DM-13,
    # cov: C-DM-15, C-DM-16, C-BP-06, C-BP-08, C-DM-50, C-DM-51, C-DM-52,
    # cov: C-DM-53
    """Two planners ask for the last pallets at the same instant, and exactly one
    of them gets them.

    The setup deliberately does not assume a starting quantity. It hands back
    whatever either planner still holds on the contended item, reads what is free,
    and then contends for exactly that. So the claim is exact whatever the run
    history was, which is what lets the same claim hold on a second oracle run.

    A build that reads free stock, decides in application code, and then writes
    passes every other grader in this suite and fails here.
    """
    release_every_hold(planner_client, SKU_CONTENDED)
    release_every_hold(planner2_client, SKU_CONTENDED)

    free_now = int(board_row(planner_client, SKU_CONTENDED)["free"])
    assert free_now >= 1, (
        f"item {SKU_CONTENDED!r} reads {free_now} free after both planners handed "
        f"back their holds, so there are no last pallets to contend for"
    )
    on_hand_now = db.on_hand(SKU_CONTENDED)
    # The baseline is measured rather than assumed. Anchoring the assertions
    # below to a literal 0 would encode a fact this grader never established, and
    # a violated assumption would then read as an application defect.
    reserved_now = db.reserved(SKU_CONTENDED)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(reserve, planner_client, SKU_CONTENDED, free_now)
        second = pool.submit(reserve, planner2_client, SKU_CONTENDED, free_now)
        responses = [first.result(), second.result()]

    codes = [r.status_code for r in responses]
    winners = [r for r in responses if r.status_code in (200, 201)]
    losers = [r for r in responses if r.status_code == 409]

    assert len(winners) == 1, (
        f"two simultaneous reservations for all {free_now} free pallets of "
        f"{SKU_CONTENDED!r} returned {codes!r}. Exactly one may succeed: two "
        f"successes is an oversell, none is a lost reservation"
    )
    assert len(losers) == 1, (
        f"the losing reservation for {SKU_CONTENDED!r} returned {codes!r}, "
        f"expected exactly one 409"
    )

    refused = refusal_body(losers[0])
    assert REFUSAL_FIELD in refused, (
        f"the losing reservation for {SKU_CONTENDED!r} carries no "
        f"{REFUSAL_FIELD} field: {refused!r}"
    )
    assert int(refused[REFUSAL_FIELD]) == 0, (
        f"the losing reservation for {SKU_CONTENDED!r} reports "
        f"{refused[REFUSAL_FIELD]!r} still free, expected 0 once the winner took "
        f"all {free_now}"
    )

    reference = str(winners[0].json()["reference"])
    try:
        assert db.reserved(SKU_CONTENDED) == reserved_now + free_now, (
            f"stock_items.reserved for {SKU_CONTENDED!r} reads "
            f"{db.reserved(SKU_CONTENDED)} after the contended pair, expected "
            f"{reserved_now + free_now}. Both writes landed, which is the "
            f"oversell itself"
        )
        assert db.reserved(SKU_CONTENDED) <= db.on_hand(SKU_CONTENDED), (
            f"stock_items.reserved for {SKU_CONTENDED!r} reads "
            f"{db.reserved(SKU_CONTENDED)} against on_hand "
            f"{db.on_hand(SKU_CONTENDED)}. Free stock is negative, so the check "
            f"constraint the brief requires is absent"
        )
        assert db.on_hand(SKU_CONTENDED) == on_hand_now, (
            f"the contended pair moved on_hand for {SKU_CONTENDED!r} from "
            f"{on_hand_now} to {db.on_hand(SKU_CONTENDED)}"
        )
        assert db.held_total(SKU_CONTENDED) == reserved_now + free_now, (
            f"the live reservations on {SKU_CONTENDED!r} sum to "
            f"{db.held_total(SKU_CONTENDED)} while the counter reads "
            f"{db.reserved(SKU_CONTENDED)}. The loser left a row behind"
        )
    finally:
        release_every_hold(planner_client, SKU_CONTENDED)
        release_every_hold(planner2_client, SKU_CONTENDED)

    assert int(board_row(planner_client, SKU_CONTENDED)["free"]) == free_now, (
        f"free stock for {SKU_CONTENDED!r} did not return to {free_now} after "
        f"both planners handed back their holds"
    )
    assert reference, (
        f"the winning reservation on {SKU_CONTENDED!r} reported no reference"
    )


def test_duplicate_release_refused(planner_client, db):
    # cov: C-CF-26, C-CF-35, C-DC-28, C-DM-32, C-DM-33, C-DM-34, C-DM-36,
    # cov: C-DM-37, C-DM-38, C-DM-39, C-DM-40, C-DM-41, C-DM-42, C-DM-43,
    # cov: C-DM-35, C-UF-22, C-UF-23, C-DC-36
    """Releasing a reservation twice is a conflict, and the second call appends
    no second line."""
    created = reserve_ok(planner_client, SKU_ADJUSTED, 2)
    reference = str(created["reference"])
    releases_before = db.count_ledger(SKU_ADJUSTED, KIND_RELEASE)
    reserved_before = db.reserved(SKU_ADJUSTED)

    release_ok(planner_client, reference)
    assert db.count_ledger(SKU_ADJUSTED, KIND_RELEASE) == releases_before + 1, (
        f"releasing {reference!r} left the release-line count for "
        f"{SKU_ADJUSTED!r} at {db.count_ledger(SKU_ADJUSTED, KIND_RELEASE)}, "
        f"expected {releases_before + 1}"
    )

    repeat = release(planner_client, reference)
    assert repeat.status_code == 409, (
        f"POST /api/reservations/{reference}/release a second time returned "
        f"{repeat.status_code}, expected 409. Body was {repeat.text[:400]}"
    )
    assert db.count_ledger(SKU_ADJUSTED, KIND_RELEASE) == releases_before + 1, (
        f"the refused second release appended a line anyway: the release-line "
        f"count for {SKU_ADJUSTED!r} reads "
        f"{db.count_ledger(SKU_ADJUSTED, KIND_RELEASE)}"
    )
    assert db.reserved(SKU_ADJUSTED) == reserved_before - 2, (
        f"stock_items.reserved for {SKU_ADJUSTED!r} reads "
        f"{db.reserved(SKU_ADJUSTED)} after one release with one refused repeat, "
        f"expected {reserved_before - 2}. A refused release gave stock back twice"
    )
    row = db.reservation(reference)
    assert str(row["status"]) == STATUS_RELEASED, (
        f"reservation {reference!r} carries status {row['status']!r} after the "
        f"refused repeat, expected {STATUS_RELEASED!r}"
    )


def test_adjustment_below_held_stock_refused(admin_client, db):
    # cov: C-CF-30, C-CF-31, C-DM-54, C-DM-55, C-DM-56, C-DM-58, C-DM-64,
    # cov: C-DM-66, C-DM-67, C-DM-75, C-UF-26, C-UF-27, C-UF-28, C-UF-29
    """An adjustment that would strand held stock is refused from the other side
    of the same constraint, with the quantity still free named."""
    row = board_row(admin_client, SKU_LIVE)
    on_hand_before = int(row["on_hand"])
    reserved_before = int(row["reserved"])
    lines_before = db.count_ledger(SKU_LIVE)

    assert reserved_before >= 1, (
        f"item {SKU_LIVE!r} holds {reserved_before} pallets, but the seed keeps 6 "
        f"of them held so that an adjustment can be refused from below"
    )

    refused = adjust(admin_client, SKU_LIVE, -on_hand_before, probe_reason("writeoff"))
    assert refused.status_code == 409, (
        f"POST /api/adjustments moving {SKU_LIVE!r} by {-on_hand_before} under "
        f"{reserved_before} held pallets returned {refused.status_code}, expected "
        f"409. Body was {refused.text[:400]}"
    )
    body = refusal_body(refused)
    assert REFUSAL_FIELD in body, (
        f"the adjustment refusal for {SKU_LIVE!r} carries no {REFUSAL_FIELD} "
        f"field: {body!r}"
    )
    assert int(body[REFUSAL_FIELD]) == on_hand_before - reserved_before, (
        f"the adjustment refusal for {SKU_LIVE!r} reports "
        f"{body[REFUSAL_FIELD]!r} still free, expected "
        f"{on_hand_before - reserved_before}"
    )

    assert db.on_hand(SKU_LIVE) == on_hand_before, (
        f"the refused adjustment moved on_hand for {SKU_LIVE!r} from "
        f"{on_hand_before} to {db.on_hand(SKU_LIVE)}"
    )
    assert db.reserved(SKU_LIVE) == reserved_before, (
        f"the refused adjustment moved held stock for {SKU_LIVE!r} from "
        f"{reserved_before} to {db.reserved(SKU_LIVE)}"
    )
    assert db.count_ledger(SKU_LIVE) == lines_before, (
        f"the refused adjustment appended a ledger line: {SKU_LIVE!r} moved from "
        f"{lines_before} lines to {db.count_ledger(SKU_LIVE)}"
    )


def test_zero_quantity_reservation_refused(planner_client, db):
    # cov: C-CF-21, C-DC-24, C-DM-25, C-UF-31
    """A reservation of nothing is a validation refusal rather than a stock
    refusal, and it writes nothing."""
    reservations_before = db.count_reservations()
    reserved_before = db.reserved(SKU_ADJUSTED)

    refused = reserve(planner_client, SKU_ADJUSTED, 0)
    assert refused.status_code == 422, (
        f"POST /api/reservations for 0 of {SKU_ADJUSTED!r} returned "
        f"{refused.status_code}, expected 422. A quantity below 1 is a validation "
        f"refusal, distinct from the 409 a stock shortfall earns. Body was "
        f"{refused.text[:400]}"
    )
    assert db.count_reservations() == reservations_before, (
        f"the refused zero-quantity reservation wrote a row anyway: reservations "
        f"moved from {reservations_before} to {db.count_reservations()}"
    )
    assert db.reserved(SKU_ADJUSTED) == reserved_before, (
        f"the refused zero-quantity reservation moved held stock for "
        f"{SKU_ADJUSTED!r} from {reserved_before} to {db.reserved(SKU_ADJUSTED)}"
    )


def test_empty_pallet_row_reads_zero_free(auditor_client, db):
    # cov: C-UF-34, C-UF-35, C-UF-36, C-UF-37, C-UF-38, C-UF-39, C-UF-40,
    # cov: C-UF-41, C-UF-42, C-UF-03, C-UF-05, C-CF-53, C-CF-54, C-TR-09,
    # cov: C-TR-10, C-TR-11, C-TR-12, C-TR-13, C-DC-18, C-DC-20, C-RL-10,
    # cov: C-RL-11, C-BP-10, C-BP-13, C-BP-14
    """An item nothing has ever moved reads three zeros with an empty ledger,
    never an error, and an item that does not exist reads as missing."""
    row = board_row(auditor_client, SKU_EMPTY)
    assert int(row["on_hand"]) == 0, (
        f"the board reports on_hand {row['on_hand']!r} for {SKU_EMPTY!r}, which "
        f"the seed opens at 0"
    )
    assert int(row["reserved"]) == 0, (
        f"the board reports reserved {row['reserved']!r} for {SKU_EMPTY!r}, which "
        f"nothing in this product ever holds"
    )
    assert int(row["free"]) == 0, (
        f"the board reports free {row['free']!r} for {SKU_EMPTY!r}, expected 0"
    )

    lines = ledger(auditor_client, SKU_EMPTY)
    assert lines == [], (
        f"GET /api/ledger for {SKU_EMPTY!r} returned {lines!r}, expected an empty "
        f"collection rather than an error or a placeholder line"
    )
    assert db.count_ledger(SKU_EMPTY) == 0, (
        f"the ledger table holds {db.count_ledger(SKU_EMPTY)} lines for "
        f"{SKU_EMPTY!r}, which the seed opens with none"
    )

    stored = db.item(SKU_EMPTY)
    assert int(stored["on_hand"]) == 0, (
        f"stock_items.on_hand for {SKU_EMPTY!r} reads {stored['on_hand']!r}, "
        f"expected 0"
    )
    assert db.held_total(SKU_EMPTY) == 0, (
        f"{SKU_EMPTY!r} carries live reservations summing to "
        f"{db.held_total(SKU_EMPTY)}, expected none"
    )

    missing = auditor_client.get("/ledger", params={"sku": UNKNOWN_SKU})
    assert missing.status_code == 404, (
        f"GET /api/ledger for the unknown sku {UNKNOWN_SKU!r} returned "
        f"{missing.status_code}, expected 404. Body was {missing.text[:400]}"
    )
    assert db.item(UNKNOWN_SKU) is None, (
        f"{UNKNOWN_SKU!r} exists in stock_items, so the 404 above proves nothing"
    )
