"""Black-box HTTP substeps for deku/smoke-tip-calculator.

Every assertion is against the deployed app via APP_PUBLIC_URL. No agent code
is imported. No provider SDKs (this task has no backing services).
"""

from __future__ import annotations


def test_health_endpoint_returns_200(client):
    response = client.get("/api/health")
    assert response.status_code == 200, (
        f"GET /api/health returned {response.status_code}: {response.text[:400]}"
    )


def test_calculate_basic_returns_exact_shape(client):
    """Normal case: bill 100, tip 15%, no split. Values pinned in instruction.md."""
    response = client.get("/api/calculate", params={"bill": 100, "tip": 15})
    assert response.status_code == 200, (
        f"GET /api/calculate returned {response.status_code}: {response.text[:400]}"
    )
    payload = response.json()

    for field in ("bill", "tip_percent", "people", "tip_amount", "total", "per_person"):
        assert field in payload, (
            f"response missing required field {field!r}: {payload}"
        )

    assert int(payload["people"]) == 1, (
        f"people must default to 1 when omitted, got {payload['people']!r}"
    )
    assert float(payload["tip_amount"]) == 15.00, (
        f"tip_amount for bill=100 tip=15 must be 15.00, got {payload['tip_amount']!r}"
    )
    assert float(payload["total"]) == 115.00, (
        f"total for bill=100 tip=15 must be 115.00, got {payload['total']!r}"
    )
    assert float(payload["per_person"]) == 115.00, (
        f"per_person for people=1 must equal total, got {payload['per_person']!r}"
    )


def test_calculate_split_returns_per_person(client):
    """Split case: bill 100, tip 20%, split 4 ways -> 30.00 each."""
    response = client.get("/api/calculate", params={"bill": 100, "tip": 20, "people": 4})
    assert response.status_code == 200, (
        f"GET /api/calculate split-case returned {response.status_code}: {response.text[:400]}"
    )
    payload = response.json()

    assert int(payload["people"]) == 4
    assert float(payload["tip_amount"]) == 20.00, (
        f"tip_amount for bill=100 tip=20 must be 20.00, got {payload['tip_amount']!r}"
    )
    assert float(payload["total"]) == 120.00, (
        f"total for bill=100 tip=20 must be 120.00, got {payload['total']!r}"
    )
    assert float(payload["per_person"]) == 30.00, (
        f"per_person for total=120 people=4 must be 30.00, got {payload['per_person']!r}"
    )


def test_invalid_bill_returns_400(client):
    """A negative bill is a rule violation, not a server error."""
    response = client.get("/api/calculate", params={"bill": -5, "tip": 10})
    assert response.status_code == 400, (
        f"a negative bill must return 400 (not {response.status_code}): {response.text[:400]}"
    )
    payload = response.json()
    assert "error" in payload, (
        f"400 response must carry a JSON error field; got {payload}"
    )
    assert isinstance(payload["error"], str) and payload["error"].strip(), (
        f"error field must be a non-empty string; got {payload['error']!r}"
    )
