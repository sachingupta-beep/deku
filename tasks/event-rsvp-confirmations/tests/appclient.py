"""Authenticated HTTP clients against the deployed app.

Every task's App Contract pins the same two things: the app answers at
`APP_PUBLIC_URL`, and `POST /api/auth/login` takes `{"email", "password"}` and
returns `{"access_token": ...}`. Everything else about the app is the agent's
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
    token = response.json().get("access_token")
    assert token, f"login response for {email} has no access_token: {response.text[:400]}"
    return token


def client(token: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=api_base(), timeout=TIMEOUT, headers=headers)


def seeded_password(env_var: str, default: str) -> str:
    """Seeded passwords come from the harness, mirroring /app/USER_README.md."""
    return os.environ.get(env_var, default)
