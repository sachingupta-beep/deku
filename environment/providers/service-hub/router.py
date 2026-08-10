"""Dynamic routing: one lazy mount per service.

How a request finds its service
-------------------------------
::

    GET /keycloak/admin/realms/orbit/users
        │
        ├─ Starlette matches Mount("/keycloak")            <- registered at boot
        │                                                     (no import yet)
        ├─ LazyServiceMount.__call__
        │     └─ registry.acquire("keycloak")              <- imports NOW, once
        │            import -> construct -> on_startup -> build app
        │
        └─ delegate to the service's own FastAPI app with
           scope["path"] = "/admin/realms/orbit/users"     <- Mount rewrote it

Why a ``Mount`` and not a catch-all handler
-------------------------------------------
A catch-all ``@app.api_route("/{service}/{rest:path}")`` would have to re-dispatch
by hand: reparse the path, forge a sub-request, and reinvent every piece of
routing the service's own app already does -- path params, method matching,
``307`` redirects, its own exception handlers. Worse, the service's OpenAPI would
be unreachable and its ``/docs`` would generate broken URLs.

``Mount`` gives all of that for free, because it is what FastAPI's own
``app.mount()`` uses: it strips the matched prefix from ``scope["path"]`` and
appends it to ``scope["root_path"]``, so the sub-app sees itself as living at the
root while still generating correct absolute URLs. Registering the mounts at boot
costs one small object per service and imports nothing -- the laziness lives one
level down, inside :class:`LazyServiceMount`, not in the route table.

Route precedence
----------------
Registration order is match order, and the hub's own routes are registered before
the mounts, so ``/hub/*``, ``/health``, ``/audit/*`` and ``/docs`` can never be
shadowed by a service. :data:`hub.manifest.RESERVED_SLUGS` refuses those names at
discovery time anyway -- belt and braces, because a service that silently ate the
control plane would be a miserable thing to debug.
"""

from __future__ import annotations

import difflib
import logging
from typing import Any, Awaitable, Callable, Dict, List, MutableMapping

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.routing import Mount

from hub.errors import HubError, ServiceNotFound
from service_registry import ServiceRegistry

logger = logging.getLogger("hub.router")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]


class LazyServiceMount:
    """ASGI app that loads its service on first call, then gets out of the way.

    One instance per service, created at boot. It holds a slug and a registry
    reference and nothing else, so 27 of them cost nothing measurable. After the
    first request the body of :meth:`__call__` is a dict lookup plus a delegation.
    """

    __slots__ = ("_registry", "_slug")

    def __init__(self, registry: ServiceRegistry, slug: str) -> None:
        self._registry = registry
        self._slug = slug

    def __repr__(self) -> str:  # shows up in Starlette's route repr
        return f"<LazyServiceMount {self._slug!r}>"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return

        try:
            record = await self._registry.acquire(self._slug)
        except HubError as exc:
            await _send_hub_error(exc, scope, receive, send)
            return

        app = record.app
        if app is None:  # defensive: acquire() guarantees this, belt and braces
            await _send_hub_error(
                HubError(
                    f"{self._slug} reported ready without an app",
                    service=self._slug,
                ),
                scope,
                receive,
                send,
            )
            return

        await app(scope, receive, send)


async def _send_hub_error(exc: HubError, scope: Scope, receive: Receive, send: Send) -> None:
    """Render a hub error at the raw-ASGI level (no service app exists to do it)."""
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1011})
        return
    await exc.to_response()(scope, receive, send)


def install_service_routes(app: FastAPI, registry: ServiceRegistry) -> List[str]:
    """Mount every discovered service lazily. Returns the slugs mounted.

    Call this **after** the control plane is installed, so hub routes win.
    """
    mounted: List[str] = []
    for descriptor in registry.descriptors():
        app.router.routes.append(
            Mount(
                descriptor.base_path,
                app=LazyServiceMount(registry, descriptor.slug),
                name=f"service:{descriptor.slug}",
            )
        )
        mounted.append(descriptor.slug)
    logger.info("mounted %d lazy service route(s)", len(mounted))
    return mounted


def install_unknown_service_handler(app: FastAPI, registry: ServiceRegistry) -> None:
    """Catch-all for paths that look like a service call but name no known service.

    Registered last, so it only sees what nothing else matched. Without it an
    agent that writes ``/keyclock/...`` gets FastAPI's bare ``{"detail":"Not
    Found"}`` and no way to tell a typo'd service from a typo'd endpoint. With
    it, the reply names the mistake and suggests the fix -- which is the
    difference between an agent recovering in one turn and burning its budget
    guessing.
    """

    @app.api_route(
        "/{service}/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        include_in_schema=False,
    )
    async def _unknown_service(service: str, path: str) -> JSONResponse:
        known = sorted(d.slug for d in registry.descriptors())
        suggestions = difflib.get_close_matches(service, known, n=3, cutoff=0.5)
        exc = ServiceNotFound(
            f"no service is registered under {service!r}",
            service=service,
            hint=(
                f"did you mean {', '.join(repr(s) for s in suggestions)}?"
                if suggestions
                else "GET /hub/services lists every available slug"
            ),
            requested_path=f"/{service}/{path}".rstrip("/"),
            available=known,
        )
        return exc.to_response()


def service_index(registry: ServiceRegistry, base_url: str = "") -> Dict[str, Any]:
    """Compact map of slug -> base URL. The one call an agent makes to orient itself."""
    root = base_url.rstrip("/")
    return {
        descriptor.slug: f"{root}{descriptor.base_path}"
        for descriptor in registry.descriptors()
    }
