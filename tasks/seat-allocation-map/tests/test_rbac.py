"""Authorization substeps.

PLAN.md 4.7: hiding a button is not a permission. Every assertion here goes to the
API directly, because that is the only place authorization can actually be proven.
"""

from __future__ import annotations

from conftest import new_employee_payload

MUTATING_ENDPOINTS = [
    ("POST", "/employees"),
    ("POST", "/seats/allocate"),
    ("POST", "/seats/release"),
    ("POST", "/import"),
]


def test_employee_allocate_denied_at_api(employee_client, db):
    """An employee session cannot allocate or release, even calling the API directly."""
    seat = db.pick_seat(status="available")
    target = db.employee_without_seat()

    allocate = employee_client.post(
        "/seats/allocate", json={"employee_id": target["id"], "seat_id": seat["id"]}
    )
    assert allocate.status_code in (401, 403), (
        f"employee allocate returned {allocate.status_code}, expected 401/403: "
        f"{allocate.text[:400]}"
    )
    assert db.count_active_allocations_for_seat(seat["id"]) == 0, (
        "an employee-initiated allocation reached the database"
    )
    assert db.seat_by_id(seat["id"])["status"] == "available", (
        "an employee-initiated allocation changed seat status"
    )

    seated = db.employee_with_seat()
    release = employee_client.post("/seats/release", json={"employee_id": seated["id"]})
    assert release.status_code in (401, 403), (
        f"employee release returned {release.status_code}, expected 401/403: "
        f"{release.text[:400]}"
    )
    assert db.active_allocation_for_employee(seated["id"]) is not None, (
        "an employee-initiated release freed a seat"
    )


def test_employee_create_denied_at_api(employee_client, db, unique_email, any_project_id):
    """An employee session cannot create employees."""
    response = employee_client.post(
        "/employees", json=new_employee_payload(unique_email, any_project_id)
    )
    assert response.status_code in (401, 403), (
        f"employee create returned {response.status_code}, expected 401/403: "
        f"{response.text[:400]}"
    )
    assert db.employee_by_email(unique_email) is None, (
        "an employee-initiated create reached the database"
    )


def test_unauthenticated_requests_denied(anon_client):
    """Anonymous callers are rejected on reads and mutations alike."""
    read = anon_client.get("/employees")
    assert read.status_code in (401, 403), (
        f"anonymous GET /api/employees returned {read.status_code}, expected 401/403: "
        f"{read.text[:400]}"
    )

    for method, path in MUTATING_ENDPOINTS:
        response = anon_client.request(method, path, json={})
        assert response.status_code in (401, 403), (
            f"anonymous {method} /api{path} returned {response.status_code}, "
            f"expected 401/403: {response.text[:400]}"
        )
