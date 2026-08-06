"""Fixtures for deku/calculator.

Black box: every assertion goes through the deployed HTTP surface. Nothing here
imports the agent's code, and no backing-service adapter is used -- this task
declares no service slots on purpose, so there is no capability fixture to
resolve and nothing to seed.

There are no credentials. The app has no authentication, which is why no seeded
email or password appears anywhere in this directory (validate_task.py enforces
that every credential a verifier uses is pinned literally in instruction.md --
the cheapest way to satisfy that is to use none).
"""

from __future__ import annotations

import os

import httpx
import pytest

TIMEOUT = 15.0


def app_url() -> str:
    return os.environ["APP_PUBLIC_URL"].rstrip("/")


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=app_url(), timeout=TIMEOUT) as c:
        yield c


@pytest.fixture
def clean_history(client):
    """Empty the history so a test starts from a known state.

    The browser pass runs BEFORE pytest (PLAN.md 4.5), so by the time these
    tests run the history already holds whatever the browser grader created.
    Tests that assert on history contents must clear first or they are asserting
    against the browser pass's leftovers, not their own writes.

    Uses the same DELETE endpoint that `test_history_clear_empties_the_log`
    covers. That is deliberate: a broken clear should fail loudly across every
    history assertion rather than quietly corrupting one.
    """
    client.delete("/api/history")
    yield
