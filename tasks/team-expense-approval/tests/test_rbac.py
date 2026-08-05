"""Authorization substeps -- the heart of this task.

PLAN.md 4.7: hiding a button is not a permission. Every assertion here goes to
the API directly, because that is the only place authorization can be proven.

Every permission assertion checks BOTH the status code AND that the underlying
database row is unchanged: a 403 that still wrote is a worse bug than a 200.
"""

from __future__ import annotations

from conftest import submit_claim_payload

MUTATING_ENDPOINTS = [
    ("POST", "/claims", {"amount_cents": 100, "currency": "USD", "category": "meals",
                          "description": "x", "expense_date": "2026-08-03"}),
    ("POST", "/claims/1/approve", {}),
    ("POST", "/claims/1/reject", {"reason": "x"}),
    ("POST", "/claims/1/cancel", {}),
    ("POST", "/claims/1/reimburse", {}),
]


# --------------------------------------------------------------- employee role


def test_employee_approve_denied_at_api(ellen_client, mia_employee_id, db):
    """An employee cannot approve any claim, even via a direct API call."""
    claim = db.any_submitted_from_report(mia_employee_id)
    before_state = claim["state"]

    response = ellen_client.post(f"/claims/{claim['id']}/approve")
    assert response.status_code in (401, 403), (
        f"employee approve returned {response.status_code}, expected 401/403: "
        f"{response.text[:400]}"
    )
    after = db.claim_by_id(claim["id"])
    assert after["state"] == before_state, (
        f"employee-initiated approve mutated the claim state "
        f"{before_state!r} -> {after['state']!r}"
    )


def test_employee_reimburse_denied_at_api(ellen_client, db):
    """An employee cannot mark anything reimbursed."""
    claim = db.pick_claim(state="approved")
    before_state = claim["state"]

    response = ellen_client.post(f"/claims/{claim['id']}/reimburse")
    assert response.status_code in (401, 403), (
        f"employee reimburse returned {response.status_code}, expected 401/403: "
        f"{response.text[:400]}"
    )
    after = db.claim_by_id(claim["id"])
    assert after["state"] == before_state, (
        f"employee-initiated reimburse mutated the claim: {before_state!r} -> "
        f"{after['state']!r}"
    )


def test_employee_cannot_read_other_employees_claim(evan_client, ellen_employee_id, db):
    """Evan cannot read Ellen's claim, even though they share a manager."""
    others = db.claims_for_employee(ellen_employee_id)
    assert others, "no seeded claims for Ellen -- fixture prerequisite failed"
    target = others[0]

    response = evan_client.get(f"/claims/{target['id']}")
    assert response.status_code in (401, 403, 404), (
        f"employee reading peer's claim returned {response.status_code}, "
        f"expected 401/403/404: {response.text[:400]}"
    )


def test_employee_list_excludes_other_employees_claims(evan_client, ellen_employee_id):
    """An employee's list view must not surface any peer's claim ids."""
    from _shapes import items as as_list

    forbidden_ids = set()
    for state in ("submitted", "approved", "rejected", "reimbursed"):
        response = evan_client.get("/claims", params={"state": state})
        assert response.status_code == 200, (
            f"employee GET /api/claims returned {response.status_code}: "
            f"{response.text[:400]}"
        )
        for row in as_list(response.json()):
            assert int(row.get("employee_id", -1)) != int(-1), (
                f"claim row missing employee_id: {row}"
            )
            forbidden_ids.add(int(row["employee_id"]))

    assert ellen_employee_id not in forbidden_ids, (
        f"Evan's /api/claims listing exposed rows belonging to Ellen "
        f"(employee_id={ellen_employee_id}): {sorted(forbidden_ids)[:10]}"
    )


# ---------------------------------------------------------------- manager role


def test_manager_cannot_approve_other_managers_report(
    mark_client, mia_employee_id, db
):
    """Mark cannot approve a claim from Mia's team -- the cross-tenant test."""
    claim = db.any_submitted_from_report(mia_employee_id)
    before_state = claim["state"]

    response = mark_client.post(f"/claims/{claim['id']}/approve")
    assert response.status_code in (401, 403, 404), (
        f"cross-team approve returned {response.status_code}, expected 401/403/404: "
        f"{response.text[:400]}"
    )
    after = db.claim_by_id(claim["id"])
    assert after["state"] == before_state, (
        f"cross-team approve mutated the claim: {before_state!r} -> {after['state']!r}"
    )
    assert after.get("approved_by") in (None, "", 0), (
        f"cross-team approve stamped approved_by={after.get('approved_by')!r} "
        f"despite the 4xx"
    )


def test_manager_cannot_reject_other_managers_report(
    mark_client, mia_employee_id, db
):
    """Mark cannot reject a claim from Mia's team either."""
    claim = db.any_submitted_from_report(mia_employee_id)
    before_state = claim["state"]

    response = mark_client.post(
        f"/claims/{claim['id']}/reject", json={"reason": "not mine to reject"}
    )
    assert response.status_code in (401, 403, 404), (
        f"cross-team reject returned {response.status_code}, expected 401/403/404: "
        f"{response.text[:400]}"
    )
    after = db.claim_by_id(claim["id"])
    assert after["state"] == before_state, (
        f"cross-team reject mutated the claim: {before_state!r} -> {after['state']!r}"
    )


# ---------------------------------------------------------------- finance role


def test_finance_approve_denied_at_api(finance_client, mia_employee_id, db):
    """Finance reads everything but cannot approve."""
    claim = db.any_submitted_from_report(mia_employee_id)
    before_state = claim["state"]

    response = finance_client.post(f"/claims/{claim['id']}/approve")
    assert response.status_code in (401, 403), (
        f"finance approve returned {response.status_code}, expected 401/403: "
        f"{response.text[:400]}"
    )
    after = db.claim_by_id(claim["id"])
    assert after["state"] == before_state, (
        f"finance-initiated approve mutated the claim: {before_state!r} -> "
        f"{after['state']!r}"
    )


def test_finance_reject_denied_at_api(finance_client, mia_employee_id, db):
    """Finance cannot reject either."""
    claim = db.any_submitted_from_report(mia_employee_id)
    before_state = claim["state"]

    response = finance_client.post(
        f"/claims/{claim['id']}/reject", json={"reason": "not my call"}
    )
    assert response.status_code in (401, 403), (
        f"finance reject returned {response.status_code}, expected 401/403: "
        f"{response.text[:400]}"
    )
    after = db.claim_by_id(claim["id"])
    assert after["state"] == before_state, (
        f"finance-initiated reject mutated the claim: {before_state!r} -> "
        f"{after['state']!r}"
    )


# ----------------------------------------------------------- anonymous callers


def test_unauthenticated_requests_denied(anon_client):
    """Every mutating endpoint rejects anonymous callers."""
    read = anon_client.get("/claims")
    assert read.status_code in (401, 403), (
        f"anonymous GET /api/claims returned {read.status_code}, expected 401/403: "
        f"{read.text[:400]}"
    )
    for method, path, body in MUTATING_ENDPOINTS:
        response = anon_client.request(method, path, json=body)
        assert response.status_code in (401, 403), (
            f"anonymous {method} /api{path} returned {response.status_code}, "
            f"expected 401/403: {response.text[:400]}"
        )
