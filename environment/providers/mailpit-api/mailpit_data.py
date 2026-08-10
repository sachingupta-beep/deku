"""Data access module for the Mailpit mock service.

Mailpit is MailHog's successor, and it is deliberately *not* a reskin of it.
Four things drive the shape of this API:

* **A real search query language.** MailHog takes `kind=from|to|containing`;
  Mailpit takes `query=from:billing is:unread -tag:receipt "order total"` ---
  prefixed terms, `is:`/`has:` flags, date bounds, quoted phrases and negation,
  all ANDed together.
* **A message has state.** Read/unread is tracked and mutable, and reading a
  message through `GET /api/v1/message/{id}` marks it read as a side effect.
  Tags are first-class: settable, renameable, deletable, searchable.
* **Mailpit analyses what it captured.** `html-check` scores the HTML against a
  client matrix, `link-check` reports what each link answered, and `sa-check`
  returns SpamAssassin rule hits. None of these exist in MailHog.
* **Chaos is error codes, not behaviours.** MailHog's Jim rolls against
  behavioural chances (`DisconnectChance`, `RejectSenderChance`); Mailpit's
  Chaos configures an *SMTP error code* and an integer *percentage* per trigger
  --- Sender, Recipient, Authentication --- and returns that code.

The list and the read return the same message in different shapes: the list
gives a `Snippet` and an attachment *count*, the read gives `Text`, `HTML` and
the attachment *list*.

Mutations --- reads, tags, deletes, sends, chaos --- are held in process memory
and reset on restart.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_float, opt_int, opt_str)

_store = get_store("mailpit-api")
_API = "mailpit-api"

MAILPIT_VERSION = "v1.21.3"
LATEST_VERSION = "v1.21.3"
SMTP_BIND = "0.0.0.0:1025"
HTTP_BIND = "0.0.0.0:8025"
DATABASE = "/data/mailpit.db"
SPAM_THRESHOLD = 5.0

# The client matrix html-check scores against. Mailpit ships the caniemail data
# set; this is a representative slice of it, held here so the seed only has to
# name the clients that fail.
EMAIL_CLIENTS = [
    ("Outlook", "windows", "2019"),
    ("Outlook", "macos", "16.78"),
    ("Gmail", "desktop-webmail", ""),
    ("Gmail", "android", ""),
    ("Apple Mail", "macos", "16.0"),
    ("Apple Mail", "ios", "17.0"),
    ("Yahoo! Mail", "desktop-webmail", ""),
    ("Thunderbird", "macos", "115"),
]


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
    return [{**_strip_ctx(r), "read": _flag(r, "read"),
             "to": _semi_list(r, "to"), "cc": _semi_list(r, "cc"),
             "bcc": _semi_list(r, "bcc"), "replyTo": _semi_list(r, "replyTo"),
             "tags": _semi_list(r, "tags")} for r in rows]


def _coerce_attachments(rows):
    return [{**_strip_ctx(r), "inline": _flag(r, "inline")} for r in rows]


def _coerce_rules(rows):
    return [{**_strip_ctx(r), "score": opt_float(r, "score", default=0.0)}
            for r in rows]


def _coerce_links(rows):
    return [{**_strip_ctx(r), "statusCode": opt_int(r, "statusCode", default=0),
             "followedStatusCode": opt_int(r, "followedStatusCode", default=0)}
            for r in rows]


def _coerce_warnings(rows):
    return [{**_strip_ctx(r), "found": opt_int(r, "found", default=1),
             "tags": _semi_list(r, "tags"),
             "unsupportedOn": _semi_list(r, "unsupportedOn"),
             "partialOn": _semi_list(r, "partialOn")} for r in rows]


_store.register("messages", primary_key="id",
                initial_loader=lambda: _coerce_messages(
                    _load("messages.json", "messages")))
# A part id, a rule name, a URL and a warning slug are each unique only within
# their message, so these tables need composite keys.
_store.register("attachments", primary_key="_pk",
                initial_loader=lambda: _coerce_attachments(
                    _load("attachments.json", "attachments")))
_store.register("spam_rules", primary_key="_pk",
                initial_loader=lambda: _coerce_rules(
                    _load("spam_rules.json", "spam_rules")))
_store.register("links", primary_key="_pk",
                initial_loader=lambda: _coerce_links(
                    _load("links.json", "links")))
_store.register("html_warnings", primary_key="_pk",
                initial_loader=lambda: _coerce_warnings(
                    _load("html_warnings.json", "html_warnings")))
_store.register_document("chaos",
                         initial_loader=lambda: _load_json("chaos.json"))
_store.register_document("relay",
                         initial_loader=lambda: _load_json("relay.json"))
# `SMTPAcceptedSize` is the byte count Mailpit has taken over SMTP, so it is
# seeded from the corpus rather than hard-coded --- and it must not shrink when
# messages are deleted, which is why it is stored rather than derived per read.
_store.register_document(
    "stats", initial_loader=lambda: {**_load_json("stats.json"),
                                     "SMTPAcceptedSize": _seeded_size()})


def _messages():
    return _store.table("messages").rows()


def _attachments(message_id=None):
    rows = _store.table("attachments").rows()
    if message_id is None:
        return rows
    return sorted((a for a in rows if a["messageId"] == message_id),
                  key=lambda a: a["partId"])


def _stats():
    return _store.document("stats").get()


def _bump(counter, amount=1):
    stats = dict(_stats())
    stats[counter] = stats.get(counter, 0) + amount
    _store.document("stats").set(stats)


def _seeded_size():
    return sum(len(_raw_source(m).encode("utf-8")) for m in _messages())


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def _error(status, message):
    return {"error": message, "code": status, "message": message}


def _not_found(message="message not found"):
    return _error(404, message)


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------

_ADDRESS_RE = re.compile(r"^\s*(?:\"?(?P<name>[^\"<]*?)\"?\s*)?<(?P<addr>[^>]*)>\s*$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _address(raw):
    """Mailpit reports an address as `{Name, Address}`, not a header string."""
    raw = (raw or "").strip()
    match = _ADDRESS_RE.match(raw)
    if match:
        return {"Name": (match.group("name") or "").strip(),
                "Address": match.group("addr").strip()}
    return {"Name": "", "Address": raw}


def _addresses(values):
    return [_address(v) for v in values]


def _format(address):
    if address["Name"]:
        return f"{address['Name']} <{address['Address']}>"
    return address["Address"]


def _all_addresses(message):
    return [_address(a)["Address"]
            for a in [message["from"]] + message["to"] + message["cc"]
            + message["bcc"] + message["replyTo"]]


# ---------------------------------------------------------------------------
# Raw source, size and snippet
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
    return f"--=_mailpit-{message_id[:12]}"


def _header_pairs(message):
    """Every header in the order Mailpit reports them."""
    pairs = [("Return-Path", f"<{message['returnPath']}>"
                             if message["returnPath"] else "<>"),
             ("Date", _rfc2822(message["date"])),
             ("From", message["from"]),
             ("To", ", ".join(message["to"]))]
    if message["cc"]:
        pairs.append(("Cc", ", ".join(message["cc"])))
    if message["bcc"]:
        pairs.append(("Bcc", ", ".join(message["bcc"])))
    if message["replyTo"]:
        pairs.append(("Reply-To", ", ".join(message["replyTo"])))
    pairs.append(("Subject", message["subject"]))
    pairs.append(("Message-ID", f"<{message['messageId']}>"))
    if message["listUnsubscribe"]:
        pairs.append(("List-Unsubscribe", message["listUnsubscribe"]))
        pairs.append(("List-Unsubscribe-Post", "List-Unsubscribe=One-Click"))
    pairs.append(("MIME-Version", "1.0"))
    pairs.append(("Content-Type", _content_type(message)))
    return pairs


def _content_type(message):
    parts = _attachments(message["id"])
    if parts:
        kind = "related" if any(p["inline"] for p in parts) else "mixed"
        return f'multipart/{kind}; boundary="{_boundary(message["id"])}"'
    if message["html"] and message["text"]:
        return f'multipart/alternative; boundary="{_boundary(message["id"])}"'
    if message["html"]:
        return "text/html; charset=UTF-8"
    return "text/plain; charset=UTF-8"


def _body_source(message):
    """The MIME body, rebuilt from the text, the HTML and the parts."""
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
        headers = [f"Content-Type: {part['contentType']}",
                   "Content-Transfer-Encoding: base64"]
        disposition = "inline" if part["inline"] else "attachment"
        headers.append(f'Content-Disposition: {disposition}; '
                       f'filename="{part["fileName"]}"')
        if part["contentId"]:
            headers.append(f"Content-ID: <{part['contentId']}>")
        chunks.append("\r\n".join(headers) + "\r\n\r\n" + part["body"])
    return ("".join(f"--{boundary}\r\n{c}\r\n" for c in chunks)
            + f"--{boundary}--\r\n")


def _raw_source(message):
    headers = "\r\n".join(f"{k}: {v}" for k, v in _header_pairs(message))
    return headers + "\r\n\r\n" + _body_source(message)


def _size(message):
    return len(_raw_source(message).encode("utf-8"))


_TAG_STRIP = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _snippet(message, length=100):
    """The one-line preview the list view shows, from the text or the HTML."""
    source = message["text"] or _TAG_STRIP.sub(" ", message["html"])
    flat = _WHITESPACE.sub(" ", source).strip()
    return flat if len(flat) <= length else flat[:length].rstrip() + "..."


def _list_unsubscribe(message):
    header = message["listUnsubscribe"]
    links = re.findall(r"<([^>]+)>", header)
    return {"Header": header, "Links": links,
            "HeaderPost": "List-Unsubscribe=One-Click" if header else "",
            "Errors": ""}


# ---------------------------------------------------------------------------
# The two message shapes
# ---------------------------------------------------------------------------

def _attachment_entry(part):
    return {"PartID": part["partId"], "FileName": part["fileName"],
            "ContentType": part["contentType"],
            "ContentID": part["contentId"],
            "Size": len(part["body"].encode("utf-8"))}


def summary_representation(message):
    """The list shape: a snippet and an attachment *count*."""
    return {
        "ID": message["id"],
        "MessageID": message["messageId"],
        "Read": message["read"],
        "From": _address(message["from"]),
        "To": _addresses(message["to"]),
        "Cc": _addresses(message["cc"]),
        "Bcc": _addresses(message["bcc"]),
        "ReplyTo": _addresses(message["replyTo"]),
        "Subject": message["subject"],
        "Created": message["created"],
        "Tags": message["tags"],
        "Size": _size(message),
        "Attachments": len([p for p in _attachments(message["id"])
                            if not p["inline"]]),
        "Snippet": _snippet(message),
    }


def message_representation(message):
    """The read shape: the bodies and the attachment *list*."""
    parts = _attachments(message["id"])
    return {
        "ID": message["id"],
        "MessageID": message["messageId"],
        "Read": message["read"],
        "From": _address(message["from"]),
        "To": _addresses(message["to"]),
        "Cc": _addresses(message["cc"]),
        "Bcc": _addresses(message["bcc"]),
        "ReplyTo": _addresses(message["replyTo"]),
        "ReturnPath": message["returnPath"],
        "Subject": message["subject"],
        "Date": message["date"],
        "Tags": message["tags"],
        "Text": message["text"],
        "HTML": message["html"],
        "Size": _size(message),
        "ListUnsubscribe": _list_unsubscribe(message),
        "Inline": [_attachment_entry(p) for p in parts if p["inline"]],
        "Attachments": [_attachment_entry(p) for p in parts
                        if not p["inline"]],
    }


def _sorted_messages():
    """Newest first, which is the order Mailpit's list returns."""
    return sorted(_messages(), key=lambda m: m["created"], reverse=True)


def _envelope(rows, start, limit, matched=None):
    start = max(0, int(start or 0))
    limit = max(1, min(int(limit or 50), 200))
    page = rows[start:start + limit]
    total = len(_messages())
    return {
        "total": total,
        "unread": len([m for m in _messages() if not m["read"]]),
        "count": len(page),
        "messages_count": len(rows) if matched is None else matched,
        "start": start,
        "tags": all_tags(),
        "messages": [summary_representation(m) for m in page],
    }


def list_messages(start=0, limit=50):
    return _envelope(_sorted_messages(), start, limit)


def get_message(message_id):
    """Reading a message marks it read --- Mailpit does this as a side effect."""
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    if not message["read"]:
        _store.table("messages").upsert({**message, "read": True})
        message = _store.table("messages").get(message_id)
    return message_representation(message)


def get_headers(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    headers = {}
    for name, value in _header_pairs(message):
        headers.setdefault(name, []).append(value)
    return headers


def get_raw(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    return {"__raw__": _raw_source(message),
            "__content_type__": "text/plain; charset=utf-8",
            "__filename__": f"{message_id}.eml"}


def get_part(message_id, part_id):
    if not _store.table("messages").get(message_id):
        return _not_found()
    for part in _attachments(message_id):
        if part["partId"] == str(part_id):
            return {"__raw__": part["body"],
                    "__content_type__": part["contentType"],
                    "__filename__": part["fileName"]}
    return _not_found(f"part {part_id} not found in message {message_id}")


def get_thumbnail(message_id, part_id):
    """Mailpit renders a thumbnail for image parts and refuses anything else."""
    part = get_part(message_id, part_id)
    if "error" in part:
        return part
    if not part["__content_type__"].startswith("image/"):
        return _error(400, f"part {part_id} is {part['__content_type__']}, "
                           f"which cannot be thumbnailed")
    return {"__raw__": part["__raw__"], "__content_type__": "image/png",
            "__filename__": f"thumb-{part['__filename__']}"}


# ---------------------------------------------------------------------------
# Read state, tags, deletes
# ---------------------------------------------------------------------------

def set_read(payload):
    """An empty (or absent) `IDs` updates every message, as Mailpit does."""
    payload = payload or {}
    ids = payload.get("IDs") or []
    if "Read" not in payload:
        return _error(400, "Read is required and must be a boolean")
    read = payload["Read"]
    if not isinstance(read, bool):
        return _error(400, "Read must be a boolean")
    for message_id in ids:
        if not _store.table("messages").get(message_id):
            return _not_found(f"message {message_id} not found")
    rows = ([_store.table("messages").get(i) for i in ids] if ids
            else list(_messages()))
    for message in rows:
        _store.table("messages").upsert({**message, "read": read})
    return {"updated": len(rows), "read": read}


def all_tags():
    return sorted({tag for m in _messages() for tag in m["tags"]})


_TAG_RE = re.compile(r"^[a-zA-Z0-9\-\. _]+$")


def _validate_tags(tags):
    for tag in tags:
        if not _TAG_RE.match(tag or ""):
            return _error(400, f"invalid tag {tag!r}; tags may contain letters, "
                               f"digits, spaces, dashes, dots and underscores")
    return None


def set_tags(payload):
    payload = payload or {}
    ids = payload.get("IDs") or []
    tags = payload.get("Tags")
    if tags is None:
        return _error(400, "Tags is required")
    if not isinstance(tags, list):
        return _error(400, "Tags must be an array")
    if not ids:
        return _error(400, "IDs is required and must not be empty")
    invalid = _validate_tags(tags)
    if invalid:
        return invalid
    for message_id in ids:
        if not _store.table("messages").get(message_id):
            return _not_found(f"message {message_id} not found")
    for message_id in ids:
        message = _store.table("messages").get(message_id)
        _store.table("messages").upsert({**message, "tags": sorted(set(tags))})
    return {"updated": len(ids), "tags": sorted(set(tags))}


def rename_tag(tag, payload):
    if tag not in all_tags():
        return _not_found(f"tag {tag!r} not found")
    new_name = (payload or {}).get("Name")
    if not new_name:
        return _error(400, "Name is required")
    invalid = _validate_tags([new_name])
    if invalid:
        return invalid
    renamed = 0
    for message in list(_messages()):
        if tag in message["tags"]:
            tags = sorted({new_name if t == tag else t
                           for t in message["tags"]})
            _store.table("messages").upsert({**message, "tags": tags})
            renamed += 1
    return {"renamed": renamed, "from": tag, "to": new_name}


def delete_tag(tag):
    if tag not in all_tags():
        return _not_found(f"tag {tag!r} not found")
    removed = 0
    for message in list(_messages()):
        if tag in message["tags"]:
            tags = [t for t in message["tags"] if t != tag]
            _store.table("messages").upsert({**message, "tags": tags})
            removed += 1
    return {"removed": removed, "tag": tag}


def _delete_rows(rows):
    for message in rows:
        message_id = message["id"]
        for table in ("attachments", "spam_rules", "links", "html_warnings"):
            _store.table(table).delete_where(
                lambda r, _id=message_id: r["messageId"] == _id)
        _store.table("messages").delete(message_id)
    if rows:
        _bump("MessagesDeleted", len(rows))
    return {"deleted": len(rows)}


def delete_messages(payload):
    """An empty (or absent) `IDs` deletes everything, as Mailpit does."""
    ids = (payload or {}).get("IDs") or []
    if not ids:
        return _delete_rows(list(_messages()))
    for message_id in ids:
        if not _store.table("messages").get(message_id):
            return _not_found(f"message {message_id} not found")
    return _delete_rows([_store.table("messages").get(i) for i in ids])


# ---------------------------------------------------------------------------
# The search query language
# ---------------------------------------------------------------------------

_PREFIXES = ("from", "to", "cc", "bcc", "reply-to", "addressed", "subject",
             "message-id", "tag", "before", "after")
_IS_VALUES = ("read", "unread", "tagged", "untagged", "attachment")
_TOKEN_RE = re.compile(r'[!-]?(?:[a-zA-Z-]+:)?"[^"]*"|\S+')


def _tokenize(query):
    return _TOKEN_RE.findall(query or "")


def _parse_query(query):
    """Split a Mailpit query into terms, or report the first thing wrong.

    A term is `(negate, field, value)`. `field` is one of the prefixes, `is`,
    `has`, or `None` for a bare word that is matched against everything.
    """
    terms, errors = [], []
    for token in _tokenize(query):
        negate = token[0] in "-!"
        if negate:
            token = token[1:]
        field, sep, value = token.partition(":")
        if not sep:
            terms.append((negate, None, token.strip('"').lower()))
            continue
        field = field.lower()
        value = value.strip('"')
        if field in ("is", "has"):
            if value.lower() not in _IS_VALUES:
                errors.append(f"unknown {field}: value {value!r}; expected one "
                              f"of {', '.join(_IS_VALUES)}")
                continue
            terms.append((negate, "is", value.lower()))
        elif field in _PREFIXES:
            if field in ("before", "after") and not _DATE_RE.match(value):
                errors.append(f"{field}: expects a YYYY-MM-DD date, got "
                              f"{value!r}")
                continue
            terms.append((negate, field, value.lower()))
        else:
            errors.append(f"unknown search prefix {field!r}; expected one of "
                          f"{', '.join(_PREFIXES)}, is, has")
    return terms, errors


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _joined(values):
    return " ".join(values).lower()


def _term_matches(message, field, value):
    if field is None:
        haystack = " ".join([message["subject"], message["text"],
                             message["html"], _joined(_all_addresses(message)),
                             _joined(message["tags"])]).lower()
        return value in haystack
    if field == "from":
        return value in message["from"].lower()
    if field in ("to", "cc", "bcc"):
        return value in _joined(message[field])
    if field == "reply-to":
        return value in _joined(message["replyTo"])
    if field == "addressed":
        return value in _joined([message["from"]] + message["to"]
                                + message["cc"] + message["bcc"])
    if field == "subject":
        return value in message["subject"].lower()
    if field == "message-id":
        return value in message["messageId"].lower()
    if field == "tag":
        return any(value == t.lower() for t in message["tags"])
    if field == "before":
        return message["date"][:10] < value
    if field == "after":
        return message["date"][:10] > value
    if field == "is":
        if value == "read":
            return message["read"]
        if value == "unread":
            return not message["read"]
        if value == "tagged":
            return bool(message["tags"])
        if value == "untagged":
            return not message["tags"]
        # An inline image is not an attachment, here or in the summary count.
        return any(not p["inline"] for p in _attachments(message["id"]))
    return False


def _matching(query):
    terms, errors = _parse_query(query)
    if errors:
        return None, _error(400, "; ".join(errors))
    if not terms:
        return None, _error(400, "query is required")
    rows = []
    for message in _sorted_messages():
        if all(_term_matches(message, field, value) != negate
               for negate, field, value in terms):
            rows.append(message)
    return rows, None


def search_messages(query=None, start=0, limit=50):
    rows, failure = _matching(query)
    if failure:
        return failure
    return _envelope(rows, start, limit, matched=len(rows))


def delete_search(query=None):
    """Mailpit deletes exactly what the same query would have listed."""
    rows, failure = _matching(query)
    if failure:
        return failure
    return _delete_rows(rows)


# ---------------------------------------------------------------------------
# Analysis: html-check, link-check, sa-check
# ---------------------------------------------------------------------------

def _client_key(family, platform, version):
    return f"{family}|{platform}|{version}"


def _warning_results(warning):
    unsupported = set(warning["unsupportedOn"])
    partial = set(warning["partialOn"])
    results, counts = [], {"no": 0, "partial": 0, "yes": 0}
    for family, platform, version in EMAIL_CLIENTS:
        key = _client_key(family, platform, version)
        support = "no" if key in unsupported else (
            "partial" if key in partial else "yes")
        counts[support] += 1
        results.append({"Family": family, "Platform": platform,
                        "Version": version, "Support": support,
                        "NotesByNumber": ""})
    total = len(EMAIL_CLIENTS)
    score = {"Found": warning["found"],
             "Supported": round(counts["yes"] / total * 100, 2),
             "Partial": round(counts["partial"] / total * 100, 2),
             "Unsupported": round(counts["no"] / total * 100, 2)}
    return results, score


def html_check(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    if not message["html"]:
        return _error(400, "message does not contain an HTML part")
    warnings = sorted((w for w in _store.table("html_warnings").rows()
                       if w["messageId"] == message_id),
                      key=lambda w: w["slug"])
    rendered, supported, partial, unsupported = [], 0.0, 0.0, 0.0
    for warning in warnings:
        results, score = _warning_results(warning)
        supported += score["Supported"]
        partial += score["Partial"]
        unsupported += score["Unsupported"]
        rendered.append({"Slug": warning["slug"], "Title": warning["title"],
                         "Description": warning["description"],
                         "Category": warning["category"],
                         "Tags": warning["tags"], "NotesByNumber": {},
                         "Results": results, "Score": score})
    platforms = {}
    for family, platform, _version in EMAIL_CLIENTS:
        platforms.setdefault(family.lower(), [])
        if platform not in platforms[family.lower()]:
            platforms[family.lower()].append(platform)
    # `Total` averages the per-warning percentages, so a message with no
    # warnings scores a clean 100% supported.
    tests = len(rendered)
    return {"Platforms": platforms,
            "Total": {"Nodes": _count_nodes(message["html"]), "Tests": tests,
                      "Supported": round(supported / tests, 2) if tests else 100.0,
                      "Partial": round(partial / tests, 2) if tests else 0.0,
                      "Unsupported": round(unsupported / tests, 2) if tests else 0.0},
            "Warnings": rendered}


def _count_nodes(html):
    return len(re.findall(r"<[a-zA-Z][^>]*>", html or ""))


def link_check(message_id, follow=False):
    """`follow=true` resolves a redirect to its target, as Mailpit does."""
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    rows = sorted((l for l in _store.table("links").rows()
                   if l["messageId"] == message_id), key=lambda l: l["url"])
    links, errors = [], 0
    for row in rows:
        url, code, status = row["url"], row["statusCode"], row["status"]
        if follow and row["followsTo"]:
            url = row["followsTo"]
            code, status = row["followedStatusCode"], row["followedStatus"]
        if code == 0 or code >= 400:
            errors += 1
        links.append({"URL": url, "StatusCode": code, "Status": status})
    return {"Errors": errors, "Links": links}


def sa_check(message_id):
    message = _store.table("messages").get(message_id)
    if not message:
        return _not_found()
    rules = sorted((r for r in _store.table("spam_rules").rows()
                    if r["messageId"] == message_id),
                   key=lambda r: (-r["score"], r["name"]))
    score = round(float(sum(r["score"] for r in rules)), 3)
    return {"Error": "", "IsSpam": score >= SPAM_THRESHOLD, "Score": score,
            "Rules": [{"Score": r["score"], "Name": r["name"],
                       "Description": r["description"]} for r in rules]}


# ---------------------------------------------------------------------------
# Chaos: an SMTP error code and a percentage, per trigger
# ---------------------------------------------------------------------------

_TRIGGERS = ("Sender", "Recipient", "Authentication")


def get_chaos():
    return _store.document("chaos").get()


def set_chaos(payload):
    settings = {k: dict(v) for k, v in get_chaos().items()}
    errors = []
    for trigger, values in (payload or {}).items():
        if trigger not in _TRIGGERS:
            errors.append(f"unknown trigger {trigger!r}; expected one of "
                          f"{', '.join(_TRIGGERS)}")
            continue
        if not isinstance(values, dict):
            errors.append(f"{trigger} must be an object with ErrorCode and "
                          f"Probability")
            continue
        if "ErrorCode" in values:
            code = values["ErrorCode"]
            if not isinstance(code, int) or not 400 <= code <= 599:
                errors.append(f"{trigger}.ErrorCode must be an SMTP error code "
                              f"between 400 and 599")
            else:
                settings[trigger]["ErrorCode"] = code
        if "Probability" in values:
            chance = values["Probability"]
            if not isinstance(chance, int) or isinstance(chance, bool) \
                    or not 0 <= chance <= 100:
                errors.append(f"{trigger}.Probability must be a whole "
                              f"percentage between 0 and 100")
            else:
                settings[trigger]["Probability"] = chance
    if errors:
        return _error(400, "; ".join(errors))
    _store.document("chaos").set(settings)
    return settings


def _roll(value):
    """A stable 0-99 roll for an address.

    Seeded from the address so the same recipient always meets the same fate at
    the same probability --- `hash()` is salted per process and would not be
    reproducible across runs.
    """
    digest = hashlib.sha256((value or "").encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _chaos_refusal(sender, recipient, authenticated):
    """Let Chaos refuse the session, if a probability has been set.

    Mailpit answers with an SMTP error code, which is not an HTTP status; the
    code is reported in the body and the request itself fails with 400.
    """
    chaos = get_chaos()
    checks = [("Authentication", "authentication rejected",
               "orbit-mailpit-user" if authenticated else ""),
              ("Sender", f"sender {sender} rejected", sender),
              ("Recipient", f"recipient {recipient} rejected", recipient)]
    for trigger, reason, seed in checks:
        settings = chaos.get(trigger) or {}
        probability = settings.get("Probability", 0)
        if not probability or not seed:
            continue
        if _roll(seed) < probability:
            _bump("SMTPRejected")
            return _error(400, f"chaos: {reason}"), settings.get("ErrorCode")
    return None, None


# ---------------------------------------------------------------------------
# Send and release
# ---------------------------------------------------------------------------

_ID_ALPHABET = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "abcdefghijklmnopqrstuvwxyz0123456789")


def _new_id(seed):
    """A 22-character Mailpit-style id, derived so it is reproducible."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    value = int.from_bytes(digest, "big")
    chars = []
    for _ in range(22):
        value, index = divmod(value, len(_ID_ALPHABET))
        chars.append(_ID_ALPHABET[index])
    return "".join(chars)


def _send_address(entry):
    if isinstance(entry, str):
        return entry
    entry = entry or {}
    email = entry.get("Email", "")
    name = entry.get("Name", "")
    return f"{name} <{email}>" if name else email


def _email_of(entry):
    return _address(_send_address(entry))["Address"]


def send_message(payload):
    """Mailpit accepts mail over HTTP as well as SMTP, so this creates one."""
    payload = payload or {}
    sender = payload.get("From")
    if not sender or not _email_of(sender):
        return _error(400, "From.Email is required")
    recipients = payload.get("To") or []
    if not recipients:
        return _error(400, "at least one To recipient is required")
    for group in ("To", "Cc", "Bcc"):
        for entry in payload.get(group) or []:
            email = _email_of(entry)
            if not _EMAIL_RE.match(email):
                return _error(400, f"{group} contains an invalid address "
                                   f"{email!r}")
    if not _EMAIL_RE.match(_email_of(sender)):
        return _error(400, f"From contains an invalid address "
                           f"{_email_of(sender)!r}")
    tags = payload.get("Tags") or []
    invalid = _validate_tags(tags)
    if invalid:
        return invalid
    refusal, smtp_code = _chaos_refusal(_email_of(sender),
                                        _email_of(recipients[0]),
                                        bool(payload.get("Auth")))
    if refusal:
        return {**refusal, "smtpErrorCode": smtp_code}
    created = _now()
    message_id = _new_id(f"{_email_of(sender)}|{payload.get('Subject', '')}|"
                         f"{'|'.join(_email_of(r) for r in recipients)}")
    row = {
        "id": message_id,
        "messageId": f"{message_id}@mailpit.example",
        "read": False,
        "from": _send_address(sender),
        "to": [_send_address(r) for r in recipients],
        "cc": [_send_address(r) for r in payload.get("Cc") or []],
        "bcc": [_send_address(r) for r in payload.get("Bcc") or []],
        "replyTo": [_send_address(r) for r in payload.get("ReplyTo") or []],
        "returnPath": _email_of(sender),
        "subject": payload.get("Subject", ""),
        "date": created,
        "created": created,
        "tags": sorted(set(tags)),
        "listUnsubscribe": "",
        "text": payload.get("Text", ""),
        "html": payload.get("HTML", ""),
    }
    _store_insert("messages", row)
    for index, attachment in enumerate(payload.get("Attachments") or [], 2):
        part_id = str(index)
        _store_insert("attachments", {
            "_pk": f"{message_id}#{part_id}", "messageId": message_id,
            "partId": part_id,
            "fileName": attachment.get("Filename", f"part-{part_id}"),
            "contentType": attachment.get("ContentType",
                                          "application/octet-stream"),
            "contentId": attachment.get("ContentID", ""),
            "inline": bool(attachment.get("ContentID")),
            "body": attachment.get("Content", ""),
        })
    _bump("SMTPAccepted")
    _bump("SMTPAcceptedSize", _size(_store.table("messages").get(message_id)))
    return {"ID": message_id}


def release_message(message_id, payload):
    """Relay a captured message, subject to the relay's recipient rules."""
    if not _store.table("messages").get(message_id):
        return _not_found()
    relay = _store.document("relay").get()
    if not relay.get("Enabled"):
        return _error(400, "SMTP relay is not configured")
    recipients = (payload or {}).get("To") or []
    if not recipients:
        return _error(400, "To is required and must not be empty")
    allowed = relay.get("AllowedRecipients") or ""
    blocked = relay.get("BlockedRecipients") or ""
    for recipient in recipients:
        if not _EMAIL_RE.match(recipient):
            return _error(400, f"invalid recipient address {recipient!r}")
        if allowed and not re.search(allowed, recipient):
            return _error(400, f"recipient {recipient} is not permitted by the "
                               f"relay's allowed-recipients rule")
        if blocked and re.search(blocked, recipient):
            return _error(400, f"recipient {recipient} is blocked by the "
                               f"relay's blocked-recipients rule")
    _bump("SMTPAccepted", len(recipients))
    return {"__status__": 200, "released": True, "messageId": message_id,
            "to": recipients, "via": relay["SMTPServer"],
            "note": "no mail is actually relayed by the mock; the accepted "
                    "count in /api/v1/info records the release"}


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def livez():
    return {"__raw__": "ok", "__content_type__": "text/plain; charset=utf-8",
            "__filename__": "livez.txt"}


def readyz():
    return {"__raw__": "ok", "__content_type__": "text/plain; charset=utf-8",
            "__filename__": "readyz.txt"}


def service_info():
    stats = _stats()
    return {
        "Database": DATABASE,
        "DatabaseSize": sum(_size(m) for m in _messages()) + 32768,
        "LatestVersion": LATEST_VERSION,
        "Messages": len(_messages()),
        "Tags": {tag: len([m for m in _messages() if tag in m["tags"]])
                 for tag in all_tags()},
        "Unread": len([m for m in _messages() if not m["read"]]),
        "Version": MAILPIT_VERSION,
        "RuntimeStats": {
            "Memory": stats.get("Memory", 0),
            "MessagesDeleted": stats.get("MessagesDeleted", 0),
            "SMTPAccepted": stats.get("SMTPAccepted", 0),
            "SMTPAcceptedSize": stats.get("SMTPAcceptedSize", 0),
            "SMTPIgnored": stats.get("SMTPIgnored", 0),
            "SMTPRejected": stats.get("SMTPRejected", 0),
            "Uptime": stats.get("Uptime", 0),
        },
    }


def webui_config():
    relay = _store.document("relay").get()
    return {
        "DisableDelete": False,
        "DisableHTMLCheck": False,
        "DisableSMTPLog": False,
        "HideDeleteAllButton": False,
        "Label": "Orbit Labs (mock)",
        "SpamAssassin": True,
        "MessageRelay": {
            "Enabled": relay.get("Enabled", False),
            "SMTPServer": relay.get("SMTPServer", ""),
            "ReturnPath": relay.get("ReturnPath", ""),
            "AllowedRecipients": relay.get("AllowedRecipients", ""),
            "BlockedRecipients": relay.get("BlockedRecipients", ""),
            "OverrideFrom": relay.get("OverrideFrom", ""),
            "PreserveMessageIDs": relay.get("PreserveMessageIDs", False),
        },
    }


_store.eager_load()
