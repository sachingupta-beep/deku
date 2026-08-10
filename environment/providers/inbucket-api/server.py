"""FastAPI server wrapping inbucket_data module as REST endpoints.

Every route below a mailbox takes the mailbox as its first path segment,
because Inbucket has no global inbox: there is no endpoint that lists all mail
and none that lists the mailboxes. The `{name}` segment accepts either a bare
mailbox name or a full address, and both are put through the same naming
policy, so `/api/v1/mailbox/amelia.ortega` and
`/api/v1/mailbox/Amelia.Ortega+billing@orbit-labs.com` read the same mailbox.

The monitor endpoints are the only cross-mailbox view.
"""

from fastapi import Body, FastAPI, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Any, Dict, Optional

import inbucket_data
try:
    from tracking_middleware import install_tracker
    from admin_plane import install_admin_plane
except ModuleNotFoundError as _shared_plane_err:  # standalone run without the shared module on sys.path
    import logging as _logging
    _logging.error("SHARED PLANE MISSING - audit + admin disabled: %s", _shared_plane_err)
    def install_tracker(app):  # no-op fallback: audit endpoints disabled
        return None

    def install_admin_plane(app, store=None, one_shot_registry=None):
        return None

app = FastAPI(title="Inbucket API (Mock)",
              version=inbucket_data.INBUCKET_VERSION)
install_tracker(app)
install_admin_plane(app, store=inbucket_data._store)


@app.get("/health")
def health():
    return inbucket_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result["code"],
                        content={"error": result["message"]})


def _ok(result, status_code=200):
    """Render a data-module result.

    A `__raw__` result is a download: the raw source or an attachment, served
    with its own content type rather than wrapped in JSON.
    """
    if _is_error(result):
        return _fail(result)
    if isinstance(result, dict) and "__raw__" in result:
        headers = {"Content-Disposition":
                   f'attachment; filename="{result["__filename__"]}"'}
        return PlainTextResponse(result["__raw__"],
                                 media_type=result["__content_type__"],
                                 headers=headers)
    if isinstance(result, dict) and "__status__" in result:
        body = {k: v for k, v in result.items() if k != "__status__"}
        if not body:
            return Response(status_code=result["__status__"])
        return JSONResponse(status_code=result["__status__"], content=body)
    return JSONResponse(status_code=status_code, content=result)


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

@app.get("/status")
def status():
    return inbucket_data.status()


@app.get("/debug/vars")
def debug_vars():
    return inbucket_data.debug_vars()


# ---------------------------------------------------------------------------
# The monitor: the only cross-mailbox view.
#
# Declared before the mailbox routes purely for readability -- the paths do not
# overlap, since /api/v1/monitor/... and /api/v1/mailbox/... differ on a literal
# segment.
# ---------------------------------------------------------------------------

@app.get("/api/v1/monitor/messages")
def monitor_messages(limit: Optional[int] = Query(None, ge=1, le=200)):
    return _ok(inbucket_data.monitor_messages(limit=limit))


@app.get("/api/v1/monitor/mailbox/{name}")
def monitor_mailbox(name: str, limit: Optional[int] = Query(None, ge=1, le=200)):
    return _ok(inbucket_data.monitor_mailbox(name, limit=limit))


# ---------------------------------------------------------------------------
# One mailbox
# ---------------------------------------------------------------------------

@app.get("/api/v1/mailbox/{name}")
def list_mailbox(name: str):
    return _ok(inbucket_data.list_mailbox(name))


@app.post("/api/v1/mailbox/{name}")
def deliver(name: str, payload: Dict[str, Any] = Body(default={})):
    """Not an Inbucket endpoint -- it stands in for an SMTP delivery."""
    return _ok(inbucket_data.deliver(name, payload))


@app.delete("/api/v1/mailbox/{name}")
def purge_mailbox(name: str):
    return _ok(inbucket_data.purge_mailbox(name))


# ---------------------------------------------------------------------------
# One message
# ---------------------------------------------------------------------------

@app.get("/api/v1/mailbox/{name}/{message_id}")
def get_message(name: str, message_id: str):
    return _ok(inbucket_data.get_message(name, message_id))


@app.patch("/api/v1/mailbox/{name}/{message_id}")
def mark_seen(name: str, message_id: str,
              payload: Dict[str, Any] = Body(default={})):
    return _ok(inbucket_data.mark_seen(name, message_id, payload))


@app.delete("/api/v1/mailbox/{name}/{message_id}")
def delete_message(name: str, message_id: str):
    return _ok(inbucket_data.delete_message(name, message_id))


@app.get("/api/v1/mailbox/{name}/{message_id}/source")
def get_source(name: str, message_id: str):
    return _ok(inbucket_data.get_source(name, message_id))


@app.get("/api/v1/mailbox/{name}/{message_id}/attach/{index}/{filename}")
def get_attachment(name: str, message_id: str, index: str, filename: str):
    return _ok(inbucket_data.get_attachment(name, message_id, index, filename))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8123)
