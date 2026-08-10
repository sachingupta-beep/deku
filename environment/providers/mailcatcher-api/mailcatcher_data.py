"""Data access module for the MailCatcher mock service.

MailCatcher is a Ruby/Sinatra app, and it is the smallest surface of the five
mail services here. That minimalism is the identity, not an omission: there is
no search, no tags, no read state, no mailboxes, no sessions and no settings.
Everything hangs off `/messages`.

What it does have is distinctive:

* **The format is a file extension, not a path segment.** `/messages/1.json`,
  `.html`, `.plain`, `.source`, `.eml`. Which extensions will work for a given
  message is advertised in its `formats` array, so a client checks that rather
  than guessing.
* **Ids are plain integers.** `1`, `2`, `3` --- assigned in arrival order. Every
  other capture tool in this fleet uses an opaque token, a ULID, a timestamp or
  a GUID.
* **Addresses come back angle-bracketed**, as the SMTP envelope wrote them:
  `"<billing@orbit-labs.com>"`, and a null return path is the literal `"<>"`.
* **Attachments are addressed by Content-ID**, not by index, filename or MIME
  section number: `/messages/{id}/parts/{cid}`.
* **`.html` rewrites `cid:` references** to those part URLs, so the HTML it
  serves is directly renderable --- which is the whole reason the endpoint
  exists.

Keys are snake_case (`created_at`, `is_attachment`) and `size` is a **string**,
because Ruby serialised them that way.

Mutations --- deliveries and deletes --- are held in process memory and reset on
restart.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_str)

_store = get_store("mailcatcher-api")
_API = "mailcatcher-api"

MAILCATCHER_VERSION = "0.10.0"
RUBY_VERSION = "ruby 3.3.6"
SMTP_BIND = "0.0.0.0:1025"
HTTP_BIND = "0.0.0.0:1080"
FORMATS = ("source", "html", "plain", "eml")


def _store_insert(_table, _row):
    """Persist a newly-created row into the shared store (drift/injection-safe).

    Synthesizes the table's registered primary key from the row's ``id`` field
    when the row doesn't already carry it, so creates work regardless of whether
    the table was registered with primary_key="id" or a domain-specific key.
    """
    _t = _store.table(_table)
    if _t.primary_key not in _row and "id" in _row:
        _row = {**_row, _t.primary_key: _row["id"]}
    return _t.upsert(_row)


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _semi_list(row, column):
    raw = opt_str(row, column, default="")
    return [part for part in raw.split(";") if part]


def _flag(row, column, default="0"):
    return opt_str(row, column, default=default) == "1"


def _coerce_messages(rows):
    return [{**_strip_ctx(r), "recipients": _semi_list(r, "recipients"),
             "cc": _semi_list(r, "cc")} for r in rows]


def _coerce_parts(rows):
    return [{**_strip_ctx(r), "is_attachment": _flag(r, "is_attachment")}
            for r in rows]


_store.register("messages", primary_key="id",
                initial_loader=lambda: _coerce_messages(
                    _load("messages.json", "messages")))
# A Content-ID is unique only within its message, so the store needs a
# composite key.
_store.register("parts", primary_key="_pk",
                initial_loader=lambda: _coerce_parts(
                    _load("parts.json", "parts")))


def _messages():
    return _store.table("messages").rows()


def _parts(message_id):
    return sorted((p for p in _store.table("parts").rows()
                   if p["message_id"] == message_id),
                  key=lambda p: p["cid"])


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def _error(status, message):
    return {"error": message, "code": status, "message": message}


def _not_found(message="Message not found"):
    return _error(404, message)


# ---------------------------------------------------------------------------
# Addresses: angle-bracketed, as the envelope wrote them
# ---------------------------------------------------------------------------

def _bracket(address):
    """MailCatcher reports the envelope, so `<>` is a real, empty sender."""
    address = (address or "").strip()
    if not address:
        return "<>"
    if address.startswith("<") and address.endswith(">"):
        return address
    return f"<{address}>"


def _unbracket(address):
    address = (address or "").strip()
    if address.startswith("<") and address.endswith(">"):
        return address[1:-1]
    return address


# ---------------------------------------------------------------------------
# Source, size and formats
# ---------------------------------------------------------------------------

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
           "Oct", "Nov", "Dec"]
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _rfc2822(stamp):
    try:
        moment = datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return stamp
    return (f"{_DAYS[moment.weekday()]}, {moment.day:02d} "
            f"{_MONTHS[moment.month - 1]} {moment.year} "
            f"{moment.strftime('%H:%M:%S')} +0000")


def _boundary(message_id):
    return f"--==_mimepart_{message_id}_orbit"


def _source(message):
    """Rebuild the RFC 822 source MailCatcher captured."""
    parts = _parts(message["id"])
    lines = [f"Date: {_rfc2822(message['created_at'])}",
             f"From: {_unbracket(message['sender']) or 'MAILER-DAEMON'}",
             f"To: {', '.join(_unbracket(r) for r in message['recipients'])}"]
    if message["cc"]:
        lines.append(f"Cc: {', '.join(_unbracket(c) for c in message['cc'])}")
    lines += [f"Subject: {message['subject']}",
              f"Message-ID: <{message['id']}.orbit@mailcatcher.example>",
              "MIME-Version: 1.0"]
    if not parts and not (message["text"] and message["html"]):
        kind = "text/html" if message["html"] else "text/plain"
        lines.append(f"Content-Type: {kind}; charset=UTF-8")
        return "\r\n".join(lines) + "\r\n\r\n" + (message["html"]
                                                  or message["text"])
    boundary = _boundary(message["id"])
    lines.append(f'Content-Type: {message["type"]}; boundary="{boundary}"')
    chunks = []
    if message["text"]:
        chunks.append("Content-Type: text/plain; charset=UTF-8\r\n\r\n"
                      + message["text"])
    if message["html"]:
        chunks.append("Content-Type: text/html; charset=UTF-8\r\n\r\n"
                      + message["html"])
    for part in parts:
        disposition = "attachment" if part["is_attachment"] else "inline"
        chunks.append(f"Content-Type: {part['type']}\r\n"
                      f"Content-Transfer-Encoding: base64\r\n"
                      f"Content-ID: <{part['cid']}>\r\n"
                      f'Content-Disposition: {disposition}; '
                      f'filename="{part["filename"]}"\r\n\r\n' + part["body"])
    body = ("".join(f"--{boundary}\r\n{c}\r\n" for c in chunks)
            + f"--{boundary}--\r\n")
    return "\r\n".join(lines) + "\r\n\r\n" + body


def _size(message):
    """A string, because Ruby serialised it that way."""
    return str(len(_source(message).encode("utf-8")))


def _formats(message):
    """Which extensions will actually work for this message.

    A client is meant to read this rather than guess: asking for `.html` on a
    message that has no HTML part is a 404, and this is how to know in advance.
    """
    formats = ["source"]
    if message["html"]:
        formats.append("html")
    if message["text"]:
        formats.append("plain")
    return formats


# ---------------------------------------------------------------------------
# Representations
# ---------------------------------------------------------------------------

def summary_representation(message):
    """The list shape --- no bodies, no attachments."""
    return {
        "id": int(message["id"]),
        "sender": _bracket(message["sender"]),
        "recipients": [_bracket(r) for r in message["recipients"]],
        "subject": message["subject"],
        "size": _size(message),
        "type": message["type"],
        "created_at": message["created_at"],
    }


def _part_representation(message, part):
    return {
        "cid": part["cid"],
        "type": part["type"],
        "filename": part["filename"],
        "size": len(part["body"].encode("utf-8")),
        "is_attachment": part["is_attachment"],
        "href": f"/messages/{message['id']}/parts/{part['cid']}",
    }


def message_representation(message):
    """The read shape --- adds `formats` and the attachment list."""
    return {
        **summary_representation(message),
        "cc": [_bracket(c) for c in message["cc"]],
        "formats": _formats(message),
        "attachments": [_part_representation(message, p)
                        for p in _parts(message["id"])],
    }


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def _sorted_messages():
    """Oldest first --- id order, which is arrival order."""
    return sorted(_messages(), key=lambda m: int(m["id"]))


def list_messages():
    return [summary_representation(m) for m in _sorted_messages()]


def get_message(message_id):
    message = _store.table("messages").get(str(message_id))
    if not message:
        return _not_found()
    return message_representation(message)


_CID_RE = re.compile(r'cid:([^"\'\s>)]+)')


def get_html(message_id):
    """Serve the HTML with its `cid:` references rewritten to part URLs.

    This is the point of the endpoint: MailCatcher hands back HTML a browser can
    render directly, with every inline image pointing at
    `/messages/{id}/parts/{cid}` instead of a `cid:` URI nothing can fetch.
    """
    message = _store.table("messages").get(str(message_id))
    if not message:
        return _not_found()
    if not message["html"]:
        return _not_found(f"Message {message_id} has no html part; it offers "
                          f"{', '.join(_formats(message))}")
    html = _CID_RE.sub(
        lambda m: f"/messages/{message['id']}/parts/{m.group(1)}",
        message["html"])
    return {"__raw__": html, "__content_type__": "text/html;charset=utf-8",
            "__filename__": f"{message_id}.html"}


def get_plain(message_id):
    message = _store.table("messages").get(str(message_id))
    if not message:
        return _not_found()
    if not message["text"]:
        return _not_found(f"Message {message_id} has no plain part; it offers "
                          f"{', '.join(_formats(message))}")
    return {"__raw__": message["text"],
            "__content_type__": "text/plain;charset=utf-8",
            "__filename__": f"{message_id}.txt"}


def get_source(message_id):
    message = _store.table("messages").get(str(message_id))
    if not message:
        return _not_found()
    return {"__raw__": _source(message),
            "__content_type__": "text/plain;charset=utf-8",
            "__filename__": f"{message_id}.source"}


def get_eml(message_id):
    """The same bytes as `.source`, served as a downloadable message/rfc822."""
    message = _store.table("messages").get(str(message_id))
    if not message:
        return _not_found()
    return {"__raw__": _source(message), "__content_type__": "message/rfc822",
            "__filename__": f"{message_id}.eml"}


def get_part(message_id, cid):
    """Attachments are addressed by Content-ID, not by index or filename."""
    message = _store.table("messages").get(str(message_id))
    if not message:
        return _not_found()
    parts = _parts(str(message_id))
    for part in parts:
        if part["cid"] == cid:
            return {"__raw__": part["body"], "__content_type__": part["type"],
                    "__filename__": part["filename"]}
    if not parts:
        return _not_found(f"Message {message_id} has no parts")
    return _not_found(f"Message {message_id} has no part with cid {cid!r}; it "
                      f"has {', '.join(p['cid'] for p in parts)}")


def unsupported_format(message_id, extension):
    message = _store.table("messages").get(str(message_id))
    if not message:
        return _not_found()
    return _error(400, f"'{extension}' is not a supported format; this message "
                       f"offers {', '.join(_formats(message))} "
                       f"(and eml, which mirrors source)")


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def _drop(message):
    _store.table("parts").delete_where(
        lambda p, _id=message["id"]: p["message_id"] == _id)
    _store.table("messages").delete(message["id"])


def delete_message(message_id):
    message = _store.table("messages").get(str(message_id))
    if not message:
        return _not_found()
    _drop(message)
    return {"__status__": 204}


def delete_all_messages():
    count = len(_messages())
    for message in list(_messages()):
        _drop(message)
    return {"__status__": 200, "deleted": count}


_ADDRESS_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _next_id():
    """Integer ids in arrival order, which is MailCatcher's scheme."""
    taken = {int(m["id"]) for m in _messages()}
    candidate = 1
    while candidate in taken:
        candidate += 1
    return str(candidate)


def deliver(payload):
    """Accept a message over HTTP.

    Not a MailCatcher endpoint --- MailCatcher only accepts mail over SMTP,
    which a mock cannot offer. It stands in for that delivery so the id scheme,
    the `formats` array and the read paths can all be exercised.
    """
    payload = payload or {}
    sender = _unbracket(payload.get("sender") or payload.get("from") or "")
    if not sender:
        return _error(400, "sender is required")
    if not _ADDRESS_RE.match(sender):
        return _error(400, f"sender {sender!r} is not a valid address")
    recipients = payload.get("recipients") or payload.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]
    recipients = [_unbracket(r) for r in recipients]
    if not recipients:
        return _error(400, "at least one recipient is required")
    for recipient in recipients:
        if not _ADDRESS_RE.match(recipient):
            return _error(400, f"recipient {recipient!r} is not a valid address")
    text = payload.get("plain") or payload.get("text") or ""
    html = payload.get("html") or ""
    if not text and not html:
        return _error(400, "a plain or html body is required")
    message_id = _next_id()
    row = {
        "id": message_id, "sender": sender, "recipients": recipients,
        "cc": [_unbracket(c) for c in (payload.get("cc") or [])],
        "subject": payload.get("subject", ""),
        "type": _type_for(text, html), "created_at": _now(),
        "text": text, "html": html,
    }
    _store_insert("messages", row)
    return {"__status__": 201, **message_representation(
        _store.table("messages").get(message_id)),
        "note": "not a MailCatcher endpoint; it stands in for the SMTP "
                "delivery a mock cannot accept"}


def _type_for(text, html):
    if text and html:
        return "multipart/alternative"
    return "text/html" if html else "text/plain"


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def service_info():
    """Not a MailCatcher endpoint --- a convenience summary of the capture."""
    return {"version": MAILCATCHER_VERSION, "ruby": RUBY_VERSION,
            "smtp": SMTP_BIND, "http": HTTP_BIND,
            "messages": len(_messages()),
            "note": "MailCatcher itself serves only the web UI at /; this "
                    "summary is a convenience for the mock"}


_store.eager_load()
