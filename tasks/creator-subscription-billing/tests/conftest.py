"""Task fixtures for ethara/creator-subscription-billing.

Two rules from PLAN.md 4.4 govern this file:

1. **Implementation agnostic.** Nothing here may assume the agent's framework,
   file layout, ORM or module names. The only things we may assume are the App
   Contract (the app answers at APP_PUBLIC_URL, REST under /api), whatever
   instruction.md pinned explicitly -- endpoint paths and bodies, the
   `access_token` login key, the seeded accounts, the fixed subscription price
   of 1000 USD minor units, the six table names, the canonical object-key
   scheme -- and third-party API shapes exposed by the capability adapters.

2. **Provider agnostic.** Domain helpers below are composed from the generic
   `Backend` primitives in capabilities.py, never from a provider SDK.
   Payments assertions go through the `payments` fixture (deku-pay adapter);
   storage assertions go through the `object_store` fixture (S3-compatible
   adapter). Swapping a provider replaces the adapter, not this file and not
   a single test.
"""

from __future__ import annotations

import os
import time

import pytest
from _shapes import items
from appclient import client, login, seeded_password
from capabilities import Backend, make_backend, make_payments, make_store

# ---------------------------------------------------------------- accounts
# Seeded by the reference app (instruction.md > Data model > Seed data).

CREATOR_EMAIL = "nova@ethara.ai"
CREATOR_SLUG = "nova"
CREATOR_2_EMAIL = "orion@ethara.ai"
CREATOR_2_SLUG = "orion"

READER_EMAIL = "reader@ethara.ai"          # non-subscribing at seed time
READER_2_EMAIL = "reader2@ethara.ai"       # non-subscribing at seed time
READER_3_EMAIL = "reader3@ethara.ai"       # already active on Nova at seed time

# The subscription price, pinned by instruction.md (integer minor units).
SUBSCRIPTION_AMOUNT = 1000
SUBSCRIPTION_CURRENCY = "usd"

# Deterministic test card tokens exposed by deku-pay (instruction.md >
# Core features > Payments).
CARD_OK = "tok_visa_ok"
CARD_DECLINE = "tok_visa_decline"
CARD_FLAKE = "tok_visa_webhook_flake"

# Bounded settlement poll -- deku-pay is asynchronous by design (PLAN.md 3.3.1).
SETTLEMENT_TIMEOUT_S = 30.0
SETTLEMENT_INTERVAL_S = 0.5


# ------------------------------------------------------------------- HTTP


@pytest.fixture(scope="session")
def anon_client():
    with client() as c:
        yield c


@pytest.fixture(scope="session")
def creator_token() -> str:
    return login(CREATOR_EMAIL, seeded_password("SEED_CREATOR_PASSWORD", "deku-demo-pw-2026"))


@pytest.fixture(scope="session")
def creator_client(creator_token: str):
    with client(creator_token) as c:
        yield c


@pytest.fixture(scope="session")
def creator2_client():
    token = login(CREATOR_2_EMAIL, seeded_password("SEED_CREATOR2_PASSWORD", "deku-demo-pw-2026"))
    with client(token) as c:
        yield c


@pytest.fixture(scope="session")
def reader_token() -> str:
    return login(READER_EMAIL, seeded_password("SEED_READER_PASSWORD", "deku-demo-pw-2026"))


@pytest.fixture(scope="session")
def reader_client(reader_token: str):
    with client(reader_token) as c:
        yield c


@pytest.fixture(scope="session")
def reader2_client():
    token = login(READER_2_EMAIL, seeded_password("SEED_READER2_PASSWORD", "deku-demo-pw-2026"))
    with client(token) as c:
        yield c


@pytest.fixture(scope="session")
def subscribed_reader_client():
    """reader3 is seeded with an already-active Nova subscription."""
    token = login(READER_3_EMAIL, seeded_password("SEED_READER3_PASSWORD", "deku-demo-pw-2026"))
    with client(token) as c:
        yield c


# ---------------------------------------------- capability fixtures (slots)


@pytest.fixture(scope="session")
def payments():
    """deku-pay adapter -- see harness/verifier/capabilities.py."""
    return make_payments()


@pytest.fixture(scope="session")
def object_store():
    """S3-compatible adapter over MinIO."""
    return make_store()


# ------------------------------------------- backend slot, domain helpers


class BillingStore:
    """Domain queries for this task, composed from capability primitives.

    The generic Backend surface is `count`, `rows`, `one` -- provider swappable.
    Everything below is a thin domain shape over those three.
    """

    def __init__(self, backend: Backend) -> None:
        self._b = backend

    # -- creators / users ------------------------------------------------

    def user_by_email(self, email: str) -> dict | None:
        return self._b.one("users", email=email)

    def creator_by_slug(self, slug: str) -> dict | None:
        return self._b.one("creators", slug=slug)

    def creator_by_email(self, email: str) -> dict | None:
        user = self.user_by_email(email)
        if user is None:
            return None
        return self._b.one("creators", user_id=user["id"])

    # -- posts / images --------------------------------------------------

    def posts_for_creator(self, creator_id: int, visibility: str | None = None) -> list[dict]:
        where: dict = {"creator_id": creator_id}
        if visibility:
            where["visibility"] = visibility
        return self._b.rows("posts", limit=200, **where)

    def pick_post(self, creator_id: int, visibility: str) -> dict:
        found = self.posts_for_creator(creator_id, visibility)
        assert found, (
            f"no {visibility!r} post seeded for creator_id={creator_id}"
        )
        return found[0]

    def images_for_post(self, post_id: int) -> list[dict]:
        return self._b.rows("post_images", limit=50, post_id=post_id)

    # -- subscriptions ---------------------------------------------------

    def subscription(self, reader_id: int, creator_id: int) -> dict | None:
        return self._b.one(
            "subscriptions", reader_id=reader_id, creator_id=creator_id
        )

    def active_subscription(self, reader_id: int, creator_id: int) -> dict | None:
        return self._b.one(
            "subscriptions",
            reader_id=reader_id,
            creator_id=creator_id,
            status="active",
        )

    def count_active_subscribers(self, creator_id: int) -> int:
        return self._b.count("subscriptions", creator_id=creator_id, status="active")

    def count_subscription_rows(self, reader_id: int, creator_id: int) -> int:
        return self._b.count(
            "subscriptions", reader_id=reader_id, creator_id=creator_id
        )

    # -- charges ---------------------------------------------------------

    def charges_for_subscription(self, subscription_id: int) -> list[dict]:
        return self._b.rows("charges", limit=20, subscription_id=subscription_id)

    def count_succeeded_charges_for_creator(self, creator_id: int) -> int:
        # No cross-table join in the generic Backend; walk active subs for this
        # creator and sum succeeded charges attached to them.
        total = 0
        for sub in self._b.rows("subscriptions", limit=500, creator_id=creator_id):
            total += self._b.count(
                "charges", subscription_id=sub["id"], status="succeeded"
            )
        return total


@pytest.fixture(scope="session")
def db() -> BillingStore:
    return BillingStore(make_backend())


# ------------------------------------------------------------------ utilities


@pytest.fixture
def unique_email() -> str:
    return f"verifier-{os.urandom(6).hex()}@ethara.ai"


def wait_for_status(
    getter, target: set[str], timeout: float = SETTLEMENT_TIMEOUT_S
) -> dict | None:
    """Poll `getter()` until it returns a dict whose `status` is in `target`.

    deku-pay settlement is asynchronous (PLAN.md 3.3.1). Asserting immediately
    after POST /subscriptions is a race the substep would lose. The bounded
    poll here is the honest way to write these substeps; when it times out the
    caller reports "settlement did not complete within Ns" so the failure is
    diagnosable rather than a mystery flake.
    """
    deadline = time.monotonic() + timeout
    latest: dict | None = None
    while time.monotonic() < deadline:
        latest = getter()
        if latest is not None and latest.get("status") in target:
            return latest
        time.sleep(SETTLEMENT_INTERVAL_S)
    return latest


def resolve_creator_id(client_, slug: str) -> int:
    response = client_.get("/creators")
    assert response.status_code == 200, (
        f"GET /api/creators returned {response.status_code}: {response.text[:400]}"
    )
    for creator in items(response.json()):
        if creator.get("slug") == slug:
            return int(creator["id"])
    raise AssertionError(f"creator with slug {slug!r} not returned by /api/creators")
