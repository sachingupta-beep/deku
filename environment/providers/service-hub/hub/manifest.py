"""``service.toml`` -> :class:`ServiceDescriptor`.

The manifest is the *only* thing the hub reads at startup. It is deliberately
cheap: pure TOML, no imports, no seed files touched. 27 manifests parse in a
couple of milliseconds, which is what makes "discover everything, load nothing"
possible.

A manifest carries three kinds of information:

1. **Identity** -- slug, display name, category, which upstream product is being
   simulated. Drives ``GET /hub/services`` so an agent can discover the fleet
   without loading any of it.
2. **Wiring** -- the dotted path to the :class:`~hub.base.ServiceModule`
   subclass, and which directory under ``data/`` holds its seeds.
3. **Advertised surface** -- route prefixes, auth scheme, health path. This is
   documentation the hub can serve before the module is loaded; it is not
   enforced against the real router, because the router is the source of truth
   once loaded (``GET /hub/services/<slug>`` reports live routes then).

Example::

    [service]
    slug     = "supabase"
    name     = "Supabase (self-host)"
    category = "backend"
    status   = "implemented"
    module   = "services.supabase.service:SupabaseService"
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import ManifestError

MANIFEST_FILENAME = "service.toml"

SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")

RESERVED_SLUGS = frozenset(
    {"hub", "audit", "health", "docs", "redoc", "openapi.json", "static", "favicon.ico"}
)
"""Slugs that would shadow a hub-level route. Rejected at discovery time rather
than producing a service nobody can reach."""

CATEGORIES = ("backend", "database", "auth", "email", "payments")

STATUSES = ("implemented", "declared")
"""``declared`` means the catalog entry exists but no module backs it yet, so
the router answers 501 with a pointer at the authoring guide. It is an honest
placeholder, not a stub that returns fake success."""


@dataclass(frozen=True)
class ServiceDescriptor:
    """Everything the hub knows about a service before loading it."""

    slug: str
    name: str
    category: str
    summary: str
    status: str
    module: str
    manifest_path: Path
    package_dir: Path

    upstream: str = ""
    version: str = "v1"
    tags: Tuple[str, ...] = ()

    data_dir_name: str = ""
    seeds: Tuple[str, ...] = ()

    auth_scheme: str = "none"
    auth_roles: Tuple[str, ...] = ()
    auth_description: str = ""

    health_path: str = "/health"
    route_prefixes: Tuple[str, ...] = ()

    @property
    def base_path(self) -> str:
        return f"/{self.slug}"

    @property
    def implemented(self) -> bool:
        return self.status == "implemented"

    @property
    def store_name(self) -> str:
        """Name this service's :class:`~hub.store.Store` is registered under."""
        return self.slug

    def to_public(self) -> Dict[str, Any]:
        """The shape ``GET /hub/services`` returns. Discovery contract -- keep stable."""
        return {
            "slug": self.slug,
            "name": self.name,
            "category": self.category,
            "summary": self.summary,
            "status": self.status,
            "version": self.version,
            "upstream": self.upstream,
            "tags": list(self.tags),
            "base_path": self.base_path,
            "health_path": f"{self.base_path}{self.health_path}",
            "openapi_path": f"{self.base_path}/openapi.json",
            "docs_path": f"{self.base_path}/docs",
            "route_prefixes": [f"{self.base_path}{p}" for p in self.route_prefixes],
            "auth": {
                "scheme": self.auth_scheme,
                "roles": list(self.auth_roles),
                "description": self.auth_description,
            },
        }


def _require(table: Dict[str, Any], key: str, path: Path) -> Any:
    if key not in table or table[key] in (None, ""):
        raise ManifestError(f"[service].{key} is required", hint=f"in {path}")
    return table[key]


def _tuple(value: Any) -> Tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def load_manifest(path: Path) -> ServiceDescriptor:
    """Parse and validate one ``service.toml``. Raises :class:`ManifestError`."""
    try:
        with open(path, "rb") as handle:
            raw = tomllib.load(handle)
    except OSError as exc:
        raise ManifestError(f"cannot read manifest: {exc}", hint=str(path))
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"malformed TOML: {exc}", hint=str(path))

    service = raw.get("service")
    if not isinstance(service, dict):
        raise ManifestError("missing [service] table", hint=str(path))

    slug = str(_require(service, "slug", path))
    if not SLUG_RE.match(slug):
        raise ManifestError(
            f"slug {slug!r} must be lowercase kebab-case (a-z, 0-9, '-')", hint=str(path)
        )
    if slug in RESERVED_SLUGS:
        raise ManifestError(
            f"slug {slug!r} is reserved by the hub control plane",
            service=slug,
            hint=f"pick another slug in {path}",
        )

    category = str(_require(service, "category", path))
    if category not in CATEGORIES:
        raise ManifestError(
            f"category {category!r} must be one of {', '.join(CATEGORIES)}",
            service=slug,
            hint=str(path),
        )

    status = str(service.get("status", "declared"))
    if status not in STATUSES:
        raise ManifestError(
            f"status {status!r} must be one of {', '.join(STATUSES)}",
            service=slug,
            hint=str(path),
        )

    module = str(service.get("module", "") or "")
    if status == "implemented":
        if ":" not in module:
            raise ManifestError(
                "[service].module must be 'package.module:ClassName' for an "
                "implemented service",
                service=slug,
                hint=str(path),
            )

    data = raw.get("data", {}) or {}
    auth = raw.get("auth", {}) or {}
    health = raw.get("health", {}) or {}
    routes = raw.get("routes", {}) or {}

    health_path = str(health.get("path", "/health"))
    if not health_path.startswith("/"):
        raise ManifestError(
            f"[health].path {health_path!r} must start with '/'", service=slug, hint=str(path)
        )

    return ServiceDescriptor(
        slug=slug,
        name=str(_require(service, "name", path)),
        category=category,
        summary=str(service.get("summary", "")),
        status=status,
        module=module,
        manifest_path=path,
        package_dir=path.parent,
        upstream=str(service.get("upstream", "")),
        version=str(service.get("version", "v1")),
        tags=_tuple(service.get("tags")),
        data_dir_name=str(data.get("dir", slug)),
        seeds=_tuple(data.get("seeds")),
        auth_scheme=str(auth.get("scheme", "none")),
        auth_roles=_tuple(auth.get("roles")),
        auth_description=str(auth.get("description", "")),
        health_path=health_path,
        route_prefixes=_tuple(routes.get("prefixes")),
    )


def discover_manifests(
    services_dir: Path, *, strict: bool = False
) -> Tuple[List[ServiceDescriptor], List[Dict[str, str]]]:
    """Scan ``services_dir`` for ``*/service.toml``.

    Returns ``(descriptors, problems)`` sorted by slug. A malformed manifest is
    collected into ``problems`` and skipped so one bad file cannot stop the hub
    from serving the other 26 services -- unless ``strict``, which re-raises.
    Duplicate slugs are a hard error either way: two services answering on the
    same path is never the intent.
    """
    descriptors: List[ServiceDescriptor] = []
    problems: List[Dict[str, str]] = []
    seen: Dict[str, Path] = {}

    if not services_dir.is_dir():
        raise ManifestError(f"services directory not found: {services_dir}")

    for manifest_path in sorted(services_dir.glob(f"*/{MANIFEST_FILENAME}")):
        try:
            descriptor = load_manifest(manifest_path)
        except ManifestError as exc:
            if strict:
                raise
            problems.append({"manifest": str(manifest_path), "error": exc.message})
            continue
        if descriptor.slug in seen:
            raise ManifestError(
                f"duplicate slug {descriptor.slug!r}",
                service=descriptor.slug,
                hint=f"already declared by {seen[descriptor.slug]}",
            )
        seen[descriptor.slug] = manifest_path
        descriptors.append(descriptor)

    descriptors.sort(key=lambda d: d.slug)
    return descriptors, problems
