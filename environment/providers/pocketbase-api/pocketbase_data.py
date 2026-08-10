"""Data access module for the PocketBase API mock service.

Models a self-hosted PocketBase instance backing the Orbit Labs status page:
collection metadata, record CRUD with the PocketBase filter/sort/expand
grammar, file references, request logs, backups, crons and settings.
The auth endpoints (`auth-with-password`, `auth-refresh`, OAuth2) are served by
`pocketbase-auth-api`.

Record ids are 15-character strings, timestamps use PocketBase's
`YYYY-MM-DD HH:MM:SS.mmmZ` format, and list reads return the
`{page, perPage, totalItems, totalPages, items}` envelope. Mutations are held
in process memory and reset on restart.
"""

import json
import re
import time
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_float, opt_int, opt_str, strict_bool)

_store = get_store("pocketbase-api")
_API = "pocketbase-api"


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


def _load_settings():
    with open(DATA_DIR / "settings.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("collections", primary_key="id",
                initial_loader=lambda: _coerce_collections(_load("collections.json", "collections")))
_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json", "users")))
_store.register("services", primary_key="id",
                initial_loader=lambda: _coerce_services(_load("services.json", "services")))
_store.register("incidents", primary_key="id",
                initial_loader=lambda: _coerce_incidents(_load("incidents.json", "incidents")))
_store.register("incident_updates", primary_key="id",
                initial_loader=lambda: _coerce_incident_updates(_load("incident_updates.json", "incident_updates")))
_store.register("subscribers", primary_key="id",
                initial_loader=lambda: _coerce_subscribers(_load("subscribers.json", "subscribers")))
_store.register("logs", primary_key="id",
                initial_loader=lambda: _coerce_logs(_load("logs.json", "logs")))
_store.register("backups", primary_key="key",
                initial_loader=lambda: _coerce_backups(_load("backups.json", "backups")))
_store.register("crons", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("crons.json", "crons")])
_store.register_document("settings", initial_loader=_load_settings)
# Born-empty: realtime subscriptions and file tokens are created at runtime only.
_store.register("subscriptions", primary_key="clientId", initial_loader=lambda: [])
_store.register("file_tokens", primary_key="token", initial_loader=lambda: [])


def _collections_rows():
    return _store.table("collections").rows()


def _users_rows():
    return _store.table("users").rows()


def _services_rows():
    return _store.table("services").rows()


def _incidents_rows():
    return _store.table("incidents").rows()


def _incident_updates_rows():
    return _store.table("incident_updates").rows()


def _subscribers_rows():
    return _store.table("subscribers").rows()


def _logs_rows():
    return _store.table("logs").rows()


def _backups_rows():
    return _store.table("backups").rows()


def _crons_rows():
    return _store.table("crons").rows()


def _settings_doc():
    return _store.document("settings").get()


def _subscriptions_rows():
    return _store.table("subscriptions").rows()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + ".000Z"


def _semi_list(r, column):
    raw = opt_str(r, column, default="")
    return [part for part in raw.split(";") if part]


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

def _coerce_collections(rows):
    out = []
    for r in rows:
        out.append({
            **_strip_ctx(r),
            "system": strict_bool(r, "system"),
            "fields": [_parse_field(spec) for spec in _semi_list(r, "fields")],
            "indexes": _semi_list(r, "indexes"),
        })
    return out


def _parse_field(spec):
    """`name:type:required` from the seed becomes a PocketBase field descriptor."""
    parts = (spec.split(":") + ["text", "false"])[:3]
    return {"name": parts[0], "type": parts[1], "required": parts[2] == "true"}


def _coerce_users(rows):
    return [{**_strip_ctx(r), "emailVisibility": strict_bool(r, "emailVisibility"),
             "verified": strict_bool(r, "verified"),
             "oncall": strict_bool(r, "oncall")} for r in rows]


def _coerce_services(rows):
    return [{**_strip_ctx(r), "uptime_30d": opt_float(r, "uptime_30d", default=0.0),
             "sort_order": opt_int(r, "sort_order", default=0),
             "monitored": strict_bool(r, "monitored")} for r in rows]


def _coerce_incidents(rows):
    return [{**_strip_ctx(r), "severity": opt_int(r, "severity", default=4),
             "assignee": opt_str(r, "assignee", default=""),
             "attachments": _semi_list(r, "attachments"),
             "resolved": opt_str(r, "resolved", default="")} for r in rows]


def _coerce_incident_updates(rows):
    return [_strip_ctx(r) for r in rows]


def _coerce_subscribers(rows):
    return [{**_strip_ctx(r), "services": _semi_list(r, "services"),
             "confirmed": strict_bool(r, "confirmed")} for r in rows]


def _coerce_logs(rows):
    return [{**_strip_ctx(r), "level": opt_int(r, "level", default=0),
             "status": opt_int(r, "status", default=200),
             "execTime": opt_float(r, "execTime", default=0.0)} for r in rows]


def _coerce_backups(rows):
    return [{**_strip_ctx(r), "size": opt_int(r, "size", default=0)} for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id():
    """PocketBase record ids are 15-character alphanumeric strings."""
    return uuid.uuid4().hex[:15]


def _error(code, message, data=None):
    """PocketBase-shaped error body. The house `error` key drives the response."""
    return {"error": message, "code": code, "message": message, "data": data or {}}


def _page_envelope(items, page, per_page, total, skip_total=False):
    if skip_total:
        return {"page": page, "perPage": per_page, "totalItems": -1,
                "totalPages": -1, "items": items}
    pages = (total + per_page - 1) // per_page if per_page else 0
    return {"page": page, "perPage": per_page, "totalItems": total,
            "totalPages": pages, "items": items}


# Collections that hold records, in the order the admin UI lists them.
RECORD_COLLECTIONS = {
    "users": _users_rows,
    "services": _services_rows,
    "incidents": _incidents_rows,
    "incident_updates": _incident_updates_rows,
    "subscribers": _subscribers_rows,
}

# (collection, field) -> (target collection, cardinality)
_RELATIONS = {
    ("incidents", "service"): ("services", "single"),
    ("incidents", "assignee"): ("users", "single"),
    ("incident_updates", "incident"): ("incidents", "single"),
    ("incident_updates", "author"): ("users", "single"),
    ("subscribers", "services"): ("services", "multi"),
}

# File fields and whether they hold a single filename or a list.
_FILE_FIELDS = {
    ("users", "avatar"): "single",
    ("incidents", "attachments"): "multi",
}


def _collection_meta(name_or_id):
    return _store.table("collections").find_one(
        lambda c: c["name"] == name_or_id or c["id"] == name_or_id)


# ---------------------------------------------------------------------------
# Identity + collection rules
# ---------------------------------------------------------------------------

GUEST = "guest"
USER = "user"
SUPERUSER = "superuser"


def resolve_identity(authorization=None):
    """Map an Authorization header onto (kind, record_id).

    PocketBase accepts the raw token or a `Bearer`-prefixed one. The superuser
    token grants everything; the seeded user token authenticates as that record;
    any other non-empty token authenticates as the same record, keeping the
    fleet convention that any token is accepted. No token means guest.
    """
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        return GUEST, ""
    tokens = _settings_doc().get("tokens", {})
    if token == tokens.get("superuser"):
        return SUPERUSER, "__superuser__"
    return USER, tokens.get("userRecordId", "")


def _rule_allows(rule, kind, auth_id, record=None):
    """Evaluate a seeded collection rule token against the caller's identity."""
    if rule == "@public":
        return True
    if kind == SUPERUSER:
        return True
    if rule == "@superuser":
        return False
    if rule == "@auth":
        return kind != GUEST
    if rule == "@owner":
        return kind != GUEST and (record is None or record.get("id") == auth_id)
    return kind != GUEST


def _rule_as_pb(rule):
    """Render a seeded rule token the way PocketBase reports it."""
    return {"@public": "", "@superuser": None,
            "@auth": "@request.auth.id != ''",
            "@owner": "id = @request.auth.id"}.get(rule, rule)


_RULE_FOR_ACTION = {"list": "listRule", "view": "viewRule", "create": "createRule",
                    "update": "updateRule", "delete": "deleteRule"}


def _authorize(collection, action, kind, auth_id, record=None):
    """Return None when allowed, otherwise a PocketBase-shaped error."""
    meta = _collection_meta(collection)
    rule = meta[_RULE_FOR_ACTION[action]]
    if _rule_allows(rule, kind, auth_id, record):
        return None
    if kind == GUEST:
        return _error(403, "Only superusers can perform this action."
                      if rule == "@superuser" else
                      "The request requires valid record authorization token.")
    return _error(403, "Only superusers can perform this action.")


# ---------------------------------------------------------------------------
# Filter grammar
# ---------------------------------------------------------------------------

_OPERATORS = ["?!=", "?=", "!~", ">=", "<=", "!=", "~", "=", ">", "<"]


def _split_top(expr, sep):
    """Split on `sep` at the top level, ignoring quoted spans and parentheses."""
    parts, buf, quote, depth, i = [], "", None, 0, 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            buf += ch
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote, buf = ch, buf + ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and expr.startswith(sep, i):
            parts.append(buf)
            buf = ""
            i += len(sep)
            continue
        buf += ch
        i += 1
    parts.append(buf)
    return [p.strip() for p in parts]


def _parse_literal(raw):
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in ("null", "nil"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def _parse_condition(expr):
    """`status != "resolved"` -> ("status", "!=", "resolved"), or None."""
    for op in _OPERATORS:
        idx = _find_top(expr, op)
        if idx > 0:
            return expr[:idx].strip(), op, _parse_literal(expr[idx + len(op):])
    return None


def _find_top(expr, op):
    quote, i = None, 0
    while i < len(expr):
        ch = expr[i]
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            continue
        if expr.startswith(op, i):
            return i
        i += 1
    return -1


def _compare(value, op, operand):
    if op in ("~", "!~"):
        needle = str(operand).replace("%", "")
        hit = needle.lower() in str(value if value is not None else "").lower()
        return hit if op == "~" else not hit
    if op in ("?=", "?!="):
        items = value if isinstance(value, list) else [value]
        hit = any(_compare(item, "=", operand) for item in items)
        return hit if op == "?=" else not hit
    if isinstance(value, bool) and not isinstance(operand, bool):
        operand = str(operand).strip().lower() in ("true", "1", "yes")
    elif isinstance(value, (int, float)) and isinstance(operand, str):
        try:
            operand = type(value)(operand)
        except ValueError:
            pass
    elif isinstance(value, str) and isinstance(operand, (int, float)):
        operand = str(operand)
    try:
        if op == "=":
            return value == operand
        if op == "!=":
            return value != operand
        if op == ">":
            return value > operand
        if op == ">=":
            return value >= operand
        if op == "<":
            return value < operand
        if op == "<=":
            return value <= operand
    except TypeError:
        return False
    return False


def _match_filter(row, expr):
    """OR of ANDs, matching PocketBase's `&&` binding tighter than `||`."""
    for or_part in _split_top(expr, "||"):
        clauses = _split_top(or_part.strip("() "), "&&")
        if all(_match_clause(row, c) for c in clauses if c):
            return True
    return False


def _match_clause(row, clause):
    parsed = _parse_condition(clause.strip("() "))
    if not parsed:
        return False
    field, op, operand = parsed
    return _compare(row.get(field), op, operand)


def _apply_filter(rows, expr):
    if not expr:
        return rows, None
    try:
        return [r for r in rows if _match_filter(r, expr)], None
    except Exception:
        return [], _error(400, "Something went wrong while processing your request.",
                          {"filter": {"code": "validation_invalid_filter",
                                      "message": f"Invalid filter expression: {expr}"}})


def _apply_sort(rows, sort):
    """`-created,title`; `@random` is accepted but kept stable for determinism."""
    if not sort:
        return rows
    out = list(rows)
    for clause in reversed([c.strip() for c in sort.split(",") if c.strip()]):
        if clause == "@random":
            continue
        descending = clause.startswith("-")
        field = clause.lstrip("+-")
        out.sort(key=lambda r: (r.get(field) is None, _sort_key(r.get(field))),
                 reverse=descending)
    return out


def _sort_key(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return ";".join(str(v) for v in value)
    return str(value)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _serialize(collection, row, kind, auth_id):
    meta = _collection_meta(collection)
    out = {"id": row["id"], "collectionId": meta["id"], "collectionName": collection}
    for key, value in row.items():
        if key in ("id", "created", "updated"):
            continue
        out[key] = value
    out["created"] = row.get("created", "")
    out["updated"] = row.get("updated", "")
    if meta["type"] == "auth" and kind != SUPERUSER and row["id"] != auth_id \
            and not row.get("emailVisibility", False):
        out["email"] = ""
    return out


def _apply_expand(collection, records, expand, kind, auth_id):
    """Attach related records under `expand`, one relation level deep."""
    for field in [f.strip() for f in (expand or "").split(",") if f.strip()]:
        rel = _RELATIONS.get((collection, field.split(".")[0]))
        if not rel:
            continue
        target, cardinality = rel
        by_id = {r["id"]: r for r in RECORD_COLLECTIONS[target]()}
        for record in records:
            raw = record.get(field.split(".")[0])
            ids = raw if isinstance(raw, list) else ([raw] if raw else [])
            hits = [_serialize(target, by_id[i], kind, auth_id) for i in ids if i in by_id]
            if not hits:
                continue
            bucket = record.setdefault("expand", {})
            bucket[field.split(".")[0]] = hits if cardinality == "multi" else hits[0]
    return records


def _project(record, fields):
    if not fields:
        return record
    wanted = [f.strip() for f in fields.split(",") if f.strip()]
    if "*" in wanted:
        return record
    return {k: v for k, v in record.items() if k in wanted}


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

def list_collections(page=1, per_page=30, kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    rows = [_public_collection(c) for c in _collections_rows()]
    start = (page - 1) * per_page
    return _page_envelope(rows[start:start + per_page], page, per_page, len(rows))


def get_collection(name_or_id, kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    meta = _collection_meta(name_or_id)
    if not meta:
        return _error(404, "The requested resource wasn't found.")
    return _public_collection(meta)


def _public_collection(meta):
    return {**{k: v for k, v in meta.items() if k not in _RULE_FOR_ACTION.values()},
            **{rule: _rule_as_pb(meta[rule]) for rule in _RULE_FOR_ACTION.values()}}


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def list_records(collection, page=1, per_page=30, sort=None, filter_expr=None,
                 expand=None, fields=None, skip_total=False, kind=GUEST, auth_id=""):
    if collection not in RECORD_COLLECTIONS:
        return _error(404, "Missing collection context.")
    denied = _authorize(collection, "list", kind, auth_id)
    if denied:
        return denied
    rows, err = _apply_filter(RECORD_COLLECTIONS[collection](), filter_expr)
    if err:
        return err
    rows = _apply_sort(rows, sort)
    total = len(rows)
    per_page = max(1, min(int(per_page or 30), 500))
    page = max(1, int(page or 1))
    start = (page - 1) * per_page
    items = [_serialize(collection, r, kind, auth_id) for r in rows[start:start + per_page]]
    items = _apply_expand(collection, items, expand, kind, auth_id)
    items = [_project(i, fields) for i in items]
    return _page_envelope(items, page, per_page, total, skip_total)


def get_record(collection, record_id, expand=None, fields=None, kind=GUEST, auth_id=""):
    if collection not in RECORD_COLLECTIONS:
        return _error(404, "Missing collection context.")
    row = _store.table(collection).get(record_id)
    if not row:
        return _error(404, "The requested resource wasn't found.")
    denied = _authorize(collection, "view", kind, auth_id, row)
    if denied:
        return denied
    record = _serialize(collection, row, kind, auth_id)
    record = _apply_expand(collection, [record], expand, kind, auth_id)[0]
    return _project(record, fields)


def create_record(collection, body, kind=GUEST, auth_id=""):
    if collection not in RECORD_COLLECTIONS:
        return _error(404, "Missing collection context.")
    denied = _authorize(collection, "create", kind, auth_id)
    if denied:
        return denied
    invalid = _validate(collection, body or {}, creating=True)
    if invalid:
        return _error(400, "Failed to create record.", invalid)
    now = _now()
    row = {"id": body.get("id") or _new_id(), "created": now, "updated": now}
    for field in _collection_meta(collection)["fields"]:
        row[field["name"]] = _cast(collection, field, body.get(field["name"]))
    _store_insert(collection, row)
    return _serialize(collection, row, kind, auth_id)


def update_record(collection, record_id, body, kind=GUEST, auth_id=""):
    if collection not in RECORD_COLLECTIONS:
        return _error(404, "Missing collection context.")
    row = _store.table(collection).get(record_id)
    if not row:
        return _error(404, "The requested resource wasn't found.")
    denied = _authorize(collection, "update", kind, auth_id, row)
    if denied:
        return denied
    invalid = _validate(collection, body or {}, creating=False)
    if invalid:
        return _error(400, "Failed to update record.", invalid)
    known = {f["name"]: f for f in _collection_meta(collection)["fields"]}
    patch = {name: _cast(collection, known[name], value)
             for name, value in (body or {}).items() if name in known}
    patch["updated"] = _now()
    return _serialize(collection, _store.table(collection).patch(record_id, patch),
                      kind, auth_id)


def delete_record(collection, record_id, kind=GUEST, auth_id=""):
    if collection not in RECORD_COLLECTIONS:
        return _error(404, "Missing collection context.")
    row = _store.table(collection).get(record_id)
    if not row:
        return _error(404, "The requested resource wasn't found.")
    denied = _authorize(collection, "delete", kind, auth_id, row)
    if denied:
        return denied
    _store.table(collection).delete(record_id)
    return {"deleted": record_id}


def _validate(collection, body, creating):
    """Required-field and relation checks, reported in PocketBase's `data` shape."""
    problems = {}
    for field in _collection_meta(collection)["fields"]:
        name, value = field["name"], body.get(field["name"])
        if creating and field["required"] and value in (None, "", []):
            problems[name] = {"code": "validation_required",
                              "message": "Missing required value."}
            continue
        if value in (None, "", []):
            continue
        rel = _RELATIONS.get((collection, name))
        if rel:
            ids = value if isinstance(value, list) else [value]
            missing = [i for i in ids if not _store.table(rel[0]).get(i)]
            if missing:
                problems[name] = {
                    "code": "validation_missing_rel_records",
                    "message": f"Failed to find records from field {name}: "
                               f"{', '.join(missing)}."}
    return problems


def _is_multi(collection, field_name):
    key = (collection, field_name)
    return _FILE_FIELDS.get(key) == "multi" or _RELATIONS.get(key, ("", ""))[1] == "multi"


def _cast(collection, field, value):
    """Coerce an incoming value to the declared field type."""
    if value is None:
        return [] if _is_multi(collection, field["name"]) else ""
    if field["type"] == "bool":
        return bool(value) if isinstance(value, bool) else \
            str(value).strip().lower() in ("true", "1", "yes")
    if field["type"] == "number":
        try:
            return int(value) if float(value).is_integer() else float(value)
        except (TypeError, ValueError):
            return 0
    if isinstance(value, list):
        return list(value)
    return value


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def get_file(collection, record_id, filename, thumb=None):
    """Return the stored file descriptor.

    Real PocketBase streams the file bytes; this mock answers with the metadata
    so a benchmark run stays deterministic and diffable.
    """
    if collection not in RECORD_COLLECTIONS:
        return _error(404, "Missing collection context.")
    row = _store.table(collection).get(record_id)
    if not row:
        return _error(404, "The requested resource wasn't found.")
    field = None
    for (owner, candidate) in _FILE_FIELDS:
        if owner != collection:
            continue
        stored = row.get(candidate)
        names = stored if isinstance(stored, list) else ([stored] if stored else [])
        if filename in names:
            field = candidate
            break
    if not field:
        return _error(404, "The requested resource wasn't found.")
    return {"collectionId": _collection_meta(collection)["id"],
            "collectionName": collection, "recordId": record_id, "field": field,
            "filename": filename, "thumb": thumb or "",
            "mimeType": _mime_for(filename), "size": _size_for(filename),
            "url": f"/api/files/{collection}/{record_id}/{filename}"}


_MIME_BY_EXT = {"png": "image/png", "jpg": "image/jpeg", "svg": "image/svg+xml",
                "txt": "text/plain", "pdf": "application/pdf", "zip": "application/zip"}


def _mime_for(filename):
    return _MIME_BY_EXT.get(filename.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def _size_for(filename):
    """Deterministic pseudo-size so repeated runs produce identical responses."""
    return 4096 + sum(ord(c) for c in filename) * 37


def create_file_token(kind=GUEST, auth_id=""):
    if kind == GUEST:
        return _error(403, "The request requires valid record authorization token.")
    token = uuid.uuid4().hex
    _store.table("file_tokens").upsert(
        {"token": token, "issued_to": auth_id, "created": _now()})
    return {"token": token}


# ---------------------------------------------------------------------------
# Logs / backups / crons / settings / realtime
# ---------------------------------------------------------------------------

def list_logs(page=1, per_page=30, filter_expr=None, sort="-created",
              kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    rows, err = _apply_filter(_logs_rows(), filter_expr)
    if err:
        return err
    rows = _apply_sort(rows, sort)
    per_page = max(1, min(int(per_page or 30), 500))
    page = max(1, int(page or 1))
    start = (page - 1) * per_page
    return _page_envelope(rows[start:start + per_page], page, per_page, len(rows))


def log_stats(filter_expr=None, kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    rows, err = _apply_filter(_logs_rows(), filter_expr)
    if err:
        return err
    buckets = {}
    for row in rows:
        day = str(row.get("created", ""))[:10]
        buckets[day] = buckets.get(day, 0) + 1
    return [{"date": f"{day} 00:00:00.000Z", "total": total}
            for day, total in sorted(buckets.items())]


def list_backups(kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    return sorted(_backups_rows(), key=lambda b: b["modified"], reverse=True)


def create_backup(name=None, kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    key = name or f"pb_backup_orbit_status_{time.strftime('%Y%m%d%H%M%S', time.gmtime())}.zip"
    if _store.table("backups").get(key):
        return _error(400, "Failed to create backup.",
                      {"name": {"code": "validation_backup_name_exists",
                                "message": "A backup with this name already exists."}})
    backup = {"key": key, "size": _size_for(key) * 1024, "modified": _now()}
    _store.table("backups").upsert(backup)
    return backup


def delete_backup(key, kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    if not _store.table("backups").get(key):
        return _error(404, "The requested resource wasn't found.")
    _store.table("backups").delete(key)
    return {"deleted": key}


def list_crons(kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    return _crons_rows()


def get_settings(kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    return {k: v for k, v in _settings_doc().items() if k != "tokens"}


def subscribe(client_id=None, subscriptions=None, kind=GUEST, auth_id=""):
    """Realtime subscribe. The SSE stream itself is out of scope for the mock."""
    client_id = client_id or _new_id()
    topics = subscriptions or []
    unknown = [t for t in topics if t.split("/")[0] not in RECORD_COLLECTIONS]
    if unknown:
        return _error(400, "Something went wrong while processing your request.",
                      {"subscriptions": {"code": "validation_unknown_collection",
                                         "message": f"Unknown topic(s): {', '.join(unknown)}."}})
    record = {"clientId": client_id, "subscriptions": topics,
              "identity": auth_id or "", "created": _now()}
    _store.table("subscriptions").upsert(record)
    return record


def list_subscriptions(kind=GUEST, auth_id=""):
    if kind != SUPERUSER:
        return _error(403, "Only superusers can perform this action.")
    return _subscriptions_rows()


def health():
    settings = _settings_doc()
    return {"code": 200, "message": "API is healthy.",
            "data": {"canBackup": True, "version": settings.get("version", "v0.24.4"),
                     "appName": settings.get("meta", {}).get("appName", "PocketBase")}}


_store.eager_load()
