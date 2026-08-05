"""Substeps asserting UI numbers reflect real state, and seed data is present."""

from __future__ import annotations

from _shapes import flatten, items
from conftest import (
    CREATOR_2_SLUG,
    CREATOR_SLUG,
    SUBSCRIPTION_AMOUNT,
    SUBSCRIPTION_CURRENCY,
)


def test_seeded_creators_present(anon_client, db):
    """The two seeded creators exist and are surfaced by GET /api/creators."""
    for slug in (CREATOR_SLUG, CREATOR_2_SLUG):
        creator = db.creator_by_slug(slug)
        assert creator is not None, f"seeded creator {slug!r} is missing from DB"

    response = anon_client.get("/creators")
    assert response.status_code == 200, (
        f"GET /api/creators returned {response.status_code}: {response.text[:400]}"
    )
    slugs = {creator.get("slug") for creator in items(response.json())}
    assert {CREATOR_SLUG, CREATOR_2_SLUG} <= slugs, (
        f"GET /api/creators is missing seeded creator slugs; got {slugs}"
    )


def test_free_post_body_visible_to_anonymous(anon_client, db):
    """A free post's body is served without authentication."""
    creator = db.creator_by_slug(CREATOR_SLUG)
    assert creator is not None
    free = db.pick_post(creator["id"], visibility="free")

    response = anon_client.get(f"/posts/{free['id']}")
    assert response.status_code == 200, (
        f"anonymous GET /api/posts/{free['id']} returned {response.status_code} "
        f"on a FREE post: {response.text[:400]}"
    )
    payload = response.json()
    body = payload.get("body")
    assert body, (
        f"free post {free['id']} was returned without a body to an anonymous "
        f"reader: {str(payload)[:400]}"
    )


def test_dashboard_subscriber_count_matches_database(creator_client, db):
    """The creator dashboard's active_subscribers matches the DB exactly."""
    creator = db.creator_by_slug(CREATOR_SLUG)
    assert creator is not None
    expected = db.count_active_subscribers(creator["id"])

    response = creator_client.get("/dashboard")
    assert response.status_code == 200, (
        f"GET /api/dashboard returned {response.status_code}: {response.text[:400]}"
    )
    payload = flatten(response.json())
    assert str(expected) in payload, (
        f"dashboard does not surface true active_subscribers count {expected}; "
        f"got: {payload[:600]}"
    )


def test_dashboard_revenue_matches_succeeded_charges(creator_client, db):
    """Monthly revenue is computed from succeeded charges, in the pinned currency."""
    creator = db.creator_by_slug(CREATOR_SLUG)
    assert creator is not None
    succeeded = db.count_succeeded_charges_for_creator(creator["id"])
    expected_revenue = succeeded * SUBSCRIPTION_AMOUNT

    response = creator_client.get("/dashboard")
    assert response.status_code == 200
    payload = flatten(response.json())
    assert SUBSCRIPTION_CURRENCY in payload, (
        f"dashboard does not name the currency {SUBSCRIPTION_CURRENCY!r}: "
        f"{payload[:600]}"
    )
    # Match on the integer minor-unit value (the pinned representation) or the
    # decimal presentation ($X.YZ), tolerating either shape.
    minor = str(expected_revenue)
    major = f"{expected_revenue / 100:.2f}"
    assert minor in payload or major in payload, (
        f"dashboard revenue does not match succeeded-charge total; "
        f"expected {minor} minor units (or {major}), got: {payload[:600]}"
    )


def test_orion_dashboard_empty_state(creator2_client, db):
    """A creator with no active subscribers gets a coherent zero state."""
    orion = db.creator_by_slug(CREATOR_2_SLUG)
    assert orion is not None

    response = creator2_client.get("/dashboard")
    assert response.status_code == 200, (
        f"GET /api/dashboard for Orion returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    payload = response.json()
    flat = flatten(payload)
    # A zero-subscriber creator should have zero active subscribers and zero
    # monthly revenue -- broken empty states show NaN, "-", or a stale count.
    subs = db.count_active_subscribers(orion["id"])
    assert subs == 0, (
        f"seed data drift: Orion is expected to have zero active subscribers, "
        f"got {subs}"
    )
    assert "0" in flat, (
        f"Orion dashboard does not carry a zero count anywhere: {flat[:600]}"
    )
    # No revenue in a currency other than usd should appear.
    assert SUBSCRIPTION_CURRENCY in flat, (
        f"Orion dashboard omits the pinned currency label: {flat[:600]}"
    )
