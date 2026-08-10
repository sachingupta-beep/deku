"""Data access module for the smtp4dev mock service.

smtp4dev is a .NET application, and it shows in every contract. Five things
follow from that and are modelled rather than smoothed into the shape the other
capture tools use:

* **Pages, not offsets.** Every list is a `PagedResult`:
  `{results, firstRowOnPage, lastRowOnPage, currentPage, pageCount, pageSize,
  rowCount}`, driven by `page` (1-based), `pageSize`, `sortColumn` and
  `sortIsDescending`. MailHog counts from a `start` offset; Mailpit does too;
  smtp4dev counts pages.
* **Sessions are first-class, and separate from messages.** A session is the
  SMTP *conversation*, kept with its full transcript --- including the ones that
  produced no message at all, because the client failed to authenticate or hung
  up after a rejected recipient. Nothing else in this fleet keeps the
  conversation.
* **Mailboxes are recipient-matching rules.** Mail is filed by testing the
  recipient against each mailbox's pattern, with `Default` as the catch-all.
  Inbucket *derives* a mailbox from the address; smtp4dev *routes* to one.
* **MIME parts are a tree, not a list.** Parts are addressed by section number
  (`1`, `1.1`, `1.1.2`), and a container part has children rather than content.
* **The server settings are writable.** `POST /api/Server` is the Settings
  dialog, and lowering `numberOfMessagesToKeep` trims the store on the spot.

Mutations --- deliveries, read flags, relays, deletes and settings --- are held
in process memory and reset on restart.
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
    read_seed_with_ctx, get_store, opt_str)

_store = get_store("smtp4dev-api")
_API = "smtp4dev-api"

SMTP4DEV_VERSION = "3.8.6"
FRAMEWORK = ".NET 8.0.11"
DEFAULT_MAILBOX = "Default"
SECURE_MODES = ("None", "StartTls", "ImplicitTls", "StartTlsWhenAvailable")


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
    return [{**_strip_ctx(r), "isUnread": _flag(r, "isUnread"),
             "isRelayed": _flag(r, "isRelayed"),
             "secureConnection": _flag(r, "secureConnection"),
             "to": _comma_list(r, "to"), "cc": _comma_list(r, "cc"),
             "bcc": _comma_list(r, "bcc")} for r in rows]


def _comma_list(row, column):
    """Recipients are comma-separated here, as they are in an SMTP header."""
    raw = opt_str(row, column, default="")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _coerce_parts(rows):
    return [{**_strip_ctx(r), "isAttachment": _flag(r, "isAttachment"),
             "warnings": _semi_list(r, "warnings")} for r in rows]


def _coerce_sessions(rows):
    return [{**_strip_ctx(r),
             "terminatedWithError": _flag(r, "terminatedWithError"),
             "secureConnection": _flag(r, "secureConnection")} for r in rows]


def _coerce_mailboxes(rows):
    return [{**_strip_ctx(r), "recipients": _semi_list(r, "recipients")}
            for r in rows]


_store.register("messages", primary_key="id",
                initial_loader=lambda: _coerce_messages(
                    _load("messages.json", "messages")))
# A part's section number is unique only within its message, so the store needs
# a composite key.
_store.register("parts", primary_key="_pk",
                initial_loader=lambda: _coerce_parts(
                    _load("parts.json", "parts")))
_store.register("sessions", primary_key="id",
                initial_loader=lambda: _coerce_sessions(
                    _load("sessions.json", "sessions")))
_store.register("mailboxes", primary_key="name",
                initial_loader=lambda: _coerce_mailboxes(
                    _load("mailboxes.json", "mailboxes")))
_store.register_document("server",
                         initial_loader=lambda: _load_json("server.json"))


def _messages():
    return _store.table("messages").rows()


def _sessions():
    return _store.table("sessions").rows()


def _mailboxes():
    return _store.table("mailboxes").rows()


def _server():
    return _store.document("server").get()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def _error(status, message):
    return {"error": message, "code": status, "message": message}


def _not_found(message="Message not found"):
    return _error(404, message)


# ---------------------------------------------------------------------------
# The PagedResult envelope
# ---------------------------------------------------------------------------

def _paged(rows, page, page_size, render):
    """smtp4dev's PagedResult: 1-based pages, not a start offset."""
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 25), 200))
    row_count = len(rows)
    page_count = max(1, -(-row_count // page_size))
    start = (page - 1) * page_size
    window = rows[start:start + page_size]
    return {
        "results": [render(r) for r in window],
        "firstRowOnPage": start + 1 if window else 0,
        "lastRowOnPage": start + len(window),
        "currentPage": page,
        "pageCount": page_count,
        "pageSize": page_size,
        "rowCount": row_count,
    }


def _sorted(rows, sort_column, descending, allowed, default_column, key_of):
    if sort_column and sort_column not in allowed:
        return None, _error(400, f"sortColumn '{sort_column}' is not sortable; "
                                 f"expected one of {', '.join(sorted(allowed))}")
    column = sort_column or default_column
    return sorted(rows, key=lambda r: key_of(r, column),
                  reverse=bool(descending)), None


# ---------------------------------------------------------------------------
# Mailbox routing
# ---------------------------------------------------------------------------

def _pattern(rule):
    return re.compile("^" + ".*".join(re.escape(p) for p in rule.split("*"))
                      + "$", re.IGNORECASE)


def mailbox_for(recipient):
    """Route a recipient to a mailbox by matching each mailbox's rule.

    smtp4dev *routes* to a mailbox; Inbucket *derives* one from the address.
    `Default` is the catch-all and is only used when nothing else claims the
    recipient, so it is checked last regardless of seed order.
    """
    named = [m for m in _mailboxes() if m["name"] != DEFAULT_MAILBOX]
    for mailbox in sorted(named, key=lambda m: m["name"]):
        for rule in mailbox["recipients"]:
            if _pattern(rule).match(recipient or ""):
                return mailbox["name"]
    return DEFAULT_MAILBOX


def list_mailboxes():
    return [{"name": m["name"], "recipients": m["recipients"],
             "description": m["description"],
             "messageCount": len([x for x in _messages()
                                  if x["mailbox"] == m["name"]])}
            for m in sorted(_mailboxes(), key=lambda m: m["name"])]


# ---------------------------------------------------------------------------
# MIME parts: a tree, addressed by section number
# ---------------------------------------------------------------------------

def _parts(message_id):
    return sorted((p for p in _store.table("parts").rows()
                   if p["messageId"] == message_id),
                  key=lambda p: [int(n) for n in p["partId"].split(".")])


def _part(message_id, part_id):
    for part in _parts(message_id):
        if part["partId"] == part_id:
            return part
    return None


def _part_node(part, children):
    return {
        "id": part["partId"],
        "name": part["name"],
        "contentType": part["contentType"],
        "messageId": part["messageId"],
        "isAttachment": part["isAttachment"],
        "fileName": part["fileName"],
        "contentId": part["contentId"],
        "size": len(part["body"].encode("utf-8")),
        "headers": _part_headers(part),
        "warnings": part["warnings"],
        "childParts": children,
    }


def _part_headers(part):
    headers = [{"name": "Content-Type", "value": part["contentType"]}]
    if part["isAttachment"]:
        headers.append({"name": "Content-Transfer-Encoding", "value": "base64"})
        headers.append({"name": "Content-Disposition",
                        "value": f'attachment; filename="{part["fileName"]}"'})
    if part["contentId"]:
        headers.append({"name": "Content-ID", "value": f"<{part['contentId']}>"})
    return headers


def _part_tree(message_id, parent_id=""):
    """Assemble the flat rows into the tree smtp4dev returns."""
    return [_part_node(p, _part_tree(message_id, p["partId"]))
            for p in _parts(message_id) if p["parentId"] == parent_id]


def _leaf_of_type(message_id, prefix):
    for part in _parts(message_id):
        if part["contentType"].startswith(prefix) and not part["isAttachment"]:
            return part
    return None


# ---------------------------------------------------------------------------
# Representations
# ---------------------------------------------------------------------------

def _attachment_count(message):
    return len([p for p in _parts(message["id"]) if p["isAttachment"]])


def summary_representation(message):
    """The list shape: no bodies, no parts, but the relay and parse state."""
    return {
        "id": message["id"],
        "mailbox": message["mailbox"],
        "from": message["from"],
        "to": message["to"],
        "receivedDate": message["receivedDate"],
        "subject": message["subject"],
        "attachmentCount": _attachment_count(message),
        "isUnread": message["isUnread"],
        "isRelayed": message["isRelayed"],
        "deliveredTo": message["deliveredTo"],
        "hasMimeParseError": bool(message["mimeParseError"]),
    }


def message_representation(message):
    """The read shape: headers, the part tree, and both error fields."""
    return {
        "id": message["id"],
        "mailbox": message["mailbox"],
        "from": message["from"],
        "to": message["to"],
        "cc": message["cc"],
        "bcc": message["bcc"],
        "deliveredTo": message["deliveredTo"],
        "receivedDate": message["receivedDate"],
        "subject": message["subject"],
        "isUnread": message["isUnread"],
        "isRelayed": message["isRelayed"],
        "relayError": message["relayError"],
        "mimeParseError": message["mimeParseError"],
        "secureConnection": message["secureConnection"],
        "sessionId": message["sessionId"],
        "attachmentCount": _attachment_count(message),
        "headers": _message_headers(message),
        "parts": _part_tree(message["id"]),
    }


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


def _message_headers(message):
    """A list of name/value pairs, which is smtp4dev's shape --- not a map."""
    root = _part(message["id"], "1")
    headers = [{"name": "Date", "value": _rfc2822(message["receivedDate"])},
               {"name": "From", "value": message["from"]},
               {"name": "To", "value": ", ".join(message["to"])}]
    if message["cc"]:
        headers.append({"name": "Cc", "value": ", ".join(message["cc"])})
    headers.append({"name": "Subject", "value": message["subject"]})
    headers.append({"name": "Message-ID",
                    "value": f"<{message['id']}@smtp4dev.orbit-labs.local>"})
    headers.append({"name": "MIME-Version", "value": "1.0"})
    headers.append({"name": "Content-Type",
                    "value": root["contentType"] if root
                             else "text/plain; charset=utf-8"})
    return headers


def _boundary(message_id, part_id):
    return f"==_orbit_{message_id[:8]}_{part_id.replace('.', '_')}"


def _part_source(message, part):
    header_lines = "\r\n".join(f"{h['name']}: {h['value']}"
                               for h in _part_headers(part))
    children = [p for p in _parts(message["id"])
                if p["parentId"] == part["partId"]]
    if not children:
        return header_lines + "\r\n\r\n" + part["body"]
    boundary = _boundary(message["id"], part["partId"])
    header_lines = header_lines.replace(
        part["contentType"], f'{part["contentType"]}; boundary="{boundary}"')
    chunks = "".join(f"--{boundary}\r\n{_part_source(message, c)}\r\n"
                     for c in children)
    return header_lines + "\r\n\r\n" + chunks + f"--{boundary}--\r\n"


def message_source(message):
    root = _part(message["id"], "1")
    envelope = "\r\n".join(f"{h['name']}: {h['value']}"
                           for h in _message_headers(message)
                           if h["name"] != "Content-Type")
    if not root:
        return envelope + "\r\n\r\n" + message["text"]
    return envelope + "\r\n" + _part_source(message, root)


def session_representation(session, with_log=False):
    body = {
        "id": session["id"],
        "clientAddress": session["clientAddress"],
        "clientName": session["clientName"],
        "startDate": session["startDate"],
        "endDate": session["endDate"],
        "numberOfMessages": len([m for m in _messages()
                                 if m["sessionId"] == session["id"]]),
        "terminatedWithError": session["terminatedWithError"],
        "sessionErrorType": session["sessionErrorType"],
        "sessionError": session["sessionError"],
        "secureConnection": session["secureConnection"],
        "authenticatedUser": session["authenticatedUser"],
    }
    if with_log:
        body["log"] = session["log"]
    return body


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

_MESSAGE_SORTS = {"receivedDate", "from", "to", "subject", "attachmentCount",
                  "isUnread", "mailbox"}


def _message_key(message, column):
    if column == "to":
        return ", ".join(message["to"]).lower()
    if column == "attachmentCount":
        return _attachment_count(message)
    if column == "isUnread":
        return message["isUnread"]
    value = message.get(column, "")
    return value.lower() if isinstance(value, str) else value


def _matches_search(message, terms):
    haystack = " ".join([message["from"], ", ".join(message["to"]),
                         ", ".join(message["cc"]), message["subject"],
                         message["text"], message["html"]]).lower()
    return terms.lower() in haystack


def list_messages(mailbox_name=None, search_terms=None, sort_column=None,
                  sort_is_descending=True, page=1, page_size=25):
    rows = list(_messages())
    if mailbox_name:
        if not _store.table("mailboxes").get(mailbox_name):
            return _not_found(f"Mailbox '{mailbox_name}' does not exist")
        rows = [m for m in rows if m["mailbox"] == mailbox_name]
    if search_terms:
        rows = [m for m in rows if _matches_search(m, search_terms)]
    rows, failure = _sorted(rows, sort_column, sort_is_descending,
                            _MESSAGE_SORTS, "receivedDate", _message_key)
    if failure:
        return failure
    return _paged(rows, page, page_size, summary_representation)


def get_message(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    return message_representation(message)


def get_source(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    return {"__raw__": message_source(message),
            "__content_type__": "message/rfc822",
            "__filename__": f"{message_id}.eml"}


def get_html(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    part = _leaf_of_type(message_id, "text/html")
    if not part:
        return _not_found("Message has no text/html part")
    return {"__raw__": part["body"], "__content_type__": "text/html",
            "__filename__": f"{message_id}.html"}


def get_plaintext(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    part = _leaf_of_type(message_id, "text/plain")
    if not part:
        return _not_found("Message has no text/plain part")
    return {"__raw__": part["body"], "__content_type__": "text/plain",
            "__filename__": f"{message_id}.txt"}


def get_part_content(message_id, part_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    part = _part(message_id, part_id)
    if not part:
        return _not_found(f"Message has no part '{part_id}'; it has "
                          f"{', '.join(p['partId'] for p in _parts(message_id))}")
    if not part["body"]:
        return _error(400, f"Part '{part_id}' is a {part['contentType']} "
                           f"container and has no content of its own")
    return {"__raw__": part["body"],
            "__content_type__": part["contentType"],
            "__filename__": part["fileName"] or f"{message_id}-{part_id}"}


def get_part_source(message_id, part_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    part = _part(message_id, part_id)
    if not part:
        return _not_found(f"Message has no part '{part_id}'; it has "
                          f"{', '.join(p['partId'] for p in _parts(message_id))}")
    return {"__raw__": _part_source(message, part),
            "__content_type__": "text/plain; charset=utf-8",
            "__filename__": f"{message_id}-{part_id}.txt"}


def mark_read(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    _store.table("messages").upsert({**message, "isUnread": False})
    return {"id": message_id, "isUnread": False}


def mark_all_read(mailbox_name=None):
    if mailbox_name and not _store.table("mailboxes").get(mailbox_name):
        return _not_found(f"Mailbox '{mailbox_name}' does not exist")
    updated = 0
    for message in list(_messages()):
        if mailbox_name and message["mailbox"] != mailbox_name:
            continue
        if message["isUnread"]:
            _store.table("messages").upsert({**message, "isUnread": False})
            updated += 1
    return {"mailbox": mailbox_name or "*", "markedRead": updated}


def _drop_message(message):
    _store.table("parts").delete_where(
        lambda p, _id=message["id"]: p["messageId"] == _id)
    _store.table("messages").delete(message["id"])


def delete_message(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    _drop_message(message)
    return {"id": message_id, "deleted": True}


def delete_all_messages(mailbox_name=None):
    """`DELETE /api/Messages/*` --- the literal star is smtp4dev's."""
    if mailbox_name and not _store.table("mailboxes").get(mailbox_name):
        return _not_found(f"Mailbox '{mailbox_name}' does not exist")
    rows = [m for m in _messages()
            if not mailbox_name or m["mailbox"] == mailbox_name]
    for message in rows:
        _drop_message(message)
    return {"mailbox": mailbox_name or "*", "deleted": len(rows)}


# ---------------------------------------------------------------------------
# Relay
# ---------------------------------------------------------------------------

_ADDRESS_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def relay_message(message_id, payload):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    options = _server().get("relayOptions") or {}
    if not options.get("isEnabled"):
        return _error(400, "Relay is not enabled; set relayOptions.isEnabled "
                           "through POST /api/Server first")
    if not options.get("smtpServer"):
        return _error(400, "Relay has no smtpServer configured")
    overrides = (payload or {}).get("overrideRecipientAddresses") or []
    if not isinstance(overrides, list):
        return _error(400, "overrideRecipientAddresses must be an array")
    recipients = overrides or message["to"]
    if not recipients:
        return _error(400, "Message has no recipients and none were overridden")
    for recipient in recipients:
        if not _ADDRESS_RE.match(recipient):
            return _error(400, f"'{recipient}' is not a valid recipient address")
    _store.table("messages").upsert({**message, "isRelayed": True,
                                     "relayError": ""})
    return {"id": message_id, "relayed": True, "recipients": recipients,
            "via": f"{options['smtpServer']}:{options.get('smtpPort')}",
            "tlsMode": options.get("tlsMode"),
            "note": "no mail is actually relayed by the mock; isRelayed is set "
                    "on the message so the outcome is readable back"}


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def deliver(payload):
    """Accept a message over HTTP.

    Not an smtp4dev endpoint --- smtp4dev only accepts mail over SMTP, which a
    mock cannot offer. It stands in for that delivery so mailbox routing, the
    retention trim and the read paths can all be exercised, and the response
    reports which mailbox the recipient was routed to.
    """
    payload = payload or {}
    sender = payload.get("from")
    if not sender:
        return _error(400, "from is required")
    if not _ADDRESS_RE.match(sender):
        return _error(400, f"'{sender}' is not a valid sender address")
    recipients = payload.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]
    if not recipients:
        return _error(400, "at least one to recipient is required")
    for recipient in recipients:
        if not _ADDRESS_RE.match(recipient):
            return _error(400, f"'{recipient}' is not a valid recipient address")
    message_id = str(uuid.uuid4())
    session_id = payload.get("sessionId") or _open_session(payload, recipients)
    mailbox = mailbox_for(recipients[0])
    received = _now()
    row = {
        "id": message_id, "mailbox": mailbox, "sessionId": session_id,
        "from": sender, "to": list(recipients),
        "cc": list(payload.get("cc") or []),
        "bcc": list(payload.get("bcc") or []),
        "deliveredTo": recipients[0],
        "subject": payload.get("subject", ""),
        "receivedDate": received, "isUnread": True, "isRelayed": False,
        "relayError": "", "mimeParseError": "",
        "secureConnection": bool(payload.get("secureConnection", True)),
        "text": payload.get("text", ""), "html": payload.get("html", ""),
    }
    _store_insert("messages", row)
    _write_parts(message_id, row)
    trimmed = _apply_retention()
    return {"__status__": 201, "id": message_id, "mailbox": mailbox,
            "sessionId": session_id, "trimmed": trimmed,
            "note": "not an smtp4dev endpoint; it stands in for the SMTP "
                    "delivery a mock cannot accept"}


def _write_parts(message_id, row):
    """Build the part tree the delivered bodies imply."""
    def add(part_id, parent, name, content_type, body, attachment=False,
            filename=""):
        _store_insert("parts", {
            "_pk": f"{message_id}#{part_id}", "messageId": message_id,
            "partId": part_id, "parentId": parent, "name": name,
            "contentType": content_type, "isAttachment": attachment,
            "fileName": filename, "contentId": "", "warnings": [],
            "body": body})

    if row["text"] and row["html"]:
        add("1", "", "multipart/alternative", "multipart/alternative", "")
        add("1.1", "1", "text/plain", "text/plain; charset=utf-8", row["text"])
        add("1.2", "1", "text/html", "text/html; charset=utf-8", row["html"])
    elif row["html"]:
        add("1", "", "text/html", "text/html; charset=utf-8", row["html"])
    else:
        add("1", "", "text/plain", "text/plain; charset=utf-8", row["text"])


def _open_session(payload, recipients):
    """Record the SMTP conversation the delivery would have been part of."""
    session_id = str(uuid.uuid4())
    stamp = _now()
    client = payload.get("clientAddress", "172.19.0.2")
    lines = ["S: 220 smtp4dev.orbit-labs.local smtp4dev ready",
             f"C: EHLO {payload.get('clientName', 'api.orbit-labs.com')}",
             "S: 250-smtp4dev.orbit-labs.local",
             "S: 250 8BITMIME",
             f"C: MAIL FROM:<{payload.get('from')}>",
             "S: 250 OK"]
    for recipient in recipients:
        lines.append(f"C: RCPT TO:<{recipient}>")
        lines.append("S: 250 OK")
    lines += ["C: DATA", "S: 354 Start mail input; end with <CRLF>.<CRLF>",
              "C: <message data>", "S: 250 OK: queued", "C: QUIT",
              "S: 221 Goodbye"]
    _store_insert("sessions", {
        "id": session_id, "clientAddress": client,
        "clientName": payload.get("clientName", "api.orbit-labs.com"),
        "startDate": stamp, "endDate": stamp, "terminatedWithError": False,
        "sessionErrorType": "None", "sessionError": "",
        "secureConnection": bool(payload.get("secureConnection", True)),
        "authenticatedUser": payload.get("authenticatedUser", ""),
        "log": "\n".join(lines)})
    return session_id


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

_SESSION_SORTS = {"startDate", "endDate", "clientAddress", "numberOfMessages",
                  "terminatedWithError"}


def _session_key(session, column):
    if column == "numberOfMessages":
        return len([m for m in _messages() if m["sessionId"] == session["id"]])
    if column == "terminatedWithError":
        return session["terminatedWithError"]
    value = session.get(column, "")
    return value.lower() if isinstance(value, str) else value


def list_sessions(sort_column=None, sort_is_descending=True, page=1,
                  page_size=25):
    rows, failure = _sorted(list(_sessions()), sort_column, sort_is_descending,
                            _SESSION_SORTS, "startDate", _session_key)
    if failure:
        return failure
    return _paged(rows, page, page_size, session_representation)


def get_session(session_id):
    session = _store.table("sessions").get(session_id)
    if not session:
        return _not_found("Session not found")
    return session_representation(session, with_log=True)


def get_session_log(session_id):
    session = _store.table("sessions").get(session_id)
    if not session:
        return _not_found("Session not found")
    return {"__raw__": session["log"],
            "__content_type__": "text/plain; charset=utf-8",
            "__filename__": f"{session_id}.log"}


def delete_session(session_id):
    session = _store.table("sessions").get(session_id)
    if not session:
        return _not_found("Session not found")
    _store.table("sessions").delete(session_id)
    return {"id": session_id, "deleted": True}


def delete_all_sessions():
    rows = list(_sessions())
    for session in rows:
        _store.table("sessions").delete(session["id"])
    return {"deleted": len(rows)}


# ---------------------------------------------------------------------------
# Server settings --- readable and writable
# ---------------------------------------------------------------------------

_INT_SETTINGS = {"portNumber": (1, 65535), "imapPortNumber": (1, 65535),
                 "numberOfMessagesToKeep": (1, 100000),
                 "numberOfSessionsToKeep": (1, 100000)}
_BOOL_SETTINGS = {"isRunning", "allowRemoteConnections",
                  "webAuthenticationRequired", "disableMessageSanitisation",
                  "authenticationRequired", "recycleOnStartup",
                  "deliverMessagesToUsersDefaultMailbox"}
_STRING_SETTINGS = {"hostName", "credentialsValidationExpression"}
_RELAY_INTS = {"smtpPort": (1, 65535)}
_RELAY_STRINGS = {"smtpServer", "login", "password", "senderAddress",
                  "automaticRelayExpression"}


def get_server():
    return _server()


def update_server(payload):
    """`POST /api/Server` is the Settings dialog, and it takes effect at once."""
    settings = json.loads(json.dumps(_server()))
    errors = []
    for key, value in (payload or {}).items():
        if key == "relayOptions":
            errors += _apply_relay(settings, value)
        elif key in _INT_SETTINGS:
            low, high = _INT_SETTINGS[key]
            if not isinstance(value, int) or isinstance(value, bool) \
                    or not low <= value <= high:
                errors.append(f"{key} must be a whole number between {low} "
                              f"and {high}")
            else:
                settings[key] = value
        elif key in _BOOL_SETTINGS:
            if not isinstance(value, bool):
                errors.append(f"{key} must be a boolean")
            else:
                settings[key] = value
        elif key in _STRING_SETTINGS:
            settings[key] = str(value)
        elif key == "secureConnectionMode":
            if value not in SECURE_MODES:
                errors.append(f"secureConnectionMode must be one of "
                              f"{', '.join(SECURE_MODES)}")
            else:
                settings[key] = value
        else:
            errors.append(f"'{key}' is not a server setting")
    if errors:
        return _error(400, "; ".join(errors))
    _store.document("server").set(settings)
    trimmed = _apply_retention()
    return {**_server(), "trimmed": trimmed}


def _apply_relay(settings, value):
    if not isinstance(value, dict):
        return ["relayOptions must be an object"]
    errors = []
    options = dict(settings.get("relayOptions") or {})
    for key, item in value.items():
        if key in _RELAY_INTS:
            low, high = _RELAY_INTS[key]
            if not isinstance(item, int) or isinstance(item, bool) \
                    or not low <= item <= high:
                errors.append(f"relayOptions.{key} must be a whole number "
                              f"between {low} and {high}")
            else:
                options[key] = item
        elif key in _RELAY_STRINGS:
            options[key] = str(item)
        elif key == "isEnabled":
            if not isinstance(item, bool):
                errors.append("relayOptions.isEnabled must be a boolean")
            else:
                options[key] = item
        elif key == "tlsMode":
            if item not in SECURE_MODES:
                errors.append(f"relayOptions.tlsMode must be one of "
                              f"{', '.join(SECURE_MODES)}")
            else:
                options[key] = item
        elif key == "automaticEmails":
            if not isinstance(item, list):
                errors.append("relayOptions.automaticEmails must be an array")
            else:
                options[key] = list(item)
        else:
            errors.append(f"'relayOptions.{key}' is not a relay setting")
    if not errors:
        settings["relayOptions"] = options
    return errors


def _apply_retention():
    """Keep only the newest N messages and sessions, as the settings ask.

    smtp4dev trims the moment the setting changes rather than on a timer, so
    lowering the number in the Settings dialog empties the list in front of you.
    """
    settings = _server()
    trimmed = {"messages": 0, "sessions": 0}
    keep_messages = settings.get("numberOfMessagesToKeep") or 0
    if keep_messages:
        rows = sorted(_messages(), key=lambda m: m["receivedDate"],
                      reverse=True)
        for message in rows[keep_messages:]:
            _drop_message(message)
            trimmed["messages"] += 1
    keep_sessions = settings.get("numberOfSessionsToKeep") or 0
    if keep_sessions:
        rows = sorted(_sessions(), key=lambda s: s["startDate"], reverse=True)
        for session in rows[keep_sessions:]:
            _store.table("sessions").delete(session["id"])
            trimmed["sessions"] += 1
    return trimmed


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def version():
    return {"version": SMTP4DEV_VERSION, "framework": FRAMEWORK,
            "isRunning": _server().get("isRunning", True)}


_store.eager_load()
