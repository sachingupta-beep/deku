"""Payments substeps.

Black box: every assertion goes through the deployed HTTP surface, the `db`
capability fixture, and the `payments` capability fixture (deku-pay adapter).
Nothing here imports a payments SDK or the agent's code.

PLAN.md 4.7: a browser grader cannot tell a real charge from a `setTimeout`.
Every meaningful payments assertion lives here.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import hmac
import json
import os

from appclient import client
from conftest import (
    CARD_DECLINE,
    CARD_FLAKE,
    CARD_OK,
    CREATOR_SLUG,
    READER_2_EMAIL,
    READER_EMAIL,
    SUBSCRIPTION_AMOUNT,
    SUBSCRIPTION_CURRENCY,
    resolve_creator_id,
    seeded_password,
    wait_for_status,
)
from appclient import api_base, login


def _fresh_reader_token(email: str, env: str, default: str) -> str:
    return login(email, seeded_password(env, default))


def _subscribe(client_, creator_id: int, source: str) -> dict:
    response = client_.post(
        "/subscriptions", json={"creator_id": creator_id, "source": source}
    )
    assert response.status_code in (200, 201), (
        f"POST /api/subscriptions returned {response.status_code}: {response.text[:400]}"
    )
    return response.json()


def _get_subscription(client_, sub_id: int) -> dict:
    response = client_.get(f"/subscriptions/{sub_id}")
    assert response.status_code == 200, (
        f"GET /api/subscriptions/{sub_id} returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    return response.json()


# ==================================================================== charges


def test_subscribe_creates_real_charge(reader_client, db, payments):
    """A subscribe attempt creates a real charge in deku-pay for the pinned amount."""
    creator_id = resolve_creator_id(reader_client, CREATOR_SLUG)

    charges_before = len(payments.charges())
    subscription = _subscribe(reader_client, creator_id, CARD_OK)

    # Wait until at least one new charge exists AND settles. The provider is
    # asynchronous by design (PLAN.md 3.3.1) -- asserting immediately would race.
    def latest_charge():
        found = payments.find_charge(
            SUBSCRIPTION_AMOUNT, SUBSCRIPTION_CURRENCY, status="succeeded"
        )
        return {"status": found.status, "charge": found} if found else None

    settled = wait_for_status(latest_charge, {"succeeded"})
    assert settled is not None, (
        f"no succeeded charge for {SUBSCRIPTION_AMOUNT} {SUBSCRIPTION_CURRENCY} "
        f"appeared in deku-pay within settlement timeout; subscription={subscription}"
    )

    charges_after = payments.charges()
    assert len(charges_after) > charges_before, (
        "no new charge appeared in deku-pay after POST /api/subscriptions -- "
        "the app is not calling the real payment provider"
    )

    # A charge for the wrong amount would mean the price was not pinned or the
    # app is faking the integration behind the scenes.
    assert settled["charge"].amount == SUBSCRIPTION_AMOUNT, (
        f"charge amount {settled['charge'].amount} != pinned {SUBSCRIPTION_AMOUNT}"
    )
    assert settled["charge"].currency.lower() == SUBSCRIPTION_CURRENCY, (
        f"charge currency {settled['charge'].currency!r} != {SUBSCRIPTION_CURRENCY!r}"
    )


def test_successful_charge_activates_subscription(reader_client, db):
    """After a succeeded charge, the subscription becomes active."""
    creator_id = resolve_creator_id(reader_client, CREATOR_SLUG)
    subscription = _subscribe(reader_client, creator_id, CARD_OK)
    sub_id = subscription["id"]

    resolved = wait_for_status(lambda: _get_subscription(reader_client, sub_id), {"active"})
    assert resolved is not None and resolved.get("status") == "active", (
        f"subscription {sub_id} did not become active within settlement timeout; "
        f"last seen: {resolved}"
    )

    reader = db.user_by_email(READER_EMAIL)
    assert reader is not None, "seeded reader is missing from the database"
    row = db.active_subscription(reader["id"], creator_id)
    assert row is not None, (
        "no active subscription row exists in the database even though the API "
        "reports the subscription as active -- UI and persisted state disagree"
    )


def test_declined_card_does_not_activate_subscription(reader2_client, db, payments):
    """A declined card never yields an active subscription and never a succeeded charge."""
    creator_id = resolve_creator_id(reader2_client, CREATOR_SLUG)

    subscription = _subscribe(reader2_client, creator_id, CARD_DECLINE)
    sub_id = subscription["id"]

    # Poll until the subscription settles into a non-pending, non-active state.
    resolved = wait_for_status(
        lambda: _get_subscription(reader2_client, sub_id),
        {"canceled", "past_due", "failed"},
    )
    assert resolved is not None, (
        f"declined subscription {sub_id} never left pending state within timeout"
    )
    assert resolved.get("status") != "active", (
        f"declined card produced an ACTIVE subscription: {resolved}"
    )

    reader = db.user_by_email(READER_2_EMAIL)
    assert reader is not None
    active = db.active_subscription(reader["id"], creator_id)
    assert active is None, (
        f"declined card produced an active subscription row: {active}"
    )


def test_duplicate_webhook_is_idempotent(reader_client, db, payments):
    """tok_visa_webhook_flake delivers the settlement webhook twice.

    The subscription must go active exactly once, and revenue for that
    creator must not double-count.
    """
    creator_id = resolve_creator_id(reader_client, CREATOR_SLUG)

    subscribers_before = db.count_active_subscribers(creator_id)
    succeeded_before = db.count_succeeded_charges_for_creator(creator_id)

    subscription = _subscribe(reader_client, creator_id, CARD_FLAKE)
    sub_id = subscription["id"]

    resolved = wait_for_status(
        lambda: _get_subscription(reader_client, sub_id), {"active"}
    )
    assert resolved is not None, (
        f"flaky-webhook subscription {sub_id} did not activate within timeout"
    )

    # Give the duplicate delivery a moment to arrive and be handled.
    import time

    time.sleep(2.0)

    subscribers_after = db.count_active_subscribers(creator_id)
    succeeded_after = db.count_succeeded_charges_for_creator(creator_id)

    assert subscribers_after - subscribers_before == 1, (
        f"active subscriber count moved by {subscribers_after - subscribers_before}, "
        f"expected exactly 1 -- duplicate webhook double-granted access"
    )
    assert succeeded_after - succeeded_before <= 1, (
        f"succeeded-charge count moved by {succeeded_after - succeeded_before} "
        f"for one subscription -- duplicate webhook double-counted revenue"
    )


def test_invalid_webhook_signature_rejected(anon_client):
    """A webhook body with a wrong signature must be rejected, not trusted."""
    payload = {
        "id": "evt_forged_" + os.urandom(4).hex(),
        "type": "charge.succeeded",
        "data": {"object": {"id": "ch_forged", "status": "succeeded"}},
    }
    body = json.dumps(payload).encode()
    bad_signature = hmac.new(b"not-the-real-secret", body, hashlib.sha256).hexdigest()

    response = anon_client.post(
        "/webhooks/payments",
        content=body,
        headers={
            "Deku-Signature": bad_signature,
            "Content-Type": "application/json",
        },
    )
    assert 400 <= response.status_code < 500, (
        f"forged webhook returned {response.status_code}, expected 4xx: "
        f"{response.text[:400]}"
    )
    assert response.status_code != 200, (
        "app accepted a webhook with an invalid HMAC signature -- an attacker "
        "could grant subscriptions for free by posting synthetic events"
    )


def test_concurrent_subscribe_single_active_row(db):
    """Two simultaneous subscribe calls for one reader-creator pair: at most one active row."""
    token = _fresh_reader_token(READER_EMAIL, "SEED_READER_PASSWORD", "reader")
    reader = db.user_by_email(READER_EMAIL)
    assert reader is not None

    # Use a fresh single-shot client to look up creator id, then post two
    # concurrent subscribes from independent clients.
    with client(token) as bootstrap:
        creator_id = resolve_creator_id(bootstrap, CREATOR_SLUG)

    def attempt() -> int:
        with client(token) as c:
            response = c.post(
                "/subscriptions",
                json={"creator_id": creator_id, "source": CARD_OK},
            )
            return response.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: attempt(), range(2)))

    # At least one must have been accepted; the second must not create a second
    # concurrent non-canceled row. Which of accept-and-idempotent-return, or
    # accept-and-reject-second is up to the agent -- both satisfy the invariant.
    successes = [code for code in statuses if code in (200, 201)]
    conflicts = [code for code in statuses if 400 <= code < 500]
    assert successes, (
        f"neither concurrent subscribe attempt succeeded, statuses={statuses}"
    )
    assert successes or conflicts, (
        f"unexpected statuses from concurrent subscribes: {statuses}"
    )

    # The persisted invariant is what matters: at most one non-canceled row.
    active_or_pending = 0
    for status in ("pending", "active"):
        active_or_pending += db._b.count(
            "subscriptions", reader_id=reader["id"], creator_id=creator_id, status=status
        )
    assert active_or_pending <= 1, (
        f"reader has {active_or_pending} concurrent non-canceled subscriptions "
        f"for one creator -- the partial unique index is not enforced"
    )
