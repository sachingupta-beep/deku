"""Data access module for the Directus API mock service.

Models a self-hosted Directus 11 instance running the Orbit Labs marketing site:
the `posts`, `categories` and `job_openings` collections, the system collections
(users, roles, permissions, files, activity, flows, settings), and the Directus
query language — `filter` JSON, `fields` with relational dot-notation, `sort`,
`search`, `limit`/`offset`/`page`, `meta` and `aggregate`/`groupBy`.

Access control is data-driven: `permissions.json` maps (role, collection, action)
onto a Directus permission filter, exactly as the real product stores it, so the
admin plane can drift a permission row and change what the API returns.
Mutations are held in process memory and reset on restart.
"""

import json
import time
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str, strict_bool)

_store = get_store("directus-api")
_API = "directus-api"


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


_store.register("posts", primary_key="id",
                initial_loader=lambda: _coerce_posts(_load("posts.json", "posts")))
_store.register("categories", primary_key="id",
                initial_loader=lambda: _coerce_categories(_load("categories.json", "categories")))
_store.register("job_openings", primary_key="id",
                initial_loader=lambda: _coerce_jobs(_load("job_openings.json", "job_openings")))
_store.register("collections", primary_key="collection",
                initial_loader=lambda: _coerce_collections(_load("collections.json", "collections")))
_store.register("fields", primary_key="id",
                initial_loader=lambda: _coerce_fields(_load("fields.json", "fields")))
_store.register("directus_users", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("users.json", "directus_users")])
_store.register("directus_roles", primary_key="id",
                initial_loader=lambda: _coerce_roles(_load("roles.json", "directus_roles")))
_store.register("directus_permissions", primary_key="id",
                initial_loader=lambda: _coerce_permissions(_load("permissions.json", "directus_permissions")))
_store.register("directus_files", primary_key="id",
                initial_loader=lambda: _coerce_files(_load("files.json", "directus_files")))
_store.register("directus_activity", primary_key="id",
                initial_loader=lambda: _coerce_activity(_load("activity.json", "directus_activity")))
_store.register("directus_flows", primary_key="id",
                initial_loader=lambda: _coerce_flows(_load("flows.json", "directus_flows")))
_store.register_document("settings", initial_loader=_load_settings)
# Born-empty: sessions are minted at runtime by POST /auth/login.
_store.register("sessions", primary_key="access_token", initial_loader=lambda: [])


def _posts_rows():
    return _store.table("posts").rows()


def _categories_rows():
    return _store.table("categories").rows()


def _jobs_rows():
    return _store.table("job_openings").rows()


def _collections_rows():
    return _store.table("collections").rows()


def _fields_rows():
    return _store.table("fields").rows()


def _users_rows():
    return _store.table("directus_users").rows()


def _roles_rows():
    return _store.table("directus_roles").rows()


def _permissions_rows():
    return _store.table("directus_permissions").rows()


def _files_rows():
    return _store.table("directus_files").rows()


def _activity_rows():
    return _store.table("directus_activity").rows()


def _flows_rows():
    return _store.table("directus_flows").rows()


def _settings_doc():
    return _store.document("settings").get()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".000Z"


def _csv_list(r, column):
    raw = opt_str(r, column, default="")
    return [part for part in raw.split(";") if part]


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

def _coerce_posts(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "category": opt_int(r, "category", default=None),
             "reading_minutes": opt_int(r, "reading_minutes", default=0),
             "hits": opt_int(r, "hits", default=0),
             "tags": _csv_list(r, "tags"),
             "publish_date": opt_str(r, "publish_date", default="") or None,
             "image": opt_str(r, "image", default="") or None} for r in rows]


def _coerce_categories(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "sort": opt_int(r, "sort", default=0)} for r in rows]


def _coerce_jobs(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "salary_min": opt_int(r, "salary_min", default=0),
             "salary_max": opt_int(r, "salary_max", default=0),
             "posted_on": opt_str(r, "posted_on", default="") or None,
             "closes_on": opt_str(r, "closes_on", default="") or None} for r in rows]


def _coerce_collections(rows):
    return [{**_strip_ctx(r), "hidden": strict_bool(r, "hidden"),
             "singleton": strict_bool(r, "singleton")} for r in rows]


def _coerce_fields(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "sort": opt_int(r, "sort", default=0),
             "required": strict_bool(r, "required"),
             "readonly": strict_bool(r, "readonly"),
             "hidden": strict_bool(r, "hidden")} for r in rows]


def _coerce_roles(rows):
    return [{**_strip_ctx(r), "admin_access": strict_bool(r, "admin_access"),
             "app_access": strict_bool(r, "app_access")} for r in rows]


def _coerce_permissions(rows):
    out = []
    for r in rows:
        raw = opt_str(r, "permissions", default="{}") or "{}"
        out.append({**_strip_ctx(r), "id": opt_int(r, "id", default=0),
                    "permissions": json.loads(raw),
                    "fields": _field_list(opt_str(r, "fields", default="*"))})
    return out


def _field_list(raw):
    return ["*"] if raw.strip() == "*" else [f.strip() for f in raw.split(",") if f.strip()]


def _coerce_files(rows):
    return [{**_strip_ctx(r), "filesize": opt_int(r, "filesize", default=0),
             "width": opt_int(r, "width", default=None),
             "height": opt_int(r, "height", default=None),
             "folder": opt_str(r, "folder", default="") or None} for r in rows]


def _coerce_activity(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0)} for r in rows]


def _coerce_flows(rows):
    out = []
    for r in rows:
        options = {}
        for pair in _csv_list(r, "options"):
            key, _, value = pair.partition("=")
            options[key] = value
        out.append({**_strip_ctx(r), "options": options,
                    "accountability": None if opt_str(r, "accountability") == "null"
                    else opt_str(r, "accountability")})
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(status, code, message):
    """Directus-shaped error body. The house `error` key drives the response."""
    return {"error": message, "status": status,
            "errors": [{"message": message, "extensions": {"code": code}}]}


def _forbidden():
    """Directus answers 403 for anything the caller may not see, including rows
    that do not exist -- deliberately, so the API never leaks record existence."""
    return _error(403, "FORBIDDEN", "You don't have permission to access this.")


def _next_serial(table):
    """Next auto-increment id for a user collection.

    Scans the live rows instead of caching a counter: the admin plane can inject
    rows out of band and a cached counter would collide with them.
    """
    ids = [r["id"] for r in _store.table(table).rows() if isinstance(r.get("id"), int)]
    return (max(ids) + 1) if ids else 1


USER_COLLECTIONS = {
    "posts": _posts_rows,
    "categories": _categories_rows,
    "job_openings": _jobs_rows,
}

# (collection, field) -> (related table, related key)
_RELATIONS = {
    ("posts", "category"): ("categories", "id"),
    ("posts", "author"): ("directus_users", "id"),
    ("posts", "image"): ("directus_files", "id"),
    ("job_openings", "hiring_manager"): ("directus_users", "id"),
}

_RELATED_ROWS = {
    "categories": _categories_rows,
    "directus_users": _users_rows,
    "directus_files": _files_rows,
}

# Fields never returned for a related directus_users record.
_USER_PRIVATE_FIELDS = {"last_page", "language", "theme"}


# ---------------------------------------------------------------------------
# Authentication + permissions
# ---------------------------------------------------------------------------

ADMIN = "admin"
EDITOR = "editor"
PUBLIC = "public"


def resolve_identity(authorization=None, access_token=None):
    """Map a static token / bearer token onto (kind, user_id, role_id).

    Directus accepts a static token as `Authorization: Bearer <token>` or as an
    `access_token` query parameter. The admin token grants `admin_access`, the
    editor token authenticates as the editor user, and any other non-empty token
    is also treated as the editor -- keeping the fleet convention that any token
    is accepted. No token at all resolves to the Public role.
    """
    token = (access_token or "").strip()
    if not token and authorization:
        raw = str(authorization).strip()
        token = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    tokens = _settings_doc().get("tokens", {})
    if not token:
        return PUBLIC, "", tokens.get("publicRoleId", "")
    if token == tokens.get("admin"):
        return ADMIN, tokens.get("adminUserId", ""), _role_of(tokens.get("adminUserId"))
    session = _store.table("sessions").get(token)
    if session:
        return session["kind"], session["user"], session["role"]
    return EDITOR, tokens.get("editorUserId", ""), _role_of(tokens.get("editorUserId"))


def _role_of(user_id):
    user = _store.table("directus_users").get(user_id)
    return user["role"] if user else ""


def _is_admin(role_id):
    role = _store.table("directus_roles").get(role_id)
    return bool(role and role["admin_access"])


def _permission_for(role_id, collection, action):
    """The permission row governing (role, collection, action), or None."""
    return _store.table("directus_permissions").find_one(
        lambda p: p["role"] == role_id and p["collection"] == collection
        and p["action"] == action)


def _authorize(role_id, collection, action):
    """Return (permission_row, error). Admin roles bypass the permission table."""
    if _is_admin(role_id):
        return None, None
    permission = _permission_for(role_id, collection, action)
    if not permission:
        return None, _forbidden()
    return permission, None


def _permitted_fields(permission, row):
    if not permission or permission["fields"] == ["*"]:
        return row
    allowed = set(permission["fields"])
    return {k: v for k, v in row.items() if k in allowed}


# ---------------------------------------------------------------------------
# Filter language
# ---------------------------------------------------------------------------

def _match(row, node, collection=None):
    """Evaluate a Directus filter object against a row."""
    if not node:
        return True
    for key, value in node.items():
        if key == "_and":
            if not all(_match(row, sub, collection) for sub in value):
                return False
        elif key == "_or":
            if not any(_match(row, sub, collection) for sub in value):
                return False
        elif key.startswith("_"):
            return False
        else:
            if not _match_field(row, key, value, collection):
                return False
    return True


def _match_field(row, field, condition, collection):
    if isinstance(condition, dict) and condition and \
            not any(k.startswith("_") for k in condition):
        related = _resolve_relation(row, field, collection)
        return _match(related, condition) if related else False
    value = row.get(field)
    if not isinstance(condition, dict):
        return _compare(value, "_eq", condition)
    return all(_compare(value, op, operand) for op, operand in condition.items())


def _resolve_relation(row, field, collection):
    target = _RELATIONS.get((collection, field))
    if not target:
        return None
    table, key = target
    needle = row.get(field)
    if needle in (None, ""):
        return None
    return next((r for r in _RELATED_ROWS[table]() if r.get(key) == needle), None)


def _compare(value, op, operand):
    if op == "_eq":
        return _eq(value, operand)
    if op == "_neq":
        return not _eq(value, operand)
    if op == "_null":
        return (value in (None, "")) is bool(operand)
    if op == "_nnull":
        return (value not in (None, "")) is bool(operand)
    if op == "_empty":
        return (value in (None, "", [])) is bool(operand)
    if op == "_nempty":
        return (value not in (None, "", [])) is bool(operand)
    if op == "_in":
        return any(_eq(value, item) for item in operand or [])
    if op == "_nin":
        return not any(_eq(value, item) for item in operand or [])
    if op == "_contains":
        return _haystack(value, operand, case_sensitive=True)
    if op == "_icontains":
        return _haystack(value, operand, case_sensitive=False)
    if op == "_ncontains":
        return not _haystack(value, operand, case_sensitive=True)
    if op == "_starts_with":
        return str(value or "").startswith(str(operand))
    if op == "_ends_with":
        return str(value or "").endswith(str(operand))
    if op in ("_between", "_nbetween"):
        low, high = (operand or [None, None])[:2]
        inside = _order(value, low, ">=") and _order(value, high, "<=")
        return inside if op == "_between" else not inside
    if op in ("_lt", "_lte", "_gt", "_gte"):
        return _order(value, operand,
                      {"_lt": "<", "_lte": "<=", "_gt": ">", "_gte": ">="}[op])
    return False


def _eq(value, operand):
    if isinstance(value, bool) or isinstance(operand, bool):
        return bool(value) == bool(operand)
    if isinstance(value, list):
        return operand in value
    if isinstance(value, int) and isinstance(operand, str):
        try:
            operand = int(operand)
        except ValueError:
            return False
    if isinstance(value, str) and isinstance(operand, (int, float)):
        operand = str(operand)
    return value == operand


def _haystack(value, needle, case_sensitive):
    if isinstance(value, list):
        return any(_haystack(item, needle, case_sensitive) for item in value)
    left, right = str(value or ""), str(needle)
    if not case_sensitive:
        left, right = left.lower(), right.lower()
    return right in left


def _order(value, operand, op):
    if value is None or operand is None:
        return False
    if isinstance(value, (int, float)) and isinstance(operand, str):
        try:
            operand = type(value)(operand)
        except ValueError:
            return False
    if isinstance(value, str) and isinstance(operand, (int, float)):
        operand = str(operand)
    try:
        return {"<": value < operand, "<=": value <= operand,
                ">": value > operand, ">=": value >= operand}[op]
    except TypeError:
        return False


def _search(rows, term):
    if not term:
        return rows
    needle = str(term).lower()
    return [r for r in rows
            if any(needle in str(v).lower() for v in r.values() if v is not None)]


def _sort(rows, spec):
    if not spec:
        return rows
    out = list(rows)
    for clause in reversed([c.strip() for c in spec.split(",") if c.strip()]):
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
        return ",".join(str(v) for v in value)
    return str(value)


# ---------------------------------------------------------------------------
# Field selection
# ---------------------------------------------------------------------------

def _apply_fields(rows, spec, collection):
    """Project `fields`, expanding relations written in dot notation."""
    if not spec:
        return rows
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    plain, nested, expand_all = [], {}, False
    for part in parts:
        if part == "*":
            plain.append("*")
        elif part == "*.*":
            plain.append("*")
            expand_all = True
        elif "." in part:
            head, _, tail = part.partition(".")
            nested.setdefault(head, []).append(tail)
        else:
            plain.append(part)
    out = []
    for row in rows:
        projected = dict(row) if "*" in plain else {k: row.get(k) for k in plain}
        targets = dict(nested)
        if expand_all:
            for (owner, field) in _RELATIONS:
                if owner == collection:
                    targets.setdefault(field, ["*"])
        for field, sub_fields in targets.items():
            related = _resolve_relation(row, field, collection)
            projected[field] = _project_related(related, sub_fields) if related else None
        out.append(projected)
    return out


def _project_related(related, sub_fields):
    visible = {k: v for k, v in related.items() if k not in _USER_PRIVATE_FIELDS}
    if "*" in sub_fields:
        return visible
    return {k: visible.get(k) for k in sub_fields}


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

def list_items(collection, filter_json=None, fields=None, sort=None, search=None,
               limit=100, offset=0, page=None, meta=None, aggregate_json=None,
               group_by=None, role_id="", kind=PUBLIC):
    if collection not in USER_COLLECTIONS:
        return _forbidden()
    permission, denied = _authorize(role_id, collection, "read")
    if denied:
        return denied
    rows = USER_COLLECTIONS[collection]()
    if permission:
        rows = [r for r in rows if _match(r, permission["permissions"], collection)]
    # total_count is what the role may read; filter_count applies the query on top.
    total = len(rows)
    try:
        parsed = json.loads(filter_json) if filter_json else None
    except json.JSONDecodeError:
        return _error(400, "INVALID_QUERY", "Invalid filter: could not parse JSON.")
    if parsed:
        rows = [r for r in rows if _match(r, parsed, collection)]
    rows = _search(rows, search)
    filter_count = len(rows)

    if aggregate_json:
        return _aggregate(rows, aggregate_json, group_by)

    rows = _sort(rows, sort)
    limit = int(limit if limit is not None else 100)
    offset = int(offset or 0)
    if page:
        offset = (max(1, int(page)) - 1) * limit
    rows = rows if limit < 0 else rows[offset:offset + limit]
    rows = [_permitted_fields(permission, r) for r in rows]
    data = _apply_fields(rows, fields, collection)
    if not meta:
        return {"data": data}
    return {"data": data, "meta": _meta(meta, total, filter_count)}


def _meta(spec, total, filter_count):
    wanted = {"total_count", "filter_count"} if spec.strip() == "*" else \
        {p.strip() for p in spec.split(",") if p.strip()}
    out = {}
    if "total_count" in wanted:
        out["total_count"] = total
    if "filter_count" in wanted:
        out["filter_count"] = filter_count
    return out


def _aggregate(rows, aggregate_json, group_by):
    try:
        spec = json.loads(aggregate_json)
    except json.JSONDecodeError:
        return _error(400, "INVALID_QUERY", "Invalid aggregate: could not parse JSON.")
    groups = {}
    keys = [k.strip() for k in (group_by or "").split(",") if k.strip()]
    for row in rows:
        bucket = tuple(row.get(k) for k in keys)
        groups.setdefault(bucket, []).append(row)
    out = []
    for bucket, members in groups.items():
        entry = {key: value for key, value in zip(keys, bucket)}
        for function, field in spec.items():
            entry[function] = _aggregate_value(function, field, members)
        out.append(entry)
    return {"data": out}


def _aggregate_value(function, field, members):
    if function == "count":
        return len(members) if field in ("*", None) else \
            len([m for m in members if m.get(field) not in (None, "")])
    values = [m.get(field) for m in members if isinstance(m.get(field), (int, float))]
    if not values:
        return None
    if function == "sum":
        return sum(values)
    if function == "avg":
        return round(sum(values) / len(values), 4)
    if function == "min":
        return min(values)
    if function == "max":
        return max(values)
    return None


def get_item(collection, item_id, fields=None, role_id="", kind=PUBLIC):
    if collection not in USER_COLLECTIONS:
        return _forbidden()
    permission, denied = _authorize(role_id, collection, "read")
    if denied:
        return denied
    row = _store.table(collection).get(_cast_id(collection, item_id))
    if not row:
        return _forbidden()
    if permission and not _match(row, permission["permissions"], collection):
        return _forbidden()
    projected = _apply_fields([_permitted_fields(permission, row)], fields, collection)
    return {"data": projected[0]}


def create_item(collection, payload, role_id="", kind=PUBLIC):
    if collection not in USER_COLLECTIONS:
        return _forbidden()
    _, denied = _authorize(role_id, collection, "create")
    if denied:
        return denied
    missing = _missing_required(collection, payload or {})
    if missing:
        return _error(400, "FAILED_VALIDATION",
                      f'Value for field "{missing}" in collection "{collection}" '
                      f"can't be null.")
    row = {"id": _next_serial(collection)}
    for field in _collection_fields(collection):
        if field["field"] == "id":
            continue
        row[field["field"]] = _cast(field, (payload or {}).get(field["field"]))
    if collection == "posts":
        row["date_created"] = row["date_updated"] = _now()
        row["user_created"] = _settings_doc()["tokens"].get("editorUserId", "")
    _store_insert(collection, row)
    return {"data": row}


def update_item(collection, item_id, payload, role_id="", kind=PUBLIC):
    if collection not in USER_COLLECTIONS:
        return _forbidden()
    permission, denied = _authorize(role_id, collection, "update")
    if denied:
        return denied
    row = _store.table(collection).get(_cast_id(collection, item_id))
    if not row:
        return _forbidden()
    if permission and not _match(row, permission["permissions"], collection):
        return _forbidden()
    known = {f["field"]: f for f in _collection_fields(collection)}
    unknown = [k for k in (payload or {}) if k not in known]
    if unknown:
        return _error(400, "INVALID_PAYLOAD",
                      f'Invalid payload. Field "{unknown[0]}" does not exist in '
                      f'collection "{collection}".')
    patch = {k: _cast(known[k], v) for k, v in (payload or {}).items() if k != "id"}
    if collection == "posts":
        patch["date_updated"] = _now()
    return {"data": _store.table(collection).patch(row["id"], patch)}


def delete_item(collection, item_id, role_id="", kind=PUBLIC):
    if collection not in USER_COLLECTIONS:
        return _forbidden()
    _, denied = _authorize(role_id, collection, "delete")
    if denied:
        return denied
    row = _store.table(collection).get(_cast_id(collection, item_id))
    if not row:
        return _forbidden()
    _store.table(collection).delete(row["id"])
    return None


def _collection_fields(collection):
    return [f for f in _fields_rows() if f["collection"] == collection]


def _missing_required(collection, payload):
    for field in _collection_fields(collection):
        if field["field"] == "id" or not field["required"]:
            continue
        if payload.get(field["field"]) in (None, "", []):
            return field["field"]
    return None


def _cast_id(collection, item_id):
    try:
        return int(item_id)
    except (TypeError, ValueError):
        return item_id


def _cast(field, value):
    if value is None:
        return [] if field["type"] == "csv" else None
    if field["type"] == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    if field["type"] == "boolean":
        return bool(value) if isinstance(value, bool) else \
            str(value).strip().lower() in ("true", "1", "yes")
    if field["type"] == "csv":
        return list(value) if isinstance(value, list) else \
            [p for p in str(value).split(",") if p]
    return value


# ---------------------------------------------------------------------------
# Schema + system collections
# ---------------------------------------------------------------------------

def list_collections(role_id="", kind=PUBLIC):
    if not _is_admin(role_id) and kind == PUBLIC:
        return _forbidden()
    return {"data": [_with_meta(c) for c in _collections_rows()]}


def get_collection(collection, role_id="", kind=PUBLIC):
    if not _is_admin(role_id) and kind == PUBLIC:
        return _forbidden()
    row = _store.table("collections").get(collection)
    if not row:
        return _forbidden()
    return {"data": _with_meta(row)}


def _with_meta(row):
    """Directus splits a collection into `schema` and `meta` halves."""
    meta_keys = {"icon", "note", "display_template", "hidden", "singleton",
                 "sort_field", "archive_field", "archive_value", "accountability",
                 "group"}
    return {"collection": row["collection"],
            "meta": {k: v for k, v in row.items() if k in meta_keys},
            "schema": {"name": row["collection"]}}


def list_fields(collection=None, role_id="", kind=PUBLIC):
    if not _is_admin(role_id) and kind == PUBLIC:
        return _forbidden()
    rows = _fields_rows()
    if collection:
        if not _store.table("collections").get(collection):
            return _forbidden()
        rows = [f for f in rows if f["collection"] == collection]
    return {"data": [_field_payload(f) for f in rows]}


def _field_payload(field):
    return {"collection": field["collection"], "field": field["field"],
            "type": field["type"],
            "meta": {"interface": field["interface"], "special": field["special"],
                     "required": field["required"], "readonly": field["readonly"],
                     "hidden": field["hidden"], "sort": field["sort"],
                     "note": field["note"]},
            "schema": {"name": field["field"], "data_type": field["type"],
                       "is_nullable": not field["required"]}}


def list_users(filter_json=None, fields=None, sort=None, limit=100, offset=0,
               role_id="", kind=PUBLIC):
    if not _is_admin(role_id):
        return _forbidden()
    rows = _users_rows()
    if filter_json:
        try:
            rows = [r for r in rows if _match(r, json.loads(filter_json))]
        except json.JSONDecodeError:
            return _error(400, "INVALID_QUERY", "Invalid filter: could not parse JSON.")
    rows = _sort(rows, sort)[int(offset or 0):int(offset or 0) + int(limit or 100)]
    return {"data": _apply_fields(rows, fields, "directus_users")}


def get_user(user_id, role_id="", kind=PUBLIC):
    if not _is_admin(role_id):
        return _forbidden()
    row = _store.table("directus_users").get(user_id)
    if not row:
        return _forbidden()
    return {"data": row}


def get_me(user_id, role_id="", kind=PUBLIC):
    if kind == PUBLIC:
        return _error(401, "INVALID_CREDENTIALS", "Invalid user credentials.")
    row = _store.table("directus_users").get(user_id)
    if not row:
        return _error(401, "INVALID_CREDENTIALS", "Invalid user credentials.")
    return {"data": row}


def list_roles(role_id="", kind=PUBLIC):
    if not _is_admin(role_id):
        return _forbidden()
    return {"data": _roles_rows()}


def get_role(target_id, role_id="", kind=PUBLIC):
    if not _is_admin(role_id):
        return _forbidden()
    row = _store.table("directus_roles").get(target_id)
    if not row:
        return _forbidden()
    return {"data": row}


def list_permissions(role_id="", kind=PUBLIC):
    if not _is_admin(role_id):
        return _forbidden()
    return {"data": _permissions_rows()}


def list_files(filter_json=None, sort=None, limit=100, offset=0,
               role_id="", kind=PUBLIC):
    _, denied = _authorize(role_id, "directus_files", "read")
    if denied:
        return denied
    rows = _files_rows()
    if filter_json:
        try:
            rows = [r for r in rows if _match(r, json.loads(filter_json))]
        except json.JSONDecodeError:
            return _error(400, "INVALID_QUERY", "Invalid filter: could not parse JSON.")
    rows = _sort(rows, sort)[int(offset or 0):int(offset or 0) + int(limit or 100)]
    return {"data": rows}


def get_file(file_id, role_id="", kind=PUBLIC):
    _, denied = _authorize(role_id, "directus_files", "read")
    if denied:
        return denied
    row = _store.table("directus_files").get(file_id)
    if not row:
        return _forbidden()
    return {"data": row}


def list_activity(filter_json=None, sort="-timestamp", limit=100, offset=0,
                  role_id="", kind=PUBLIC):
    if not _is_admin(role_id):
        return _forbidden()
    rows = _activity_rows()
    if filter_json:
        try:
            rows = [r for r in rows if _match(r, json.loads(filter_json))]
        except json.JSONDecodeError:
            return _error(400, "INVALID_QUERY", "Invalid filter: could not parse JSON.")
    rows = _sort(rows, sort)[int(offset or 0):int(offset or 0) + int(limit or 100)]
    return {"data": rows}


def list_flows(role_id="", kind=PUBLIC):
    if not _is_admin(role_id):
        return _forbidden()
    return {"data": _flows_rows()}


def get_settings(role_id="", kind=PUBLIC):
    if not _is_admin(role_id):
        return _forbidden()
    return {"data": {k: v for k, v in _settings_doc().items() if k != "tokens"}}


# ---------------------------------------------------------------------------
# Auth + server
# ---------------------------------------------------------------------------

def login(email=None, password=None):
    credentials = _settings_doc()["tokens"].get("credentials", {})
    if email != credentials.get("email") or password != credentials.get("password"):
        return _error(401, "INVALID_CREDENTIALS", "Invalid user credentials.")
    tokens = _settings_doc()["tokens"]
    user_id = tokens.get("editorUserId", "")
    session = {"access_token": f"dr_session_{uuid.uuid4().hex[:16]}",
               "refresh_token": f"dr_refresh_{uuid.uuid4().hex[:24]}",
               "kind": EDITOR, "user": user_id, "role": _role_of(user_id),
               "created": _now()}
    _store.table("sessions").upsert(session)
    return {"data": {"access_token": session["access_token"], "expires": 900000,
                     "refresh_token": session["refresh_token"]}}


def server_health():
    return {"status": "ok", "releaseId": _settings_doc().get("version", "11.1.1"),
            "serviceId": "8f2c1b40-5e93-4a17-9d26-71c0e84b3f52",
            "checks": {"pg:responseTime": [{"status": "ok", "componentType": "datastore",
                                            "observedValue": 3.1, "observedUnit": "ms"}],
                       "storage:local:responseTime": [{"status": "ok",
                                                       "componentType": "objectstore",
                                                       "observedValue": 1.4,
                                                       "observedUnit": "ms"}]}}


def server_info():
    settings = _settings_doc()
    return {"data": {
        "project": {"project_name": settings["project_name"],
                    "project_descriptor": settings["project_descriptor"],
                    "project_logo": None, "project_color": settings["project_color"],
                    "default_language": settings["default_language"],
                    "public_note": settings["public_note"]},
        "directus": {"version": settings["version"]},
        "node": {"version": "20.11.1", "uptime": 864321},
        "os": {"type": "Linux", "version": "6.1.0", "uptime": 1728642},
    }}


_store.eager_load()
