"""Substeps asserting that what the UI shows is what the database holds."""

from __future__ import annotations

from _shapes import flatten, items
from conftest import new_employee_payload

AMIT_EMAIL = "amit@ethara.ai"
AMIT_SEAT = "B4-23"
AMIT_FLOOR = 2
AMIT_ZONE = "B"
AMIT_PROJECT = "talos"


def test_amit_seat_matches_database(admin_client, db):
    """The canonical seeded record is consistent across the API and the database."""
    seat = db.seat_by_number(AMIT_SEAT)
    assert seat is not None, f"seeded seat {AMIT_SEAT} is missing"
    assert (seat["floor"], seat["zone"]) == (AMIT_FLOOR, AMIT_ZONE), (
        f"seat {AMIT_SEAT} is on floor {seat["floor"]} zone {seat["zone"]}, "
        f"expected floor {AMIT_FLOOR} zone {AMIT_ZONE}"
    )

    employee = db.employee_by_email(AMIT_EMAIL)
    assert employee is not None, f"seeded employee {AMIT_EMAIL} is missing"

    allocation = db.active_allocation_for_employee(employee["id"])
    assert allocation is not None, f"{AMIT_EMAIL} has no active allocation"
    assert allocation["seat_id"] == seat["id"], (
        f"{AMIT_EMAIL} is allocated to a seat other than {AMIT_SEAT}"
    )

    detail = admin_client.get(f"/employees/{employee["id"]}")
    assert detail.status_code == 200, (
        f"GET /api/employees/{employee["id"]} returned {detail.status_code}: "
        f"{detail.text[:400]}"
    )
    body = flatten(detail.json())
    assert AMIT_SEAT.lower() in body, f"employee detail does not surface seat {AMIT_SEAT}"
    assert AMIT_PROJECT in body, f"employee detail does not surface project {AMIT_PROJECT}"


def test_dashboard_counts_match_database(admin_client, db):
    """Dashboard numbers are computed from real state, not invented or stale."""
    response = admin_client.get("/dashboard")
    assert response.status_code == 200, (
        f"GET /api/dashboard returned {response.status_code}: {response.text[:400]}"
    )
    payload = flatten(response.json())

    expected = {
        "total employees": db.count_employees(),
        "total seats": db.count_seats(),
        "occupied seats": db.count_seats("occupied"),
        "available seats": db.count_seats("available"),
        "reserved seats": db.count_seats("reserved"),
    }

    missing = [label for label, value in expected.items() if str(value) not in payload]
    assert not missing, (
        f"dashboard response is missing true counts for {missing}; "
        f"expected {expected}, got {payload[:600]}"
    )


def test_available_seats_filter_matches_database(admin_client, db):
    """Filtering available seats on a floor returns exactly the free desks on it."""
    floor = 3
    expected = {seat["seat_number"] for seat in db.available_seats_on_floor(floor)}
    assert expected, f"no available seats seeded on floor {floor}"

    response = admin_client.get(
        "/seats/available", params={"floor": floor, "status": "available"}
    )
    assert response.status_code == 200, (
        f"GET /api/seats/available returned {response.status_code}: {response.text[:400]}"
    )

    rows = items(response.json())
    assert rows, f"no available seats returned for floor {floor}"

    for row in rows:
        assert int(row["floor"]) == floor, f"row on wrong floor: {row}"
        assert str(row["status"]).lower() == "available", f"row not available: {row}"

    returned = {str(row["seat_number"]) for row in rows}
    assert returned <= expected, (
        f"API reported seats that are not available on floor {floor}: "
        f"{sorted(returned - expected)[:10]}"
    )


def test_duplicate_employee_email_rejected(admin_client, db, any_project_id):
    """A second employee with an existing email is rejected, and no row is written."""
    existing = db.employee_by_email(AMIT_EMAIL)
    assert existing is not None, f"seeded employee {AMIT_EMAIL} is missing"

    before = db.count_employees_with_email(AMIT_EMAIL)
    response = admin_client.post(
        "/employees", json=new_employee_payload(AMIT_EMAIL, any_project_id)
    )
    assert 400 <= response.status_code < 500, (
        f"duplicate email returned {response.status_code}, expected 4xx: "
        f"{response.text[:400]}"
    )
    assert db.count_employees_with_email(AMIT_EMAIL) == before, (
        "a duplicate employee row was written despite the rejection"
    )
