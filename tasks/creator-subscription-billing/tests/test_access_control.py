"""Authorization substeps.

PLAN.md 4.7: hiding a button is not a permission. Every assertion here goes to
the API directly, because that is the only place authorization can actually be
proven. A locked-post UI could be a beautiful lie sitting on top of a paid body
the API happily returned in the JSON.
"""

from __future__ import annotations

from conftest import (
    CARD_OK,
    CREATOR_2_SLUG,
    CREATOR_EMAIL,
    CREATOR_SLUG,
    READER_2_EMAIL,
    resolve_creator_id,
)


def _pick_paid_post_id(client_, slug: str) -> int:
    """Read the paid post list from the creator profile as an anonymous request
    would see it -- but resolve through the entitled reader so the response
    actually contains post ids. The test then re-checks the paid post from a
    non-entitled session.
    """
    response = client_.get(f"/creators/{slug}")
    assert response.status_code == 200, (
        f"GET /api/creators/{slug} returned {response.status_code}: {response.text[:400]}"
    )
    payload = response.json()
    # The profile shape is at the agent's discretion apart from carrying posts;
    # tolerate a top-level list, a "posts" key, or a nested envelope.
    candidates: list[dict] = []
    if isinstance(payload, dict):
        for key in ("posts", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
    elif isinstance(payload, list):
        candidates = payload

    for post in candidates:
        if post.get("visibility") == "subscriber_only":
            return int(post["id"])
    raise AssertionError(
        f"no subscriber_only post surfaced by GET /api/creators/{slug}: {str(payload)[:400]}"
    )


def test_non_subscriber_paid_post_api_denied(subscribed_reader_client, reader2_client):
    """A non-subscriber's GET on a paid post must not return the paid body."""
    paid_id = _pick_paid_post_id(subscribed_reader_client, CREATOR_SLUG)

    response = reader2_client.get(f"/posts/{paid_id}")
    # 403 is the intended reply; 401 / 404 (obscure existence) also acceptable.
    assert response.status_code in (401, 403, 404), (
        f"non-subscriber paid-post request returned {response.status_code}, "
        f"expected 401/403/404: {response.text[:400]}"
    )

    if response.status_code == 200:
        # Belt-and-braces in case a shape mutation slips a 200 through: verify
        # no paid content is exposed. The status assertion above should already
        # have failed if we got here.
        assert "body" not in response.json(), (
            "paid post body returned to a non-subscriber"
        )


def test_non_subscriber_paid_post_body_omitted_from_list(reader2_client):
    """A non-subscriber's creator profile view must not carry paid bodies."""
    response = reader2_client.get(f"/creators/{CREATOR_SLUG}")
    assert response.status_code == 200, (
        f"GET /api/creators/{CREATOR_SLUG} returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    payload = response.json()
    posts: list[dict] = []
    if isinstance(payload, dict):
        for key in ("posts", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                posts = value
                break
    elif isinstance(payload, list):
        posts = payload

    paid_posts_with_body = [
        post for post in posts
        if post.get("visibility") == "subscriber_only" and post.get("body")
    ]
    assert not paid_posts_with_body, (
        f"paid post bodies leaked to a non-subscriber via the profile list: "
        f"{[p.get('id') for p in paid_posts_with_body]}"
    )


def test_declined_reader_cannot_read_paid_post(reader2_client, subscribed_reader_client):
    """A reader whose card declined has no access to paid posts."""
    paid_id = _pick_paid_post_id(subscribed_reader_client, CREATOR_SLUG)

    response = reader2_client.get(f"/posts/{paid_id}")
    assert response.status_code in (401, 403, 404), (
        f"reader with a declined subscription got {response.status_code} on a "
        f"paid post, expected 401/403/404: {response.text[:400]}"
    )


def test_unauthenticated_requests_denied(anon_client, subscribed_reader_client):
    """Anonymous callers cannot read paid posts or reach protected endpoints."""
    paid_id = _pick_paid_post_id(subscribed_reader_client, CREATOR_SLUG)

    read = anon_client.get(f"/posts/{paid_id}")
    assert read.status_code in (401, 403, 404), (
        f"anonymous GET /api/posts/{paid_id} returned {read.status_code}, "
        f"expected 401/403/404: {read.text[:400]}"
    )

    dashboard = anon_client.get("/dashboard")
    assert dashboard.status_code in (401, 403), (
        f"anonymous GET /api/dashboard returned {dashboard.status_code}, "
        f"expected 401/403: {dashboard.text[:400]}"
    )

    post = anon_client.post("/posts", json={"title": "x", "body": "", "visibility": "free"})
    assert post.status_code in (401, 403), (
        f"anonymous POST /api/posts returned {post.status_code}, expected 401/403: "
        f"{post.text[:400]}"
    )

    subscribe = anon_client.post(
        "/subscriptions", json={"creator_id": 1, "source": CARD_OK}
    )
    assert subscribe.status_code in (401, 403), (
        f"anonymous POST /api/subscriptions returned {subscribe.status_code}, "
        f"expected 401/403: {subscribe.text[:400]}"
    )


def test_creator_cannot_subscribe_to_self(creator_client, db, payments):
    """A creator subscribing to their own content is rejected -- never charged."""
    creator = db.creator_by_slug(CREATOR_SLUG)
    assert creator is not None, "seeded creator Nova is missing"

    charges_before = len(payments.charges())
    response = creator_client.post(
        "/subscriptions", json={"creator_id": creator["id"], "source": CARD_OK}
    )
    assert 400 <= response.status_code < 500, (
        f"creator subscribing to self returned {response.status_code}, "
        f"expected 4xx: {response.text[:400]}"
    )

    # And -- critically -- no charge was created in deku-pay for that call.
    charges_after = payments.charges()
    assert len(charges_after) == charges_before, (
        f"creator self-subscribe created {len(charges_after) - charges_before} "
        f"new charge(s) in deku-pay; the app must never charge a creator for "
        f"their own content"
    )
