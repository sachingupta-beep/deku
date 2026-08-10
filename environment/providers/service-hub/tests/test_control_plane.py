"""The ``/hub/*`` control plane and the ``/audit`` trail."""

from __future__ import annotations


def test_root_index_lists_every_service_url(client):
    body = client.get("/").json()
    assert body["hub"] == "service-hub"
    assert len(body["services"]) == 27
    assert body["services"]["supabase"].endswith("/supabase")


def test_container_health_is_constant_time(client):
    """Docker's healthcheck asks "is the process serving?". Answering it by
    probing 27 services would defeat the design, so it must not load anything."""
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["services_discovered"] == 27
    assert body["services_loaded"] == 0


def test_hub_index_names_the_other_endpoints(client):
    body = client.get("/hub").json()
    assert body["endpoints"]["services"] == "/hub/services"
    assert body["lazy_loading"]["enabled"] is True


def test_catalog_groups_by_category(client):
    categories = client.get("/hub/catalog").json()["categories"]
    assert set(categories) == {"backend", "database", "auth", "email", "payments"}
    assert len(categories["backend"]) == 6
    assert len(categories["database"]) == 5
    assert len(categories["auth"]) == 8
    assert len(categories["email"]) == 5
    assert len(categories["payments"]) == 3


def test_services_filter_by_category(client):
    body = client.get("/hub/services", params={"category": "email"}).json()
    assert body["total"] == 5
    assert {s["slug"] for s in body["services"]} == {
        "mailhog", "mailpit", "inbucket", "smtp4dev", "mailcatcher"
    }


def test_services_filter_by_status(client):
    assert client.get("/hub/services", params={"status": "implemented"}).json()["total"] == 1
    assert client.get("/hub/services", params={"status": "declared"}).json()["total"] == 26


def test_services_filter_by_loaded(client):
    assert client.get("/hub/services", params={"loaded": True}).json()["total"] == 0
    client.get("/supabase/rest/v1/projects")
    body = client.get("/hub/services", params={"loaded": True}).json()
    assert [s["slug"] for s in body["services"]] == ["supabase"]


def test_service_view_gains_routes_once_loaded(client):
    before = client.get("/hub/services/supabase").json()
    assert "routes" not in before

    client.get("/supabase/rest/v1/projects")
    after = client.get("/hub/services/supabase").json()
    paths = {r["path"] for r in after["routes"]}
    assert "/supabase/rest/v1/{table}" in paths
    assert "/supabase/health" in paths
    assert "profiles" in after["tables"]
    assert "settings" in after["documents"]


def test_unknown_service_view_is_a_hub_error(client):
    response = client.get("/hub/services/nope")
    assert response.status_code == 404
    assert response.json()["error"]["scope"] == "hub"


def test_service_openapi_endpoint_loads_on_demand(client):
    """The one deliberately non-idempotent read: you cannot describe a surface
    you have not built."""
    assert client.get("/hub/metrics").json()["loaded"] == 0
    schema = client.get("/hub/services/supabase/openapi.json").json()
    assert "/rest/v1/{table}" in schema["paths"]
    assert client.get("/hub/metrics").json()["loaded"] == 1


def test_load_is_idempotent(client):
    first = client.post("/hub/services/supabase/load").json()
    second = client.post("/hub/services/supabase/load").json()
    assert first["state"] == second["state"] == "ready"
    assert second["load_count"] == 1


def test_unload_is_idempotent(client):
    client.post("/hub/services/supabase/load")
    assert client.post("/hub/services/supabase/unload").json()["state"] == "unloaded"
    assert client.post("/hub/services/supabase/unload").json()["state"] == "unloaded"


def test_reset_all_only_touches_loaded_services(client):
    client.post("/hub/services/supabase/load")
    body = client.post("/hub/reset").json()
    assert body["reset"] == 1
    assert body["results"][0]["service"] == "supabase"
    assert len(body["skipped"]) == 26


def test_hub_health_probes_only_loaded_services(client):
    body = client.get("/hub/health").json()
    assert body["status"] == "ok"
    assert body["services"]["supabase"] == {"state": "discovered"}

    client.get("/supabase/rest/v1/projects")
    body = client.get("/hub/health").json()
    assert body["services"]["supabase"]["status"] == "ok"
    assert body["services"]["supabase"]["checks"]["rows"]["projects"] == 5


def test_metrics_report_load_timings(client):
    client.get("/supabase/rest/v1/projects")
    body = client.get("/hub/metrics").json()
    assert body["loaded"] == 1
    assert body["load_ms_max"] > 0
    assert body["services"]["supabase"]["request_count"] == 1
    assert body["services"]["keycloak"]["load_ms"] is None


def test_problems_is_empty_for_a_clean_catalog(client):
    assert client.get("/hub/problems").json() == {"count": 0, "problems": []}


def test_reap_endpoint_runs_the_reaper_on_demand(client):
    """With ttl=0 the reaper is off, so an explicit call evicts nothing -- the
    endpoint exists to force a sweep, not to override the policy."""
    client.post("/hub/services/supabase/load")
    assert client.post("/hub/reap").json() == {"evicted": [], "count": 0}


# --- audit -----------------------------------------------------------------


def test_audit_records_service_calls_with_the_service_name(client):
    client.get("/supabase/rest/v1/projects")
    entries = client.get("/audit/requests").json()["requests"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["service"] == "supabase"
    assert entry["method"] == "GET"
    assert entry["path"] == "/supabase/rest/v1/projects"
    assert entry["status_code"] == 200
    assert entry["duration_ms"] >= 0


def test_audit_captures_request_and_response_bodies(client, service_key):
    client.post("/supabase/rest/v1/projects", json={"name": "Audited"},
                headers={"apikey": service_key})
    entry = client.get("/audit/requests").json()["requests"][0]
    assert "Audited" in entry["request_body"]
    assert "Audited" in entry["response_body"]


def test_audit_ignores_control_plane_and_health_traffic(client):
    """The trail should hold the agent's work, not the harness's bookkeeping."""
    client.get("/hub/services")
    client.get("/hub/health")
    client.get("/health")
    client.get("/supabase/health")
    client.post("/hub/services/supabase/load")
    assert client.get("/audit/requests").json()["total"] == 0


def test_audit_filters_by_service(client):
    client.get("/supabase/rest/v1/projects")
    client.get("/keycloak/admin/realms")  # 501, but still the agent's traffic
    assert client.get("/audit/requests", params={"service": "supabase"}).json()["total"] == 1
    assert client.get("/audit/requests", params={"service": "keycloak"}).json()["total"] == 1


def test_audit_summary_counts_by_service_and_endpoint(client):
    client.get("/supabase/rest/v1/projects")
    client.get("/supabase/rest/v1/projects")
    client.get("/supabase/rest/v1/nope")
    summary = client.get("/audit/summary").json()
    assert summary["total_requests"] == 3
    assert summary["by_service"] == {"supabase": 3}
    assert summary["endpoints"]["GET /supabase/rest/v1/projects"]["statuses"] == {"200": 2}
    assert summary["endpoints"]["GET /supabase/rest/v1/nope"]["statuses"] == {"404": 1}


def test_audit_can_be_cleared(client):
    client.get("/supabase/rest/v1/projects")
    assert client.get("/audit/requests/clear").json()["cleared"] == 1
    assert client.get("/audit/requests").json()["total"] == 0


def test_audit_pagination_and_body_suppression(client):
    for _ in range(3):
        client.get("/supabase/rest/v1/projects")
    body = client.get("/audit/requests",
                      params={"limit": 2, "offset": 1, "include_body": False}).json()
    assert body["total"] == 3
    assert body["returned"] == 2
    assert "response_body" not in body["requests"][0]
