"""Fixtures for deku/smoke-tip-calculator.

Black box: every assertion goes through the deployed HTTP surface. Nothing here
imports the agent's code, and no backing-service adapter is used -- this task
declares no service slots on purpose.
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
