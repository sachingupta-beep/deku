"""Service Hub -- one container, many simulated services.

    uvicorn main:app --host 0.0.0.0 --port 8080

Boot sequence
-------------
1. Parse ``HUB_*`` environment into a :class:`~hub.config.HubConfig`.
2. Discover ``services/*/service.toml``. Manifests only -- no imports, no seeds.
3. Build the app: audit middleware, ``/hub`` control plane, ``/audit`` endpoints,
   then one lazy :class:`~router.LazyServiceMount` per discovered service.
4. On lifespan startup, load only what ``HUB_EAGER_SERVICES`` names (nothing, by
   default) and start the idle reaper if ``HUB_IDLE_TTL`` is set.

A cold hub therefore holds 27 manifests and 27 mount objects: a few hundred
kilobytes. The first ``GET /supabase/rest/v1/projects`` is what pays for
Supabase, and nothing at all pays for the other 26.

Route precedence, in registration order (first match wins):

    /health, /            hub liveness + index
    /audit/*              request log
    /hub/*                control plane
    /docs, /openapi.json  the hub's own schema
    /<slug>/*             lazy service mounts
    /{service}/{path}     "no such service" catch-all, with a suggestion
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request

from hub import __version__
from hub.audit import AuditLog, AuditMiddleware, install_audit
from hub.config import HubConfig
from hub.control import install_control_plane
from router import install_service_routes, install_unknown_service_handler
from service_registry import ServiceRegistry

logger = logging.getLogger("hub")

DESCRIPTION = """
A single container hosting simulated **Supabase, PocketBase, Appwrite, Directus,
Nhost, PostgreSQL, MySQL, MariaDB, SQLite, CockroachDB, Keycloak, Zitadel, Logto,
SuperTokens, Ory Kratos, Dex, MailHog, Mailpit, Inbucket, smtp4dev, MailCatcher,
Lago, Kill Bill** and more -- each behind its own path prefix, each loaded on
first use.

**Start at `/hub`.** `GET /hub/services` lists everything discovered; a service
loads the first time you call it.
"""


def configure_logging() -> None:
    """Single-line logs on stdout -- what `docker logs` and a harness both want."""
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=os.environ.get("HUB_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def _idle_reaper(registry: ServiceRegistry, interval: int) -> None:
    """Background eviction loop. Cancelled on shutdown."""
    while True:
        await asyncio.sleep(interval)
        try:
            await registry.reap_idle()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 -- the reaper must outlive one bad unload
            logger.exception("idle reaper iteration failed")


def create_app(config: Optional[HubConfig] = None) -> FastAPI:
    """Build a hub app. The factory (not a module-level singleton) is what lets
    the test suite stand up several independent hubs in one process."""
    configure_logging()
    config = config or HubConfig.from_env()

    registry = ServiceRegistry(config)
    registry.discover()
    audit_log = AuditLog(max_entries=config.audit_max_entries)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        eager = await registry.load_eager()
        if eager:
            logger.info("eager-loaded: %s", ", ".join(eager))
        reaper: Optional[asyncio.Task] = None
        if config.idle_ttl_seconds > 0:
            reaper = asyncio.create_task(
                _idle_reaper(registry, config.reaper_interval_seconds)
            )
            logger.info(
                "idle reaper on: evicting after %ds idle, checked every %ds",
                config.idle_ttl_seconds,
                config.reaper_interval_seconds,
            )
        try:
            yield
        finally:
            if reaper is not None:
                reaper.cancel()
                try:
                    await reaper
                except asyncio.CancelledError:
                    pass
            await registry.shutdown_all()

    app = FastAPI(
        title="Service Hub",
        version=__version__,
        summary="One container, many simulated services, loaded on demand.",
        description=DESCRIPTION,
        docs_url="/docs" if config.expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.expose_docs else None,
        lifespan=lifespan,
    )
    app.state.registry = registry
    app.state.config = config
    app.state.audit = audit_log

    if config.audit_enabled:
        app.add_middleware(
            AuditMiddleware,
            log=audit_log,
            slugs=frozenset(d.slug for d in registry.descriptors()),
            max_body_bytes=config.audit_max_body_bytes,
        )

    # --- hub-level routes, registered before the mounts so nothing shadows them

    @app.get("/health", tags=["hub"], summary="Container liveness")
    async def health() -> Dict[str, Any]:
        """Cheap and constant-time. Deliberately does **not** probe the services:
        Docker's healthcheck asks "is the process serving?", and answering it by
        loading 27 services would defeat the whole design."""
        return {
            "status": "ok",
            "hub": "service-hub",
            "version": __version__,
            "services_discovered": len(registry.records()),
            "services_loaded": len(registry.loaded_slugs()),
        }

    @app.get("/", tags=["hub"], summary="Index")
    async def index(request: Request) -> Dict[str, Any]:
        base = str(request.base_url).rstrip("/")
        return {
            "hub": "service-hub",
            "version": __version__,
            "docs": f"{base}/docs",
            "discover": f"{base}/hub/services",
            "catalog": f"{base}/hub/catalog",
            "health": f"{base}/health",
            "services": {
                d.slug: f"{base}{d.base_path}" for d in registry.descriptors()
            },
        }

    install_audit(app, audit_log)
    install_control_plane(app, __version__)
    install_service_routes(app, registry)
    install_unknown_service_handler(app, registry)
    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual runs only
    import uvicorn

    settings = HubConfig.from_env()
    uvicorn.run("main:app", host=settings.host, port=settings.port, log_level="info")
