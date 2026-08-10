"""FastAPI server wrapping mailcatcher_data module as REST endpoints.

MailCatcher's whole API hangs off `/messages`, and the *format* is a file
extension rather than a path segment: `/messages/1.json`, `.html`, `.plain`,
`.source`, `.eml`. Which of those a given message offers is advertised in its
`formats` array.

Note the route ordering: the extension routes are declared before the catch-all
`/{message_id}.{extension}`, which exists only to turn an unrecognised
extension into a 400 that says what the message does offer. Starlette matches in
declaration order, so the specific ones win.
"""

from fastapi import Body, FastAPI, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Any, Dict

import mailcatcher_data
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

app = FastAPI(title="MailCatcher API (Mock)",
              version=mailcatcher_data.MAILCATCHER_VERSION)
install_tracker(app)
install_admin_plane(app, store=mailcatcher_data._store)


@app.get("/health")
def health():
    return mailcatcher_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result["code"],
                        content={"error": result["message"]})


def _ok(result, status_code=200):
    """Render a data-module result.

    A `__raw__` result is one of the extension formats: the rewritten HTML, the
    plain body, the source, or an attachment fetched by Content-ID.
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


@app.get("/info")
def service_info():
    """Not a MailCatcher endpoint -- a convenience summary of the capture."""
    return mailcatcher_data.service_info()


# ---------------------------------------------------------------------------
# The whole API: /messages
# ---------------------------------------------------------------------------

@app.get("/messages")
def list_messages():
    return _ok(mailcatcher_data.list_messages())


@app.post("/messages")
def deliver(payload: Dict[str, Any] = Body(default={})):
    """Not a MailCatcher endpoint -- it stands in for an SMTP delivery."""
    return _ok(mailcatcher_data.deliver(payload))


@app.delete("/messages")
def delete_all_messages():
    return _ok(mailcatcher_data.delete_all_messages())


# The format is the file extension. These are declared before the catch-all
# below so an unrecognised extension is the only thing that falls through.

@app.get("/messages/{message_id}.json")
def get_message(message_id: str):
    return _ok(mailcatcher_data.get_message(message_id))


@app.get("/messages/{message_id}.html")
def get_html(message_id: str):
    return _ok(mailcatcher_data.get_html(message_id))


@app.get("/messages/{message_id}.plain")
def get_plain(message_id: str):
    return _ok(mailcatcher_data.get_plain(message_id))


@app.get("/messages/{message_id}.source")
def get_source(message_id: str):
    return _ok(mailcatcher_data.get_source(message_id))


@app.get("/messages/{message_id}.eml")
def get_eml(message_id: str):
    return _ok(mailcatcher_data.get_eml(message_id))


@app.get("/messages/{message_id}/parts/{cid}")
def get_part(message_id: str, cid: str):
    return _ok(mailcatcher_data.get_part(message_id, cid))


@app.delete("/messages/{message_id}")
def delete_message(message_id: str):
    return _ok(mailcatcher_data.delete_message(message_id))


@app.get("/messages/{message_id}.{extension}")
def unsupported_format(message_id: str, extension: str):
    """Last resort: name the formats this message actually offers."""
    return _ok(mailcatcher_data.unsupported_format(message_id, extension))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8125)
