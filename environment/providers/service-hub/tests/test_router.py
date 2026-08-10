"""Dynamic routing: prefix dispatch, path rewriting, precedence and isolation."""

from __future__ import annotations

from starlette.routing import Mount

from router import LazyServiceMount, service_index


def test_one_lazy_mount_per_service(app):
    mounts = [r for r in app.router.routes if isinstance(r, Mount)]
    assert len(mounts) == 27
    assert all(isinstance(m.app, LazyServiceMount) for m in mounts)
    assert {m.path for m in mounts} == {
        f"/{d.slug}" for d in app.state.registry.descriptors()
    }


def test_hub_routes_are_registered_before_the_mounts(app):
    """Precedence is registration order. If a mount ever ended up in front of the
    control plane, a service could shadow it.

    Asserted positionally rather than by path, because ``include_router`` puts
    the ``/hub`` routes behind a single wrapper object on newer FastAPI versions
    and there is no path attribute to look up.
    """
    routes = app.router.routes
    catch_all = len(routes) - 1
    mounts = [i for i, r in enumerate(routes) if isinstance(r, Mount)]
    hub_level = [i for i, r in enumerate(routes) if not isinstance(r, Mount) and i != catch_all]
    assert mounts, "no service mounts registered"
    assert max(hub_level) < min(mounts)


def test_catch_all_is_registered_last(app):
    """It must only see what nothing else matched."""
    last = app.router.routes[-1]
    assert getattr(last, "path", "") == "/{service}/{path:path}"


def test_control_plane_is_reachable_and_unshadowed(client):
    """The behavioural half of the precedence test."""
    assert client.get("/hub/services").status_code == 200
    assert client.get("/health").json()["hub"] == "service-hub"
    assert client.get("/audit/summary").status_code == 200


def test_mount_strips_the_prefix(client):
    """``/supabase/rest/v1/`` must reach the service's ``/rest/v1/`` route.

    If the mount stopped rewriting ``scope["path"]`` this 404s, because the
    service's own router knows nothing about its slug.
    """
    response = client.get("/supabase/rest/v1/")
    assert response.status_code == 200
    assert response.json()["basePath"] == "/rest/v1"


def test_deep_paths_with_path_params_survive_the_mount(client, service_key):
    response = client.get(
        "/supabase/storage/v1/object/info/avatars/public/amelia.png",
        headers={"apikey": service_key},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "public/amelia.png"


def test_every_service_exposes_health_at_its_declared_path(client):
    """The one endpoint the hub guarantees on behalf of every service, because
    the base class installs it rather than trusting 27 authors to remember."""
    response = client.get("/supabase/health")
    assert response.status_code == 200
    assert response.json()["service"] == "supabase"
    assert response.json()["status"] == "ok"


def test_service_openapi_is_isolated(client):
    """A service's schema describes that service and nothing else -- no hub
    routes leaking in, no sibling services."""
    schema = client.get("/supabase/openapi.json").json()
    paths = set(schema["paths"])
    assert "/rest/v1/{table}" in paths
    assert "/health" in paths
    assert not any(p.startswith("/hub") for p in paths)
    assert not any("keycloak" in p for p in paths)
    assert schema["info"]["title"] == "Supabase (self-host) (simulated)"


def test_hub_openapi_does_not_contain_service_routes(client):
    """The converse: mounted sub-apps are opaque to the parent schema, which is
    why discovery goes through /hub/services instead of one giant document."""
    paths = set(client.get("/openapi.json").json()["paths"])
    assert "/hub/services" in paths
    assert not any(p.startswith("/supabase/rest") for p in paths)


def test_unknown_service_gets_a_suggestion(client):
    response = client.get("/keyclock/admin/realms")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["scope"] == "hub"
    assert error["code"] == "service_not_found"
    assert "keycloak" in error["hint"]
    assert error["requested_path"] == "/keyclock/admin/realms"


def test_unknown_service_without_a_near_match_lists_the_catalog(client):
    error = client.get("/zzzzzz/x").json()["error"]
    assert "GET /hub/services" in error["hint"]
    assert len(error["available"]) == 27


def test_unknown_path_inside_a_known_service_is_the_services_own_404(client):
    """Not the hub's 404 -- the service owns its own error shape, and confusing
    the two would let an agent mistake a bad path for a missing service."""
    response = client.get("/supabase/no/such/route")
    assert response.status_code == 404
    assert "error" not in response.json() or response.json().get("detail") == "Not Found"


def test_all_http_methods_route_through_the_mount(client, service_key):
    headers = {"apikey": service_key}
    assert client.get("/supabase/rest/v1/profiles", headers=headers).status_code == 200
    assert client.post("/supabase/rest/v1/profiles", json={"username": "x"},
                       headers=headers).status_code == 201
    assert client.patch("/supabase/rest/v1/profiles?username=eq.x", json={"plan": "pro"},
                        headers=headers).status_code == 200
    assert client.delete("/supabase/rest/v1/profiles?username=eq.x",
                         headers=headers).status_code == 200


def test_service_index_maps_slugs_to_urls(registry):
    index = service_index(registry, base_url="http://hub:8080/")
    assert index["supabase"] == "http://hub:8080/supabase"
    assert index["ory-kratos"] == "http://hub:8080/ory-kratos"
    assert len(index) == 27
