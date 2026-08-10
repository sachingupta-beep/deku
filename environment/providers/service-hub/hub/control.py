"""The ``/hub/*`` control plane.

Two audiences, one API:

* **The agent under evaluation** reads ``/hub/services`` and ``/hub/catalog`` to
  discover what exists, and ``/hub/services/<slug>/openapi.json`` to learn one
  service's surface. It never needs to be told in its prompt which services are
  up -- discovery is a call, and the answer is generated from the manifests.
* **The harness** drives the lifecycle: pre-warm before a task, ``reset``
  between tasks, ``metrics`` after a run.

Everything here is namespaced under ``/hub`` and excluded from the audit log, so
harness traffic never pollutes the trace a grader reads.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request

from .errors import HubError
from .manifest import CATEGORIES

router = APIRouter(prefix="/hub", tags=["hub"])


def _registry(request: Request):
    return request.app.state.registry


@router.get("", summary="Hub index")
@router.get("/", include_in_schema=False)
async def hub_index(request: Request) -> Dict[str, Any]:
    """Entry point. Start here: it names every other endpoint worth calling."""
    registry = _registry(request)
    config = request.app.state.config
    return {
        "hub": "service-hub",
        "version": request.app.state.hub_version,
        "uptime_seconds": round(time.time() - registry.started_at, 3),
        "services": {
            "discovered": len(registry.records()),
            "loaded": len(registry.loaded_slugs()),
            "loaded_slugs": registry.loaded_slugs(),
        },
        "lazy_loading": {
            "enabled": True,
            "eager_services": list(config.eager_services),
            "idle_ttl_seconds": config.idle_ttl_seconds or None,
        },
        "endpoints": {
            "catalog": "/hub/catalog",
            "services": "/hub/services",
            "service": "/hub/services/{slug}",
            "service_openapi": "/hub/services/{slug}/openapi.json",
            "load": "POST /hub/services/{slug}/load",
            "unload": "POST /hub/services/{slug}/unload",
            "reload": "POST /hub/services/{slug}/reload",
            "reset": "POST /hub/services/{slug}/reset",
            "reset_all": "POST /hub/reset",
            "health": "/hub/health",
            "metrics": "/hub/metrics",
            "audit": "/audit/requests",
        },
    }


@router.get("/catalog", summary="Services grouped by category")
async def catalog(request: Request) -> Dict[str, Any]:
    """The whole fleet in one response, grouped the way the categories read."""
    return _registry(request).catalog()


@router.get("/services", summary="List services")
async def list_services(
    request: Request,
    category: Optional[str] = Query(None, description=f"one of: {', '.join(CATEGORIES)}"),
    status: Optional[str] = Query(None, description="implemented | declared"),
    state: Optional[str] = Query(None, description="ready | discovered | declared | failed | unloaded"),
    loaded: Optional[bool] = Query(None, description="filter to currently-loaded services"),
) -> Dict[str, Any]:
    """Every discovered service with its descriptor and live state.

    This is the discovery call. It answers without importing anything, so asking
    what exists never has the side effect of loading it.
    """
    registry = _registry(request)
    services: List[Dict[str, Any]] = []
    for record in sorted(registry.records(), key=lambda r: r.slug):
        if category and record.descriptor.category != category:
            continue
        if status and record.descriptor.status != status:
            continue
        if state and record.state.value != state:
            continue
        if loaded is not None and record.ready is not loaded:
            continue
        entry = record.descriptor.to_public()
        entry.update(record.status())
        services.append(entry)
    return {"total": len(services), "services": services}


@router.get("/services/{slug}", summary="Describe one service")
async def get_service(request: Request, slug: str) -> Dict[str, Any]:
    """Descriptor plus lifecycle state. Once loaded, also its live route table."""
    return _registry(request).service_view(slug)


@router.get("/services/{slug}/openapi.json", summary="One service's OpenAPI schema")
async def service_openapi(request: Request, slug: str) -> Dict[str, Any]:
    """Return the service's schema, **loading it if needed**.

    The one endpoint here that is deliberately not side-effect-free: you cannot
    describe a surface you have not built. An agent that only wants to know
    whether a service exists should call ``/hub/services/{slug}`` instead.
    """
    registry = _registry(request)
    record = await registry.acquire(slug)
    return record.app.openapi()


@router.post("/services/{slug}/load", summary="Load a service now")
async def load_service(request: Request, slug: str) -> Dict[str, Any]:
    """Pre-warm. Idempotent -- loading a loaded service just reports it."""
    registry = _registry(request)
    record = await registry.acquire(slug)
    return {"service": slug, "state": record.state.value, "load_ms": record.load_ms,
            "load_count": record.load_count}


@router.post("/services/{slug}/unload", summary="Unload a service")
async def unload_service(request: Request, slug: str) -> Dict[str, Any]:
    """Run the teardown hook and free the service's rows. Idempotent."""
    record = await _registry(request).unload(slug)
    return {"service": slug, "state": record.state.value}


@router.post("/services/{slug}/reload", summary="Reload a service from seeds")
async def reload_service(
    request: Request,
    slug: str,
    reimport: bool = Query(False, description="also drop the Python module, picking up code edits"),
) -> Dict[str, Any]:
    """Unload then load again. The way to clear a ``failed`` state."""
    record = await _registry(request).reload(slug, reimport=reimport)
    return {"service": slug, "state": record.state.value, "load_ms": record.load_ms,
            "load_count": record.load_count}


@router.post("/services/{slug}/reset", summary="Reset one service's data")
async def reset_service(request: Request, slug: str) -> Dict[str, Any]:
    """Rewind the data to its post-seed baseline without re-importing.

    The between-tasks call. Milliseconds, where a reload pays for the import and
    the seed parse again.
    """
    return await _registry(request).reset(slug)


@router.post("/reset", summary="Reset every loaded service")
async def reset_all(request: Request) -> Dict[str, Any]:
    """Reset all loaded services. Unloaded ones are already pristine, so they
    are reported as skipped rather than being loaded just to be reset."""
    registry = _registry(request)
    results = [await registry.reset(slug) for slug in registry.loaded_slugs()]
    return {"reset": len(results), "results": results,
            "skipped": [s for s in sorted(r.slug for r in registry.records())
                        if s not in registry.loaded_slugs()]}


@router.post("/reap", summary="Unload idle services now")
async def reap(request: Request) -> Dict[str, Any]:
    """Run the idle reaper immediately instead of waiting for its interval."""
    evicted = await _registry(request).reap_idle()
    return {"evicted": evicted, "count": len(evicted)}


@router.get("/health", summary="Hub and per-service health")
async def health(request: Request) -> Dict[str, Any]:
    """Aggregate health. Probes only loaded services -- an unloaded service is
    not unhealthy, it just has not been asked for yet."""
    return _registry(request).health()


@router.get("/metrics", summary="Load timings and request counts")
async def metrics(request: Request) -> Dict[str, Any]:
    return _registry(request).metrics()


@router.get("/problems", summary="Manifests that failed to parse")
async def problems(request: Request) -> Dict[str, Any]:
    """Non-empty means a ``service.toml`` was skipped at discovery. Empty is the
    healthy case; the endpoint exists so a silent skip is still findable."""
    found = _registry(request).problems
    return {"count": len(found), "problems": found}


def install_control_plane(app, hub_version: str) -> None:
    """Mount the control plane and the hub-level error handler."""
    app.state.hub_version = hub_version
    app.include_router(router)

    @app.exception_handler(HubError)
    async def _hub_error(_request: Request, exc: HubError):
        return exc.to_response()
