"""Business rules and state machines the brief pins, observed over HTTP.

Persistence assertions belong in test_data_integrity.py; role boundaries belong
in test_authorization.py; rejection paths belong in test_edge_cases.py.
"""

from __future__ import annotations

from _shapes import items
from conftest import (
    ALL_LINES, ALL_REGIONS, ANALYST_TOTAL, AURORA_TOTAL, BASALT_TOTAL,
    JANUARY_END, JANUARY_START, JANUARY_TITLE, LINE_AURORA, LINE_BASALT,
    LINE_TOTALS, REGION_TOTALS, SEEDED_TRANSACTIONS, ANALYST_JANUARY_REFS,
    breakdown_map, create_report, report_id_by_title, summary_for,
    transactions_for, unique_report_title,
)


# cov: C-CF-01, C-DC-41, C-RL-15, C-DM-04, C-DM-05
def test_login_returns_access_token(anon_client):
    """POST /api/auth/login exchanges the seeded credentials for a bearer token."""
    from conftest import ANALYST_EMAIL, PASSWORD

    response = anon_client.post(
        "/auth/login", json={"email": ANALYST_EMAIL, "password": PASSWORD}
    )
    assert response.status_code == 200, (
        f"login for {ANALYST_EMAIL} returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    token = response.json().get("access_token")
    assert isinstance(token, str) and token, (
        f"login response carries no access_token: {response.text[:400]}"
    )


# cov: C-CF-04, C-CF-05, C-DC-27, C-RL-16
def test_me_returns_role_and_region(analyst_client, manager_north_client):
    """GET /api/me reports the caller's role, and a region only for a manager."""
    from conftest import REGION_NORTH

    analyst = analyst_client.get("/me")
    assert analyst.status_code == 200, (
        f"GET /api/me as the analyst returned {analyst.status_code}: "
        f"{analyst.text[:400]}"
    )
    body = analyst.json()
    assert body.get("role") == "analyst", (
        f"GET /api/me reports role {body.get('role')!r} for the analyst"
    )
    assert not body.get("region"), (
        f"the analyst carries region {body.get('region')!r}; the analyst has none"
    )

    manager = manager_north_client.get("/me")
    assert manager.status_code == 200, (
        f"GET /api/me as the North manager returned {manager.status_code}: "
        f"{manager.text[:400]}"
    )
    mbody = manager.json()
    assert mbody.get("role") == "manager", (
        f"GET /api/me reports role {mbody.get('role')!r} for a manager"
    )
    region = mbody.get("region")
    region_name = region.get("name") if isinstance(region, dict) else region
    assert region_name == REGION_NORTH, (
        f"the North manager carries region {region_name!r}; expected {REGION_NORTH!r}"
    )


# cov: C-CF-16, C-CF-17, C-DC-34, C-RL-01, C-OV-01
def test_reports_list_shape_for_analyst(analyst_client):
    """GET /api/reports returns a top-level array carrying both seeded reports."""
    from conftest import FEBRUARY_TITLE

    response = analyst_client.get("/reports")
    assert response.status_code == 200, (
        f"GET /api/reports returned {response.status_code}: {response.text[:400]}"
    )
    payload = response.json()
    assert isinstance(payload, list), (
        f"GET /api/reports returned {type(payload).__name__}; the brief pins a "
        f"top-level JSON array"
    )
    titles = {row.get("title") for row in items(payload)}
    assert JANUARY_TITLE in titles, (
        f"{JANUARY_TITLE!r} is missing from the analyst's report list: {sorted(titles)}"
    )
    assert FEBRUARY_TITLE in titles, (
        f"{FEBRUARY_TITLE!r} is missing from the analyst's report list, so the "
        f"analyst cannot see drafts: {sorted(titles)}"
    )


# cov: C-CF-06, C-CF-07, C-DC-25, C-RL-04, C-DM-20, C-DM-21, C-DM-22, C-DM-24
def test_analyst_creates_draft_report(analyst_client):
    """POST /api/reports on an analyst token creates a report in draft state."""
    title = unique_report_title("Draft")
    response = create_report(analyst_client, title, JANUARY_START, JANUARY_END)
    assert response.status_code in (200, 201), (
        f"POST /api/reports returned {response.status_code}: {response.text[:400]}"
    )
    body = response.json()
    assert body.get("status") == "draft", (
        f"a freshly created report carries status {body.get('status')!r}; "
        f"expected 'draft'"
    )
    assert body.get("title") == title, (
        f"the created report carries title {body.get('title')!r}; expected {title!r}"
    )
    assert str(body.get("period_start")).startswith(JANUARY_START), (
        f"the created report carries period_start {body.get('period_start')!r}; "
        f"expected {JANUARY_START!r}"
    )
    assert str(body.get("period_end")).startswith(JANUARY_END), (
        f"the created report carries period_end {body.get('period_end')!r}; "
        f"expected {JANUARY_END!r}"
    )


# cov: C-CF-11, C-CF-12, C-CF-13, C-RL-05, C-DM-26
def test_publish_flips_draft_to_published(analyst_client):
    """Publishing a draft returns 200, flips the status and stamps published_at."""
    title = unique_report_title("Publish")
    created = create_report(analyst_client, title, JANUARY_START, JANUARY_END)
    assert created.status_code in (200, 201), (
        f"POST /api/reports returned {created.status_code}: {created.text[:400]}"
    )
    report_id = created.json().get("id")
    assert report_id is not None, f"the created report has no id: {created.text[:400]}"

    published = analyst_client.post(f"/reports/{report_id}/publish")
    assert published.status_code == 200, (
        f"publishing report {report_id} returned {published.status_code}: "
        f"{published.text[:400]}"
    )
    body = published.json()
    assert body.get("status") == "published", (
        f"the published report carries status {body.get('status')!r}"
    )
    assert body.get("published_at"), (
        f"the published report carries no published_at: {published.text[:400]}"
    )


# cov: C-CF-22, C-CF-30, C-CF-31, C-CF-32, C-CF-48, C-CF-49, C-OV-02, C-OV-03, C-OV-04, C-DM-03
def test_summary_shape_and_analyst_totals(analyst_client):
    """The analyst's January summary carries the pinned shape and the pinned figures."""
    report_id = report_id_by_title(analyst_client, JANUARY_TITLE)
    assert report_id is not None, (
        f"{JANUARY_TITLE!r} is not in the analyst's report list"
    )

    summary = summary_for(analyst_client, report_id)
    assert "report_id" in summary, f"summary has no report_id: {str(summary)[:300]}"
    assert int(summary["total"]) == ANALYST_TOTAL, (
        f"the analyst's grand total is {summary.get('total')!r}; the seeded ledger "
        f"produces {ANALYST_TOTAL}"
    )

    regions = breakdown_map(summary, "by_region", "region")
    assert set(regions) == set(ALL_REGIONS), (
        f"by_region names are {sorted(regions)}; expected {sorted(ALL_REGIONS)}"
    )
    for name, expected in REGION_TOTALS.items():
        assert regions[name] == expected, (
            f"by_region total for {name!r} is {regions[name]}; expected {expected}"
        )

    lines = breakdown_map(summary, "by_product_line", "product_line")
    assert set(lines) == set(ALL_LINES), (
        f"by_product_line names are {sorted(lines)}; expected {sorted(ALL_LINES)}"
    )
    assert lines[LINE_AURORA] == AURORA_TOTAL, (
        f"by_product_line total for {LINE_AURORA!r} is {lines[LINE_AURORA]}; "
        f"expected {AURORA_TOTAL}"
    )
    assert lines[LINE_BASALT] == BASALT_TOTAL, (
        f"by_product_line total for {LINE_BASALT!r} is {lines[LINE_BASALT]}; "
        f"expected {BASALT_TOTAL}"
    )


# cov: C-CF-28, C-CF-29, C-OV-07
def test_summary_breakdowns_sum_to_total(analyst_client):
    """Both breakdowns add up to the grand total the same response reports."""
    report_id = report_id_by_title(analyst_client, JANUARY_TITLE)
    assert report_id is not None, f"{JANUARY_TITLE!r} is not in the report list"

    summary = summary_for(analyst_client, report_id)
    total = int(summary["total"])
    regions = breakdown_map(summary, "by_region", "region")
    lines = breakdown_map(summary, "by_product_line", "product_line")

    assert sum(regions.values()) == total, (
        f"by_region sums to {sum(regions.values())} while total reads {total}; "
        f"the two views of one period disagree"
    )
    assert sum(lines.values()) == total, (
        f"by_product_line sums to {sum(lines.values())} while total reads {total}; "
        f"the two views of one period disagree"
    )
    assert sum(LINE_TOTALS.values()) == total, (
        f"the pinned product line totals sum to {sum(LINE_TOTALS.values())} while "
        f"the app reports {total}"
    )


# cov: C-CF-33, C-CF-34, C-CF-35, C-CF-50, C-CF-24, C-CF-25, C-DC-30, C-DM-29, C-DM-30
def test_transactions_endpoint_rows_sum_to_total(analyst_client):
    """The rows behind the January summary are exactly the six settled in-period rows."""
    report_id = report_id_by_title(analyst_client, JANUARY_TITLE)
    assert report_id is not None, f"{JANUARY_TITLE!r} is not in the report list"

    rows = transactions_for(analyst_client, report_id)
    refs = [row.get("external_ref") for row in rows]
    assert sorted(refs) == sorted(ANALYST_JANUARY_REFS), (
        f"the analyst's row list is {sorted(refs)}; the seeded ledger puts "
        f"{sorted(ANALYST_JANUARY_REFS)} inside the January period"
    )

    for row in rows:
        ref = row.get("external_ref")
        seeded = SEEDED_TRANSACTIONS[ref]
        assert int(row.get("amount")) == seeded["amount"], (
            f"{ref} carries amount {row.get('amount')!r}; the ledger pins "
            f"{seeded['amount']}"
        )
        assert row.get("status") == "settled", (
            f"{ref} carries status {row.get('status')!r} in a report row list that "
            f"may only hold settled rows"
        )

    summary = summary_for(analyst_client, report_id)
    assert sum(int(row["amount"]) for row in rows) == int(summary["total"]), (
        f"the listed rows sum to {sum(int(row['amount']) for row in rows)} while the "
        f"summary reports {summary['total']}; the aggregate does not reconcile"
    )


# cov: C-CF-47, C-DC-29, C-DM-13, C-DM-32
def test_product_lines_returns_both_lines(analyst_client):
    """GET /api/product-lines returns both seeded product lines by name."""
    response = analyst_client.get("/product-lines")
    assert response.status_code == 200, (
        f"GET /api/product-lines returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    names = {row.get("name") for row in items(response.json())}
    assert names == set(ALL_LINES), (
        f"product lines are {sorted(names)}; expected {sorted(ALL_LINES)}"
    )


# cov: C-CF-44, C-CF-45, C-DC-28, C-DM-12, C-DM-31, C-RL-02, C-RL-03
def test_regions_list_scoped_for_analyst(analyst_client):
    """The analyst reads every region, and may name any one of them on a summary."""
    from conftest import REGION_SOUTH, SOUTH_TOTAL

    response = analyst_client.get("/regions")
    assert response.status_code == 200, (
        f"GET /api/regions returned {response.status_code}: {response.text[:400]}"
    )
    names = {row.get("name") for row in items(response.json())}
    assert names == set(ALL_REGIONS), (
        f"the analyst sees regions {sorted(names)}; expected {sorted(ALL_REGIONS)}"
    )

    report_id = report_id_by_title(analyst_client, JANUARY_TITLE)
    assert report_id is not None, f"{JANUARY_TITLE!r} is not in the report list"
    scoped = summary_for(analyst_client, report_id, region=REGION_SOUTH)
    scoped_regions = breakdown_map(scoped, "by_region", "region")
    assert list(scoped_regions) == [REGION_SOUTH], (
        f"the analyst naming {REGION_SOUTH!r} sees regions {sorted(scoped_regions)}; "
        f"an analyst may name any region and reads that one"
    )
    assert int(scoped["total"]) == SOUTH_TOTAL, (
        f"the analyst naming {REGION_SOUTH!r} reads total {scoped.get('total')!r}; "
        f"expected {SOUTH_TOTAL}"
    )
