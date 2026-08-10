"""Data access module for the Inbucket mock service.

Inbucket is a third model again, and the difference from MailHog and Mailpit is
structural rather than cosmetic:

* **There is no global inbox.** Every read names a mailbox --- there is no
  endpoint that lists all captured mail, and no endpoint that lists the
  mailboxes either. A client is expected to know the address it sent to. The
  monitor is the only cross-mailbox view.
* **The mailbox is *derived* from the address, not stored.** Under the default
  `local` policy the mailbox is the local part, lowercased, with any
  subaddress stripped. So `Amelia.Ortega@orbit-labs.com`,
  `amelia.ortega+billing@orbit-labs.com` and `AMELIA.ORTEGA@acme-partner.example`
  are three addresses, two domains, and **one mailbox**. The `{name}` path
  segment accepts either form and is put through the same policy.
* **Every mailbox exists.** An unknown one is `200 []`, never a 404 --- there is
  nothing to create, so there is nothing to be missing.
* **A message to two recipients is two messages.** Inbucket stores a copy per
  mailbox, each with its own id and its own `seen` flag.
* **Deletion is per-mailbox.** `DELETE /api/v1/mailbox/{name}` purges one
  mailbox; nothing empties the server.

The keys are hyphenated (`posix-millis`, `content-type`, `download-link`)
because Inbucket's are, and messages list **oldest first** --- arrival order ---
where MailHog and Mailpit list newest first.

Mutations --- deliveries, seen flags, deletes and purges --- are held in process
memory and reset on restart.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("inbucket-api")
_API = "inbucket-api"

INBUCKET_VERSION = "3.1.0"
BUILD_DATE = "2026-02-11T08:41:03Z"


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


def _coerce_messages(rows):
    return [{**_strip_ctx(r), "seen": _flag(r, "seen"),
             "to": _semi_list(r, "to"), "cc": _semi_list(r, "cc")}
            for r in rows]


def _coerce_attachments(rows):
    return [{**_strip_ctx(r), "index": opt_int(r, "index", default=0),
             "size": opt_int(r, "size", default=0)} for r in rows]


_store.register("messages", primary_key="id",
                initial_loader=lambda: _coerce_messages(
                    _load("messages.json", "messages")))
# An attachment index is unique only within its message, so the store needs a
# composite key.
_store.register("attachments", primary_key="_pk",
                initial_loader=lambda: _coerce_attachments(
                    _load("attachments.json", "attachments")))
_store.register_document("config",
                         initial_loader=lambda: _load_json("config.json"))
_store.register_document("expvars",
                         initial_loader=lambda: _load_json("expvars.json"))


def _messages():
    return _store.table("messages").rows()


def _config():
    return _store.document("config").get()


def _expvars():
    return _store.document("expvars").get()


def _bump(counter, amount=1):
    counters = dict(_expvars())
    counters[counter] = counters.get(counter, 0) + amount
    _store.document("expvars").set(counters)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def _error(status, message):
    return {"error": message, "code": status, "message": message}


def _not_found(message="message not found"):
    return _error(404, message)


# ---------------------------------------------------------------------------
# The mailbox naming policy
# ---------------------------------------------------------------------------

_ANGLE_RE = re.compile(r"<([^>]*)>")


def _bare_address(value):
    """Strip a display name, leaving the address itself."""
    match = _ANGLE_RE.search(value or "")
    return (match.group(1) if match else (value or "")).strip()


def mailbox_for(name):
    """Derive the mailbox Inbucket stores an address under.

    This is the heart of the service. The `{name}` path segment may be a bare
    mailbox name or a full address, and either goes through the same policy, so
    `GET /api/v1/mailbox/Amelia.Ortega+billing@orbit-labs.com` and
    `GET /api/v1/mailbox/amelia.ortega` read the same mailbox.
    """
    config = _config()
    address = _bare_address(name)
    if config.get("mailboxNaming") == "full":
        derived = address
    else:
        local, _, _domain = address.partition("@")
        delimiter = config.get("subaddressDelimiter", "+")
        if config.get("stripSubaddress", True) and delimiter in local:
            local = local.split(delimiter, 1)[0]
        derived = local
    return derived if config.get("caseSensitive") else derived.lower()


def _mailbox_rows(mailbox):
    """Oldest first --- arrival order, which is what Inbucket shows."""
    return sorted((m for m in _messages() if m["mailbox"] == mailbox),
                  key=lambda m: (m["date"], m["id"]))


def _message_in(mailbox, message_id):
    message = _store.table("messages").get(message_id)
    if not message or message["mailbox"] != mailbox:
        return None
    return message


def _attachments(message_id):
    return sorted((a for a in _store.table("attachments").rows()
                   if a["messageId"] == message_id),
                  key=lambda a: a["index"])


# ---------------------------------------------------------------------------
# Representations
# ---------------------------------------------------------------------------

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
           "Oct", "Nov", "Dec"]
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parsed(stamp):
    try:
        return datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return None


def _rfc2822(stamp):
    moment = _parsed(stamp)
    if not moment:
        return stamp
    return (f"{_DAYS[moment.weekday()]}, {moment.day:02d} "
            f"{_MONTHS[moment.month - 1]} {moment.year} "
            f"{moment.strftime('%H:%M:%S')} +0000")


def _posix_millis(stamp):
    moment = _parsed(stamp)
    return int(moment.timestamp() * 1000) if moment else 0


def _boundary(message_id):
    return f"==_inbucket_{message_id}"


def _headers(message):
    headers = {
        "Date": [_rfc2822(message["date"])],
        "From": [message["from"]],
        "To": [", ".join(message["to"])],
        "Subject": [message["subject"]],
        "Message-ID": [f"<{message['id']}@inbucket.example>"],
        "Delivered-To": [message["deliveredTo"]],
        "MIME-Version": ["1.0"],
        "Content-Type": [_content_type(message)],
    }
    if message["cc"]:
        headers["Cc"] = [", ".join(message["cc"])]
    return headers


def _content_type(message):
    if _attachments(message["id"]):
        return f'multipart/mixed; boundary="{_boundary(message["id"])}"'
    if message["html"] and message["text"]:
        return f'multipart/alternative; boundary="{_boundary(message["id"])}"'
    if message["html"]:
        return "text/html; charset=UTF-8"
    return "text/plain; charset=UTF-8"


def _body_source(message):
    parts = _attachments(message["id"])
    if not parts and not (message["html"] and message["text"]):
        return message["html"] or message["text"]
    boundary = _boundary(message["id"])
    chunks = []
    if message["text"]:
        chunks.append("Content-Type: text/plain; charset=UTF-8\r\n\r\n"
                      + message["text"])
    if message["html"]:
        chunks.append("Content-Type: text/html; charset=UTF-8\r\n\r\n"
                      + message["html"])
    for part in parts:
        chunks.append(f"Content-Type: {part['contentType']}\r\n"
                      f"Content-Transfer-Encoding: base64\r\n"
                      f'Content-Disposition: attachment; '
                      f'filename="{part["filename"]}"\r\n\r\n' + part["body"])
    return ("".join(f"--{boundary}\r\n{c}\r\n" for c in chunks)
            + f"--{boundary}--\r\n")


def message_source(message):
    headers = "\r\n".join(f"{name}: {value}"
                          for name, values in _headers(message).items()
                          for value in values)
    return headers + "\r\n\r\n" + _body_source(message)


def _size(message):
    return len(message_source(message).encode("utf-8"))


def header_representation(message):
    """The list shape --- headers only, no bodies and no attachments."""
    return {
        "mailbox": message["mailbox"],
        "id": message["id"],
        "from": message["from"],
        "to": message["to"],
        "subject": message["subject"],
        "date": message["date"],
        "posix-millis": _posix_millis(message["date"]),
        "size": _size(message),
        "seen": message["seen"],
    }


def _attachment_representation(message, part):
    link = (f"/api/v1/mailbox/{message['mailbox']}/{message['id']}"
            f"/attach/{part['index']}/{part['filename']}")
    return {
        "filename": part["filename"],
        "content-type": part["contentType"],
        "download-link": link,
        "view-link": link,
        "md5": part["md5"],
        "size": part["size"],
    }


def message_representation(message):
    """The read shape --- headers, both bodies, and the attachment list."""
    return {
        **header_representation(message),
        "header": _headers(message),
        "body": {"text": message["text"], "html": message["html"]},
        "attachments": [_attachment_representation(message, p)
                        for p in _attachments(message["id"])],
    }


# ---------------------------------------------------------------------------
# Mailbox reads
# ---------------------------------------------------------------------------

def list_mailbox(name):
    """An unknown mailbox is an empty list, not a 404 --- they all exist."""
    mailbox = mailbox_for(name)
    return [header_representation(m) for m in _mailbox_rows(mailbox)]


def get_message(name, message_id):
    mailbox = mailbox_for(name)
    message = _message_in(mailbox, message_id)
    if not message:
        return _not_found(f"message {message_id} not found in mailbox "
                          f"{mailbox}")
    return message_representation(message)


def get_source(name, message_id):
    mailbox = mailbox_for(name)
    message = _message_in(mailbox, message_id)
    if not message:
        return _not_found(f"message {message_id} not found in mailbox "
                          f"{mailbox}")
    return {"__raw__": message_source(message),
            "__content_type__": "text/plain; charset=utf-8",
            "__filename__": f"{message_id}.eml"}


def get_attachment(name, message_id, index, filename):
    """Inbucket puts the filename in the path, and checks it."""
    mailbox = mailbox_for(name)
    message = _message_in(mailbox, message_id)
    if not message:
        return _not_found(f"message {message_id} not found in mailbox "
                          f"{mailbox}")
    parts = _attachments(message_id)
    try:
        position = int(index)
    except (TypeError, ValueError):
        return _error(400, "attachment index must be an integer")
    if position < 0 or position >= len(parts):
        return _not_found(f"message {message_id} has {len(parts)} "
                          f"attachment(s); {position} is out of range")
    part = parts[position]
    if filename != part["filename"]:
        return _not_found(f"attachment {position} of {message_id} is "
                          f"{part['filename']!r}, not {filename!r}")
    return {"__raw__": part["body"], "__content_type__": part["contentType"],
            "__filename__": part["filename"]}


# ---------------------------------------------------------------------------
# Mailbox writes
# ---------------------------------------------------------------------------

def mark_seen(name, message_id, payload):
    mailbox = mailbox_for(name)
    message = _message_in(mailbox, message_id)
    if not message:
        return _not_found(f"message {message_id} not found in mailbox "
                          f"{mailbox}")
    payload = payload or {}
    if "seen" not in payload:
        return _error(400, "seen is required and must be a boolean")
    if not isinstance(payload["seen"], bool):
        return _error(400, "seen must be a boolean")
    _store.table("messages").upsert({**message, "seen": payload["seen"]})
    return {"mailbox": mailbox, "id": message_id, "seen": payload["seen"]}


def _drop(message):
    _store.table("attachments").delete_where(
        lambda a, _id=message["id"]: a["messageId"] == _id)
    _store.table("messages").delete(message["id"])


def delete_message(name, message_id):
    mailbox = mailbox_for(name)
    message = _message_in(mailbox, message_id)
    if not message:
        return _not_found(f"message {message_id} not found in mailbox "
                          f"{mailbox}")
    _drop(message)
    _bump("retentionDeletesTotal")
    return {"mailbox": mailbox, "id": message_id, "deleted": True}


def purge_mailbox(name):
    """Per-mailbox, because nothing in Inbucket empties the whole server."""
    mailbox = mailbox_for(name)
    rows = _mailbox_rows(mailbox)
    for message in rows:
        _drop(message)
    if rows:
        _bump("retentionDeletesTotal", len(rows))
    return {"mailbox": mailbox, "purged": len(rows)}


_ADDRESS_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def deliver(name, payload):
    """Accept a message for a mailbox.

    Not an Inbucket endpoint --- Inbucket only accepts mail over SMTP, which a
    mock cannot offer. It stands in for that delivery so the naming policy, the
    per-mailbox cap and the read paths can all be exercised, and the response
    reports which mailbox the address resolved to.
    """
    payload = payload or {}
    sender = payload.get("from") or payload.get("From")
    if not sender:
        return _error(400, "from is required")
    if not _ADDRESS_RE.match(_bare_address(sender)):
        return _error(400, f"from is not a valid address: {sender!r}")
    if not _ADDRESS_RE.match(_bare_address(name)) and "@" in name:
        return _error(400, f"{name!r} is neither a mailbox name nor a valid "
                           f"address")
    mailbox = mailbox_for(name)
    recipients = payload.get("to") or payload.get("To") or [name]
    if isinstance(recipients, str):
        recipients = [recipients]
    stamp = _now()
    message_id = _next_id(stamp)
    row = {
        "id": message_id,
        "mailbox": mailbox,
        "from": sender,
        "to": list(recipients),
        "cc": list(payload.get("cc") or payload.get("Cc") or []),
        "deliveredTo": _bare_address(name),
        "subject": payload.get("subject") or payload.get("Subject") or "",
        "date": stamp,
        "seen": False,
        "text": payload.get("text") or payload.get("Text") or "",
        "html": payload.get("html") or payload.get("Html") or "",
    }
    _store_insert("messages", row)
    _bump("smtpReceivedTotal")
    _bump("smtpConnectsTotal")
    evicted = _enforce_cap(mailbox)
    return {"__status__": 201, "mailbox": mailbox, "id": message_id,
            "addressedTo": _bare_address(name), "evicted": evicted,
            "note": "not an Inbucket endpoint; it stands in for the SMTP "
                    "delivery a mock cannot accept"}


def _next_id(stamp):
    """Inbucket's ids are the arrival time plus a per-server sequence.

    The sequence walks past anything already taken, so purging a mailbox and
    delivering again cannot reuse a live id.
    """
    prefix = stamp.replace("-", "").replace(":", "").replace("Z", "")
    table = _store.table("messages")
    sequence = len(_messages()) + 1
    while table.get(f"{prefix}-{sequence:04d}"):
        sequence += 1
    return f"{prefix}-{sequence:04d}"


def _enforce_cap(mailbox):
    """Inbucket drops the oldest message once a mailbox is over its cap."""
    cap = _config().get("mailboxMessageCap", 0)
    if not cap:
        return []
    rows = _mailbox_rows(mailbox)
    evicted = []
    while len(rows) > cap:
        oldest = rows.pop(0)
        _drop(oldest)
        evicted.append(oldest["id"])
    if evicted:
        _bump("retentionDeletesTotal", len(evicted))
    return evicted


# ---------------------------------------------------------------------------
# Monitor: the only cross-mailbox view
# ---------------------------------------------------------------------------

def monitor_messages(limit=None):
    """A snapshot of what the `/monitor/messages` SSE stream would have emitted.

    The real endpoint holds the connection open; a mock cannot usefully stream,
    so the most recent deliveries across every mailbox are returned instead.
    This is the only place the API shows more than one mailbox at a time.
    """
    limit = limit or _config().get("monitorHistory", 30)
    rows = sorted(_messages(), key=lambda m: (m["date"], m["id"]),
                  reverse=True)[:limit]
    return {"messages": [header_representation(m) for m in rows],
            "note": "the real /api/v1/monitor/messages endpoint is a "
                    "server-sent-event stream; the mock returns a snapshot of "
                    "the most recent deliveries instead"}


def monitor_mailbox(name, limit=None):
    limit = limit or _config().get("monitorHistory", 30)
    mailbox = mailbox_for(name)
    rows = list(reversed(_mailbox_rows(mailbox)))[:limit]
    return {"mailbox": mailbox,
            "messages": [header_representation(m) for m in rows],
            "note": "the real /api/v1/monitor/mailbox/{name} endpoint is a "
                    "server-sent-event stream; the mock returns a snapshot "
                    "instead"}


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def status():
    config = _config()
    mailboxes = sorted({m["mailbox"] for m in _messages()})
    return {
        "version": INBUCKET_VERSION,
        "build-date": BUILD_DATE,
        "smtp-listener": config.get("smtpAddr"),
        "pop3-listener": config.get("pop3Addr"),
        "web-listener": config.get("webAddr"),
        "storage": config.get("storageType"),
        "mailbox-naming": config.get("mailboxNaming"),
        "case-sensitive": config.get("caseSensitive"),
        "strip-subaddress": config.get("stripSubaddress"),
        "mailbox-message-cap": config.get("mailboxMessageCap"),
        "retention-period": config.get("retentionPeriod"),
        "monitor-visible": config.get("monitorVisible"),
        "messages": len(_messages()),
        "mailboxes-with-mail": len(mailboxes),
    }


def debug_vars():
    counters = _expvars()
    return {
        **{k: v for k, v in counters.items() if k != "uptimeSeconds"},
        "retainedCurrent": len(_messages()),
        "retainedSize": sum(_size(m) for m in _messages()),
        "uptimeSeconds": counters.get("uptimeSeconds", 0),
    }


_store.eager_load()
