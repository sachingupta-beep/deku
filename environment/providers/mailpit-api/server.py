"""FastAPI server wrapping mailpit_data module as REST endpoints.

Mailpit's API splits the inbox into two shapes on purpose:

* `/api/v1/messages` --- the **list**: a paginated envelope of summaries, each
  with a `Snippet` and an attachment *count*, plus the inbox-wide `total`,
  `unread` and `tags`. It is also where read state is set and messages are
  deleted in bulk.
* `/api/v1/message/{id}` --- the **read**: one message with its `Text`, `HTML`
  and attachment *list*, the raw source, the headers, the individual parts, and
  the three analyses Mailpit runs over it (`html-check`, `link-check`,
  `sa-check`).

Note the singular/plural split in the paths --- it is Mailpit's, not a typo.
"""

from fastapi import Body, FastAPI, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Any, Dict, Optional

import mailpit_data
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

app = FastAPI(title="Mailpit API (Mock)",
              version=mailpit_data.MAILPIT_VERSION)
install_tracker(app)
install_admin_plane(app, store=mailpit_data._store)


@app.get("/health")
def health():
    return mailpit_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    body = {"error": result["message"]}
    if "smtpErrorCode" in result:
        body["smtpErrorCode"] = result["smtpErrorCode"]
    return JSONResponse(status_code=result["code"], content=body)


def _ok(result, status_code=200):
    """Render a data-module result.

    A `__raw__` result is a download: the raw source, a MIME part or a
    plain-text probe, served with its own content type rather than wrapped in
    JSON.
    """
    if _is_error(result):
        return _fail(result)
    if isinstance(result, dict) and "__raw__" in result:
        headers = {"Content-Disposition":
                   f'inline; filename="{result["__filename__"]}"'}
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

@app.get("/livez")
def livez():
    return _ok(mailpit_data.livez())


@app.get("/readyz")
def readyz():
    return _ok(mailpit_data.readyz())


@app.get("/api/v1/info")
def service_info():
    return mailpit_data.service_info()


@app.get("/api/v1/webui")
def webui_config():
    return mailpit_data.webui_config()


# ---------------------------------------------------------------------------
# The list: summaries, read state, bulk delete
# ---------------------------------------------------------------------------

@app.get("/api/v1/messages")
def list_messages(start: int = Query(0, ge=0),
                  limit: int = Query(50, ge=1, le=200)):
    return _ok(mailpit_data.list_messages(start=start, limit=limit))


@app.put("/api/v1/messages")
def set_read(payload: Dict[str, Any] = Body(default={})):
    return _ok(mailpit_data.set_read(payload))


@app.delete("/api/v1/messages")
def delete_messages(payload: Dict[str, Any] = Body(default={})):
    return _ok(mailpit_data.delete_messages(payload))


@app.get("/api/v1/search")
def search_messages(query: Optional[str] = None, start: int = Query(0, ge=0),
                    limit: int = Query(50, ge=1, le=200)):
    return _ok(mailpit_data.search_messages(query=query, start=start,
                                            limit=limit))


@app.delete("/api/v1/search")
def delete_search(query: Optional[str] = None):
    return _ok(mailpit_data.delete_search(query=query))


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

@app.get("/api/v1/tags")
def list_tags():
    return _ok(mailpit_data.all_tags())


@app.put("/api/v1/tags")
def set_tags(payload: Dict[str, Any] = Body(default={})):
    return _ok(mailpit_data.set_tags(payload))


@app.put("/api/v1/tags/{tag}")
def rename_tag(tag: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(mailpit_data.rename_tag(tag, payload))


@app.delete("/api/v1/tags/{tag}")
def delete_tag(tag: str):
    return _ok(mailpit_data.delete_tag(tag))


# ---------------------------------------------------------------------------
# The read: one message, its parts and the analyses over it
# ---------------------------------------------------------------------------

@app.get("/api/v1/message/{message_id}")
def get_message(message_id: str):
    return _ok(mailpit_data.get_message(message_id))


@app.get("/api/v1/message/{message_id}/raw")
def get_raw(message_id: str):
    return _ok(mailpit_data.get_raw(message_id))


@app.get("/api/v1/message/{message_id}/headers")
def get_headers(message_id: str):
    return _ok(mailpit_data.get_headers(message_id))


@app.get("/api/v1/message/{message_id}/part/{part_id}")
def get_part(message_id: str, part_id: str):
    return _ok(mailpit_data.get_part(message_id, part_id))


@app.get("/api/v1/message/{message_id}/part/{part_id}/thumbnail")
def get_thumbnail(message_id: str, part_id: str):
    return _ok(mailpit_data.get_thumbnail(message_id, part_id))


@app.get("/api/v1/message/{message_id}/html-check")
def html_check(message_id: str):
    return _ok(mailpit_data.html_check(message_id))


@app.get("/api/v1/message/{message_id}/link-check")
def link_check(message_id: str, follow: bool = False):
    return _ok(mailpit_data.link_check(message_id, follow=follow))


@app.get("/api/v1/message/{message_id}/sa-check")
def sa_check(message_id: str):
    return _ok(mailpit_data.sa_check(message_id))


@app.post("/api/v1/message/{message_id}/release")
def release_message(message_id: str,
                    payload: Dict[str, Any] = Body(default={})):
    return _ok(mailpit_data.release_message(message_id, payload))


# ---------------------------------------------------------------------------
# Send and chaos
# ---------------------------------------------------------------------------

@app.post("/api/v1/send")
def send_message(payload: Dict[str, Any] = Body(default={})):
    return _ok(mailpit_data.send_message(payload))


@app.get("/api/v1/chaos")
def get_chaos():
    return _ok(mailpit_data.get_chaos())


@app.put("/api/v1/chaos")
def set_chaos(payload: Dict[str, Any] = Body(default={})):
    return _ok(mailpit_data.set_chaos(payload))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8122)
