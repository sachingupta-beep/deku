"""Denial at the API: role boundaries and region scope, asserted over HTTP.

Every denial here is asserted against a direct API call, never against a hidden
button, and every mutating denial re-reads the target to prove nothing changed.
"""

from __future__ import annotations

from _shapes import items
from conftest import (
    ALL_REGIONS, JANUARY_TITLE, FEBRUARY_TITLE, JANUARY_END, JANUARY_START,
    LINE_AURORA, LINE_BASALT, NORTH_TOTAL, NORTH_JANUARY_REFS, REGION_NORTH,
    REGION_SOUTH, SOUTH_TOTAL, SOUTH_JANUARY_REFS, breakdown_map,
    report_id_by_title, summary_for, transactions_for, unique_report_title,
)


# cov: C-CF-38, C-CF-39, C-CF-40, C-CF-41, C-RL-07, C-OV-06, C-CN-01
def test_manager_summary_scoped_to_own_region(manager_north_client,
                                              manager_south_client):
    """Each manager's summary carries one region entry, their own, with its total."""
    north_id = report_id_by_title(manager_north_client, JANUARY_TITLE)
    assert north_id is not None, f"{JANUARY_TITLE!r} is not visible to the North manager"
    north = summary_for(manager_north_client, north_id)
    assert int(north["total"]) == NORTH_TOTAL, (
        f"the North manager reads total {north.get('total')!r}; the ledger produces "
        f"{NORTH_TOTAL} for {REGION_NORTH!r}"
    )
    north_regions = breakdown_map(north, "by_region", "region")
    assert list(north_regions) == [REGION_NORTH], (
        f"the North manager sees regions {sorted(north_regions)}; a manager reads "
        f"exactly one region entry"
    )
    north_lines = breakdown_map(north, "by_product_line", "product_line")
    assert north_lines.get(LINE_AURORA) == 165000, (
        f"the North manager reads {north_lines.get(LINE_AURORA)!r} for {LINE_AURORA!r}; "
        f"the North rows produce 165000"
    )
    assert north_lines.get(LINE_BASALT) == 30000, (
        f"the North manager reads {north_lines.get(LINE_BASALT)!r} for {LINE_BASALT!r}; "
        f"the North rows produce 30000"
    )

    south_id = report_id_by_title(manager_south_client, JANUARY_TITLE)
    assert south_id is not None, f"{JANUARY_TITLE!r} is not visible to the South manager"
    south = summary_for(manager_south_client, south_id)
    assert int(south["total"]) == SOUTH_TOTAL, (
        f"the South manager reads total {south.get('total')!r}; the ledger produces "
        f"{SOUTH_TOTAL} for {REGION_SOUTH!r}"
    )
    south_regions = breakdown_map(south, "by_region", "region")
    assert list(south_regions) == [REGION_SOUTH], (
        f"the South manager sees regions {sorted(south_regions)}"
    )


# cov: C-CF-20, C-CF-21, C-RL-10, C-RL-11, C-RL-13
def test_manager_cannot_create_report(manager_north_client, analyst_client, db):
    """A manager posting to the create endpoint is denied and no row appears."""
    before = db.count_reports()
    title = unique_report_title("Forbidden")
    response = manager_north_client.post(
        "/reports",
        json={"title": title, "period_start": JANUARY_START, "period_end": JANUARY_END},
    )
    assert response.status_code in (401, 403), (
        f"a manager POSTing /api/reports got {response.status_code}; the brief pins "
        f"401 or 403: {response.text[:400]}"
    )
    after = db.count_reports()
    assert after == before, (
        f"the reports table went from {before} to {after} rows on a denied create; "
        f"a denial must leave the underlying row set unchanged"
    )
    titles = {row.get("title") for row in items(analyst_client.get("/reports").json())}
    assert title not in titles, (
        f"{title!r} appears in the analyst's report list after a denied create"
    )


# cov: C-CF-20, C-RL-11
def test_manager_cannot_publish_report(manager_north_client, analyst_client, db):
    """A manager publishing an analyst's draft is denied and the draft stays a draft."""
    title = unique_report_title("Unpublished")
    created = analyst_client.post(
        "/reports",
        json={"title": title, "period_start": JANUARY_START, "period_end": JANUARY_END},
    )
    assert created.status_code in (200, 201), (
        f"POST /api/reports returned {created.status_code}: {created.text[:400]}"
    )
    report_id = created.json().get("id")
    assert report_id is not None, f"the created report has no id: {created.text[:400]}"

    response = manager_north_client.post(f"/reports/{report_id}/publish")
    assert response.status_code in (401, 403), (
        f"a manager publishing report {report_id} got {response.status_code}; the "
        f"brief pins 401 or 403: {response.text[:400]}"
    )
    row = db.report_by_id(report_id)
    assert row is not None, f"report {report_id} vanished from reports"
    assert row.get("status") == "draft", (
        f"report {report_id} reads {row.get('status')!r} after a denied publish"
    )
    assert not row.get("published_at"), (
        f"report {report_id} carries published_at {row.get('published_at')!r} after a "
        f"denied publish"
    )


# cov: C-CF-42, C-CF-43, C-RL-09, C-RL-12, C-DC-31, C-TR-22
def test_manager_cross_region_query_forbidden(manager_north_client):
    """Naming another region on the summary endpoint is refused, with no figure leaked."""
    report_id = report_id_by_title(manager_north_client, JANUARY_TITLE)
    assert report_id is not None, f"{JANUARY_TITLE!r} is not visible to the North manager"

    response = manager_north_client.get(
        f"/reports/{report_id}/summary", params={"region": REGION_SOUTH}
    )
    assert response.status_code == 403, (
        f"the North manager asking for {REGION_SOUTH!r} got {response.status_code}; "
        f"the brief pins 403: {response.text[:400]}"
    )
    body = response.text
    assert str(SOUTH_TOTAL) not in body, (
        f"the refusal body leaks the {REGION_SOUTH!r} total {SOUTH_TOTAL}: {body[:400]}"
    )
    assert REGION_SOUTH not in body or "403" in body or "forbid" in body.lower(), (
        f"the refusal body reads like a figure rather than a refusal: {body[:400]}"
    )


# cov: C-RL-09, C-CF-38
def test_manager_transactions_scoped_to_own_region(manager_north_client,
                                                   manager_south_client):
    """Each manager's row list holds only their own region's rows."""
    north_id = report_id_by_title(manager_north_client, JANUARY_TITLE)
    assert north_id is not None, f"{JANUARY_TITLE!r} is not visible to the North manager"
    north_refs = {row.get("external_ref")
                  for row in transactions_for(manager_north_client, north_id)}
    assert north_refs == set(NORTH_JANUARY_REFS), (
        f"the North manager sees rows {sorted(north_refs)}; the ledger puts "
        f"{sorted(NORTH_JANUARY_REFS)} in {REGION_NORTH!r} inside the period"
    )

    south_id = report_id_by_title(manager_south_client, JANUARY_TITLE)
    assert south_id is not None, f"{JANUARY_TITLE!r} is not visible to the South manager"
    south_refs = {row.get("external_ref")
                  for row in transactions_for(manager_south_client, south_id)}
    assert south_refs == set(SOUTH_JANUARY_REFS), (
        f"the South manager sees rows {sorted(south_refs)}; the ledger puts "
        f"{sorted(SOUTH_JANUARY_REFS)} in {REGION_SOUTH!r} inside the period"
    )
    assert not (north_refs & south_refs), (
        f"the two managers share rows {sorted(north_refs & south_refs)}; region scope "
        f"must make the two row sets disjoint"
    )


# cov: C-CF-18, C-CF-19, C-RL-06, C-RL-08
def test_manager_cannot_read_draft_report(manager_south_client, analyst_client):
    """A draft report is 404 for a manager and readable for the analyst."""
    listed = {row.get("title")
              for row in items(manager_south_client.get("/reports").json())}
    assert FEBRUARY_TITLE not in listed, (
        f"{FEBRUARY_TITLE!r} is a draft and appears in a manager's report list: "
        f"{sorted(listed)}"
    )

    analyst_id = report_id_by_title(analyst_client, FEBRUARY_TITLE)
    assert analyst_id is not None, (
        f"{FEBRUARY_TITLE!r} is not visible to the analyst, so the draft is missing"
    )
    response = manager_south_client.get(f"/reports/{analyst_id}")
    assert response.status_code == 404, (
        f"a manager requesting the draft by id got {response.status_code}; the brief "
        f"pins 404 so the draft's existence is not confirmed: {response.text[:400]}"
    )


# cov: C-CF-02, C-CF-03, C-DC-06
def test_unauthenticated_request_rejected(anon_client):
    """Every endpoint but health refuses a request carrying no bearer token."""
    health = anon_client.get("/health")
    assert health.status_code == 200, (
        f"GET /api/health returned {health.status_code} without a token; health is "
        f"the one route that needs none"
    )
    for path in ("/me", "/regions", "/product-lines", "/reports"):
        response = anon_client.get(path)
        assert response.status_code == 401, (
            f"GET /api{path} without a token returned {response.status_code}; the "
            f"brief pins 401: {response.text[:400]}"
        )


# cov: C-CF-46, C-CN-02
def test_manager_regions_list_scoped(manager_north_client, manager_south_client):
    """The region list itself is scoped, so the shape of the ledger does not leak."""
    north = {row.get("name")
             for row in items(manager_north_client.get("/regions").json())}
    assert north == {REGION_NORTH}, (
        f"the North manager sees regions {sorted(north)}; a manager reads only their "
        f"own region"
    )
    south = {row.get("name")
             for row in items(manager_south_client.get("/regions").json())}
    assert south == {REGION_SOUTH}, (
        f"the South manager sees regions {sorted(south)}"
    )
    assert north != set(ALL_REGIONS), (
        f"the North manager sees every region, so the region list is unscoped"
    )
