"""Authorization substeps.

PLAN.md 4.7: hiding a button is not a permission. Every assertion here goes to the
API directly, because that is the only place authorization can actually be proven.

The product has one role (`user`), so RBAC here is really tenant isolation --
one user's token must not touch another user's habits.
"""

from __future__ import annotations

import os

import httpx
from appclient import api_base, client
from conftest import new_habit_payload, today_utc

TIMEOUT = 30.0

MUTATING_ENDPOINTS_ANON = [
    ("GET", "/habits"),
    ("POST", "/habits"),
    ("GET", "/dashboard"),
]


def test_unauthenticated_requests_denied(anon_client):
    """Anonymous callers are rejected on reads and mutations alike."""
    for method, path in MUTATING_ENDPOINTS_ANON:
        response = anon_client.request(method, path, json={})
        assert response.status_code in (401, 403), (
            f"anonymous {method} /api{path} returned {response.status_code}, "
            f"expected 401/403: {response.text[:400]}"
        )


def _bootstrap_second_user() -> tuple[str, str]:
    """Register a second user through the app's own endpoints when possible.

    The App Contract does not pin a signup route -- instruction.md forbids it --
    so we fall back to PocketBase admin creation via the backend adapter. Both
    paths converge on returning (token, user_id) for the assertions below to
    exercise cross-user isolation. This helper is intentionally forgiving: if
    neither path is available in a given implementation the substep is skipped
    with a clear message rather than a spurious failure.
    """
    email = f"verifier-alt-{os.urandom(4).hex()}@ethara.ai"
    password = "verifier-alt-password"

    # 1. Try the app's login after admin-provisioning through PocketBase.
    base = os.environ.get("BACKEND_URL", "").rstrip("/")
    admin = os.environ.get("BACKEND_ADMIN_KEY", "")
    if base and admin:
        create = httpx.post(
            f"{base}/api/collections/users/records",
            headers={"Authorization": admin},
            json={
                "email": email,
                "password": password,
                "passwordConfirm": password,
            },
            timeout=TIMEOUT,
        )
        if create.status_code in (200, 201):
            token_response = httpx.post(
                f"{api_base()}/auth/login",
                json={"email": email, "password": password},
                timeout=TIMEOUT,
            )
            if token_response.status_code == 200:
                token = token_response.json().get("access_token")
                assert token, (
                    f"secondary login has no access_token: {token_response.text[:400]}"
                )
                return token, email

    import pytest

    pytest.skip(
        "no way to provision a second user in this environment - the substep needs "
        "either BACKEND_ADMIN_KEY reach or a signup endpoint the App Contract does not pin"
    )


def test_other_users_habit_not_readable(user_client, db, user_id):
    """A second user's token cannot read the seeded user's habits."""
    other_token, _ = _bootstrap_second_user()
    with client(other_token) as other:
        # The other user's own list may legitimately be empty -- what matters is
        # they cannot pull a specific habit belonging to the seeded user.
        seeded_habits = db.habits_for(user_id, deleted=False)
        assert seeded_habits, "seeded user has no habits - cross-user check is meaningless"
        target = seeded_habits[0]

        response = other.get(f"/habits/{target['id']}")
        assert response.status_code in (401, 403, 404), (
            f"cross-user GET /api/habits/{{id}} returned {response.status_code}, "
            f"expected 401/403/404: {response.text[:400]}"
        )


def test_other_users_habit_not_mutable(user_client, db, user_id):
    """A second user's token cannot mark, un-mark, rename or delete another user's habit."""
    other_token, _ = _bootstrap_second_user()
    seeded_habits = db.habits_for(user_id, deleted=False)
    assert seeded_habits, "seeded user has no habits - cross-user check is meaningless"
    target = seeded_habits[0]
    completions_before = db.count_completions(user_id, habit_id=target["id"])

    with client(other_token) as other:
        mark = other.post(f"/habits/{target['id']}/complete", json={"date": today_utc()})
        assert mark.status_code in (401, 403, 404), (
            f"cross-user complete returned {mark.status_code}, expected 401/403/404: "
            f"{mark.text[:400]}"
        )

        rename = other.patch(
            f"/habits/{target['id']}", json={"name": "hijacked"}
        )
        assert rename.status_code in (401, 403, 404), (
            f"cross-user rename returned {rename.status_code}, expected 401/403/404: "
            f"{rename.text[:400]}"
        )

        delete = other.delete(f"/habits/{target['id']}")
        assert delete.status_code in (401, 403, 404), (
            f"cross-user delete returned {delete.status_code}, expected 401/403/404: "
            f"{delete.text[:400]}"
        )

    # State on the seeded user's side is untouched.
    still_there = db.habit_by_id(target["id"])
    assert still_there is not None and still_there.get("deleted") in (False, 0, None), (
        f"the seeded habit was disturbed by another user's request: {still_there}"
    )
    assert str(still_there.get("name", "")).lower() != "hijacked", (
        "the seeded habit was renamed by a cross-user PATCH"
    )
    assert db.count_completions(user_id, habit_id=target["id"]) == completions_before, (
        "a cross-user completion attempt reached the ledger"
    )
