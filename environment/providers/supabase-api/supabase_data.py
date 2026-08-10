"""Data access module for the Supabase (self-host) API mock service.

Models the self-hosted Supabase stack's data plane: PostgREST (`/rest/v1`),
Storage (`/storage/v1`), Edge Functions (`/functions/v1`) and Realtime
(`/realtime/v1`). GoTrue lives in its own service (`supabase-auth-api`).

PostgREST semantics reproduced here: horizontal filtering (`col=eq.value`),
`select` column projection with one level of resource embedding, `order`,
`limit`/`offset`, and role-scoped row visibility standing in for RLS.
Mutations are held in process memory and reset on restart.
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
    read_seed_with_ctx, get_store, opt_bool, opt_int, opt_str, strict_bool)

_store = get_store("supabase-api")
_API = "supabase-api"


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


_store.register("profiles", primary_key="id",
                initial_loader=lambda: _coerce_profiles(_load("profiles.json", "profiles")))
_store.register("projects", primary_key="id",
                initial_loader=lambda: _coerce_projects(_load("projects.json", "projects")))
_store.register("documents", primary_key="id",
                initial_loader=lambda: _coerce_documents(_load("documents.json", "documents")))
_store.register("comments", primary_key="id",
                initial_loader=lambda: _coerce_comments(_load("comments.json", "comments")))
_store.register("buckets", primary_key="id",
                initial_loader=lambda: _coerce_buckets(_load("buckets.json", "buckets")))
_store.register("objects", primary_key="id",
                initial_loader=lambda: _coerce_objects(_load("objects.json", "objects")))
_store.register("functions", primary_key="id",
                initial_loader=lambda: _coerce_functions(_load("functions.json", "functions")))
_store.register("channels", primary_key="id",
                initial_loader=lambda: _coerce_channels(_load("channels.json", "channels")))
_store.register_document("settings", initial_loader=_load_settings)
# Born-empty: signed URLs and function invocations are created at runtime only.
_store.register("signed_urls", primary_key="token", initial_loader=lambda: [])
_store.register("invocations", primary_key="invocation_id", initial_loader=lambda: [])


def _profiles_rows():
    return _store.table("profiles").rows()


def _projects_rows():
    return _store.table("projects").rows()


def _documents_rows():
    return _store.table("documents").rows()


def _comments_rows():
    return _store.table("comments").rows()


def _buckets_rows():
    return _store.table("buckets").rows()


def _objects_rows():
    return _store.table("objects").rows()


def _functions_rows():
    return _store.table("functions").rows()


def _channels_rows():
    return _store.table("channels").rows()


def _settings_doc():
    return _store.document("settings").get()


def _signed_urls_rows():
    return _store.table("signed_urls").rows()


def _invocations_rows():
    return _store.table("invocations").rows()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _now():
    return int(time.time())


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def _semi_list(r, column):
    raw = opt_str(r, column, default="")
    return [part for part in raw.split(";") if part]


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

def _coerce_profiles(rows):
    return [{**_strip_ctx(r), "is_active": strict_bool(r, "is_active")} for r in rows]


def _coerce_projects(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "star_count": opt_int(r, "star_count", default=0)} for r in rows]


def _coerce_documents(rows):
    out = []
    for r in rows:
        out.append({
            **_strip_ctx(r),
            "id": opt_int(r, "id", default=0),
            "project_id": opt_int(r, "project_id", default=0),
            "word_count": opt_int(r, "word_count", default=0),
            "tags": _semi_list(r, "tags"),
            "published_at": opt_str(r, "published_at", default="") or None,
        })
    return out


def _coerce_comments(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "document_id": opt_int(r, "document_id", default=0),
             "resolved": strict_bool(r, "resolved")} for r in rows]


def _coerce_buckets(rows):
    return [{**_strip_ctx(r), "public": strict_bool(r, "public"),
             "file_size_limit": opt_int(r, "file_size_limit", default=None),
             "allowed_mime_types": _semi_list(r, "allowed_mime_types")} for r in rows]


def _coerce_objects(rows):
    return [{**_strip_ctx(r), "size": opt_int(r, "size", default=0)} for r in rows]


def _coerce_functions(rows):
    return [{**_strip_ctx(r), "version": opt_int(r, "version", default=1),
             "verify_jwt": strict_bool(r, "verify_jwt"),
             "import_map": opt_bool(r, "import_map", default=False)} for r in rows]


def _coerce_channels(rows):
    return [{**_strip_ctx(r), "subscriber_count": opt_int(r, "subscriber_count", default=0),
             "is_private": strict_bool(r, "is_private"),
             "event_filter": _semi_list(r, "event_filter")} for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _next_serial(table):
    """Next bigint identity value for a table whose PK is an integer.

    Scans the live rows instead of caching a counter: the admin plane can
    inject rows out of band and a cached counter would collide with them.
    """
    ids = [r["id"] for r in _store.table(table).rows() if isinstance(r.get("id"), int)]
    return (max(ids) + 1) if ids else 1


def _error(message, code, details=None, hint=None):
    """PostgREST-shaped error body. The house `error` key drives the HTTP status."""
    return {"error": message, "code": code, "details": details, "hint": hint,
            "message": message}


# ---------------------------------------------------------------------------
# Roles / RLS
# ---------------------------------------------------------------------------

ANON_ROLE = "anon"
AUTHENTICATED_ROLE = "authenticated"
SERVICE_ROLE = "service_role"


def resolve_role(apikey=None, authorization=None):
    """Map an apikey / bearer token onto a Postgres role.

    Missing or anon key -> `anon` (read-only, public rows only). The project's
    service key -> `service_role` (bypasses every policy). Any other non-empty
    token -> `authenticated`, keeping the fleet convention that any token is
    accepted while still exposing an observable auth layer.
    """
    token = (apikey or "").strip()
    if not token and authorization:
        parts = str(authorization).split(None, 1)
        token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""
    if not token:
        return ANON_ROLE
    api = _settings_doc().get("api", {})
    if token == api.get("service_role_key"):
        return SERVICE_ROLE
    if token == api.get("anon_key"):
        return ANON_ROLE
    return AUTHENTICATED_ROLE


def _visible(table, row, role):
    """Row-level visibility standing in for the project's RLS policies."""
    if role in (AUTHENTICATED_ROLE, SERVICE_ROLE):
        return True
    if table == "projects":
        return row.get("visibility") == "public"
    if table == "documents":
        return row.get("status") == "published"
    if table == "comments":
        parent = _store.table("documents").get(row.get("document_id"))
        return bool(parent) and parent.get("status") == "published"
    return True


def _apply_rls(table, rows, role):
    return [r for r in rows if _visible(table, r, role)]


# ---------------------------------------------------------------------------
# PostgREST query grammar
# ---------------------------------------------------------------------------

REST_TABLES = {
    "profiles": _profiles_rows,
    "projects": _projects_rows,
    "documents": _documents_rows,
    "comments": _comments_rows,
}

# (parent, embedded) -> (parent column, embedded column, cardinality)
_EMBEDS = {
    ("projects", "documents"): ("id", "project_id", "many"),
    ("projects", "profiles"): ("owner_id", "id", "one"),
    ("documents", "comments"): ("id", "document_id", "many"),
    ("documents", "projects"): ("project_id", "id", "one"),
    ("documents", "profiles"): ("author_id", "id", "one"),
    ("comments", "profiles"): ("author_id", "id", "one"),
    ("comments", "documents"): ("document_id", "id", "one"),
    ("profiles", "projects"): ("id", "owner_id", "many"),
    ("profiles", "documents"): ("id", "author_id", "many"),
}

_RESERVED_PARAMS = {"select", "order", "limit", "offset", "on_conflict", "columns"}


def _parse_select(spec):
    """Split a select spec into plain columns and embedded resources.

    ``id,title,comments(id,body)`` -> ``(["id", "title"], [("comments", ["id", "body"])])``
    """
    columns, embeds = [], []
    depth, buf, current = 0, "", ""
    for ch in spec or "":
        if ch == "(":
            depth += 1
            if depth == 1:
                current, buf = buf.strip(), ""
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                embeds.append((current, [c.strip() for c in buf.split(",") if c.strip()]))
                current, buf = "", ""
                continue
        elif ch == "," and depth == 0:
            if buf.strip():
                columns.append(buf.strip())
            buf = ""
            continue
        buf += ch
    if buf.strip():
        columns.append(buf.strip())
    return columns, embeds


def _project(row, columns):
    if not columns or "*" in columns:
        return dict(row)
    return {c: row.get(c) for c in columns}


def _like_to_regex(pattern):
    out = ["^"]
    for ch in pattern:
        if ch in ("%", "*"):
            out.append(".*")
        elif ch == "_":
            out.append(".")
        else:
            out.append(re.escape(ch))
    out.append("$")
    return "".join(out)


def _coerce_operand(sample, raw):
    """Coerce a query-string operand to the type of the column it is compared to."""
    text = str(raw).strip().strip('"')
    if isinstance(sample, bool):
        return text.lower() in ("true", "t", "1", "yes")
    if isinstance(sample, int):
        try:
            return int(text)
        except ValueError:
            return text
    if isinstance(sample, float):
        try:
            return float(text)
        except ValueError:
            return text
    return text


def _match(value, op, operand):
    if op == "is":
        token = operand.strip().lower()
        if token == "null":
            return value is None or value == ""
        if token in ("true", "false"):
            return bool(value) is (token == "true")
        return False
    if op == "in":
        items = [p.strip().strip('"') for p in operand.strip("()").split(",") if p.strip()]
        return any(value == _coerce_operand(value, i) for i in items)
    if op in ("like", "ilike"):
        flags = re.IGNORECASE if op == "ilike" else 0
        return bool(re.match(_like_to_regex(operand), str(value or ""), flags))
    if op == "cs":
        items = [p.strip().strip('"') for p in operand.strip("{}()").split(",") if p.strip()]
        return set(items).issubset(set(value or []))
    other = _coerce_operand(value, operand)
    try:
        if op == "eq":
            return value == other
        if op == "neq":
            return value != other
        if op == "gt":
            return value > other
        if op == "gte":
            return value >= other
        if op == "lt":
            return value < other
        if op == "lte":
            return value <= other
    except TypeError:
        return False
    return False


def _apply_filters(rows, filters):
    """Apply `col=[not.]op.operand` filters. Returns (rows, error_or_None)."""
    out = list(rows)
    for column, raw in (filters or {}).items():
        if column in _RESERVED_PARAMS or column.startswith("__"):
            continue
        expr = str(raw)
        negate = expr.startswith("not.")
        if negate:
            expr = expr[4:]
        op, _, operand = expr.partition(".")
        if not operand and op not in ("is",):
            return out, _error(
                f'unexpected "{expr}" expecting "eq", "gt", "gte", "lt", "lte", '
                f'"neq", "like", "ilike", "in", "is", "cs" or "not"',
                "PGRST100", details=f"filter on column {column!r}")
        out = [r for r in out
               if column in r and (_match(r[column], op, operand) is not negate)]
    return out, None


def _apply_order(rows, order):
    """`order=col.desc` / `col.asc.nullslast` / `col` (asc default)."""
    if not order:
        return rows
    out = list(rows)
    for clause in reversed([c.strip() for c in order.split(",") if c.strip()]):
        parts = clause.split(".")
        column, descending = parts[0], "desc" in parts[1:]
        out.sort(key=lambda r: (r.get(column) is None, _sort_key(r.get(column))),
                 reverse=descending)
    return out


def _sort_key(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return str(value)


def _embed(parent_table, sources, targets, embeds, role):
    """Attach embedded resources to each projected row.

    The join key is read from the *source* row, not the projected one, so
    `select=id,title,profiles(username)` still resolves the author even though
    `author_id` was projected away. Unknown relationships are skipped.
    """
    for name, sub_columns in embeds:
        rel = _EMBEDS.get((parent_table, name))
        if not rel:
            continue
        parent_col, child_col, cardinality = rel
        children = _apply_rls(name, REST_TABLES[name](), role) if name in REST_TABLES else []
        for source, target in zip(sources, targets):
            key = source.get(parent_col)
            matched = [_project(c, sub_columns) for c in children if c.get(child_col) == key]
            target[name] = matched if cardinality == "many" else (matched[0] if matched else None)
    return targets


# ---------------------------------------------------------------------------
# REST (PostgREST)
# ---------------------------------------------------------------------------

def rest_root():
    """PostgREST root: the schema the API exposes."""
    settings = _settings_doc()
    return {
        "swagger": "2.0",
        "info": {
            "title": "standard public schema",
            "description": "PostgREST API mock for the self-hosted Supabase project "
                           f"{settings.get('ref')}",
            "version": settings.get("services", {}).get("rest", {}).get("version", "v12.2.0"),
        },
        "host": settings.get("db", {}).get("host", "supabase-db"),
        "basePath": "/rest/v1",
        "schemes": ["http"],
        "definitions": {name: {"type": "array"} for name in REST_TABLES},
        "paths": {f"/{name}": {} for name in REST_TABLES},
    }


def select_rows(table, filters=None, select=None, order=None, limit=None, offset=0,
                role=ANON_ROLE):
    """PostgREST GET. Returns an internal envelope the server unwraps."""
    if table not in REST_TABLES:
        return _error(f'relation "public.{table}" does not exist', "42P01",
                      hint="Verify the table name and the exposed schema.")
    columns, embeds = _parse_select(select or "*")
    rows = _apply_rls(table, REST_TABLES[table](), role)
    rows, err = _apply_filters(rows, filters)
    if err:
        return err
    total = len(rows)
    rows = _apply_order(rows, order)
    start = int(offset or 0)
    rows = rows[start:start + int(limit)] if limit is not None else rows[start:]
    data = _embed(table, rows, [_project(r, columns) for r in rows], embeds, role)
    span = f"{start}-{start + len(data) - 1}" if data else "*"
    return {"data": data, "count": total, "content_range": f"{span}/{total}"}


def insert_rows(table, payload, role=ANON_ROLE, prefer="return=representation"):
    """PostgREST POST. Accepts a single object or a list of objects."""
    if table not in REST_TABLES:
        return _error(f'relation "public.{table}" does not exist', "42P01")
    if role == ANON_ROLE:
        return _error(f'new row violates row-level security policy for table "{table}"',
                      "42501", hint="Send an apikey header with a writable role.")
    records = payload if isinstance(payload, list) else [payload]
    created = []
    for record in records:
        if not isinstance(record, dict):
            return _error("expected a JSON object or an array of objects", "PGRST102")
        row = _new_row(table, record)
        if "error" in row:
            return row
        _store_insert(table, row)
        created.append(row)
    data = created if "return=minimal" not in (prefer or "") else []
    return {"data": data, "count": len(created),
            "content_range": f"*/{len(created)}"}


def _new_row(table, record):
    now = _now_iso()
    if table == "profiles":
        return {
            "id": str(record.get("id") or uuid.uuid4()),
            "username": record.get("username", ""),
            "full_name": record.get("full_name", ""),
            "email": record.get("email", ""),
            "avatar_url": record.get("avatar_url", ""),
            "role": record.get("role", "developer"),
            "plan": record.get("plan", "free"),
            "is_active": bool(record.get("is_active", True)),
            "last_seen_at": now,
            "created_at": now,
        }
    if table == "projects":
        return {
            "id": int(record["id"]) if record.get("id") is not None else _next_serial("projects"),
            "owner_id": record.get("owner_id", ""),
            "name": record.get("name", ""),
            "slug": record.get("slug") or _slugify(record.get("name", "")),
            "description": record.get("description", ""),
            "visibility": record.get("visibility", "private"),
            "status": record.get("status", "active"),
            "star_count": int(record.get("star_count") or 0),
            "created_at": now,
            "updated_at": now,
        }
    if table == "documents":
        project_id = record.get("project_id")
        if project_id is not None and not _store.table("projects").get(int(project_id)):
            return _error(
                'insert or update on table "documents" violates foreign key '
                'constraint "documents_project_id_fkey"', "23503",
                details=f"Key (project_id)=({project_id}) is not present in table \"projects\".")
        return {
            "id": int(record["id"]) if record.get("id") is not None else _next_serial("documents"),
            "project_id": int(project_id) if project_id is not None else None,
            "author_id": record.get("author_id", ""),
            "title": record.get("title", ""),
            "slug": record.get("slug") or _slugify(record.get("title", "")),
            "body": record.get("body", ""),
            "status": record.get("status", "draft"),
            "word_count": int(record.get("word_count") or len(str(record.get("body", "")).split())),
            "tags": record.get("tags") or [],
            "created_at": now,
            "updated_at": now,
            "published_at": record.get("published_at"),
        }
    document_id = record.get("document_id")
    if document_id is not None and not _store.table("documents").get(int(document_id)):
        return _error(
            'insert or update on table "comments" violates foreign key '
            'constraint "comments_document_id_fkey"', "23503",
            details=f"Key (document_id)=({document_id}) is not present in table \"documents\".")
    return {
        "id": int(record["id"]) if record.get("id") is not None else _next_serial("comments"),
        "document_id": int(document_id) if document_id is not None else None,
        "author_id": record.get("author_id", ""),
        "body": record.get("body", ""),
        "resolved": bool(record.get("resolved", False)),
        "created_at": now,
    }


def _slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def update_rows(table, patch, filters=None, role=ANON_ROLE, prefer="return=representation"):
    """PostgREST PATCH. The filter set selects the rows to update."""
    if table not in REST_TABLES:
        return _error(f'relation "public.{table}" does not exist', "42P01")
    if role == ANON_ROLE:
        return _error(f'permission denied for table "{table}"', "42501",
                      hint="Send an apikey header with a writable role.")
    if not isinstance(patch, dict) or not patch:
        return _error("expected a non-empty JSON object", "PGRST102")
    targets, err = _apply_filters(REST_TABLES[table](), filters)
    if err:
        return err
    fields = {k: v for k, v in patch.items() if k != "id"}
    if table in ("projects", "documents"):
        fields.setdefault("updated_at", _now_iso())
    updated = [_store.table(table).patch(row["id"], fields) for row in targets]
    updated = [r for r in updated if r]
    data = updated if "return=minimal" not in (prefer or "") else []
    return {"data": data, "count": len(updated), "content_range": f"*/{len(updated)}"}


def delete_rows(table, filters=None, role=ANON_ROLE, prefer="return=representation"):
    """PostgREST DELETE. Refuses an unfiltered delete, as a safety rail."""
    if table not in REST_TABLES:
        return _error(f'relation "public.{table}" does not exist', "42P01")
    if role != SERVICE_ROLE:
        return _error(f'permission denied for table "{table}"', "42501",
                      hint="Deletes require the service_role key.")
    scoped = {k: v for k, v in (filters or {}).items() if k not in _RESERVED_PARAMS}
    if not scoped:
        return _error("delete requires at least one filter", "PGRST109",
                      hint="Add a filter such as ?id=eq.101.")
    targets, err = _apply_filters(REST_TABLES[table](), scoped)
    if err:
        return err
    deleted = [row for row in targets if _store.table(table).delete(row["id"])]
    data = deleted if "return=minimal" not in (prefer or "") else []
    return {"data": data, "count": len(deleted), "content_range": f"*/{len(deleted)}"}


# ---------------------------------------------------------------------------
# RPC (Postgres functions)
# ---------------------------------------------------------------------------

def call_rpc(name, args=None, role=ANON_ROLE):
    args = args or {}
    if name == "project_stats":
        return _rpc_project_stats(args, role)
    if name == "search_documents":
        return _rpc_search_documents(args, role)
    if name == "publish_document":
        return _rpc_publish_document(args, role)
    return _error(f"Could not find the function public.{name} in the schema cache",
                  "PGRST202", hint="Verify the function name and argument names.")


def _rpc_project_stats(args, role):
    project_id = args.get("project_id")
    if project_id is None:
        return _error("missing required argument: project_id", "PGRST202")
    project = _store.table("projects").get(int(project_id))
    if not project or not _visible("projects", project, role):
        return _error(f"project {project_id} not found", "PGRST116")
    documents = [d for d in _apply_rls("documents", _documents_rows(), role)
                 if d["project_id"] == int(project_id)]
    document_ids = {d["id"] for d in documents}
    comments = [c for c in _comments_rows() if c["document_id"] in document_ids]
    return {
        "project_id": project["id"],
        "name": project["name"],
        "document_count": len(documents),
        "published_count": len([d for d in documents if d["status"] == "published"]),
        "comment_count": len(comments),
        "unresolved_comment_count": len([c for c in comments if not c["resolved"]]),
        "total_words": sum(d["word_count"] for d in documents),
    }


def _rpc_search_documents(args, role):
    query = str(args.get("query") or "").strip().lower()
    if not query:
        return _error("missing required argument: query", "PGRST202")
    limit = int(args.get("limit") or 10)
    hits = []
    for doc in _apply_rls("documents", _documents_rows(), role):
        haystack = f"{doc['title']} {doc['body']} {' '.join(doc['tags'])}".lower()
        if query in haystack:
            hits.append({
                "id": doc["id"],
                "project_id": doc["project_id"],
                "title": doc["title"],
                "slug": doc["slug"],
                "status": doc["status"],
                "rank": round(haystack.count(query) / max(len(haystack.split()), 1), 6),
            })
    hits.sort(key=lambda h: (-h["rank"], h["id"]))
    return hits[:limit]


def _rpc_publish_document(args, role):
    document_id = args.get("document_id")
    if document_id is None:
        return _error("missing required argument: document_id", "PGRST202")
    if role == ANON_ROLE:
        return _error('permission denied for function public.publish_document', "42501")
    doc = _store.table("documents").get(int(document_id))
    if not doc:
        return _error(f"document {document_id} not found", "PGRST116")
    if doc["status"] == "published":
        return _error(f"document {document_id} is already published", "P0001")
    now = _now_iso()
    return _store.table("documents").patch(
        int(document_id), {"status": "published", "published_at": now, "updated_at": now})


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def list_buckets(role=ANON_ROLE):
    rows = _buckets_rows()
    return rows if role != ANON_ROLE else [b for b in rows if b["public"]]


def get_bucket(bucket_id, role=ANON_ROLE):
    bucket = _store.table("buckets").get(bucket_id)
    if not bucket or (role == ANON_ROLE and not bucket["public"]):
        return _error("Bucket not found", "404")
    return bucket


def create_bucket(bucket_id, name=None, public=False, file_size_limit=None,
                  allowed_mime_types=None, role=ANON_ROLE):
    if role == ANON_ROLE:
        return _error("new row violates row-level security policy", "42501")
    if not bucket_id:
        return _error("id is required", "InvalidRequest")
    if _store.table("buckets").get(bucket_id):
        return _error("The resource already exists", "Duplicate")
    now = _now_iso()
    bucket = {
        "id": bucket_id,
        "name": name or bucket_id,
        "owner_id": "",
        "public": bool(public),
        "file_size_limit": file_size_limit,
        "allowed_mime_types": allowed_mime_types or [],
        "created_at": now,
        "updated_at": now,
    }
    _store_insert("buckets", bucket)
    return {"name": bucket["name"]}


def delete_bucket(bucket_id, role=ANON_ROLE):
    if role != SERVICE_ROLE:
        return _error("new row violates row-level security policy", "42501")
    if not _store.table("buckets").get(bucket_id):
        return _error("Bucket not found", "404")
    if _store.table("objects").find(lambda o: o["bucket_id"] == bucket_id):
        return _error("The bucket you tried to delete is not empty", "409")
    _store.table("buckets").delete(bucket_id)
    return {"message": "Successfully deleted"}


def list_objects(bucket_id, prefix="", limit=100, offset=0, role=ANON_ROLE):
    bucket = get_bucket(bucket_id, role=role)
    if "error" in bucket:
        return bucket
    rows = [o for o in _objects_rows()
            if o["bucket_id"] == bucket_id and o["name"].startswith(prefix or "")]
    rows.sort(key=lambda o: o["name"])
    return rows[int(offset or 0):int(offset or 0) + int(limit or 100)]


def get_object_info(bucket_id, path, role=ANON_ROLE):
    bucket = get_bucket(bucket_id, role=role)
    if "error" in bucket:
        return bucket
    obj = _store.table("objects").find_one(
        lambda o: o["bucket_id"] == bucket_id and o["name"] == path)
    return obj if obj else _error("Object not found", "404")


def sign_object(bucket_id, path, expires_in=3600, role=ANON_ROLE):
    if role == ANON_ROLE:
        return _error("new row violates row-level security policy", "42501")
    obj = get_object_info(bucket_id, path, role=role)
    if "error" in obj:
        return obj
    token = uuid.uuid4().hex
    record = {
        "token": token,
        "bucket_id": bucket_id,
        "object_name": path,
        "expires_in": int(expires_in or 3600),
        "expires_at": _now() + int(expires_in or 3600),
        "created_at": _now_iso(),
    }
    _store.table("signed_urls").upsert(record)
    return {"signedURL": f"/storage/v1/object/sign/{bucket_id}/{path}?token={token}"}


def delete_object(bucket_id, path, role=ANON_ROLE):
    if role != SERVICE_ROLE:
        return _error("new row violates row-level security policy", "42501")
    obj = _store.table("objects").find_one(
        lambda o: o["bucket_id"] == bucket_id and o["name"] == path)
    if not obj:
        return _error("Object not found", "404")
    _store.table("objects").delete(obj["id"])
    return {"message": "Successfully deleted"}


# ---------------------------------------------------------------------------
# Edge Functions
# ---------------------------------------------------------------------------

def list_functions():
    return _functions_rows()


def invoke_function(slug, payload=None, role=ANON_ROLE):
    fn = _store.table("functions").find_one(lambda f: f["slug"] == slug)
    if not fn:
        return _error(f"Function not found: {slug}", "FunctionNotFound")
    if fn["verify_jwt"] and role == ANON_ROLE:
        return _error("Missing authorization header", "401")
    if fn["status"] == "THROTTLED":
        return _error(f"Function {slug} is throttled; retry after the cooldown", "429")
    body = _function_body(slug, payload or {})
    invocation = {
        "invocation_id": _new_id("inv"),
        "function_id": fn["id"],
        "slug": slug,
        "version": fn["version"],
        "status_code": 200,
        "invoked_at": _now_iso(),
    }
    _store.table("invocations").upsert(invocation)
    return {"invocation_id": invocation["invocation_id"], "slug": slug,
            "version": fn["version"], "data": body}


def _function_body(slug, payload):
    if slug == "send-welcome-email":
        return {"queued": True, "to": payload.get("email", ""),
                "template": "welcome-v3", "message_id": _new_id("msg")}
    if slug == "billing-webhook":
        return {"received": True, "event": payload.get("type", "invoice.updated"),
                "processed_at": _now_iso()}
    if slug == "generate-report":
        docs = _documents_rows()
        return {"report_id": _new_id("rep"), "period": payload.get("period", "2026-05"),
                "documents": len(docs),
                "published": len([d for d in docs if d["status"] == "published"]),
                "total_words": sum(d["word_count"] for d in docs)}
    return {"ok": True, "echo": payload}


# ---------------------------------------------------------------------------
# Realtime
# ---------------------------------------------------------------------------

def list_channels():
    return _channels_rows()


def broadcast(messages, role=ANON_ROLE):
    if not messages:
        return _error("messages is required", "InvalidRequest")
    accepted = 0
    for message in messages:
        topic = message.get("topic")
        if not topic:
            return _error("each message requires a topic", "InvalidRequest")
        channel = _store.table("channels").find_one(lambda c: c["name"] == topic)
        if channel and channel["is_private"] and role == ANON_ROLE:
            return _error(f"Unauthorized broadcast to private channel {topic}", "401")
        accepted += 1
    return {"message": "ok", "accepted": accepted}


# ---------------------------------------------------------------------------
# Project settings
# ---------------------------------------------------------------------------

def get_settings():
    settings = _settings_doc()
    api = dict(settings.get("api", {}))
    api["service_role_key"] = _mask(api.get("service_role_key", ""))
    return {**settings, "api": api}


def _mask(secret):
    return f"{secret[:12]}...{secret[-6:]}" if len(secret) > 24 else "***"


_store.eager_load()
