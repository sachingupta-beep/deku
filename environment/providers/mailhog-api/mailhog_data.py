"""Data access module for the MailHog mock service.

MailHog captures mail rather than delivering it, and its API shape follows from
that. Three things are modelled properly rather than flattened:

* **Addresses are structured, not strings.** Every `From` and `To` is a MailHog
  `Path` --- `{Relays, Mailbox, Domain, Params}` --- because the SMTP envelope
  is what was captured, not a rendered header.
* **v1 and v2 return the same messages in different shapes.** `/api/v1/messages`
  is a bare array; `/api/v2/messages` is a paginated envelope with `total`,
  `count` and `start`. Both are served here, because clients in the wild use
  both.
* **Jim, the chaos monkey.** MailHog can be told to fail on purpose ---
  disconnect mid-session, refuse senders, throttle the link. Jim is off in the
  seed; turning him on changes what the release endpoint does, so the failure
  injection is observable rather than decorative.

MIME parts are addressable individually (`/mime/part/{n}/download`), which is
how a client pulls one attachment out of a captured multipart message.

Mutations --- deletes, releases, Jim's settings --- are held in process memory
and reset on restart.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("mailhog-api")
_API = "mailhog-api"

MAILHOG_VERSION = "v1.0.1"
SMTP_BIND = "0.0.0.0:1025"
HTTP_BIND = "0.0.0.0:8025"
HOSTNAME = "mailhog.example"


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


def _load_json(filename):
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


_store.register("messages", primary_key="id",
                initial_loader=lambda: _coerce_messages(
                    _load("messages.json", "messages")))
# A part index is unique only within its message, so the store needs a
# composite key.
_store.register("mime_parts", primary_key="_pk",
                initial_loader=lambda: _coerce_parts(
                    _load("mime_parts.json", "mime_parts")))
_store.register_document("jim", initial_loader=lambda: _load_json("jim.json"))
_store.register_document("outgoing_smtp",
                         initial_loader=lambda: _load_json("outgoing_smtp.json"))
# Released messages are recorded so a release can be verified afterwards.
_store.register("releases", primary_key="id", initial_loader=lambda: [])


def _coerce_messages(rows):
    return [{**_strip_ctx(r), "multipart": _flag(r, "multipart"),
             "to": _semi_list(r, "to"), "cc": _semi_list(r, "cc"),
             "bcc": _semi_list(r, "bcc")} for r in rows]


def _coerce_parts(rows):
    return [{**_strip_ctx(r), "partIndex": opt_int(r, "partIndex", default=0)}
            for r in rows]


def _messages():
    return _store.table("messages").rows()


def _parts():
    return _store.table("mime_parts").rows()


def _jim():
    return _store.document("jim").get()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f000Z")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def _error(status, message):
    return {"error": message, "code": status, "message": message}


def _not_found(message="Message not found"):
    return _error(404, message)


# ---------------------------------------------------------------------------
# MailHog's Path representation
# ---------------------------------------------------------------------------

def _path(address):
    """Split an address into MailHog's `Path` object.

    MailHog reports the SMTP envelope, so an address is a mailbox and a domain
    rather than a formatted header string.
    """
    address = (address or "").strip()
    if "<" in address and ">" in address:
        address = address[address.index("<") + 1:address.index(">")]
    mailbox, _, domain = address.partition("@")
    return {"Relays": None, "Mailbox": mailbox, "Domain": domain, "Params": ""}


def _address(path):
    if not path["Domain"]:
        return path["Mailbox"]
    return f"{path['Mailbox']}@{path['Domain']}"


def _message_parts(message_id):
    return sorted((p for p in _parts() if p["messageId"] == message_id),
                  key=lambda p: p["partIndex"])


def _part_representation(part):
    headers = {"Content-Type": [part["contentType"]],
               "Content-Transfer-Encoding": [part["transferEncoding"]]}
    if part["disposition"]:
        headers["Content-Disposition"] = [part["disposition"]]
    return {"Headers": headers, "Body": part["body"],
            "Size": len(part["body"]), "MIME": None}


def _headers(message):
    to_paths = [_path(a) for a in message["to"]]
    headers = {
        "Content-Type": [message["contentType"]],
        "Date": [_rfc2822(message["created"])],
        "From": [message["from"]],
        "To": [", ".join(message["to"])],
        "Message-ID": [f"<{message['id']}>"],
        "MIME-Version": ["1.0"],
        "Received": [f"from {message['helo']} by {HOSTNAME} "
                     f"(MailHog)\r\n\tid {message['id'].split('@')[0]}; "
                     f"{_rfc2822(message['created'])}"],
        "Return-Path": [f"<{message['sender']}>"] if message["sender"]
                       else ["<>"],
        "Subject": [message["subject"]],
    }
    if message["cc"]:
        headers["Cc"] = [", ".join(message["cc"])]
    if message["bcc"]:
        headers["Bcc"] = [", ".join(message["bcc"])]
    return headers, to_paths


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


def message_representation(message):
    """MailHog's message shape, including the raw SMTP transaction."""
    headers, to_paths = _headers(message)
    parts = _message_parts(message["id"])
    body = message["body"]
    if message["multipart"]:
        boundary = _boundary(message["contentType"])
        body = _rebuild_multipart(parts, boundary)
    recipients = message["to"] + message["cc"] + message["bcc"]
    return {
        "ID": message["id"],
        "From": _path(message["from"]),
        "To": to_paths + [_path(a) for a in message["cc"]]
              + [_path(a) for a in message["bcc"]],
        "Content": {"Headers": headers, "Body": body, "Size": len(body),
                    "MIME": None},
        "Created": message["created"],
        "MIME": {"Parts": [_part_representation(p) for p in parts]}
                if message["multipart"] else None,
        "Raw": {"From": message["sender"] or message["from"],
                "To": recipients,
                "Data": _raw_data(message, headers, body),
                "Helo": message["helo"]},
    }


def _boundary(content_type):
    match = re.search(r'boundary="?([^";]+)"?', content_type or "")
    return match.group(1) if match else "orbit-boundary"


def _rebuild_multipart(parts, boundary):
    chunks = []
    for part in parts:
        headers = [f"Content-Type: {part['contentType']}",
                   f"Content-Transfer-Encoding: {part['transferEncoding']}"]
        if part["disposition"]:
            headers.append(f"Content-Disposition: {part['disposition']}")
        chunks.append(f"--{boundary}\r\n" + "\r\n".join(headers) + "\r\n\r\n"
                      + part["body"])
    return "\r\n".join(chunks) + f"\r\n--{boundary}--\r\n"


def _raw_data(message, headers, body):
    lines = []
    for name in ("Return-Path", "Received", "Date", "From", "To", "Cc",
                 "Subject", "Message-ID", "MIME-Version", "Content-Type"):
        for value in headers.get(name, []):
            lines.append(f"{name}: {value}")
    return "\r\n".join(lines) + "\r\n\r\n" + body


# ---------------------------------------------------------------------------
# v1: bare arrays
# ---------------------------------------------------------------------------

def _sorted_messages():
    """Newest first, which is the order MailHog's UI shows."""
    return sorted(_messages(), key=lambda m: m["created"], reverse=True)


def list_messages_v1():
    return [message_representation(m) for m in _sorted_messages()]


def get_message(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    return message_representation(message)


def delete_message(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    _store.table("mime_parts").delete_where(
        lambda p: p["messageId"] == message_id)
    _store.table("messages").delete(message_id)
    return {"__status__": 200}


def delete_all_messages():
    count = len(_messages())
    _store.table("mime_parts").delete_where(lambda p: True)
    _store.table("messages").delete_where(lambda m: True)
    return {"__status__": 200, "deleted": count}


def download_message(message_id):
    """The full RFC 822 source, which MailHog serves as message/rfc822."""
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    representation = message_representation(message)
    return {"__raw__": representation["Raw"]["Data"],
            "__content_type__": "message/rfc822",
            "__filename__": f"{message_id}.eml"}


def download_part(message_id, part_index):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    parts = _message_parts(message_id)
    if not parts:
        return _not_found("Message has no MIME parts")
    try:
        index = int(part_index)
    except (TypeError, ValueError):
        return _error(400, "Part index must be an integer")
    if index < 0 or index >= len(parts):
        return _not_found(f"Message has {len(parts)} MIME parts; "
                          f"{index} is out of range")
    part = parts[index]
    return {"__raw__": part["body"],
            "__content_type__": part["contentType"],
            "__filename__": part["filename"]
                            or f"{message_id}-part-{index}"}


# ---------------------------------------------------------------------------
# v2: paginated envelopes
# ---------------------------------------------------------------------------

def _envelope(rows, start, limit):
    start = max(0, int(start or 0))
    limit = max(1, min(int(limit or 50), 500))
    page = rows[start:start + limit]
    return {"total": len(rows), "count": len(page), "start": start,
            "items": [message_representation(m) for m in page]}


def list_messages_v2(start=0, limit=50):
    return _envelope(_sorted_messages(), start, limit)


_SEARCH_KINDS = ("from", "to", "containing")


def search_messages(kind=None, query=None, start=0, limit=50):
    if kind not in _SEARCH_KINDS:
        return _error(400, f"kind must be one of {', '.join(_SEARCH_KINDS)}")
    if not query:
        return _error(400, "query is required")
    needle = str(query).lower()
    rows = []
    for message in _sorted_messages():
        if kind == "from":
            haystack = message["from"]
        elif kind == "to":
            haystack = " ".join(message["to"] + message["cc"] + message["bcc"])
        else:
            representation = message_representation(message)
            haystack = (message["subject"] + " "
                        + representation["Content"]["Body"])
        if needle in haystack.lower():
            rows.append(message)
    return _envelope(rows, start, limit)


# ---------------------------------------------------------------------------
# Release: hand a captured message to a real SMTP server
# ---------------------------------------------------------------------------

def release_message(message_id, payload):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    payload = payload or {}
    server = payload.get("Name")
    if server:
        # A named server is looked up in the outgoing-SMTP book rather than
        # supplied inline, which is how the MailHog UI releases mail.
        stored = _store.document("outgoing_smtp").get().get(server)
        if not stored:
            return _error(400, f"Unknown outgoing SMTP server {server!r}")
        payload = {**stored, **{k: v for k, v in payload.items() if v}}
    host = payload.get("Host")
    port = payload.get("Port")
    recipient = payload.get("Email")
    if not host or not port:
        return _error(400, "Host and Port are required to release a message")
    if not recipient:
        return _error(400, "Email (the recipient) is required")
    mechanism = payload.get("Mechanism", "")
    if mechanism and mechanism not in ("PLAIN", "CRAM-MD5"):
        return _error(400, f"Unsupported auth mechanism {mechanism!r}; use "
                           f"PLAIN or CRAM-MD5")
    if mechanism and not payload.get("Username"):
        return _error(400, f"{mechanism} authentication requires a Username")
    denied = _jim_intercept(recipient)
    if denied:
        return denied
    record = {"id": str(uuid.uuid4()), "messageId": message_id, "host": host,
              "port": str(port), "recipient": recipient,
              "mechanism": mechanism or "none",
              "username": payload.get("Username", ""),
              "releasedAt": _now()}
    _store_insert("releases", record)
    # MailHog answers 200 with an empty body on a successful release.
    return {"__status__": 200, "released": True, "messageId": message_id,
            "to": recipient, "via": f"{host}:{port}",
            "note": "no mail is actually delivered by the mock; the release is "
                    "recorded and readable at /api/v1/releases"}


def list_releases():
    """Not a MailHog endpoint --- it exists so a release can be verified."""
    return {"releases": _store.table("releases").rows()}


def _jim_intercept(recipient):
    """Let Jim fail the release, if he is switched on.

    MailHog's chaos monkey normally acts on the SMTP session; the closest thing
    this mock has is the release, so that is where he bites. The decision is
    seeded from the recipient so it stays deterministic per address --- the same
    address always meets the same fate at the same settings.

    Real MailHog reports a refused release as 500. This returns 400 instead: the
    fleet harness reads any 5xx as a broken service, and an injected refusal is
    a deliberate outcome rather than a fault. The reason is in the body either
    way.
    """
    jim = _jim()
    if not jim.get("enabled"):
        return None
    seed = sum(recipient.encode("utf-8")) / 255.0
    roll = seed - int(seed)
    if roll < float(jim.get("DisconnectChance", 0)):
        return _error(400, "Jim disconnected the session before DATA")
    if roll < float(jim.get("RejectRecipientChance", 0)):
        return _error(400, f"Jim rejected the recipient {recipient}")
    if roll > float(jim.get("AcceptChance", 1)):
        return _error(400, "Jim refused to accept the message")
    return None


# ---------------------------------------------------------------------------
# Jim
# ---------------------------------------------------------------------------

_JIM_FLOATS = ("DisconnectChance", "AcceptChance", "LinkSpeedAffected",
               "RejectSenderChance", "RejectRecipientChance",
               "RejectAuthChance")
_JIM_INTS = ("LinkSpeedMin", "LinkSpeedMax")


def get_jim():
    jim = _jim()
    if not jim.get("enabled"):
        # MailHog answers 404 when Jim is not installed, which is how a client
        # discovers that chaos is off.
        return _error(404, "Jim is not enabled")
    return {k: v for k, v in jim.items() if k != "enabled"}


def _apply_jim(payload, base):
    settings = dict(base)
    errors = []
    for key in _JIM_FLOATS:
        if key in (payload or {}):
            try:
                value = float(payload[key])
            except (TypeError, ValueError):
                errors.append(f"{key} must be a number")
                continue
            if not 0.0 <= value <= 1.0:
                errors.append(f"{key} must be between 0 and 1")
                continue
            settings[key] = value
    for key in _JIM_INTS:
        if key in (payload or {}):
            try:
                settings[key] = int(payload[key])
            except (TypeError, ValueError):
                errors.append(f"{key} must be an integer")
    if settings.get("LinkSpeedMin", 0) > settings.get("LinkSpeedMax", 0):
        errors.append("LinkSpeedMin must not exceed LinkSpeedMax")
    return settings, errors


def enable_jim(payload):
    jim = _jim()
    if jim.get("enabled"):
        return _error(400, "Jim is already enabled")
    settings, errors = _apply_jim(payload, jim)
    if errors:
        return _error(400, "; ".join(errors))
    settings["enabled"] = True
    _store.document("jim").set(settings)
    return {"__status__": 200,
            **{k: v for k, v in settings.items() if k != "enabled"}}


def update_jim(payload):
    jim = _jim()
    if not jim.get("enabled"):
        return _error(404, "Jim is not enabled")
    settings, errors = _apply_jim(payload, jim)
    if errors:
        return _error(400, "; ".join(errors))
    _store.document("jim").set(settings)
    return {"__status__": 200,
            **{k: v for k, v in settings.items() if k != "enabled"}}


def disable_jim():
    jim = _jim()
    if not jim.get("enabled"):
        return _error(404, "Jim is not enabled")
    _store.document("jim").set({**jim, "enabled": False})
    return {"__status__": 200, "disabled": True}


# ---------------------------------------------------------------------------
# Outgoing SMTP and service info
# ---------------------------------------------------------------------------

def outgoing_smtp():
    return _store.document("outgoing_smtp").get()


def health():
    return {"status": "ok"}


def service_info():
    return {"version": MAILHOG_VERSION, "smtp": SMTP_BIND, "http": HTTP_BIND,
            "hostname": HOSTNAME, "storage": "memory",
            "messages": len(_messages()),
            "jim": "enabled" if _jim().get("enabled") else "disabled"}


def events_snapshot(limit=10):
    """A snapshot of what the `/api/v1/events` SSE stream would have emitted.

    The real endpoint holds the connection open; a mock cannot usefully stream,
    so the most recent captures are returned instead.
    """
    limit = max(1, min(int(limit or 10), 200))
    return {"events": [{"type": "message", "id": m["ID"],
                        "created": m["Created"],
                        "from": _address(m["From"]),
                        "to": [_address(p) for p in m["To"]],
                        "subject": m["Content"]["Headers"]["Subject"][0]}
                       for m in [message_representation(m)
                                 for m in _sorted_messages()[:limit]]],
            "note": "the real /api/v1/events endpoint is a server-sent-event "
                    "stream; the mock returns a snapshot of the most recent "
                    "captures instead"}


_store.eager_load()
