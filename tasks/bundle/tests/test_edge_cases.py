"""Boundary, validation and empty-state paths.

Every rejection here names its pinned status; none of them is a permission
boundary, which test_authorization.py owns.
"""

from __future__ import annotations

from appclient import client
from conftest import (
    EMPTY_PERIOD_END, EMPTY_PERIOD_START, JANUARY_END, JANUARY_START,
    breakdown_map, create_report, summary_for, transactions_for,
    unique_report_title,
)


# cov: C-CF-08, C-CF-09, C-CF-10, C-DM-23, C-DC-31, C-DC-32, C-DC-33
def test_backwards_period_rejected(analyst_client, db):
    """A period whose end precedes its start is refused with 400 and creates no row."""
    before = db.count_reports()
    title = unique_report_title("Backwards")
    response = create_report(analyst_client, title, "2026-03-31", "2026-03-01")
    assert response.status_code == 400, (
        f"a backwards period returned {response.status_code}; the brief pins 400: "
        f"{response.text[:400]}"
    )
    assert response.status_code < 500, (
        f"a business-rule violation returned {response.status_code}; the brief "
        f"forbids a 5xx here"
    )
    assert response.text.strip(), (
        f"the rejection carries an empty body, so no reason is named"
    )
    after = db.count_reports()
    assert after == before, (
        f"the reports table went from {before} to {after} rows on a rejected period"
    )
    assert db.report_by_title(title) is None, (
        f"{title!r} exists in reports after a rejected create"
    )


# cov: C-CF-14, C-CF-15, C-TR-26, C-TR-27, C-TR-29, C-CN-20
def test_second_publish_conflicts(analyst_client, db):
    """Publishing an already published report conflicts and leaves the stamp alone."""
    title = unique_report_title("Twice")
    created = create_report(analyst_client, title, JANUARY_START, JANUARY_END)
    assert created.status_code in (200, 201), (
        f"POST /api/reports returned {created.status_code}: {created.text[:400]}"
    )
    report_id = created.json().get("id")
    assert report_id is not None, f"the created report has no id: {created.text[:400]}"

    first = analyst_client.post(f"/reports/{report_id}/publish")
    assert first.status_code == 200, (
        f"the first publish returned {first.status_code}: {first.text[:400]}"
    )
    stamped = db.report_by_id(report_id).get("published_at")
    assert stamped, f"report {report_id} carries no published_at after a 200 publish"

    second = analyst_client.post(f"/reports/{report_id}/publish")
    assert second.status_code == 409, (
        f"the second publish returned {second.status_code}; the brief pins 409: "
        f"{second.text[:400]}"
    )
    after = db.report_by_id(report_id)
    assert after.get("published_at") == stamped, (
        f"published_at moved from {stamped!r} to {after.get('published_at')!r} on a "
        f"refused second publish"
    )
    assert after.get("status") == "published", (
        f"report {report_id} reads {after.get('status')!r} after a refused second "
        f"publish"
    )


# cov: C-CF-36, C-CF-37
def test_empty_period_returns_zero_totals(analyst_client):
    """A period holding no settled row totals zero with empty breakdowns."""
    from conftest import create_published_report

    title = unique_report_title("Empty")
    report_id = create_published_report(
        analyst_client, title, EMPTY_PERIOD_START, EMPTY_PERIOD_END
    )

    summary = summary_for(analyst_client, report_id)
    assert int(summary["total"]) == 0, (
        f"a period with no settled rows totals {summary.get('total')!r}; expected 0"
    )
    assert breakdown_map(summary, "by_region", "region") == {}, (
        f"by_region is not empty for a period with no settled rows: "
        f"{summary.get('by_region')!r}"
    )
    assert breakdown_map(summary, "by_product_line", "product_line") == {}, (
        f"by_product_line is not empty for a period with no settled rows: "
        f"{summary.get('by_product_line')!r}"
    )
    assert transactions_for(analyst_client, report_id) == [], (
        f"the row list is not empty for a period with no settled rows"
    )


# cov: C-CF-03, C-TR-09
def test_invalid_token_rejected():
    """A syntactically valid but unissued bearer token is refused with 401."""
    with client("not-a-real-token-issued-by-this-app") as c:
        response = c.get("/reports")
    assert response.status_code == 401, (
        f"a malformed bearer token returned {response.status_code}; the brief pins "
        f"401: {response.text[:400]}"
    )


# cov: C-UF-19, C-DC-26
def test_unknown_report_returns_not_found(analyst_client, db):
    """A report id that belongs to no row is 404, not a 500 and not an empty summary."""
    highest = db.count_reports()
    missing_id = highest + 100000
    response = analyst_client.get(f"/reports/{missing_id}")
    assert response.status_code == 404, (
        f"GET /api/reports/{missing_id} returned {response.status_code}; the brief "
        f"pins a not-found card for a missing report: {response.text[:400]}"
    )
    summary = analyst_client.get(f"/reports/{missing_id}/summary")
    assert summary.status_code == 404, (
        f"the summary for a missing report returned {summary.status_code}; expected "
        f"404 rather than an invented zero: {summary.text[:400]}"
    )
