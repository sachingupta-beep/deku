"""Substeps asserting that what each role's dashboard shows is what the DB holds.

Every role sees a different slice; each slice must be computed from real state,
not invented and not stale.
"""

from __future__ import annotations

from _shapes import flatten, items


def test_manager_dashboard_matches_database(mia_client, mia_employee_id, db):
    """Mia's dashboard pending-approvals count matches submitted claims from her reports."""
    reports = db.reports_of(mia_employee_id)
    assert reports, "Mia has no direct reports in the seed data"

    expected_pending = sum(
        db.count_claims(employee_id=report["id"], state="submitted") for report in reports
    )
    assert expected_pending > 0, (
        "seed data must include at least one submitted claim from Mia's reports"
    )

    response = mia_client.get("/dashboard")
    assert response.status_code == 200, (
        f"GET /api/dashboard as manager returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    body = flatten(response.json())
    assert str(expected_pending) in body, (
        f"manager dashboard does not surface the true pending count "
        f"{expected_pending}: {body[:600]}"
    )


def test_finance_dashboard_matches_database(finance_client, db):
    """Finance's dashboard 'approved awaiting reimbursement' count is truthful."""
    expected_awaiting = db.count_claims(state="approved")

    response = finance_client.get("/dashboard")
    assert response.status_code == 200, (
        f"GET /api/dashboard as finance returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    body = flatten(response.json())
    assert str(expected_awaiting) in body, (
        f"finance dashboard does not surface the true approved-awaiting count "
        f"{expected_awaiting}: {body[:600]}"
    )


def test_manager_queue_scope_matches_database(mark_client, mark_employee_id, db):
    """Mark's queue lists ONLY submitted claims from Mark's direct reports."""
    response = mark_client.get("/claims", params={"state": "submitted"})
    assert response.status_code == 200, (
        f"manager GET /api/claims returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    rows = items(response.json())

    reports = {report["id"] for report in db.reports_of(mark_employee_id)}
    for row in rows:
        assert int(row["employee_id"]) in reports, (
            f"Mark's queue surfaced claim from employee_id={row['employee_id']}, "
            f"who is not one of his reports (reports: {sorted(reports)})"
        )

    for row in rows:
        assert str(row.get("state", "")).lower() == "submitted", (
            f"queue row not in state 'submitted': {row}"
        )
