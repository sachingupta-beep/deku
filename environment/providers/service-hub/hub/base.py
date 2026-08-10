"""The service contract: :class:`ServiceModule` and :class:`ServiceContext`.

Every simulated service is one subclass of :class:`ServiceModule`. The class is
instantiated on first request, asked for an :class:`~fastapi.APIRouter`, and the
resulting app is mounted under ``/<slug>``. Unloading drops the instance; the
seeds reload from disk on the next request.

The single most important rule for a service author
---------------------------------------------------
**Keep all state on the instance. Never at module scope.**

    class KeycloakService(ServiceModule):
        async def on_startup(self):
            self.data = KeycloakData(self.ctx)     # correct: instance state

    _DATA = KeycloakData(...)                      # wrong: survives unload

Module-level state cannot be reclaimed on unload and is shared between two hub
instances in the same process -- which is exactly what the test suite does. A
service whose state lives on the instance can be loaded, unloaded and reloaded
back to pristine seeds; one whose state lives in a module global cannot, and its
reload test will fail. :meth:`ServiceContext.store` hands out a *fresh* store per
load for the same reason.

Lifecycle
---------
=====================  =========================================================
``__init__(ctx)``      cheap; just stash ``ctx``. No I/O.
``on_startup()``       build data layers, read seeds, warm caches. Awaited once.
``build_router()``     return the routes. Called once, after ``on_startup``.
``configure_app(app)`` optional: add middleware/exception handlers to the app.
``health()``           cheap liveness probe; must not raise.
``on_shutdown()``      release anything ``on_startup`` acquired. Awaited once.
=====================  =========================================================

``on_startup`` and ``on_shutdown`` may be sync or async -- the registry inspects
and adapts. ``build_router`` is always sync.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from fastapi import APIRouter, FastAPI

from .config import HubConfig
from .manifest import ServiceDescriptor
from .store import Document, Store, Table, read_seed_with_ctx

Row = Dict[str, Any]


@dataclass
class HealthReport:
    """What ``GET /<slug>/health`` returns, plus what the hub aggregates.

    ``status`` is ``ok`` | ``degraded`` | ``error``. Keep :meth:`ServiceModule.health`
    cheap -- the hub calls it on every ``GET /hub/health``, once per loaded service.
    """

    status: str = "ok"
    detail: str = ""
    checks: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {"status": self.status}
        if self.detail:
            body["detail"] = self.detail
        if self.checks:
            body["checks"] = self.checks
        return body


@dataclass
class ServiceContext:
    """Everything a service is handed at load time.

    A service touches the hub only through this object -- it never imports the
    registry, the router or another service. That is what "logically isolated"
    means here: two services can share a process and still have no way to reach
    each other's rows except over HTTP, the same as if they were containers.
    """

    descriptor: ServiceDescriptor
    config: HubConfig
    data_dir: Path
    store: Store
    logger: logging.Logger

    @property
    def slug(self) -> str:
        return self.descriptor.slug

    # -- seeds -------------------------------------------------------------

    def seed(self, filename: str, table: str) -> List[Row]:
        """Read one seed file from this service's ``data/<dir>/``.

        Dispatches on suffix and honours the fleet's CSV-overlay-wins rule, so a
        bind-mounted ``profiles.csv`` shadows the baked ``profiles.json`` with no
        code change -- that is how a benchmark task ships its own fixtures.
        """
        return read_seed_with_ctx(self.data_dir / filename, self.slug, table)

    def register_table(
        self, name: str, primary_key: str, loader: Callable[[], Iterable[Row]]
    ) -> Table:
        """Register a table on this service's store. The loader runs on first access
        (or at :meth:`eager_load`), never at registration time."""
        return self.store.register(name, primary_key=primary_key, initial_loader=loader)

    def register_document(self, name: str, loader: Callable[[], Any]) -> Document:
        """Register a single JSON blob (settings, balance, config) on the store."""
        return self.store.register_document(name, initial_loader=loader)

    def eager_load(self) -> None:
        """Force every registered table and document to load now.

        Call this at the end of ``on_startup``. A bad seed then fails the *load*
        with a clear CoerceError naming file, row and column, instead of failing
        the agent's first request with something unrelated-looking.
        """
        self.store.eager_load()

    def table(self, name: str) -> Table:
        return self.store.table(name)

    def document(self, name: str) -> Document:
        return self.store.document(name)


class ServiceModule(ABC):
    """Base class for every simulated service."""

    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx

    # -- identity ----------------------------------------------------------

    @property
    def descriptor(self) -> ServiceDescriptor:
        return self.ctx.descriptor

    @property
    def slug(self) -> str:
        return self.ctx.descriptor.slug

    @property
    def log(self) -> logging.Logger:
        return self.ctx.logger

    # -- contract ----------------------------------------------------------

    @abstractmethod
    def build_router(self) -> APIRouter:
        """Return the service's routes.

        Paths are relative to ``/<slug>``: a route declared at ``/rest/v1/{table}``
        is reachable at ``/supabase/rest/v1/{table}``. Do not include the slug --
        the mount adds it, and hardcoding it breaks if the slug is ever changed
        in the manifest.
        """

    def configure_app(self, app: FastAPI) -> None:
        """Optional hook to add middleware or exception handlers to the service's
        own app. Runs after ``/health`` and the router are installed."""

    async def on_startup(self) -> None:
        """Startup hook. Load seeds, build data layers, warm caches."""

    async def on_shutdown(self) -> None:
        """Teardown hook. Release whatever ``on_startup`` acquired."""

    def health(self) -> HealthReport:
        """Default health: report the store's table sizes. Override for more."""
        checks = {name: len(self.ctx.store.table(name)) for name in self.ctx.store.list_tables()}
        return HealthReport(status="ok", checks={"rows": checks})

    # -- app assembly (final) ---------------------------------------------

    def create_app(self) -> FastAPI:
        """Wrap :meth:`build_router` into the service's own FastAPI app.

        Not meant to be overridden. Building the app here rather than in each
        service is what guarantees the invariants the hub advertises: every
        service has a health endpoint at its declared path, its own isolated
        OpenAPI document at ``/<slug>/openapi.json``, and its own docs page --
        without 27 authors each remembering to add them.
        """
        descriptor = self.descriptor
        expose_docs = self.ctx.config.expose_docs
        app = FastAPI(
            title=f"{descriptor.name} (simulated)",
            version=descriptor.version,
            summary=descriptor.summary or None,
            description=(
                f"{descriptor.summary}\n\n"
                f"Simulated {descriptor.name} served by Service Hub under "
                f"`{descriptor.base_path}`. Upstream reference: "
                f"{descriptor.upstream or 'n/a'}."
            ),
            docs_url="/docs" if expose_docs else None,
            redoc_url=None,
            openapi_url="/openapi.json",
        )

        health_path = descriptor.health_path
        module = self

        @app.get(
            health_path,
            tags=["hub"],
            summary=f"{descriptor.name} health",
            operation_id=f"{descriptor.slug}_health",
        )
        def _health() -> Dict[str, Any]:
            try:
                report = module.health()
            except Exception as exc:  # a broken probe must not 500 the health route
                report = HealthReport(status="error", detail=f"{type(exc).__name__}: {exc}")
            return {"service": descriptor.slug, **report.to_dict()}

        app.include_router(self.build_router())
        self.configure_app(app)
        return app
