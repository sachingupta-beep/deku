"""Shared pytest fixtures for both the hub suite and the per-service suites.

Lives at the repository root so ``tests/`` and ``services/*/tests/`` see the same
fixtures and the same ``sys.path``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hub.config import HubConfig  # noqa: E402
from main import create_app  # noqa: E402
from service_registry import ServiceRegistry  # noqa: E402


@pytest.fixture
def config() -> HubConfig:
    """A hub config independent of whatever ``HUB_*`` the shell happens to export.

    ``strict_discovery`` is on: in production one bad manifest should not stop
    the other 26 services from serving, but in a test that leniency would let a
    typo pass silently.
    """
    return HubConfig.from_env(
        strict_discovery=True,
        eager_services=(),
        idle_ttl_seconds=0,
        audit_enabled=True,
    )


@pytest.fixture
def registry(config: HubConfig) -> ServiceRegistry:
    """A discovered-but-unloaded registry, with no app around it."""
    instance = ServiceRegistry(config)
    instance.discover()
    return instance


@pytest.fixture
def app(config: HubConfig):
    """A hub app that has *not* entered its lifespan (so nothing is eager-loaded)."""
    return create_app(config)


@pytest.fixture
def client(config: HubConfig):
    """A hub client with the lifespan run, so startup and shutdown hooks fire."""
    with TestClient(create_app(config)) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def supabase_settings() -> dict:
    """The seeded project settings, so tests use the real keys instead of copies
    that silently rot when a seed changes."""
    with open(ROOT / "data" / "supabase" / "settings.json", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="session")
def service_key(supabase_settings: dict) -> str:
    return supabase_settings["api"]["service_role_key"]


@pytest.fixture(scope="session")
def anon_key(supabase_settings: dict) -> str:
    return supabase_settings["api"]["anon_key"]
