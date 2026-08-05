"""Storage substeps.

PLAN.md 4.7: a browser looking at a rendered image tells you nothing about
whether the bytes came from the real bucket or from a base64 blob the app
returned to itself. Every meaningful storage assertion goes through the
`object_store` capability fixture (S3-compatible adapter over MinIO), or
attempts a direct object fetch and expects a denial.
"""

from __future__ import annotations

import io
import os

import httpx
from appclient import app_url
from conftest import (
    CREATOR_SLUG,
    resolve_creator_id,
)

# Object-key naming scheme pinned in instruction.md > Core features.
KEY_PREFIX_TEMPLATE = "posts/{post_id}/"


def _png_bytes() -> bytes:
    # A minimal, valid 1x1 PNG. Deterministic so re-uploads produce the same key.
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03"
        b"\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _create_paid_post(creator_client) -> int:
    response = creator_client.post(
        "/posts",
        json={
            "title": f"Verifier-{os.urandom(4).hex()}",
            "body": "verifier-paid-body",
            "visibility": "subscriber_only",
        },
    )
    assert response.status_code in (200, 201), (
        f"POST /api/posts returned {response.status_code}: {response.text[:400]}"
    )
    return int(response.json()["id"])


def _upload_image(creator_client, post_id: int, data: bytes) -> dict:
    files = {"file": ("verifier.png", io.BytesIO(data), "image/png")}
    response = creator_client.post(f"/posts/{post_id}/images", files=files)
    assert response.status_code in (200, 201), (
        f"POST /api/posts/{post_id}/images returned {response.status_code}: "
        f"{response.text[:400]}"
    )
    return response.json()


def test_uploaded_image_lands_in_bucket(creator_client, object_store, db):
    """An image uploaded through the app is really in the S3 bucket at the expected key."""
    post_id = _create_paid_post(creator_client)
    upload = _upload_image(creator_client, post_id, _png_bytes())

    prefix = KEY_PREFIX_TEMPLATE.format(post_id=post_id)
    keys = object_store.list(prefix=prefix)
    assert keys, (
        f"no objects found in bucket under prefix {prefix!r}; the upload was "
        f"not delivered to the real object store"
    )

    # Prefer the exact key the API returned if the app exposes it; otherwise
    # fall back to any object under the post's prefix.
    expected_key = upload.get("object_key")
    if expected_key:
        assert object_store.exists(expected_key), (
            f"API reported object_key={expected_key!r} but the object is not "
            f"in the bucket -- app returned success without actually persisting"
        )

    # Persisted post_images row matches -- rules out an upload that hit the
    # bucket but was never linked back to the post.
    rows = db.images_for_post(post_id)
    assert rows, (
        f"post {post_id} has an uploaded image in the bucket but no post_images "
        f"row -- UI would show it, revocation would leak"
    )


def test_entitled_reader_can_fetch_paid_image(subscribed_reader_client, db):
    """The seeded active reader can actually read a paid post's image bytes."""
    creator = db.creator_by_slug(CREATOR_SLUG)
    assert creator is not None, "seeded creator Nova is missing"
    paid = db.pick_post(creator["id"], visibility="subscriber_only")
    images = db.images_for_post(paid["id"])
    assert images, (
        f"seed data is missing an image attachment on Nova's subscriber_only "
        f"post {paid['id']}; the entitled-fetch path cannot be exercised"
    )
    image = images[0]

    response = subscribed_reader_client.get(f"/posts/{paid['id']}/image/{image['id']}")
    # 200 for stream-through or 302 for a presigned URL are both acceptable
    # per the API shapes table in instruction.md.
    assert response.status_code in (200, 302), (
        f"entitled reader got {response.status_code} on a paid image, expected "
        f"200 or 302: {response.text[:400]}"
    )

    if response.status_code == 302:
        location = response.headers.get("Location") or response.headers.get("location")
        assert location, "302 without a Location header for a presigned URL"
        fetched = httpx.get(location, timeout=15.0, follow_redirects=True)
        assert fetched.status_code == 200, (
            f"presigned URL for entitled reader returned {fetched.status_code}"
        )
        assert fetched.content, "presigned fetch returned empty body"


def test_non_subscriber_cannot_fetch_paid_image(reader2_client, db):
    """A non-subscriber's request for a paid image is denied at the API."""
    creator = db.creator_by_slug(CREATOR_SLUG)
    assert creator is not None
    paid = db.pick_post(creator["id"], visibility="subscriber_only")
    images = db.images_for_post(paid["id"])
    assert images, (
        f"seed data missing an image on Nova's paid post {paid['id']}"
    )
    image = images[0]

    response = reader2_client.get(f"/posts/{paid['id']}/image/{image['id']}")
    assert response.status_code in (401, 403, 404), (
        f"non-subscriber got {response.status_code} on a paid image, expected "
        f"401/403/404: {response.text[:400]}"
    )
    assert response.status_code != 200, (
        "non-subscriber received a paid image body -- access control is broken"
    )
    # And no presigned URL should have been handed out either.
    assert response.status_code != 302, (
        "non-subscriber received a 302 to a presigned URL for a paid image -- "
        "any short-lived URL is still a leak if issued to the wrong caller"
    )


def test_paid_bucket_object_not_publicly_readable(db, object_store):
    """A paid image's object key must not be readable without app-level auth.

    Two mechanisms are acceptable (instruction.md > Core features): stream
    through the app, or hand out short-lived presigned URLs to authorised
    callers only. Neither permits an unauthenticated fetch of the raw object
    URL. We construct the naive public URL and expect it to be rejected.
    """
    creator = db.creator_by_slug(CREATOR_SLUG)
    assert creator is not None
    paid = db.pick_post(creator["id"], visibility="subscriber_only")
    images = db.images_for_post(paid["id"])
    assert images, "no seeded paid image to probe"
    key = images[0]["object_key"]

    endpoint = os.environ["STORAGE_ENDPOINT"].rstrip("/")
    bucket = os.environ["STORAGE_BUCKET"]

    # Two shapes of naive public URL cover both path-style and virtual-host
    # style MinIO configurations. If EITHER succeeds without credentials, the
    # bucket is effectively public and the guarantee is broken.
    candidates = [
        f"{endpoint}/{bucket}/{key}",
        f"{endpoint}/{key}",
    ]
    for url in candidates:
        try:
            response = httpx.get(url, timeout=10.0)
        except httpx.RequestError:
            continue
        assert response.status_code != 200, (
            f"unauthenticated GET {url} succeeded ({len(response.content)} bytes) "
            f"-- paid image is publicly readable straight from the bucket, "
            f"bypassing every app-level guard"
        )

    # Bucket adapter must still confirm the object exists (so we know we were
    # probing a real, present object, not a nonexistent key).
    assert object_store.exists(key), (
        f"object {key!r} is missing from the bucket -- the assertion above is "
        f"meaningless if the object never existed"
    )
