"""The central service registry: catalog, lifecycle and lazy loading.

Responsibilities
----------------
* **Discover** -- parse every ``services/*/service.toml`` at startup. Cheap and
  import-free, so the hub knows about 27 services while holding the code and
  data for none of them.
* **Load on demand** -- :meth:`ServiceRegistry.acquire` imports the module,
  constructs it, awaits its startup hook and builds its app, exactly once, under
  a per-slug lock. Concurrent first requests wait for one load, not N.
* **Unload** -- awaits the teardown hook and drops the instance and its store so
  the seeded rows become garbage.
* **Report** -- the state, timings and request counts behind ``/hub/*``.

State machine
-------------
::

    DECLARED ──(no module: 501 forever)
    DISCOVERED ──acquire()──> LOADING ──ok──> READY ──unload()──> UNLOADED
                                 │                                    │
                                 └──raise──> FAILED <──reload()───────┘

``FAILED`` is sticky on purpose. A service that blew up on import will blow up
identically on the next request, so retrying per-request would just convert one
clear failure into an unbounded stream of them -- and a benchmark run would see
nondeterministic timing instead of a clean, reproducible error. Recovery is an
explicit ``POST /hub/services/<slug>/reload``.

Concurrency
-----------
All mutation happens on the event loop; the per-slug :class:`asyncio.Lock` is
what makes a burst of concurrent first-requests collapse into a single load. The
blocking parts -- ``importlib.import_module`` and router construction -- are
pushed to the threadpool so one service's import cannot stall requests already
being served by another.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from hub.base import HealthReport, ServiceContext, ServiceModule
from hub.config import HubConfig
from hub.errors import (
    ManifestError,
    ServiceLoadError,
    ServiceNotFound,
    ServiceNotImplemented,
    ServiceUnavailable,
)
from hub.manifest import ServiceDescriptor, discover_manifests
from hub.store import drop_store, new_store

logger = logging.getLogger("hub.registry")


class ServiceState(str, Enum):
    """Lifecycle position of one service. ``str`` mixin so it serializes as-is."""

    DECLARED = "declared"
    DISCOVERED = "discovered"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"
    UNLOADED = "unloaded"


@dataclass
class ServiceRecord:
    """Mutable per-service bookkeeping. One per manifest, for the process lifetime."""

    descriptor: ServiceDescriptor
    state: ServiceState
    module: Optional[ServiceModule] = None
    app: Optional[FastAPI] = None
    error: Optional[str] = None
    error_type: Optional[str] = None

    loaded_at: Optional[float] = None
    load_ms: Optional[float] = None
    unloaded_at: Optional[float] = None
    last_request_at: Optional[float] = None
    request_count: int = 0
    load_count: int = 0

    @property
    def slug(self) -> str:
        return self.descriptor.slug

    @property
    def ready(self) -> bool:
        return self.state is ServiceState.READY and self.app is not None

    def touch(self) -> None:
        self.last_request_at = time.time()
        self.request_count += 1

    def status(self) -> Dict[str, Any]:
        """Lifecycle view for ``/hub/services``. Merged with the descriptor there."""
        return {
            "state": self.state.value,
            "loaded_at": self.loaded_at,
            "load_ms": self.load_ms,
            "load_count": self.load_count,
            "request_count": self.request_count,
            "last_request_at": self.last_request_at,
            "error": self.error,
            "error_type": self.error_type,
        }


class ServiceRegistry:
    """Catalog + lifecycle manager for every service in ``services/``."""

    def __init__(self, config: HubConfig) -> None:
        self.config = config
        self._records: Dict[str, ServiceRecord] = {}
        self._problems: List[Dict[str, str]] = []
        self._locks: Dict[str, asyncio.Lock] = {}
        self._locks_guard = threading.Lock()
        self._started_at = time.time()
        self._ensure_importable()

    # -- discovery ---------------------------------------------------------

    def _ensure_importable(self) -> None:
        """Put the repo root on ``sys.path`` so ``services.<pkg>`` resolves.

        Done here rather than relying on the CWD so the registry works the same
        from uvicorn, from pytest, and from a REPL.
        """
        root = str(self.config.repo_root)
        if root not in sys.path:
            sys.path.insert(0, root)

    def discover(self) -> int:
        """Scan for manifests and seed the records. Returns the count discovered."""
        descriptors, problems = discover_manifests(
            self.config.services_dir, strict=self.config.strict_discovery
        )
        self._problems = problems
        for problem in problems:
            logger.error("skipping manifest %s: %s", problem["manifest"], problem["error"])

        self._records = {
            d.slug: ServiceRecord(
                descriptor=d,
                state=ServiceState.DISCOVERED if d.implemented else ServiceState.DECLARED,
            )
            for d in descriptors
        }
        logger.info(
            "discovered %d service(s): %d implemented, %d declared",
            len(self._records),
            sum(1 for r in self._records.values() if r.descriptor.implemented),
            sum(1 for r in self._records.values() if not r.descriptor.implemented),
        )
        return len(self._records)

    # -- read side ---------------------------------------------------------

    @property
    def problems(self) -> List[Dict[str, str]]:
        return list(self._problems)

    @property
    def started_at(self) -> float:
        return self._started_at

    def descriptors(self) -> List[ServiceDescriptor]:
        return [record.descriptor for record in self._records.values()]

    def records(self) -> List[ServiceRecord]:
        return list(self._records.values())

    def get(self, slug: str) -> ServiceRecord:
        record = self._records.get(slug)
        if record is None:
            raise ServiceNotFound(
                f"no service is registered under {slug!r}",
                service=slug,
                hint="GET /hub/services lists every available slug",
                available=sorted(self._records),
            )
        return record

    def has(self, slug: str) -> bool:
        return slug in self._records

    def loaded_slugs(self) -> List[str]:
        return sorted(r.slug for r in self._records.values() if r.ready)

    # -- lazy loading ------------------------------------------------------

    def _lock_for(self, slug: str) -> asyncio.Lock:
        with self._locks_guard:
            lock = self._locks.get(slug)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[slug] = lock
            return lock

    async def acquire(self, slug: str) -> ServiceRecord:
        """Return a READY record, loading the service if this is its first request.

        Raises :class:`ServiceNotFound`, :class:`ServiceNotImplemented`,
        :class:`ServiceLoadError` or :class:`ServiceUnavailable` -- all of which
        the router renders as the hub error envelope.
        """
        record = self.get(slug)

        # Fast path: already loaded. No lock, no await -- this is the steady state
        # for every request after the first, so it must cost nothing.
        if record.ready:
            record.touch()
            return record

        if not record.descriptor.implemented:
            raise ServiceNotImplemented(
                f"{record.descriptor.name} is declared in the catalog but not "
                f"implemented yet",
                service=slug,
                hint="docs/SERVICE_AUTHORING.md walks through adding it; "
                "`python tools/new_service.py " + slug + "` scaffolds the module",
                category=record.descriptor.category,
            )

        async with self._lock_for(slug):
            # Re-check: another coroutine may have loaded it while we waited.
            if record.ready:
                record.touch()
                return record

            if record.state is ServiceState.FAILED:
                raise ServiceLoadError(
                    f"{slug} failed to load and is parked: {record.error}",
                    service=slug,
                    hint=f"POST /hub/services/{slug}/reload to retry after fixing it",
                    error_type=record.error_type,
                )

            try:
                await asyncio.wait_for(
                    self._load(record), timeout=self.config.load_timeout_seconds
                )
            except asyncio.TimeoutError:
                record.state = ServiceState.FAILED
                record.error = (
                    f"load did not finish within {self.config.load_timeout_seconds:g}s"
                )
                record.error_type = "TimeoutError"
                logger.error("service %s: %s", slug, record.error)
                raise ServiceUnavailable(
                    record.error,
                    service=slug,
                    hint=f"POST /hub/services/{slug}/reload to retry",
                )

        record.touch()
        return record

    async def _load(self, record: ServiceRecord) -> None:
        """Import -> construct -> on_startup -> build app. Caller holds the lock."""
        descriptor = record.descriptor
        slug = descriptor.slug
        record.state = ServiceState.LOADING
        record.error = None
        record.error_type = None
        started = time.perf_counter()

        try:
            service_class = await run_in_threadpool(_resolve_module, descriptor)

            ctx = ServiceContext(
                descriptor=descriptor,
                config=self.config,
                data_dir=self.config.data_dir_for(descriptor.data_dir_name or slug),
                # A *fresh* store per load: unload -> load must return to seeds,
                # not to whatever the previous incarnation mutated them into.
                store=new_store(descriptor.store_name),
                logger=logging.getLogger(f"hub.service.{slug}"),
            )

            module = service_class(ctx)
            await _maybe_await(module.on_startup())
            app = await run_in_threadpool(module.create_app)
            # Snapshot the seeded state *now*, while it is still pristine. Doing
            # it lazily on the first /reset would capture whatever the task had
            # already mutated, making reset a no-op exactly when it matters.
            ctx.store.capture_baseline()

        except Exception as exc:  # noqa: BLE001 -- every failure mode parks the service
            record.state = ServiceState.FAILED
            record.error = f"{exc}"
            record.error_type = type(exc).__name__
            record.module = None
            record.app = None
            drop_store(descriptor.store_name)
            logger.exception("service %s failed to load", slug)
            raise ServiceLoadError(
                f"{slug} failed to load: {type(exc).__name__}: {exc}",
                service=slug,
                hint=f"POST /hub/services/{slug}/reload to retry after fixing it",
                error_type=type(exc).__name__,
            ) from exc

        record.module = module
        record.app = app
        record.state = ServiceState.READY
        record.load_ms = round((time.perf_counter() - started) * 1000, 2)
        record.loaded_at = time.time()
        record.load_count += 1
        logger.info("service %s loaded in %.1fms", slug, record.load_ms)

    # -- unload / reload ---------------------------------------------------

    async def unload(self, slug: str) -> ServiceRecord:
        """Run the teardown hook and release the instance, app and store.

        The imported Python module stays in ``sys.modules`` -- code is kilobytes
        and re-importing it buys nothing. What unloading actually reclaims is the
        seeded rows, which is where a service's memory lives.
        """
        record = self.get(slug)
        async with self._lock_for(slug):
            if record.module is not None:
                try:
                    await _maybe_await(record.module.on_shutdown())
                except Exception:  # noqa: BLE001 -- a bad teardown must still unload
                    logger.exception("service %s: on_shutdown raised; unloading anyway", slug)
            record.module = None
            record.app = None
            drop_store(record.descriptor.store_name)
            if record.state is not ServiceState.FAILED:
                record.state = ServiceState.UNLOADED
            record.unloaded_at = time.time()
        logger.info("service %s unloaded", slug)
        return record

    async def reload(self, slug: str, *, reimport: bool = False) -> ServiceRecord:
        """Unload then load again, back to pristine seeds.

        ``reimport=True`` additionally drops the service's Python modules from
        ``sys.modules`` so edited code is picked up -- a development convenience,
        off by default because a benchmark run wants the bytes it booted with.
        """
        record = self.get(slug)
        await self.unload(slug)
        if reimport:
            await run_in_threadpool(_purge_modules, record.descriptor)
        record.state = ServiceState.DISCOVERED
        record.error = None
        record.error_type = None
        return await self.acquire(slug)

    async def reset(self, slug: str) -> Dict[str, Any]:
        """Restore a loaded service's data to its baseline without re-importing.

        This is the cheap between-tasks reset an eval harness wants: it rewinds
        the rows a previous task mutated in a millisecond or two, where a reload
        pays the import and seed-parse cost again. Falls back to a reload if the
        service is not currently loaded.
        """
        record = self.get(slug)
        if not record.ready:
            await self.acquire(slug)
            return {"service": slug, "reset": "loaded", "state": record.state.value}
        store = record.module.ctx.store  # type: ignore[union-attr]
        restored = store.restore("__baseline__")
        store.clear_drift_log()
        return {"service": slug, "reset": "baseline" if restored else "noop",
                "state": record.state.value}

    # -- bulk operations ---------------------------------------------------

    async def load_eager(self) -> List[str]:
        """Pre-load the slugs named in ``HUB_EAGER_SERVICES``.

        Failures are logged, not raised: an unknown or broken eager service must
        not stop the hub from booting and serving the other 26.
        """
        loaded: List[str] = []
        for slug in self.config.eager_services:
            try:
                await self.acquire(slug)
                loaded.append(slug)
            except Exception as exc:  # noqa: BLE001
                logger.error("eager load of %s failed: %s", slug, exc)
        return loaded

    async def shutdown_all(self) -> None:
        """Teardown every loaded service. Called from the hub's lifespan exit."""
        for slug in self.loaded_slugs():
            try:
                await self.unload(slug)
            except Exception:  # noqa: BLE001
                logger.exception("service %s: unload during shutdown failed", slug)

    async def reap_idle(self, now: Optional[float] = None) -> List[str]:
        """Unload services idle for longer than ``HUB_IDLE_TTL``. Returns the slugs.

        Eager services are exempt -- they were pinned deliberately. A service that
        has been loaded but never called is measured from its load time, so a
        pre-warm that no task ever used still eventually gives its memory back.
        """
        ttl = self.config.idle_ttl_seconds
        if ttl <= 0:
            return []
        now = now if now is not None else time.time()
        evicted: List[str] = []
        for record in self.records():
            if not record.ready or record.slug in self.config.eager_services:
                continue
            idle_since = record.last_request_at or record.loaded_at or now
            if now - idle_since >= ttl:
                await self.unload(record.slug)
                evicted.append(record.slug)
        if evicted:
            logger.info("reaped %d idle service(s): %s", len(evicted), ", ".join(evicted))
        return evicted

    # -- reporting ---------------------------------------------------------

    def catalog(self) -> Dict[str, Any]:
        """Grouped view for ``GET /hub/catalog``."""
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for record in sorted(self._records.values(), key=lambda r: r.slug):
            entry = record.descriptor.to_public()
            entry["state"] = record.state.value
            by_category.setdefault(record.descriptor.category, []).append(entry)
        return {
            "total": len(self._records),
            "loaded": len(self.loaded_slugs()),
            "categories": by_category,
        }

    def service_view(self, slug: str, *, include_routes: bool = True) -> Dict[str, Any]:
        """Descriptor + live lifecycle state for one service."""
        record = self.get(slug)
        view = record.descriptor.to_public()
        view.update(record.status())
        if include_routes and record.ready:
            view["routes"] = _describe_routes(record)
            view["tables"] = record.module.ctx.store.list_tables()  # type: ignore[union-attr]
            view["documents"] = record.module.ctx.store.list_documents()  # type: ignore[union-attr]
        return view

    def health(self) -> Dict[str, Any]:
        """Aggregate health. Only *loaded* services are probed -- an unloaded
        service is not unhealthy, it simply has not been asked for yet."""
        services: Dict[str, Any] = {}
        worst = "ok"
        for record in sorted(self._records.values(), key=lambda r: r.slug):
            if record.ready:
                try:
                    report = record.module.health()  # type: ignore[union-attr]
                except Exception as exc:  # noqa: BLE001
                    report = HealthReport(status="error", detail=f"{type(exc).__name__}: {exc}")
                services[record.slug] = {"state": record.state.value, **report.to_dict()}
                if report.status == "error":
                    worst = "error"
                elif report.status == "degraded" and worst == "ok":
                    worst = "degraded"
            else:
                services[record.slug] = {"state": record.state.value}
                if record.state is ServiceState.FAILED and worst == "ok":
                    worst = "degraded"
        return {
            "status": worst,
            "uptime_seconds": round(time.time() - self._started_at, 3),
            "discovered": len(self._records),
            "loaded": len(self.loaded_slugs()),
            "services": services,
        }

    def metrics(self) -> Dict[str, Any]:
        """Load timings and request counts -- what a harness charts per run."""
        per_service = {
            record.slug: {
                "state": record.state.value,
                "load_ms": record.load_ms,
                "load_count": record.load_count,
                "request_count": record.request_count,
                "last_request_at": record.last_request_at,
            }
            for record in sorted(self._records.values(), key=lambda r: r.slug)
        }
        load_times = [r.load_ms for r in self._records.values() if r.load_ms is not None]
        return {
            "uptime_seconds": round(time.time() - self._started_at, 3),
            "discovered": len(self._records),
            "loaded": len(self.loaded_slugs()),
            "total_requests": sum(r.request_count for r in self._records.values()),
            "load_ms_total": round(sum(load_times), 2),
            "load_ms_max": round(max(load_times), 2) if load_times else None,
            "rss_bytes": _rss_bytes(),
            "services": per_service,
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _resolve_module(descriptor: ServiceDescriptor) -> type:
    """Import ``package.module:ClassName`` and validate what came back.

    Runs in the threadpool -- ``import_module`` hits the filesystem and, for a
    data-heavy service, can take long enough to matter to requests in flight for
    other services.
    """
    dotted, _, class_name = descriptor.module.partition(":")
    try:
        imported = importlib.import_module(dotted)
    except ImportError as exc:
        raise ManifestError(
            f"cannot import {dotted!r} for service {descriptor.slug!r}: {exc}",
            service=descriptor.slug,
            hint=f"declared by [service].module in {descriptor.manifest_path}",
        ) from exc

    service_class = getattr(imported, class_name, None)
    if service_class is None:
        raise ManifestError(
            f"{dotted!r} has no attribute {class_name!r}",
            service=descriptor.slug,
            hint=f"declared by [service].module in {descriptor.manifest_path}",
        )
    if not (isinstance(service_class, type) and issubclass(service_class, ServiceModule)):
        raise ManifestError(
            f"{descriptor.module} is not a ServiceModule subclass",
            service=descriptor.slug,
            hint="subclass hub.base.ServiceModule",
        )
    return service_class


def _purge_modules(descriptor: ServiceDescriptor) -> None:
    """Drop the service's package from ``sys.modules`` so a reload re-imports it."""
    dotted, _, _ = descriptor.module.partition(":")
    package = dotted.rsplit(".", 1)[0] if "." in dotted else dotted
    for name in [m for m in sys.modules if m == package or m.startswith(package + ".")]:
        sys.modules.pop(name, None)


async def _maybe_await(result: Any) -> Any:
    """Allow lifecycle hooks to be written sync or async, whichever reads better."""
    if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
        return await result
    return result


def _describe_routes(record: ServiceRecord) -> List[Dict[str, Any]]:
    """Live route table of a loaded service, paths rewritten to hub-absolute.

    Derived from the app's OpenAPI document rather than by walking
    ``app.routes``. Walking looks simpler until you try it across FastAPI
    versions: ``include_router`` copies routes flat in 0.115 but inserts a
    private ``_IncludedRouter`` wrapper in 0.141, so a naive walk silently
    reports one route (``/health``) on the newer one. ``openapi()`` is public,
    stable, and already cached on the app after the first call.
    """
    base = record.descriptor.base_path
    try:
        schema = record.app.openapi()  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 -- a schema failure must not break /hub/services
        logger.exception("service %s: could not build OpenAPI for route listing", record.slug)
        return []
    routes: List[Dict[str, Any]] = []
    for path, operations in sorted(schema.get("paths", {}).items()):
        methods = sorted(m.upper() for m in operations if m.lower() != "parameters")
        first = next(iter(operations.values()), {}) if operations else {}
        routes.append(
            {
                "path": f"{base}{path}",
                "methods": methods,
                "summary": first.get("summary", "") if isinstance(first, dict) else "",
                "tags": first.get("tags", []) if isinstance(first, dict) else [],
            }
        )
    return routes


def _rss_bytes() -> Optional[int]:
    """Resident set size, or None where it cannot be read without a dependency.

    ``/proc/self/statm`` exists in the container (Linux) which is where the
    number actually matters; on Windows or macOS this returns None rather than
    pulling in psutil for a metric that is nice-to-have.
    """
    try:
        with open("/proc/self/statm", encoding="ascii") as handle:
            pages = int(handle.read().split()[1])
        return pages * 4096
    except (OSError, IndexError, ValueError):
        return None
