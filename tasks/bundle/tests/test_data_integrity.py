"""Persistence and reconciliation: what survives a re-read, and what the ledger holds.

Business rules belong in test_core_features.py.
"""

from __future__ import annotations

from conftest import (
    ALL_LINES, ALL_REGIONS, ANALYST_EMAIL, ANALYST_NAME, EXCLUDED_REFS,
    JANUARY_END, JANUARY_START, JANUARY_TITLE, FEBRUARY_TITLE,
    MANAGER_NORTH_EMAIL, MANAGER_NORTH_NAME, MANAGER_SOUTH_EMAIL,
    MANAGER_SOUTH_NAME, REGION_NORTH, REGION_SOUTH, REGION_WEST,
    SEEDED_TRANSACTIONS, breakdown_map, create_published_report,
    report_id_by_title, summary_for, transactions_for, unique_report_title,
)


# cov: C-DM-06, C-DM-07, C-DM-08, C-DM-09, C-DM-10, C-DM-11, C-DM-33, C-DM-34, C-DM-35, C-DM-36, C-RL-14, C-RL-16
def test_seeded_accounts_persisted(db):
    """The three seeded accounts exist with their pinned roles, names and regions."""
    analyst = db.user_by_email(ANALYST_EMAIL)
    assert analyst is not None, f"seeded analyst {ANALYST_EMAIL!r} is missing from users"
    assert analyst.get("role") == "analyst", (
        f"{ANALYST_EMAIL!r} has role {analyst.get('role')!r}; expected 'analyst'"
    )
    assert analyst.get("name") == ANALYST_NAME, (
        f"{ANALYST_EMAIL!r} has name {analyst.get('name')!r}; expected {ANALYST_NAME!r}"
    )
    assert not analyst.get("region_id"), (
        f"{ANALYST_EMAIL!r} carries region_id {analyst.get('region_id')!r}; an "
        f"analyst is bound to no region"
    )

    north_region = db.region_by_name(REGION_NORTH)
    south_region = db.region_by_name(REGION_SOUTH)
    west_region = db.region_by_name(REGION_WEST)
    assert north_region is not None, f"seeded region {REGION_NORTH!r} is missing"
    assert south_region is not None, f"seeded region {REGION_SOUTH!r} is missing"
    assert west_region is not None, f"seeded region {REGION_WEST!r} is missing"

    for email, name, region in (
        (MANAGER_NORTH_EMAIL, MANAGER_NORTH_NAME, north_region),
        (MANAGER_SOUTH_EMAIL, MANAGER_SOUTH_NAME, south_region),
    ):
        row = db.user_by_email(email)
        assert row is not None, f"seeded manager {email!r} is missing from users"
        assert row.get("role") == "manager", (
            f"{email!r} has role {row.get('role')!r}; expected 'manager'"
        )
        assert row.get("name") == name, (
            f"{email!r} has name {row.get('name')!r}; expected {name!r}"
        )
        assert row.get("region_id") == region.get("id"), (
            f"{email!r} carries region_id {row.get('region_id')!r}; expected the id "
            f"of {region.get('name')!r}"
        )

    for email in (MANAGER_NORTH_EMAIL, MANAGER_SOUTH_EMAIL):
        assert db.user_by_email(email).get("region_id") != west_region.get("id"), (
            f"{email!r} points at {REGION_WEST!r}, which the brief seeds with no "
            f"manager so the analyst's grand total spans a region no manager reads"
        )


# cov: C-DM-12, C-DM-31
def test_seeded_regions_persisted(db):
    """All three seeded regions exist by name."""
    for name in ALL_REGIONS:
        row = db.region_by_name(name)
        assert row is not None, (
            f"seeded region {name!r} is missing; the app did not seed on first start"
        )


# cov: C-DM-13, C-DM-32
def test_seeded_product_lines_persisted(db):
    """Both seeded product lines exist by name."""
    for name in ALL_LINES:
        row = db.product_line_by_name(name)
        assert row is not None, (
            f"seeded product line {name!r} is missing; the app did not seed on "
            f"first start"
        )


# cov: C-DM-42, C-DM-25, C-DM-23
def test_seeded_january_report_published(db):
    """The January report is seeded over its pinned period and is already published."""
    row = db.report_by_title(JANUARY_TITLE)
    assert row is not None, f"seeded report {JANUARY_TITLE!r} is missing from reports"
    assert row.get("status") == "published", (
        f"{JANUARY_TITLE!r} carries status {row.get('status')!r}; expected 'published'"
    )
    assert row.get("published_at"), (
        f"{JANUARY_TITLE!r} is published but carries no published_at timestamp"
    )
    assert str(row.get("period_start")).startswith(JANUARY_START), (
        f"{JANUARY_TITLE!r} starts at {row.get('period_start')!r}; expected "
        f"{JANUARY_START!r}"
    )
    assert str(row.get("period_end")).startswith(JANUARY_END), (
        f"{JANUARY_TITLE!r} ends at {row.get('period_end')!r}; expected {JANUARY_END!r}"
    )


# cov: C-DM-43, C-RL-01
def test_seeded_february_report_draft(db):
    """The February report is seeded and is still a draft with no publication time."""
    row = db.report_by_title(FEBRUARY_TITLE)
    assert row is not None, f"seeded report {FEBRUARY_TITLE!r} is missing from reports"
    assert row.get("status") == "draft", (
        f"{FEBRUARY_TITLE!r} carries status {row.get('status')!r}; expected 'draft'"
    )
    assert not row.get("published_at"), (
        f"{FEBRUARY_TITLE!r} is a draft but carries published_at "
        f"{row.get('published_at')!r}"
    )


# cov: C-TR-28, C-CF-15, C-DM-26
def test_published_report_survives_reread(analyst_client, db):
    """A report published in this run reads back published, with an unmoved timestamp."""
    title = unique_report_title("Reread")
    report_id = create_published_report(analyst_client, title, JANUARY_START, JANUARY_END)

    first = db.report_by_id(report_id)
    assert first is not None, f"report {report_id} is missing from reports after publish"
    stamped = first.get("published_at")
    assert stamped, f"report {report_id} carries no published_at after a 200 publish"

    fetched = analyst_client.get(f"/reports/{report_id}")
    assert fetched.status_code == 200, (
        f"GET /api/reports/{report_id} returned {fetched.status_code}: "
        f"{fetched.text[:400]}"
    )
    assert fetched.json().get("status") == "published", (
        f"report {report_id} reads back as {fetched.json().get('status')!r}"
    )

    again = db.report_by_id(report_id)
    assert again.get("published_at") == stamped, (
        f"published_at moved from {stamped!r} to {again.get('published_at')!r} on a "
        f"plain re-read"
    )


# cov: C-OV-05, C-CF-23, C-TR-23, C-TR-24, C-TR-25, C-DM-27, C-DM-28, C-DC-35, C-DC-36, C-DC-37, C-DC-38, C-DC-39, C-DC-40
def test_new_report_summary_reconciles_on_read(analyst_client):
    """A report created after seed time reconciles, so no figure was precomputed.

    A stored aggregate can only be right for a period that existed when it was
    written. This report's period is chosen at run time, so its summary can only
    be correct if every figure is derived from the ledger on the read itself.
    """
    from conftest import ANALYST_TOTAL, REGION_TOTALS, LINE_TOTALS

    title = unique_report_title("Derived")
    report_id = create_published_report(analyst_client, title, JANUARY_START, JANUARY_END)

    summary = summary_for(analyst_client, report_id)
    assert int(summary["total"]) == ANALYST_TOTAL, (
        f"a report created at run time over the January period totals "
        f"{summary.get('total')!r}; the ledger produces {ANALYST_TOTAL}"
    )

    regions = breakdown_map(summary, "by_region", "region")
    for name, expected in REGION_TOTALS.items():
        assert regions.get(name) == expected, (
            f"the run-time report reports {regions.get(name)!r} for {name!r}; "
            f"expected {expected}"
        )
    lines = breakdown_map(summary, "by_product_line", "product_line")
    for name, expected in LINE_TOTALS.items():
        assert lines.get(name) == expected, (
            f"the run-time report reports {lines.get(name)!r} for {name!r}; "
            f"expected {expected}"
        )

    rows = transactions_for(analyst_client, report_id)
    assert sum(int(row["amount"]) for row in rows) == int(summary["total"]), (
        f"the run-time report's rows sum to "
        f"{sum(int(row['amount']) for row in rows)} while the summary reports "
        f"{summary['total']}"
    )


# cov: C-CF-26, C-CF-27, C-DM-14, C-DM-15, C-DM-16, C-DM-17, C-DM-18, C-DM-19, C-DM-37, C-DM-38, C-DM-39, C-DM-40, C-DM-41, C-DM-46, C-DM-47, C-DM-48, C-DM-49, C-DM-50, C-DM-51, C-UF-22
def test_excluded_rows_absent_from_transactions(analyst_client, db, manager_north_client):
    """Refunded, void and out-of-period rows are seeded, and none of them is counted."""
    for ref, seeded in SEEDED_TRANSACTIONS.items():
        row = db.transaction_by_ref(ref)
        assert row is not None, f"seeded transaction {ref!r} is missing from transactions"
        assert int(row.get("amount")) == seeded["amount"], (
            f"{ref} carries amount {row.get('amount')!r}; the ledger pins "
            f"{seeded['amount']}"
        )
        assert row.get("status") == seeded["status"], (
            f"{ref} carries status {row.get('status')!r}; the ledger pins "
            f"{seeded['status']!r}"
        )
        assert str(row.get("occurred_on")).startswith(seeded["occurred_on"]), (
            f"{ref} occurred on {row.get('occurred_on')!r}; the ledger pins "
            f"{seeded['occurred_on']!r}"
        )

    report_id = report_id_by_title(analyst_client, JANUARY_TITLE)
    assert report_id is not None, f"{JANUARY_TITLE!r} is not in the report list"
    listed = {row.get("external_ref") for row in transactions_for(analyst_client, report_id)}
    for ref in EXCLUDED_REFS:
        assert ref not in listed, (
            f"{ref} is listed behind {JANUARY_TITLE!r}, but the ledger excludes it: "
            f"{SEEDED_TRANSACTIONS[ref]['status']} on "
            f"{SEEDED_TRANSACTIONS[ref]['occurred_on']}"
        )

    manager_report_id = report_id_by_title(manager_north_client, JANUARY_TITLE)
    assert manager_report_id is not None, (
        f"{JANUARY_TITLE!r} is not visible to the North manager"
    )
    manager_refs = {row.get("external_ref")
                    for row in transactions_for(manager_north_client, manager_report_id)}
    for ref in EXCLUDED_REFS:
        assert ref not in manager_refs, (
            f"{ref} is listed behind {JANUARY_TITLE!r} for the North manager"
        )
