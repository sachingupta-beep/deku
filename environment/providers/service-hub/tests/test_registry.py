"""Discovery and manifest validation."""

from __future__ import annotations

import dataclasses
import textwrap

import pytest

from hub.errors import ManifestError, ServiceNotFound
from hub.manifest import CATEGORIES, RESERVED_SLUGS, discover_manifests, load_manifest
from service_registry import ServiceRegistry, ServiceState

EXPECTED_SLUGS = {
    # backend / BaaS
    "supabase", "pocketbase", "appwrite", "directus", "nhost", "postgres-backend",
    # relational databases
    "sqlite", "postgresql", "mysql", "mariadb", "cockroachdb",
    # authentication
    "supabase-auth", "pocketbase-auth", "supertokens", "logto", "keycloak",
    "zitadel", "ory-kratos", "dex",
    # email
    "mailhog", "mailpit", "inbucket", "smtp4dev", "mailcatcher",
    # payments
    "inhouse-payments", "lago", "killbill",
}


def test_discovers_the_whole_catalog(registry):
    assert {d.slug for d in registry.descriptors()} == EXPECTED_SLUGS


def test_discovery_reports_no_problems(registry):
    assert registry.problems == []


def test_every_category_is_populated(registry):
    found = {d.category for d in registry.descriptors()}
    assert found == set(CATEGORIES)


def test_nothing_is_loaded_by_discovery(registry):
    """Discovery reads manifests only. If this fails, laziness is broken."""
    assert registry.loaded_slugs() == []
    assert all(
        record.state in (ServiceState.DISCOVERED, ServiceState.DECLARED)
        for record in registry.records()
    )


def test_implemented_services_are_marked_discovered(registry):
    assert registry.get("supabase").state is ServiceState.DISCOVERED
    assert registry.get("keycloak").state is ServiceState.DECLARED


def test_unknown_slug_raises_with_the_available_list(registry):
    with pytest.raises(ServiceNotFound) as excinfo:
        registry.get("nope")
    assert "nope" in excinfo.value.message
    assert "supabase" in excinfo.value.extra["available"]


def test_descriptor_public_shape_is_the_discovery_contract(registry):
    view = registry.get("supabase").descriptor.to_public()
    assert view["base_path"] == "/supabase"
    assert view["health_path"] == "/supabase/health"
    assert view["openapi_path"] == "/supabase/openapi.json"
    assert view["auth"]["scheme"] == "apikey"
    assert "service_role" in view["auth"]["roles"]
    assert "/supabase/rest/v1" in view["route_prefixes"]


def test_every_manifest_declares_auth_and_routes(registry):
    """A catalog entry with no advertised surface is useless for discovery --
    an agent would have to load the service just to learn it exists."""
    for descriptor in registry.descriptors():
        assert descriptor.summary, f"{descriptor.slug} has no summary"
        assert descriptor.route_prefixes, f"{descriptor.slug} advertises no routes"
        assert descriptor.auth_scheme, f"{descriptor.slug} declares no auth scheme"
        assert descriptor.upstream.startswith("http"), f"{descriptor.slug} has no upstream"


# --- validation ------------------------------------------------------------


def _write_manifest(tmp_path, body: str, name: str = "thing"):
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "service.toml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_reserved_slug_is_rejected(tmp_path):
    """A service called 'hub' would eat the control plane. Caught at parse time."""
    path = _write_manifest(tmp_path, """
        [service]
        slug = "hub"
        name = "Impostor"
        category = "backend"
    """)
    with pytest.raises(ManifestError) as excinfo:
        load_manifest(path)
    assert "reserved" in excinfo.value.message
    assert "hub" in RESERVED_SLUGS


def test_bad_category_is_rejected(tmp_path):
    path = _write_manifest(tmp_path, """
        [service]
        slug = "thing"
        name = "Thing"
        category = "nosuch"
    """)
    with pytest.raises(ManifestError, match="category"):
        load_manifest(path)


def test_slug_must_be_kebab_case(tmp_path):
    path = _write_manifest(tmp_path, """
        [service]
        slug = "Not_A_Slug"
        name = "Thing"
        category = "backend"
    """)
    with pytest.raises(ManifestError, match="kebab-case"):
        load_manifest(path)


def test_implemented_service_must_name_a_class(tmp_path):
    path = _write_manifest(tmp_path, """
        [service]
        slug = "thing"
        name = "Thing"
        category = "backend"
        status = "implemented"
        module = "services.thing.service"
    """)
    with pytest.raises(ManifestError, match="package.module:ClassName"):
        load_manifest(path)


def test_duplicate_slugs_are_a_hard_error(tmp_path):
    """Two services on one path is never the intent, so this raises even in the
    lenient discovery mode that skips other malformed manifests."""
    for name in ("alpha", "beta"):
        _write_manifest(tmp_path, """
            [service]
            slug = "same"
            name = "Same"
            category = "backend"
        """, name=name)
    with pytest.raises(ManifestError, match="duplicate slug"):
        discover_manifests(tmp_path, strict=False)


def test_malformed_manifest_is_skipped_not_fatal(tmp_path):
    """One bad file must not cost the other services. This is the production
    behaviour; the test suite runs with strict=True to catch it instead."""
    _write_manifest(tmp_path, """
        [service]
        slug = "good"
        name = "Good"
        category = "backend"
    """, name="good")
    _write_manifest(tmp_path, 'this is not toml [[[', name="bad")

    descriptors, problems = discover_manifests(tmp_path, strict=False)
    assert [d.slug for d in descriptors] == ["good"]
    assert len(problems) == 1
    assert "bad" in problems[0]["manifest"]

    with pytest.raises(ManifestError):
        discover_manifests(tmp_path, strict=True)


def test_registry_survives_a_bad_manifest(tmp_path, config):
    """End-to-end version of the above: the registry still boots."""
    _write_manifest(tmp_path, """
        [service]
        slug = "good"
        name = "Good"
        category = "email"
        summary = "fine"
    """, name="good")
    _write_manifest(tmp_path, "[service]\nslug = 'x'\n", name="bad")

    lenient = ServiceRegistry(
        dataclasses.replace(config, services_dir=tmp_path, strict_discovery=False)
    )
    assert lenient.discover() == 1
    assert len(lenient.problems) == 1
