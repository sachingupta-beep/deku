"""FastAPI server wrapping mailhog_data module as REST endpoints.

MailHog captures mail instead of delivering it, and it exposes the capture
through two APIs that return the same messages in different shapes:

* `/api/v1/...` --- bare arrays, plus the per-message operations: download the
  raw RFC 822 source, download a single MIME part, release the message to a real
  SMTP server.
* `/api/v2/...` --- paginated envelopes (`total`, `count`, `start`, `items`),
  search, and Jim the chaos monkey.

Both are served because clients in the wild use both.
"""

from fastapi import Body, FastAPI, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Any, Dict, Optional

import mailhog_data
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

app = FastAPI(title="MailHog API (Mock)",
              version=mailhog_data.MAILHOG_VERSION)
install_tracker(app)
install_admin_plane(app, store=mailhog_data._store)


@app.get("/health")
def health():
    return mailhog_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result["code"],
                        content={"error": result["message"]})


def _ok(result, status_code=200):
    """Render a data-module result.

    A `__raw__` result is a download: MailHog serves the raw bytes with the
    part's own content type rather than wrapping them in JSON.
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
# Service info
# ---------------------------------------------------------------------------

@app.get("/api/v1/info")
def service_info():
    """Not a MailHog endpoint — a convenience summary of the capture state."""
    return mailhog_data.service_info()


@app.get("/api/v1/events")
def events(limit: int = Query(10, ge=1, le=200)):
    return _ok(mailhog_data.events_snapshot(limit=limit))


# ---------------------------------------------------------------------------
# v1: messages
# ---------------------------------------------------------------------------

@app.get("/api/v1/messages")
def list_messages_v1():
    return _ok(mailhog_data.list_messages_v1())


@app.delete("/api/v1/messages")
def delete_all_messages():
    return _ok(mailhog_data.delete_all_messages())


@app.get("/api/v1/messages/{message_id}")
def get_message(message_id: str):
    return _ok(mailhog_data.get_message(message_id))


@app.delete("/api/v1/messages/{message_id}")
def delete_message(message_id: str):
    return _ok(mailhog_data.delete_message(message_id))


@app.get("/api/v1/messages/{message_id}/download")
def download_message(message_id: str):
    return _ok(mailhog_data.download_message(message_id))


@app.get("/api/v1/messages/{message_id}/mime/part/{part_index}/download")
def download_part(message_id: str, part_index: str):
    return _ok(mailhog_data.download_part(message_id, part_index))


@app.post("/api/v1/messages/{message_id}/release")
def release_message(message_id: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(mailhog_data.release_message(message_id, payload))


@app.get("/api/v1/releases")
def list_releases():
    """Not a MailHog endpoint — it exists so a release can be verified."""
    return _ok(mailhog_data.list_releases())


# ---------------------------------------------------------------------------
# v2: messages, search, Jim
# ---------------------------------------------------------------------------

@app.get("/api/v2/messages")
def list_messages_v2(start: int = Query(0, ge=0),
                     limit: int = Query(50, ge=1, le=500)):
    return _ok(mailhog_data.list_messages_v2(start=start, limit=limit))


@app.get("/api/v2/search")
def search_messages(kind: Optional[str] = None, query: Optional[str] = None,
                    start: int = Query(0, ge=0),
                    limit: int = Query(50, ge=1, le=500)):
    return _ok(mailhog_data.search_messages(kind=kind, query=query,
                                            start=start, limit=limit))


@app.get("/api/v2/jim")
def get_jim():
    return _ok(mailhog_data.get_jim())


@app.post("/api/v2/jim")
def enable_jim(payload: Dict[str, Any] = Body(default={})):
    return _ok(mailhog_data.enable_jim(payload))


@app.put("/api/v2/jim")
def update_jim(payload: Dict[str, Any] = Body(default={})):
    return _ok(mailhog_data.update_jim(payload))


@app.delete("/api/v2/jim")
def disable_jim():
    return _ok(mailhog_data.disable_jim())


@app.get("/api/v2/outgoing-smtp")
def outgoing_smtp():
    return _ok(mailhog_data.outgoing_smtp())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8121)
