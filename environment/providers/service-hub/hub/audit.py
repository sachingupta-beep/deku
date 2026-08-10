"""Request/response recorder, mount-aware.

The fleet this hub replaces installed a tracker per container, so each service
had its own ``/audit/requests``. Here there is one process and one audit log, and
because the recorder sits *outside* the mounts it sees the full path -- so every
entry already says which service was called, and a grader gets one ordered,
cross-service timeline of what the agent did instead of 27 logs to merge.

Written as raw ASGI rather than ``BaseHTTPMiddleware``: the latter runs each
request in a nested task and buffers the response through an anyio stream, which
adds latency to every call and interacts badly with mounted sub-apps. Here we
only wrap ``receive``/``send``, so a non-recorded path costs one string compare.

What is deliberately **not** recorded
-------------------------------------
``/hub/*`` (control plane), ``/audit/*`` (itself -- reading the log would append
to it), ``*/health`` (liveness noise), and docs and schema routes. An agent's
audit trail should contain the agent's work, not the harness's bookkeeping.

Note that ``/admin/`` paths *are* recorded, unlike in the per-container fleet
where ``/admin`` was the out-of-band drift plane and had to stay invisible. Here
the harness surface is ``/hub/*``, and ``/admin/`` belongs to the simulated
products -- Keycloak's ``/admin/realms/{realm}/users`` is ordinary agent traffic,
and silently dropping it would leave a hole in the trail a grader reads.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, FrozenSet, List, MutableMapping, Optional

from fastapi import FastAPI

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

_SKIP_PREFIXES = ("/hub", "/audit")
_SKIP_SUFFIXES = ("/health", "/docs", "/openapi.json", "/redoc")
_SKIP_EXACT = frozenset({"/", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"})


class AuditLog:
    """Bounded in-memory ring of request records."""

    def __init__(self, max_entries: int = 10_000) -> None:
        self._entries: List[Dict[str, Any]] = []
        self._max = max_entries

    def append(self, entry: Dict[str, Any]) -> None:
        self._entries.append(entry)
        if len(self._entries) > self._max:
            del self._entries[: len(self._entries) - self._max]

    def entries(self) -> List[Dict[str, Any]]:
        return self._entries

    def clear(self) -> int:
        count = len(self._entries)
        self._entries.clear()
        return count

    def summary(self) -> Dict[str, Any]:
        by_endpoint: Dict[str, Dict[str, Any]] = {}
        by_service: Dict[str, int] = {}
        for entry in self._entries:
            key = f"{entry['method']} {entry['path']}"
            bucket = by_endpoint.setdefault(key, {"count": 0, "statuses": {}})
            bucket["count"] += 1
            status = str(entry["status_code"])
            bucket["statuses"][status] = bucket["statuses"].get(status, 0) + 1
            service = entry.get("service") or "-"
            by_service[service] = by_service.get(service, 0) + 1
        return {
            "total_requests": len(self._entries),
            "by_service": dict(sorted(by_service.items())),
            "endpoints": by_endpoint,
        }


class AuditMiddleware:
    """Records every agent-visible request into an :class:`AuditLog`."""

    def __init__(
        self,
        app: Any,
        log: AuditLog,
        slugs: FrozenSet[str] = frozenset(),
        max_body_bytes: int = 512 * 1024,
    ) -> None:
        self.app = app
        self.log = log
        self.slugs = slugs
        self.max_body_bytes = max_body_bytes

    def _service_of(self, path: str) -> Optional[str]:
        head = path.lstrip("/").split("/", 1)[0]
        return head if head in self.slugs else None

    @staticmethod
    def _should_record(path: str) -> bool:
        if path in _SKIP_EXACT:
            return False
        if path.startswith(_SKIP_PREFIXES):
            return False
        if path.endswith(_SKIP_SUFFIXES):
            return False
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._should_record(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        request_chunks: List[bytes] = []
        request_size = 0

        async def recording_receive() -> MutableMapping[str, Any]:
            nonlocal request_size
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                if chunk and request_size < self.max_body_bytes:
                    request_chunks.append(chunk[: self.max_body_bytes - request_size])
                    request_size += len(chunk)
            return message

        response_chunks: List[bytes] = []
        response_size = 0
        status_code = 0

        async def recording_send(message: MutableMapping[str, Any]) -> None:
            nonlocal status_code, response_size
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk and response_size < self.max_body_bytes:
                    response_chunks.append(chunk[: self.max_body_bytes - response_size])
                    response_size += len(chunk)
            await send(message)

        started = time.time()
        perf = time.perf_counter()
        try:
            await self.app(scope, recording_receive, recording_send)
        finally:
            path = scope.get("path", "")
            query = scope.get("query_string", b"").decode("latin-1")
            self.log.append(
                {
                    "timestamp": started,
                    "timestamp_iso": time.strftime(
                        "%Y-%m-%dT%H:%M:%S", time.gmtime(started)
                    ),
                    "service": self._service_of(path),
                    "method": scope.get("method", ""),
                    "path": path,
                    "query_params": _parse_query(query),
                    "request_body": _decode(request_chunks),
                    "status_code": status_code,
                    "response_body": _decode(response_chunks),
                    "duration_ms": round((time.perf_counter() - perf) * 1000, 2),
                }
            )


def _decode(chunks: List[bytes]) -> Optional[str]:
    if not chunks:
        return None
    raw = b"".join(chunks)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return f"<binary {len(raw)} bytes>"


def _parse_query(query: str) -> Optional[Dict[str, str]]:
    if not query:
        return None
    from urllib.parse import parse_qsl

    return dict(parse_qsl(query, keep_blank_values=True))


def install_audit(app: FastAPI, log: AuditLog) -> None:
    """Add the ``/audit/*`` read endpoints.

    Same shape as the fleet's tracker so existing graders keep working, plus a
    ``service`` field per entry and a ``service`` filter, which only mean
    something once every service shares one log.
    """

    @app.get("/audit/requests", tags=["audit"], summary="Captured request log")
    def audit_requests(
        limit: Optional[int] = None,
        offset: int = 0,
        include_body: bool = True,
        service: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return captured request/response records, oldest first.

        The unpaginated default embeds every response body seen this session and
        grows without bound. Prefer ``/audit/summary`` for an overview, or page
        with ``limit``/``offset`` and ``include_body=false``.
        """
        entries = log.entries()
        if service:
            entries = [e for e in entries if e.get("service") == service]
        total = len(entries)
        window = entries[offset : offset + limit] if limit is not None else entries[offset:]
        if not include_body:
            window = [{k: v for k, v in e.items() if k != "response_body"} for e in window]
        return {"total": total, "offset": offset, "returned": len(window), "requests": window}

    @app.get("/audit/summary", tags=["audit"], summary="Aggregated request counts")
    def audit_summary() -> Dict[str, Any]:
        return log.summary()

    @app.get("/audit/requests/clear", tags=["audit"], summary="Clear the request log")
    def audit_clear() -> Dict[str, int]:
        """GET rather than DELETE, matching the fleet harness that calls it."""
        return {"cleared": log.clear()}
