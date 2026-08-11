"""Authenticated HTTP clients against the deployed app.

Every task's App Contract pins the same two things: the app answers at
`APP_PUBLIC_URL`, and `POST /api/auth/login` takes `{"email", "password"}` and
returns a bearer token as `access_token` OR `token` -- whichever its brief names.
Everything else about the app is the agent's
choice, so nothing beyond that is assumed here.

Tasks whose auth slot is an external IdP (Keycloak, Zitadel, Logto) still log in
through the app -- the app owns the session, and asserting through it is what
keeps the substeps implementation-agnostic.
"""

from __future__ import annotations

import os

import httpx

TIMEOUT = 30.0


def app_url() -> str:
    return os.environ["APP_PUBLIC_URL"].rstrip("/")


def api_base() -> str:
    return f"{app_url()}/api"


def login(email: str, password: str) -> str:
    response = httpx.post(
        f"{api_base()}/auth/login",
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, (
        f"login for {email} returned {response.status_code}: {response.text[:400]}"
    )
    # The field name is the TASK's contract, not this file's. Task briefs differ:
    # eight say `access_token`, customer-issue-queue's API table says
    # `{token, user:{...}}`. Hardcoding one of them makes the grader reject an app
    # that did exactly what its own brief promised -- which is what happened on
    # 2026-08-10: every one of 26 pytest substeps errored at fixture setup on an
    # app whose login worked, and the run published reward 0.0 with `invalid: []`,
    # asserting the measurement was sound.
    #
    # Accept either. A bearer token under a different key is not an application
    # defect, and this file is shared by every task so it cannot encode one task's
    # wording.
    body = response.json()
    token = body.get("access_token") or body.get("token")
    assert token, (
        f"login response for {email} carries neither 'access_token' nor 'token': "
        f"{response.text[:400]}"
    )
    return token


def client(token: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=api_base(), timeout=TIMEOUT, headers=headers)


def seeded_password(env_var: str, default: str) -> str:
    """Seeded passwords come from the harness, mirroring /app/USER_README.md."""
    return os.environ.get(env_var, default)
