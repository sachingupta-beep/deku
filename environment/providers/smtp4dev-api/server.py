"""FastAPI server wrapping smtp4dev_data module as REST endpoints.

The routes keep smtp4dev's own shape, which is a .NET one:

* `/api/Messages` and `/api/Sessions` are **paged**, with `page` (1-based),
  `pageSize`, `sortColumn` and `sortIsDescending` --- not a `start` offset.
* `/api/Sessions` is a peer of `/api/Messages`, not a view of it: a session is
  the SMTP conversation, and some produced no message at all.
* `/api/Server` is readable **and writable** --- it is the Settings dialog.
* The delete-everything routes really are spelled with a literal `*`.

Note the route ordering below: the literal `*` and `markAllRead` paths are
declared before `/api/Messages/{message_id}`, because a `{message_id}` pattern
would otherwise swallow them.
"""

from fastapi import Body, FastAPI, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Any, Dict, Optional

import smtp4dev_data
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

app = FastAPI(title="smtp4dev API (Mock)",
              version=smtp4dev_data.SMTP4DEV_VERSION)
install_tracker(app)
install_admin_plane(app, store=smtp4dev_data._store)


@app.get("/health")
def health():
    return smtp4dev_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result["code"],
                        content={"error": result["message"]})


def _ok(result, status_code=200):
    """Render a data-module result.

    A `__raw__` result is a download: the message source, a MIME part or a
    session transcript, served with its own content type rather than wrapped in
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
# Service state and settings
# ---------------------------------------------------------------------------

@app.get("/api/Version")
def version():
    return smtp4dev_data.version()


@app.get("/api/Server")
def get_server():
    return smtp4dev_data.get_server()


@app.post("/api/Server")
def update_server(payload: Dict[str, Any] = Body(default={})):
    return _ok(smtp4dev_data.update_server(payload))


@app.get("/api/Mailboxes")
def list_mailboxes():
    return _ok(smtp4dev_data.list_mailboxes())


# ---------------------------------------------------------------------------
# Messages
#
# The literal routes come first on purpose: `/api/Messages/{message_id}` would
# otherwise match `*` and `markAllRead` as ids.
# ---------------------------------------------------------------------------

@app.delete("/api/Messages/*")
def delete_all_messages(mailboxName: Optional[str] = None):
    return _ok(smtp4dev_data.delete_all_messages(mailbox_name=mailboxName))


@app.post("/api/Messages/markAllRead")
def mark_all_read(mailboxName: Optional[str] = None):
    return _ok(smtp4dev_data.mark_all_read(mailbox_name=mailboxName))


@app.get("/api/Messages")
def list_messages(mailboxName: Optional[str] = None,
                  searchTerms: Optional[str] = None,
                  sortColumn: Optional[str] = None,
                  sortIsDescending: bool = True,
                  page: int = Query(1, ge=1),
                  pageSize: int = Query(25, ge=1, le=200)):
    return _ok(smtp4dev_data.list_messages(
        mailbox_name=mailboxName, search_terms=searchTerms,
        sort_column=sortColumn, sort_is_descending=sortIsDescending,
        page=page, page_size=pageSize))


@app.post("/api/Messages")
def deliver(payload: Dict[str, Any] = Body(default={})):
    """Not an smtp4dev endpoint -- it stands in for an SMTP delivery."""
    return _ok(smtp4dev_data.deliver(payload))


@app.get("/api/Messages/{message_id}")
def get_message(message_id: str):
    return _ok(smtp4dev_data.get_message(message_id))


@app.delete("/api/Messages/{message_id}")
def delete_message(message_id: str):
    return _ok(smtp4dev_data.delete_message(message_id))


@app.get("/api/Messages/{message_id}/source")
def get_source(message_id: str):
    return _ok(smtp4dev_data.get_source(message_id))


@app.get("/api/Messages/{message_id}/html")
def get_html(message_id: str):
    return _ok(smtp4dev_data.get_html(message_id))


@app.get("/api/Messages/{message_id}/plaintext")
def get_plaintext(message_id: str):
    return _ok(smtp4dev_data.get_plaintext(message_id))


@app.get("/api/Messages/{message_id}/part/{part_id}/content")
def get_part_content(message_id: str, part_id: str):
    return _ok(smtp4dev_data.get_part_content(message_id, part_id))


@app.get("/api/Messages/{message_id}/part/{part_id}/source")
def get_part_source(message_id: str, part_id: str):
    return _ok(smtp4dev_data.get_part_source(message_id, part_id))


@app.post("/api/Messages/{message_id}/markRead")
def mark_read(message_id: str):
    return _ok(smtp4dev_data.mark_read(message_id))


@app.post("/api/Messages/{message_id}/relay")
def relay_message(message_id: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(smtp4dev_data.relay_message(message_id, payload))


# ---------------------------------------------------------------------------
# Sessions: the SMTP conversations, including the ones that produced no message
# ---------------------------------------------------------------------------

@app.delete("/api/Sessions/*")
def delete_all_sessions():
    return _ok(smtp4dev_data.delete_all_sessions())


@app.get("/api/Sessions")
def list_sessions(sortColumn: Optional[str] = None,
                  sortIsDescending: bool = True,
                  page: int = Query(1, ge=1),
                  pageSize: int = Query(25, ge=1, le=200)):
    return _ok(smtp4dev_data.list_sessions(
        sort_column=sortColumn, sort_is_descending=sortIsDescending,
        page=page, page_size=pageSize))


@app.get("/api/Sessions/{session_id}")
def get_session(session_id: str):
    return _ok(smtp4dev_data.get_session(session_id))


@app.delete("/api/Sessions/{session_id}")
def delete_session(session_id: str):
    return _ok(smtp4dev_data.delete_session(session_id))


@app.get("/api/Sessions/{session_id}/log")
def get_session_log(session_id: str):
    return _ok(smtp4dev_data.get_session_log(session_id))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8124)
