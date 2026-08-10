"""Hub-level error envelope.

A deliberate design rule: **hub errors and service errors never look alike.**

A simulated service answers in its upstream's own error shape -- PostgREST's
``{"code": "42P01", "message": ...}``, Keycloak's ``{"error": ...}``, Stripe's
``{"error": {"type": ...}}`` -- because an agent under evaluation must see what
the real API would have sent. Anything the *hub* itself rejects (unknown
service, module failed to import, service not implemented yet) is wrapped in
the envelope below, which no upstream vendor uses:

    {"error": {"scope": "hub", "code": "service_not_found", "message": "...",
               "service": "keyclock", "hint": "..."}}

``"scope": "hub"`` is the discriminator. An agent that sees it knows the
infrastructure said no, not the simulated API -- so retrying the same call
against a different endpoint is pointless, and a grader can tell a genuine
4xx-under-test apart from a harness failure.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse


class HubError(Exception):
    """Base for every hub-originated failure. Carries its own HTTP status."""

    status_code = 500
    code = "hub_error"

    def __init__(
        self,
        message: str,
        *,
        service: Optional[str] = None,
        hint: Optional[str] = None,
        **extra: Any,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.service = service
        self.hint = hint
        self.extra = extra

    def to_dict(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {"scope": "hub", "code": self.code, "message": self.message}
        if self.service:
            body["service"] = self.service
        if self.hint:
            body["hint"] = self.hint
        body.update(self.extra)
        return {"error": body}

    def to_response(self) -> JSONResponse:
        return JSONResponse(status_code=self.status_code, content=self.to_dict())


class ServiceNotFound(HubError):
    """No manifest declares this slug."""

    status_code = 404
    code = "service_not_found"


class ServiceNotImplemented(HubError):
    """The slug is declared in the catalog but has no module behind it yet."""

    status_code = 501
    code = "service_not_implemented"


class ServiceLoadError(HubError):
    """The module exists but importing it, constructing it, or running its
    startup hook raised. The service is parked in FAILED until a reload."""

    status_code = 503
    code = "service_load_failed"


class ManifestError(HubError):
    """``service.toml`` is missing a required field or has a bad value."""

    status_code = 500
    code = "invalid_manifest"


class ServiceUnavailable(HubError):
    """Load was attempted but did not finish inside ``HUB_LOAD_TIMEOUT``."""

    status_code = 503
    code = "service_load_timeout"
