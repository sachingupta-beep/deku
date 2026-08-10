"""Data access module for the Appwrite API mock service.

Models a self-hosted Appwrite 1.6 project backing the Orbit Labs mobile app:
Databases (documents with the Query DSL and per-document permissions), Storage,
Functions with execution history, Teams, Users, Locale and the health probes.

Documents carry Appwrite's `$`-prefixed system attributes and list responses use
the `{"total": n, "<resource>": [...]}` envelope. Mutations are held in process
memory and reset on restart.
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
    read_seed_with_ctx, get_store, opt_int, opt_str, strict_bool)

_store = get_store("appwrite-api")
_API = "appwrite-api"


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


def _load_project():
    with open(DATA_DIR / "project.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("databases", primary_key="id",
                initial_loader=lambda: _coerce_databases(_load("databases.json", "databases")))
_store.register("collections", primary_key="id",
                initial_loader=lambda: _coerce_collections(_load("collections.json", "collections")))
_store.register("feedback", primary_key="id",
                initial_loader=lambda: _coerce_documents(_load("feedback.json", "feedback")))
_store.register("feature_flags", primary_key="id",
                initial_loader=lambda: _coerce_documents(_load("feature_flags.json", "feature_flags")))
_store.register("releases", primary_key="id",
                initial_loader=lambda: _coerce_documents(_load("releases.json", "releases")))
_store.register("buckets", primary_key="id",
                initial_loader=lambda: _coerce_buckets(_load("buckets.json", "buckets")))
_store.register("files", primary_key="id",
                initial_loader=lambda: _coerce_files(_load("files.json", "files")))
_store.register("functions", primary_key="id",
                initial_loader=lambda: _coerce_functions(_load("functions.json", "functions")))
_store.register("executions", primary_key="id",
                initial_loader=lambda: _coerce_executions(_load("executions.json", "executions")))
_store.register("teams", primary_key="id",
                initial_loader=lambda: _coerce_teams(_load("teams.json", "teams")))
_store.register("memberships", primary_key="id",
                initial_loader=lambda: _coerce_memberships(_load("memberships.json", "memberships")))
_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json", "users")))
_store.register_document("project", initial_loader=_load_project)


def _databases_rows():
    return _store.table("databases").rows()


def _collections_rows():
    return _store.table("collections").rows()


def _buckets_rows():
    return _store.table("buckets").rows()


def _files_rows():
    return _store.table("files").rows()


def _functions_rows():
    return _store.table("functions").rows()


def _executions_rows():
    return _store.table("executions").rows()


def _teams_rows():
    return _store.table("teams").rows()


def _memberships_rows():
    return _store.table("memberships").rows()


def _users_rows():
    return _store.table("users").rows()


def _project_doc():
    return _store.document("project").get()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".000+00:00"


def _semi_list(r, column):
    raw = opt_str(r, column, default="")
    return [part for part in raw.split(";") if part]


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

def _coerce_databases(rows):
    return [{**_strip_ctx(r), "enabled": strict_bool(r, "enabled")} for r in rows]


def _coerce_collections(rows):
    out = []
    for r in rows:
        out.append({
            **_strip_ctx(r),
            "enabled": strict_bool(r, "enabled"),
            "documentSecurity": strict_bool(r, "documentSecurity"),
            "permissions": _semi_list(r, "permissions"),
            "attributes": [_parse_attribute(spec) for spec in _semi_list(r, "attributes")],
            "indexes": [_parse_index(spec) for spec in _semi_list(r, "indexes")],
        })
    return out


def _parse_attribute(spec):
    """`name:type:required` from the seed becomes an Appwrite attribute descriptor."""
    name, kind, required = (spec.split(":") + ["string", "false"])[:3]
    array = kind.endswith("[]")
    return {"key": name, "type": kind[:-2] if array else kind, "array": array,
            "required": required == "true", "status": "available"}


def _parse_index(spec):
    """`key:type:attribute:order` from the seed becomes an index descriptor."""
    name, kind, attribute, order = (spec.split(":") + ["key", "", "ASC"])[:4]
    return {"key": name, "type": kind, "attributes": [attribute], "orders": [order],
            "status": "available"}


def _coerce_documents(rows):
    """Document rows keep their declared attributes; only the envelope is typed."""
    out = []
    for r in rows:
        row = {**_strip_ctx(r), "permissions": _semi_list(r, "permissions")}
        for key in ("rating", "rolloutPercent", "buildNumber"):
            if key in row:
                row[key] = opt_int(r, key, default=0)
        if "enabled" in row:
            row["enabled"] = strict_bool(r, "enabled")
        if "platforms" in row:
            row["platforms"] = _semi_list(r, "platforms")
        out.append(row)
    return out


def _coerce_buckets(rows):
    return [{**_strip_ctx(r), "enabled": strict_bool(r, "enabled"),
             "fileSecurity": strict_bool(r, "fileSecurity"),
             "encryption": strict_bool(r, "encryption"),
             "antivirus": strict_bool(r, "antivirus"),
             "permissions": _semi_list(r, "permissions"),
             "allowedFileExtensions": _semi_list(r, "allowedFileExtensions"),
             "maximumFileSize": opt_int(r, "maximumFileSize", default=0)} for r in rows]


def _coerce_files(rows):
    return [{**_strip_ctx(r), "permissions": _semi_list(r, "permissions"),
             "sizeOriginal": opt_int(r, "sizeOriginal", default=0),
             "chunksTotal": opt_int(r, "chunksTotal", default=1),
             "chunksUploaded": opt_int(r, "chunksUploaded", default=1)} for r in rows]


def _coerce_functions(rows):
    return [{**_strip_ctx(r), "enabled": strict_bool(r, "enabled"),
             "live": strict_bool(r, "live"), "logging": strict_bool(r, "logging"),
             "timeout": opt_int(r, "timeout", default=15),
             "events": _semi_list(r, "events"),
             "scopes": _semi_list(r, "scopes")} for r in rows]


def _coerce_executions(rows):
    return [{**_strip_ctx(r),
             "responseStatusCode": opt_int(r, "responseStatusCode", default=200),
             "duration": float(opt_str(r, "duration", default="0") or 0)} for r in rows]


def _coerce_teams(rows):
    return [{**_strip_ctx(r), "total": opt_int(r, "total", default=0),
             "prefs": {"plan": opt_str(r, "prefs_plan", default="")}} for r in rows]


def _coerce_memberships(rows):
    return [{**_strip_ctx(r), "confirm": strict_bool(r, "confirm"),
             "roles": _semi_list(r, "roles")} for r in rows]


def _coerce_users(rows):
    return [{**_strip_ctx(r), "emailVerification": strict_bool(r, "emailVerification"),
             "phoneVerification": strict_bool(r, "phoneVerification"),
             "status": strict_bool(r, "status"),
             "labels": _semi_list(r, "labels"),
             "prefs": {"theme": opt_str(r, "prefs_theme", default=""),
                       "locale": opt_str(r, "prefs_locale", default="")}} for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id(prefix=""):
    """Appwrite auto-ids are 20-character alphanumeric strings."""
    generated = uuid.uuid4().hex[:20]
    return f"{prefix}{generated}" if prefix else generated


def _error(code, type_, message):
    """Appwrite-shaped error body. The house `error` key drives the response."""
    return {"error": message, "message": message, "code": code, "type": type_,
            "version": _project_doc().get("version", "1.6.0")}


def _envelope(key, rows):
    return {"total": len(rows), key: rows}


# Documents are stored one table per collection, keyed by collection id.
DOCUMENT_TABLES = {"feedback", "feature_flags", "releases"}

# Attributes Appwrite exposes with a `$` prefix, mapped to their stored names.
_SYSTEM_ATTRS = {"$id": "id", "$createdAt": "createdAt", "$updatedAt": "updatedAt",
                 "$permissions": "permissions", "$collectionId": "collectionId",
                 "$databaseId": "databaseId"}


def _as_document(row):
    hidden = set(_SYSTEM_ATTRS.values())
    return {"$id": row["id"], "$collectionId": row["collectionId"],
            "$databaseId": row["databaseId"], "$createdAt": row["createdAt"],
            "$updatedAt": row["updatedAt"], "$permissions": row["permissions"],
            **{k: v for k, v in row.items() if k not in hidden}}


def _as_resource(row, id_key="$id"):
    """Non-document resources expose `$id`/`$createdAt`/`$updatedAt` too."""
    out = {id_key: row["id"]}
    if "createdAt" in row:
        out["$createdAt"] = row["createdAt"]
    if "updatedAt" in row:
        out["$updatedAt"] = row["updatedAt"]
    if "permissions" in row:
        out["$permissions"] = row["permissions"]
    for key, value in row.items():
        if key in ("id", "createdAt", "updatedAt", "permissions"):
            continue
        if key.startswith("prefs_"):
            continue
        out[key] = value
    return out


# ---------------------------------------------------------------------------
# Scopes + permissions
# ---------------------------------------------------------------------------

GUEST = "guest"
SESSION = "session"
SERVER = "server"


def resolve_scope(api_key=None, session=None, jwt=None):
    """Map Appwrite auth headers onto (scope, user_id).

    A non-empty `X-Appwrite-Key` is a server key and bypasses permissions; a
    non-empty `X-Appwrite-Session` or `X-Appwrite-JWT` authenticates as the
    project's seeded session user. Any token is accepted, matching the fleet
    convention; the documented credentials are the canonical ones.
    """
    if (api_key or "").strip():
        return SERVER, ""
    if (session or "").strip() or (jwt or "").strip():
        return SESSION, _project_doc().get("credentials", {}).get("sessionUserId", "")
    return GUEST, ""


def check_project(project_id):
    """Validate the `X-Appwrite-Project` header; absent means the seeded project."""
    expected = _project_doc()["$id"]
    if project_id and project_id != expected:
        return _error(404, "project_not_found",
                      f"Project with the requested ID could not be found. "
                      f"Please check the value of the X-Appwrite-Project header "
                      f"to ensure the correct project ID is being used.")
    return None


def _team_ids_for(user_id):
    if not user_id:
        return set()
    return {m["teamId"] for m in _memberships_rows()
            if m["userId"] == user_id and m["confirm"]}


def _permits(permissions, action, scope, user_id):
    """Evaluate Appwrite permission strings such as `read("team:team_aurora")`."""
    if scope == SERVER:
        return True
    teams = _team_ids_for(user_id)
    for entry in permissions or []:
        parsed = re.match(r'^(\w+)\("([^"]+)"\)$', str(entry).strip())
        if not parsed or parsed.group(1) != action:
            continue
        role = parsed.group(2)
        if role == "any":
            return True
        if role == "users" and scope != GUEST:
            return True
        if user_id and role == f"user:{user_id}":
            return True
        if role.startswith("team:") and role.split(":", 1)[1].split("/")[0] in teams:
            return True
    return False


def _readable(collection, row, scope, user_id):
    """Row-level read check, used only when the collection has document security.

    With document security off the collection ACL gates the whole request
    instead (see :func:`_gate_read`), which is how Appwrite behaves: a caller
    without the collection's read permission gets 401, not an empty list.
    """
    if scope == SERVER:
        return True
    return _permits(row.get("permissions"), "read", scope, user_id) or \
        _permits(collection.get("permissions"), "read", scope, user_id)


def _gate_read(container, scope, user_id, security_key, scope_name):
    """401 when a collection/bucket without per-row security denies the caller."""
    if scope == SERVER or container.get(security_key):
        return None
    if _permits(container.get("permissions"), "read", scope, user_id):
        return None
    return _unauthorized(scope_name)


# ---------------------------------------------------------------------------
# Query DSL
# ---------------------------------------------------------------------------

_QUERY_RE = re.compile(r"^(\w+)\((.*)\)$", re.DOTALL)


def _parse_query(raw):
    """`equal("status", ["open"])` -> ("equal", ["status", ["open"]])."""
    match = _QUERY_RE.match(str(raw).strip())
    if not match:
        return None
    method, args = match.group(1), match.group(2).strip()
    if not args:
        return method, []
    try:
        return method, json.loads(f"[{args}]")
    except json.JSONDecodeError:
        return None


def _attr(row, name):
    return row.get(_SYSTEM_ATTRS.get(name, name))


def _values(args, index=1):
    raw = args[index] if len(args) > index else []
    return raw if isinstance(raw, list) else [raw]


def _matches(row, method, args):
    if method in ("limit", "offset", "cursorAfter", "cursorBefore",
                  "orderAsc", "orderDesc", "select"):
        return True
    name = args[0] if args else ""
    value = _attr(row, name)
    values = _values(args)
    if method == "equal":
        return any(_eq(value, v) for v in values)
    if method == "notEqual":
        return not any(_eq(value, v) for v in values)
    if method == "isNull":
        return value in (None, "", [])
    if method == "isNotNull":
        return value not in (None, "", [])
    if method == "contains":
        if isinstance(value, list):
            return any(v in value for v in values)
        return any(str(v).lower() in str(value or "").lower() for v in values)
    if method == "search":
        return all(str(v).lower() in str(value or "").lower() for v in values)
    if method == "startsWith":
        return any(str(value or "").startswith(str(v)) for v in values)
    if method == "endsWith":
        return any(str(value or "").endswith(str(v)) for v in values)
    if method == "between":
        low, high = (args[1], args[2]) if len(args) > 2 else (None, None)
        return _cmp(value, low, ">=") and _cmp(value, high, "<=")
    operators = {"greaterThan": ">", "greaterThanEqual": ">=",
                 "lessThan": "<", "lessThanEqual": "<="}
    if method in operators:
        return any(_cmp(value, v, operators[method]) for v in values)
    return True


def _eq(value, other):
    if isinstance(value, bool) or isinstance(other, bool):
        return bool(value) == bool(other)
    if isinstance(value, list):
        return other in value
    if isinstance(value, (int, float)) and isinstance(other, str):
        try:
            other = type(value)(other)
        except ValueError:
            return False
    return value == other


def _cmp(value, other, op):
    if value is None or other is None:
        return False
    if isinstance(value, str) and isinstance(other, (int, float)):
        try:
            value = type(other)(value)
        except ValueError:
            pass
    try:
        return {">": value > other, ">=": value >= other,
                "<": value < other, "<=": value <= other}[op]
    except TypeError:
        return False


def apply_queries(rows, queries):
    """Filter, sort, project and paginate. Returns (rows, total, error)."""
    parsed = []
    for raw in queries or []:
        query = _parse_query(raw)
        if not query:
            return [], 0, _error(400, "general_argument_invalid",
                                 f"Invalid query: {raw}")
        parsed.append(query)

    out = list(rows)
    for method, args in parsed:
        out = [r for r in out if _matches(r, method, args)]

    for method, args in parsed:
        if method in ("orderAsc", "orderDesc") and args:
            field = args[0]
            out.sort(key=lambda r: _sort_key(_attr(r, field)),
                     reverse=(method == "orderDesc"))

    total = len(out)

    for method, args in parsed:
        if method in ("cursorAfter", "cursorBefore") and args:
            ids = [r["id"] for r in out]
            if args[0] in ids:
                cut = ids.index(args[0])
                out = out[cut + 1:] if method == "cursorAfter" else out[:cut]

    offset = next((int(a[0]) for m, a in parsed if m == "offset" and a), 0)
    limit = next((int(a[0]) for m, a in parsed if m == "limit" and a), 25)
    out = out[offset:offset + limit]

    fields = next((a[0] for m, a in parsed if m == "select" and a), None)
    if fields:
        wanted = set(fields if isinstance(fields, list) else [fields])
        out = [{k: v for k, v in r.items()
                if k in wanted or _SYSTEM_ATTRS.get(k, k) in ("id", "collectionId",
                                                              "databaseId", "createdAt",
                                                              "updatedAt", "permissions")}
               for r in out]
    return out, total, None


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
# Databases / collections / documents
# ---------------------------------------------------------------------------

def list_databases(queries=None, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("databases.read")
    rows, total, err = apply_queries(_databases_rows(), queries)
    if err:
        return err
    return {"total": total, "databases": [_as_resource(r) for r in rows]}


def get_database(database_id, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("databases.read")
    row = _store.table("databases").get(database_id)
    if not row:
        return _database_missing(database_id)
    return _as_resource(row)


def list_collections(database_id, queries=None, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("collections.read")
    if not _store.table("databases").get(database_id):
        return _database_missing(database_id)
    rows = [c for c in _collections_rows() if c["databaseId"] == database_id]
    rows, total, err = apply_queries(rows, queries)
    if err:
        return err
    return {"total": total, "collections": [_as_resource(r) for r in rows]}


def get_collection(database_id, collection_id, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("collections.read")
    if not _store.table("databases").get(database_id):
        return _database_missing(database_id)
    row = _collection_meta(database_id, collection_id)
    if not row:
        return _collection_missing(collection_id)
    return _as_resource(row)


def _collection_meta(database_id, collection_id):
    return _store.table("collections").find_one(
        lambda c: c["id"] == collection_id and c["databaseId"] == database_id)


def list_documents(database_id, collection_id, queries=None, scope=GUEST, user_id=""):
    meta = _collection_meta(database_id, collection_id)
    if not _store.table("databases").get(database_id):
        return _database_missing(database_id)
    if not meta or collection_id not in DOCUMENT_TABLES:
        return _collection_missing(collection_id)
    denied = _gate_read(meta, scope, user_id, "documentSecurity", "collection.read")
    if denied:
        return denied
    rows_all = _store.table(collection_id).rows()
    visible = [r for r in rows_all if _readable(meta, r, scope, user_id)] \
        if meta["documentSecurity"] else rows_all
    rows, total, err = apply_queries(visible, queries)
    if err:
        return err
    return {"total": total, "documents": [_as_document(r) for r in rows]}


def get_document(database_id, collection_id, document_id, queries=None,
                 scope=GUEST, user_id=""):
    meta = _collection_meta(database_id, collection_id)
    if not meta or collection_id not in DOCUMENT_TABLES:
        return _collection_missing(collection_id)
    denied = _gate_read(meta, scope, user_id, "documentSecurity", "collection.read")
    if denied:
        return denied
    row = _store.table(collection_id).get(document_id)
    if not row:
        return _document_missing()
    if meta["documentSecurity"] and not _readable(meta, row, scope, user_id):
        return _document_missing()
    return _as_document(row)


def create_document(database_id, collection_id, document_id=None, data=None,
                    permissions=None, scope=GUEST, user_id=""):
    meta = _collection_meta(database_id, collection_id)
    if not meta or collection_id not in DOCUMENT_TABLES:
        return _collection_missing(collection_id)
    if not _permits(meta["permissions"], "create", scope, user_id):
        return _unauthorized("documents.write")
    invalid = _validate(meta, data or {})
    if invalid:
        return invalid
    now = _now()
    row = {"id": _resolve_id(document_id), "collectionId": collection_id,
           "databaseId": database_id, "permissions": list(permissions or []),
           "createdAt": now, "updatedAt": now}
    for attribute in meta["attributes"]:
        row[attribute["key"]] = _cast(attribute, (data or {}).get(attribute["key"]))
    if _store.table(collection_id).get(row["id"]):
        return _error(409, "document_already_exists",
                      f"Document with the requested ID already exists. "
                      f"Try again with a different ID or use ID.unique() to generate a unique ID.")
    _store_insert(collection_id, row)
    return _as_document(row)


def update_document(database_id, collection_id, document_id, data=None,
                    permissions=None, scope=GUEST, user_id=""):
    meta = _collection_meta(database_id, collection_id)
    if not meta or collection_id not in DOCUMENT_TABLES:
        return _collection_missing(collection_id)
    row = _store.table(collection_id).get(document_id)
    if not row:
        return _document_missing()
    governing = row["permissions"] if meta["documentSecurity"] else meta["permissions"]
    if not _permits(governing, "update", scope, user_id):
        return _unauthorized("documents.write")
    known = {a["key"]: a for a in meta["attributes"]}
    unknown = [k for k in (data or {}) if k not in known]
    if unknown:
        return _error(400, "document_invalid_structure",
                      f'Invalid document structure: Unknown attribute: "{unknown[0]}"')
    patch = {k: _cast(known[k], v) for k, v in (data or {}).items()}
    if permissions is not None:
        patch["permissions"] = list(permissions)
    patch["updatedAt"] = _now()
    return _as_document(_store.table(collection_id).patch(document_id, patch))


def delete_document(database_id, collection_id, document_id, scope=GUEST, user_id=""):
    meta = _collection_meta(database_id, collection_id)
    if not meta or collection_id not in DOCUMENT_TABLES:
        return _collection_missing(collection_id)
    row = _store.table(collection_id).get(document_id)
    if not row:
        return _document_missing()
    governing = row["permissions"] if meta["documentSecurity"] else meta["permissions"]
    if not _permits(governing, "delete", scope, user_id):
        return _unauthorized("documents.write")
    _store.table(collection_id).delete(document_id)
    return {"deleted": document_id}


def _resolve_id(document_id):
    return _new_id() if document_id in (None, "", "unique()") else document_id


def _validate(meta, data):
    known = {a["key"]: a for a in meta["attributes"]}
    for key in data:
        if key not in known:
            return _error(400, "document_invalid_structure",
                          f'Invalid document structure: Unknown attribute: "{key}"')
    for attribute in meta["attributes"]:
        if attribute["required"] and data.get(attribute["key"]) in (None, "", []):
            return _error(400, "document_invalid_structure",
                          f'Invalid document structure: Missing required attribute '
                          f'"{attribute["key"]}"')
    return None


def _cast(attribute, value):
    if value is None:
        return [] if attribute["array"] else ""
    if attribute["array"]:
        return list(value) if isinstance(value, list) else [value]
    if attribute["type"] == "boolean":
        return bool(value) if isinstance(value, bool) else \
            str(value).strip().lower() in ("true", "1", "yes")
    if attribute["type"] == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return value


def _unauthorized(scope_name):
    return _error(401, "general_unauthorized_scope",
                  f'app.current-user is missing scope ({scope_name})')


def _database_missing(database_id):
    return _error(404, "database_not_found",
                  "Database with the requested ID could not be found.")


def _collection_missing(collection_id):
    return _error(404, "collection_not_found",
                  "Collection with the requested ID could not be found.")


def _document_missing():
    return _error(404, "document_not_found",
                  "Document with the requested ID could not be found.")


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def list_buckets(queries=None, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("buckets.read")
    rows, total, err = apply_queries(_buckets_rows(), queries)
    if err:
        return err
    return {"total": total, "buckets": [_as_resource(r) for r in rows]}


def get_bucket(bucket_id, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("buckets.read")
    row = _store.table("buckets").get(bucket_id)
    if not row:
        return _bucket_missing()
    return _as_resource(row)


def list_files(bucket_id, queries=None, scope=GUEST, user_id=""):
    bucket = _store.table("buckets").get(bucket_id)
    if not bucket:
        return _bucket_missing()
    denied = _gate_read(bucket, scope, user_id, "fileSecurity", "files.read")
    if denied:
        return denied
    owned = [f for f in _files_rows() if f["bucketId"] == bucket_id]
    visible = [f for f in owned if _readable_file(bucket, f, scope, user_id)] \
        if bucket["fileSecurity"] else owned
    rows, total, err = apply_queries(visible, queries)
    if err:
        return err
    return {"total": total, "files": [_as_resource(r) for r in rows]}


def get_file(bucket_id, file_id, scope=GUEST, user_id=""):
    bucket = _store.table("buckets").get(bucket_id)
    if not bucket:
        return _bucket_missing()
    denied = _gate_read(bucket, scope, user_id, "fileSecurity", "files.read")
    if denied:
        return denied
    row = _store.table("files").get(file_id)
    if not row or row["bucketId"] != bucket_id:
        return _file_missing()
    if bucket["fileSecurity"] and not _readable_file(bucket, row, scope, user_id):
        return _file_missing()
    return _as_resource(row)


def delete_file(bucket_id, file_id, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("files.write")
    row = _store.table("files").get(file_id)
    if not row or row["bucketId"] != bucket_id:
        return _file_missing()
    _store.table("files").delete(file_id)
    return {"deleted": file_id}


def _readable_file(bucket, row, scope, user_id):
    if scope == SERVER:
        return True
    return _permits(row["permissions"], "read", scope, user_id) or \
        _permits(bucket["permissions"], "read", scope, user_id)


def _bucket_missing():
    return _error(404, "storage_bucket_not_found",
                  "Storage bucket with the requested ID could not be found.")


def _file_missing():
    return _error(404, "storage_file_not_found",
                  "The requested file could not be found.")


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def list_functions(queries=None, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("functions.read")
    rows, total, err = apply_queries(_functions_rows(), queries)
    if err:
        return err
    return {"total": total, "functions": [_as_resource(r) for r in rows]}


def get_function(function_id, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("functions.read")
    row = _store.table("functions").get(function_id)
    if not row:
        return _function_missing()
    return _as_resource(row)


def list_executions(function_id, queries=None, scope=GUEST, user_id=""):
    if scope == GUEST:
        return _unauthorized("executions.read")
    if not _store.table("functions").get(function_id):
        return _function_missing()
    rows = [e for e in _executions_rows() if e["functionId"] == function_id]
    rows, total, err = apply_queries(rows, queries)
    if err:
        return err
    return {"total": total, "executions": [_as_resource(r) for r in rows]}


def create_execution(function_id, body=None, path="/", method="POST", async_=False,
                     scope=GUEST, user_id=""):
    if scope == GUEST:
        return _unauthorized("execution.write")
    fn = _store.table("functions").get(function_id)
    if not fn:
        return _function_missing()
    if not fn["enabled"]:
        return _error(400, "function_not_found",
                      "Function is not enabled and cannot be executed.")
    now = _now()
    execution = {
        "id": _new_id("exec_"), "functionId": function_id, "trigger": "http",
        "status": "waiting" if async_ else "completed",
        "requestMethod": method, "requestPath": path,
        "responseStatusCode": 0 if async_ else 200,
        "responseBody": "" if async_ else json.dumps(_function_output(function_id, body)),
        "duration": 0.0 if async_ else 0.412,
        "errors": "", "logs": "" if async_ else f"Executed {fn['name']}.",
        "createdAt": now, "updatedAt": now,
    }
    _store_insert("executions", execution)
    return _as_resource(execution)


def _function_output(function_id, body):
    if function_id == "fn_aggregate_feedback":
        rows = _store.table("feedback").rows()
        ratings = [r["rating"] for r in rows if isinstance(r.get("rating"), int)]
        counts = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {**counts, "total": len(rows),
                "averageRating": round(sum(ratings) / len(ratings), 2) if ratings else 0}
    if function_id == "fn_notify_oncall":
        return {"paged": (body or {}).get("assignee", "jonas"), "channel": "pagerduty"}
    return {"ok": True, "echo": body or {}}


def _function_missing():
    return _error(404, "function_not_found",
                  "Function with the requested ID could not be found.")


# ---------------------------------------------------------------------------
# Teams / users / account
# ---------------------------------------------------------------------------

def list_teams(queries=None, scope=GUEST, user_id=""):
    if scope == GUEST:
        return _unauthorized("teams.read")
    rows = _teams_rows() if scope == SERVER else \
        [t for t in _teams_rows() if t["id"] in _team_ids_for(user_id)]
    rows, total, err = apply_queries(rows, queries)
    if err:
        return err
    return {"total": total, "teams": [_as_resource(r) for r in rows]}


def get_team(team_id, scope=GUEST, user_id=""):
    if scope == GUEST:
        return _unauthorized("teams.read")
    row = _store.table("teams").get(team_id)
    if not row or (scope != SERVER and team_id not in _team_ids_for(user_id)):
        return _error(404, "team_not_found",
                      "Team with the requested ID could not be found.")
    return _as_resource(row)


def list_memberships(team_id, queries=None, scope=GUEST, user_id=""):
    team = get_team(team_id, scope=scope, user_id=user_id)
    if "error" in team:
        return team
    rows = [m for m in _memberships_rows() if m["teamId"] == team_id]
    rows, total, err = apply_queries(rows, queries)
    if err:
        return err
    return {"total": total, "memberships": [_as_resource(r) for r in rows]}


def list_users(queries=None, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("users.read")
    rows, total, err = apply_queries(_users_rows(), queries)
    if err:
        return err
    return {"total": total, "users": [_as_resource(r) for r in rows]}


def get_user(target_id, scope=GUEST, user_id=""):
    if scope != SERVER:
        return _unauthorized("users.read")
    row = _store.table("users").get(target_id)
    if not row:
        return _error(404, "user_not_found",
                      "User with the requested ID could not be found.")
    return _as_resource(row)


def get_account(scope=GUEST, user_id=""):
    if scope != SESSION:
        return _error(401, "general_unauthorized_scope",
                      "User (role: guests) missing scope (account)")
    row = _store.table("users").get(user_id)
    if not row:
        return _error(404, "user_not_found",
                      "User with the requested ID could not be found.")
    return _as_resource(row)


# ---------------------------------------------------------------------------
# Health / locale
# ---------------------------------------------------------------------------

def health():
    return {"name": "http", "ping": 1, "status": "pass"}


def health_db():
    return {"name": "database", "ping": 3, "status": "pass"}


def health_storage():
    return {"name": "storage", "ping": 2, "status": "pass"}


def get_locale():
    return {"ip": "203.0.113.41", "countryCode": "US", "country": "United States",
            "continentCode": "NA", "continent": "North America", "eu": False,
            "currency": "USD"}


def get_project():
    project = _project_doc()
    return {k: v for k, v in project.items() if k != "credentials"}


_store.eager_load()
