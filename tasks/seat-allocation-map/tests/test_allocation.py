"""Allocation-engine substeps.

Black box: every assertion goes through the deployed HTTP surface or the `db`
capability fixture. Nothing here imports the agent's code or assumes its framework.
"""

from __future__ import annotations

import concurrent.futures

from appclient import client
from conftest import new_employee_payload


def test_new_joiner_allocation_persisted(admin_client, db, unique_email, any_project_id):
    """A created joiner allocated to a suggested seat leaves real, consistent state."""
    created = admin_client.post(
        "/employees", json=new_employee_payload(unique_email, any_project_id)
    )
    assert created.status_code in (200, 201), (
        f"POST /api/employees returned {created.status_code}: {created.text[:400]}"
    )

    employee = db.employee_by_email(unique_email)
    assert employee is not None, "created employee is not in the database"
    assert db.active_allocation_for_employee(employee["id"]) is None, (
        "a newly created employee must not already hold a seat"
    )

    suggested = admin_client.get("/seats/suggest", params={"employee_id": employee["id"]})
    assert suggested.status_code == 200, (
        f"GET /api/seats/suggest returned {suggested.status_code}: {suggested.text[:400]}"
    )

    seat = db.pick_seat(status="available")
    allocated = admin_client.post(
        "/seats/allocate", json={"employee_id": employee["id"], "seat_id": seat["id"]}
    )
    assert allocated.status_code in (200, 201), (
        f"POST /api/seats/allocate returned {allocated.status_code}: {allocated.text[:400]}"
    )

    allocation = db.active_allocation_for_employee(employee["id"])
    assert allocation is not None, "no active allocation row was written"
    assert allocation["seat_id"] == seat["id"], "allocation points at a different seat"

    assert db.seat_by_id(seat["id"])["status"] == "occupied", (
        "the allocated seat was not marked occupied"
    )


def test_release_frees_seat(admin_client, db):
    """Release flips the seat back to available and stamps the ledger row."""
    employee = db.employee_with_seat()
    allocation = db.active_allocation_for_employee(employee["id"])
    assert allocation is not None
    seat_id = allocation["seat_id"]

    released = admin_client.post("/seats/release", json={"employee_id": employee["id"]})
    assert released.status_code in (200, 201, 204), (
        f"POST /api/seats/release returned {released.status_code}: {released.text[:400]}"
    )

    assert db.active_allocation_for_employee(employee["id"]) is None, (
        "the allocation is still active after release"
    )
    assert db.seat_by_id(seat_id)["status"] == "available", (
        "the released seat was not returned to the available pool"
    )
    assert db.released_allocation_for_seat(seat_id) is not None, (
        "the released allocation has no release timestamp"
    )


def test_concurrent_allocate_same_seat_single_winner(admin_token, db):
    """Two simultaneous allocations of one seat: exactly one wins."""
    seat = db.pick_seat(status="available")

    first = db.employee_without_seat()
    second = db.employee_without_seat(exclude={first["id"]})
    contenders = [first["id"], second["id"]]

    def allocate(employee_id: int) -> int:
        # A fresh client per thread: sharing one would serialise the requests and
        # the race this substep exists to prove would never actually happen.
        with client(admin_token) as c:
            response = c.post(
                "/seats/allocate",
                json={"employee_id": employee_id, "seat_id": seat["id"]},
            )
            return response.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(allocate, contenders))

    successes = [code for code in statuses if code in (200, 201)]
    assert len(successes) == 1, (
        f"expected exactly one allocation to succeed, got statuses {statuses}"
    )
    assert db.count_active_allocations_for_seat(seat["id"]) == 1, (
        "the seat ended up with more than one active allocation"
    )


def test_second_allocation_for_same_employee_rejected(admin_client, db):
    """An employee already holding a seat cannot be allocated another."""
    employee = db.employee_with_seat()
    held = db.active_allocation_for_employee(employee["id"])
    assert held is not None

    other_seat = db.pick_seat(status="available")
    response = admin_client.post(
        "/seats/allocate", json={"employee_id": employee["id"], "seat_id": other_seat["id"]}
    )
    assert 400 <= response.status_code < 500, (
        f"expected a 4xx rejection, got {response.status_code}: {response.text[:400]}"
    )

    allocation = db.active_allocation_for_employee(employee["id"])
    assert allocation is not None and allocation["seat_id"] == held["seat_id"], (
        "the original allocation was disturbed by the rejected request"
    )
    assert db.seat_by_id(other_seat["id"])["status"] == "available", (
        "the rejected seat was left marked occupied - partial state leaked"
    )


def test_reserved_seat_allocation_rejected(admin_client, db):
    """Reserved seats are not allocatable."""
    seat = db.pick_seat(status="reserved")
    employee = db.employee_without_seat()

    response = admin_client.post(
        "/seats/allocate", json={"employee_id": employee["id"], "seat_id": seat["id"]}
    )
    assert 400 <= response.status_code < 500, (
        f"expected a 4xx rejection for a reserved seat, got {response.status_code}: "
        f"{response.text[:400]}"
    )
    assert db.seat_by_id(seat["id"])["status"] == "reserved", "the reserved seat changed status"
    assert db.count_active_allocations_for_seat(seat["id"]) == 0, (
        "an allocation row was written for a reserved seat"
    )


def test_maintenance_seat_allocation_rejected(admin_client, db):
    """Maintenance seats are not allocatable."""
    seat = db.pick_seat(status="maintenance")
    employee = db.employee_without_seat()

    response = admin_client.post(
        "/seats/allocate", json={"employee_id": employee["id"], "seat_id": seat["id"]}
    )
    assert 400 <= response.status_code < 500, (
        f"expected a 4xx rejection for a maintenance seat, got {response.status_code}: "
        f"{response.text[:400]}"
    )
    assert db.count_active_allocations_for_seat(seat["id"]) == 0, (
        "an allocation row was written for a maintenance seat"
    )
