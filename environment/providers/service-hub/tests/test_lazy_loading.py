"""The lazy-loading mechanism: load once, on demand, and give the memory back.

These are the tests that would catch the architecture quietly regressing into
"load everything at startup" -- which would still pass every functional test.
"""

from __future__ import annotations

import asyncio
import dataclasses
import textwrap

import httpx
import pytest

from hub.errors import ServiceLoadError, ServiceNotImplemented
from service_registry import ServiceRegistry, ServiceState


def test_boot_loads_nothing(client):
    """The whole point. 27 services discovered, zero imported."""
    body = client.get("/hub/metrics").json()
    assert body["discovered"] == 27
    assert body["loaded"] == 0


def test_discovery_does_not_load(client):
    """Asking what exists must not have the side effect of building it."""
    client.get("/hub/services")
    client.get("/hub/catalog")
    client.get("/hub/services/supabase")
    assert client.get("/hub/metrics").json()["loaded"] == 0


def test_first_request_loads_the_service(client):
    assert client.get("/hub/services/supabase").json()["state"] == "discovered"
    assert client.get("/supabase/rest/v1/projects").status_code == 200
    view = client.get("/hub/services/supabase").json()
    assert view["state"] == "ready"
    assert view["load_count"] == 1
    assert view["load_ms"] > 0


def test_second_request_reuses_the_loaded_service(client):
    for _ in range(5):
        client.get("/supabase/rest/v1/projects")
    view = client.get("/hub/services/supabase").json()
    assert view["load_count"] == 1
    assert view["request_count"] >= 5


def test_loading_one_service_does_not_load_its_neighbours(client):
    """Isolation: touching Supabase must not drag in the other 26."""
    client.get("/supabase/rest/v1/projects")
    assert client.get("/hub/metrics").json()["loaded"] == 1
    assert client.get("/hub/services").json()["services"]
    states = {s["slug"]: s["state"] for s in client.get("/hub/services").json()["services"]}
    assert states["supabase"] == "ready"
    assert states["keycloak"] == "declared"
    assert states["mailpit"] == "declared"


def test_concurrent_first_requests_load_exactly_once(app):
    """The per-slug lock, under the burst it exists for.

    Twelve simultaneous cold requests must produce one load, not twelve. Without
    the double-checked lock in ``acquire`` this races: every coroutine sees
    ``state != READY`` and starts its own import.
    """

    async def hammer():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://hub") as client:
            responses = await asyncio.gather(
                *[client.get("/supabase/rest/v1/projects") for _ in range(12)]
            )
        return responses

    responses = asyncio.run(hammer())
    assert [r.status_code for r in responses] == [200] * 12
    record = app.state.registry.get("supabase")
    assert record.load_count == 1
    assert record.request_count == 12


def test_unload_releases_the_service(client):
    client.get("/supabase/rest/v1/projects")
    assert client.post("/hub/services/supabase/unload").json()["state"] == "unloaded"
    assert client.get("/hub/metrics").json()["loaded"] == 0


def test_unload_then_request_loads_again(client):
    client.get("/supabase/rest/v1/projects")
    client.post("/hub/services/supabase/unload")
    assert client.get("/supabase/rest/v1/projects").status_code == 200
    assert client.get("/hub/services/supabase").json()["load_count"] == 2


def test_reload_returns_to_pristine_seeds(client, service_key):
    """Mutate, reload, and the mutation is gone. This is what proves service
    state is instance-scoped -- module-level state would survive."""
    headers = {"apikey": service_key}
    created = client.post(
        "/supabase/rest/v1/projects",
        json={"name": "Scratch", "visibility": "public"},
        headers=headers,
    )
    assert created.status_code == 201

    before = len(client.get("/supabase/rest/v1/projects", headers=headers).json())
    client.post("/hub/services/supabase/reload")
    after = len(client.get("/supabase/rest/v1/projects", headers=headers).json())
    assert after == before - 1 == 5


def test_reset_rewinds_data_without_reloading(client, service_key):
    """The between-tasks call: data back to baseline, no re-import."""
    headers = {"apikey": service_key}
    client.get("/supabase/rest/v1/projects")
    load_count = client.get("/hub/services/supabase").json()["load_count"]

    client.post("/supabase/rest/v1/projects", json={"name": "Scratch"}, headers=headers)
    assert len(client.get("/supabase/rest/v1/projects", headers=headers).json()) == 6

    assert client.post("/hub/services/supabase/reset").json()["reset"] == "baseline"
    assert len(client.get("/supabase/rest/v1/projects", headers=headers).json()) == 5
    assert client.get("/hub/services/supabase").json()["load_count"] == load_count


def test_declared_service_never_loads(client):
    """501 is the honest answer, and it must not leave a half-built record."""
    response = client.get("/keycloak/admin/realms")
    assert response.status_code == 501
    body = response.json()["error"]
    assert body["scope"] == "hub"
    assert body["code"] == "service_not_implemented"
    assert body["service"] == "keycloak"
    assert "SERVICE_AUTHORING" in body["hint"]
    assert client.get("/hub/metrics").json()["loaded"] == 0


def test_eager_services_are_loaded_at_startup(config):
    """The opt-out: a harness can pre-warm what a task will use."""
    from fastapi.testclient import TestClient
    from main import create_app

    eager = dataclasses.replace(config, eager_services=("supabase",))
    with TestClient(create_app(eager)) as client:
        assert client.get("/hub/metrics").json()["loaded"] == 1
        assert client.get("/hub/services/supabase").json()["state"] == "ready"


def test_unknown_eager_service_does_not_stop_boot(config):
    """A typo in HUB_EAGER_SERVICES must not cost the whole hub."""
    from fastapi.testclient import TestClient
    from main import create_app

    eager = dataclasses.replace(config, eager_services=("supabase", "nosuchthing"))
    with TestClient(create_app(eager)) as client:
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/hub/metrics").json()["loaded"] == 1


# --- failure handling ------------------------------------------------------


@pytest.fixture
def broken_registry(tmp_path, config, monkeypatch):
    """A registry whose only service raises during ``on_startup``."""
    import sys

    services = tmp_path / "services"
    (services / "boom").mkdir(parents=True)
    (services / "__init__.py").write_text("", encoding="utf-8")
    (services / "boom" / "__init__.py").write_text("", encoding="utf-8")
    (services / "boom" / "service.toml").write_text(textwrap.dedent("""
        [service]
        slug = "boom"
        name = "Boom"
        category = "backend"
        status = "implemented"
        module = "services.boom.service:BoomService"
        summary = "explodes on startup"
        upstream = "http://example.invalid"

        [routes]
        prefixes = ["/boom"]
    """), encoding="utf-8")
    (services / "boom" / "service.py").write_text(textwrap.dedent("""
        from fastapi import APIRouter
        from hub.base import ServiceModule

        class BoomService(ServiceModule):
            async def on_startup(self):
                raise RuntimeError("seed file is on fire")

            def build_router(self):
                return APIRouter()
    """), encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("services", None)  # shadow the real services package
    registry = ServiceRegistry(
        dataclasses.replace(config, repo_root=tmp_path, services_dir=services)
    )
    registry.discover()
    yield registry
    sys.modules.pop("services.boom.service", None)
    sys.modules.pop("services.boom", None)
    sys.modules.pop("services", None)


def test_startup_failure_parks_the_service(broken_registry):
    with pytest.raises(ServiceLoadError) as excinfo:
        asyncio.run(broken_registry.acquire("boom"))
    assert "seed file is on fire" in excinfo.value.message
    record = broken_registry.get("boom")
    assert record.state is ServiceState.FAILED
    assert record.error_type == "RuntimeError"


def test_failed_service_stays_failed_until_reload(broken_registry):
    """Sticky failure. Retrying per-request would turn one clear error into an
    unbounded stream of them and make run timings nondeterministic."""
    with pytest.raises(ServiceLoadError):
        asyncio.run(broken_registry.acquire("boom"))
    with pytest.raises(ServiceLoadError) as excinfo:
        asyncio.run(broken_registry.acquire("boom"))
    assert "parked" in excinfo.value.message
    assert broken_registry.get("boom").load_count == 0


def test_failed_service_does_not_break_the_hub(broken_registry):
    """One broken service, everything else still reports."""
    with pytest.raises(ServiceLoadError):
        asyncio.run(broken_registry.acquire("boom"))
    health = broken_registry.health()
    assert health["status"] == "degraded"
    assert health["services"]["boom"]["state"] == "failed"


# --- idle eviction ---------------------------------------------------------


def test_idle_reaper_unloads_stale_services(config):
    """Memory is returned without anyone asking. ``ttl=0`` disables it, so the
    reaper is opt-in and a normal run keeps whatever it loaded."""
    registry = ServiceRegistry(dataclasses.replace(config, idle_ttl_seconds=60))
    registry.discover()

    async def scenario():
        await registry.acquire("supabase")
        assert registry.loaded_slugs() == ["supabase"]
        assert await registry.reap_idle() == []           # fresh: not yet idle
        evicted = await registry.reap_idle(now=__import__("time").time() + 120)
        assert evicted == ["supabase"]
        assert registry.loaded_slugs() == []

    asyncio.run(scenario())


def test_eager_services_are_never_reaped(config):
    """Pinning a service is a statement of intent; the reaper must respect it."""
    registry = ServiceRegistry(
        dataclasses.replace(config, idle_ttl_seconds=1, eager_services=("supabase",))
    )
    registry.discover()

    async def scenario():
        await registry.acquire("supabase")
        assert await registry.reap_idle(now=__import__("time").time() + 9999) == []
        assert registry.loaded_slugs() == ["supabase"]

    asyncio.run(scenario())


def test_reaping_is_off_by_default(registry):
    async def scenario():
        await registry.acquire("supabase")
        assert await registry.reap_idle(now=__import__("time").time() + 10**6) == []

    asyncio.run(scenario())
