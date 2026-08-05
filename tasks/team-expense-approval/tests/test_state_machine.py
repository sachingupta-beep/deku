"""State-transition substeps.

Black box: every assertion goes through the deployed HTTP surface or the `db`
capability fixture. Nothing here imports the agent's code or assumes its
framework.

Every transition check asserts BOTH the response status AND the resulting
database state, so a spurious 200 that left the row unchanged is caught.
"""

from __future__ import annotations

from conftest import submit_claim_payload


# ------------------------------------------------------------------- submission


def test_submit_claim_persisted(ellen_client, ellen_employee_id, db, unique_description):
    """A submitted claim leaves a real row in state 'submitted'."""
    before = db.count_claims(employee_id=ellen_employee_id, state="submitted")

    response = ellen_client.post("/claims", json=submit_claim_payload(unique_description, 1250))
    assert response.status_code in (200, 201), (
        f"POST /api/claims returned {response.status_code}: {response.text[:400]}"
    )
    body = response.json()
    assert body.get("state") == "submitted", (
        f"created claim came back in state {body.get('state')!r}, expected 'submitted': "
        f"{str(body)[:400]}"
    )

    after = db.count_claims(employee_id=ellen_employee_id, state="submitted")
    assert after == before + 1, (
        f"expected one new submitted claim for Ellen, went {before} -> {after}"
    )

    row = db.claim_by_id(body["id"])
    assert row is not None, f"claim id {body['id']} is not in the database"
    assert int(row["amount_cents"]) == 1250, (
        f"persisted amount is {row['amount_cents']}, expected 1250"
    )


def test_zero_amount_rejected(ellen_client, unique_description):
    """Amount zero is a validation error."""
    payload = submit_claim_payload(unique_description, amount_cents=0)
    response = ellen_client.post("/claims", json=payload)
    assert 400 <= response.status_code < 500, (
        f"zero amount returned {response.status_code}, expected 4xx: "
        f"{response.text[:400]}"
    )


def test_negative_amount_rejected(ellen_client, unique_description):
    """Negative amount is a validation error."""
    payload = submit_claim_payload(unique_description, amount_cents=-1)
    response = ellen_client.post("/claims", json=payload)
    assert 400 <= response.status_code < 500, (
        f"negative amount returned {response.status_code}, expected 4xx: "
        f"{response.text[:400]}"
    )


# ------------------------------------------------------- happy-path transitions


def test_manager_approves_report_claim_persisted(
    mia_client, ellen_client, ellen_employee_id, db, unique_description
):
    """Mia approves a fresh claim from Ellen; state and stamps land in the DB."""
    created = ellen_client.post(
        "/claims", json=submit_claim_payload(unique_description, 2100)
    )
    assert created.status_code in (200, 201), (
        f"submit returned {created.status_code}: {created.text[:400]}"
    )
    claim_id = created.json()["id"]

    approved = mia_client.post(f"/claims/{claim_id}/approve")
    assert approved.status_code == 200, (
        f"manager approve returned {approved.status_code}: {approved.text[:400]}"
    )

    row = db.claim_by_id(claim_id)
    assert row["state"] == "approved", f"claim state is {row['state']!r}, expected 'approved'"
    assert row.get("approved_by"), "approved_by was not stamped"
    assert row.get("approved_at"), "approved_at was not stamped"

    events = db.events_for_claim(claim_id)
    assert events, "no claim_events row written for the approval"


def test_manager_rejects_with_reason_persisted(
    mia_client, ellen_client, db, unique_description
):
    """Rejection stamps the reason and rejector; the row lands in 'rejected'."""
    created = ellen_client.post(
        "/claims", json=submit_claim_payload(unique_description, 4200)
    )
    claim_id = created.json()["id"]

    reason = "Above per-diem limit"
    rejected = mia_client.post(f"/claims/{claim_id}/reject", json={"reason": reason})
    assert rejected.status_code == 200, (
        f"manager reject returned {rejected.status_code}: {rejected.text[:400]}"
    )

    row = db.claim_by_id(claim_id)
    assert row["state"] == "rejected", f"claim state is {row['state']!r}, expected 'rejected'"
    assert row.get("rejected_by"), "rejected_by was not stamped"
    assert row.get("rejected_at"), "rejected_at was not stamped"
    assert row.get("rejection_reason") == reason, (
        f"rejection_reason is {row.get('rejection_reason')!r}, expected {reason!r}"
    )


def test_finance_reimburses_approved_persisted(
    finance_client, mia_client, ellen_client, db, unique_description
):
    """Finance moves an approved claim to reimbursed and stamps the row."""
    created = ellen_client.post(
        "/claims", json=submit_claim_payload(unique_description, 3300)
    )
    claim_id = created.json()["id"]

    approved = mia_client.post(f"/claims/{claim_id}/approve")
    assert approved.status_code == 200, (
        f"pre-reimburse approve returned {approved.status_code}: {approved.text[:400]}"
    )

    reimbursed = finance_client.post(f"/claims/{claim_id}/reimburse")
    assert reimbursed.status_code == 200, (
        f"finance reimburse returned {reimbursed.status_code}: {reimbursed.text[:400]}"
    )

    row = db.claim_by_id(claim_id)
    assert row["state"] == "reimbursed", (
        f"claim state is {row['state']!r}, expected 'reimbursed'"
    )
    assert row.get("reimbursed_by"), "reimbursed_by was not stamped"
    assert row.get("reimbursed_at"), "reimbursed_at was not stamped"


# --------------------------------------------------- illegal transitions (409)


def test_double_approve_conflict(mia_client, ellen_client, db, unique_description):
    """A claim already approved cannot be approved again -- 409, no mutation."""
    created = ellen_client.post(
        "/claims", json=submit_claim_payload(unique_description, 1900)
    )
    claim_id = created.json()["id"]
    first = mia_client.post(f"/claims/{claim_id}/approve")
    assert first.status_code == 200, f"first approve failed: {first.text[:400]}"

    before = db.claim_by_id(claim_id)
    second = mia_client.post(f"/claims/{claim_id}/approve")
    assert second.status_code == 409, (
        f"second approve returned {second.status_code}, expected 409: "
        f"{second.text[:400]}"
    )
    after = db.claim_by_id(claim_id)
    assert after["state"] == before["state"] == "approved", (
        f"double approve disturbed the row: {before['state']!r} -> {after['state']!r}"
    )
    assert after["approved_at"] == before["approved_at"], (
        "double approve re-stamped approved_at"
    )


def test_rejected_cannot_be_reimbursed(
    finance_client, mia_client, ellen_client, db, unique_description
):
    """A rejected claim can never become reimbursed."""
    created = ellen_client.post(
        "/claims", json=submit_claim_payload(unique_description, 6000)
    )
    claim_id = created.json()["id"]
    rejected = mia_client.post(
        f"/claims/{claim_id}/reject", json={"reason": "not eligible"}
    )
    assert rejected.status_code == 200, f"reject setup failed: {rejected.text[:400]}"

    response = finance_client.post(f"/claims/{claim_id}/reimburse")
    assert response.status_code == 409, (
        f"reimbursing a rejected claim returned {response.status_code}, expected 409: "
        f"{response.text[:400]}"
    )
    row = db.claim_by_id(claim_id)
    assert row["state"] == "rejected", (
        f"rejected claim was mutated to {row['state']!r}"
    )


def test_submitted_cannot_be_reimbursed(
    finance_client, ellen_client, db, unique_description
):
    """Finance cannot skip the manager -- only approved claims are reimbursable."""
    created = ellen_client.post(
        "/claims", json=submit_claim_payload(unique_description, 2500)
    )
    claim_id = created.json()["id"]

    response = finance_client.post(f"/claims/{claim_id}/reimburse")
    assert response.status_code == 409, (
        f"reimbursing a submitted claim returned {response.status_code}, expected 409: "
        f"{response.text[:400]}"
    )
    row = db.claim_by_id(claim_id)
    assert row["state"] == "submitted", (
        f"submitted claim was mutated to {row['state']!r}"
    )
