"""Supabase data layer.

All state lives on the :class:`SupabaseData` instance, which the service builds
in ``on_startup`` and drops in ``on_shutdown``. Nothing is module-global, so
unloading the service actually frees its rows and reloading returns to pristine
seeds -- see the note in ``hub/base.py`` on why that matters.

What is reproduced from the real stack
--------------------------------------
* **PostgREST** -- horizontal filtering (``col=op.value`` with ``not.`` negation),
  ``select`` projection with one level of resource embedding, ``order`` with
  ``.desc``/``.asc``, ``limit``/``offset``, ``Content-Range``, ``Prefer:
  return=minimal``, and upstream's real SQLSTATE codes (``42P01`` unknown
  relation, ``42501`` RLS denial, ``23503`` foreign key).
* **RLS** -- role-scoped row visibility, not a decorative check: ``anon`` sees
  public projects and published documents only, and comments follow their parent
  document's visibility.
* **Storage** -- buckets, objects, signed URLs, and the "bucket not empty"
  refusal on delete.
* **Edge Functions** -- ``verify_jwt`` enforcement, a throttled function, and
  per-slug response bodies.
* **Realtime** -- channel list and broadcast, with private channels closed to ``anon``.

Error convention
----------------
Data methods **return** ``{"error": ..., "code": ...}``; they never raise. The
route layer maps ``code`` onto an HTTP status. Keeping the mapping in one table
in ``routes.py`` is what stops a 42501 from being a 404 on one endpoint and a 401
on the next.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from hub.base import ServiceContext
from hub.store import opt_bool, opt_int, opt_str, strict_bool

Row = Dict[str, Any]

ANON_ROLE = "anon"
AUTHENTICATED_ROLE = "authenticated"
SERVICE_ROLE = "service_role"

REST_TABLES = ("profiles", "projects", "documents", "comments")

#: ``(parent, embedded) -> (parent column, embedded column, cardinality)``
EMBEDS: Dict[tuple, tuple] = {
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

RESERVED_PARAMS = frozenset({"select", "order", "limit", "offset", "on_conflict", "columns"})


# ---------------------------------------------------------------------------
# Seed coercion -- pure functions, no instance state
# ---------------------------------------------------------------------------


def _strip_ctx(row: Row) -> Row:
    """Drop the loader's ``__api__``/``__table__``/``__file__`` bookkeeping keys."""
    return {k: v for k, v in row.items() if not k.startswith("__")}


def _semi_list(row: Row, column: str) -> List[str]:
    """Seed cells are strings so a CSV overlay can shadow the JSON; lists use ';'."""
    return [part for part in opt_str(row, column, default="").split(";") if part]


def _coerce_profiles(rows: Iterable[Row]) -> List[Row]:
    return [{**_strip_ctx(r), "is_active": strict_bool(r, "is_active")} for r in rows]


def _coerce_projects(rows: Iterable[Row]) -> List[Row]:
    return [
        {**_strip_ctx(r), "id": opt_int(r, "id", default=0),
         "star_count": opt_int(r, "star_count", default=0)}
        for r in rows
    ]


def _coerce_documents(rows: Iterable[Row]) -> List[Row]:
    return [
        {
            **_strip_ctx(r),
            "id": opt_int(r, "id", default=0),
            "project_id": opt_int(r, "project_id", default=0),
            "word_count": opt_int(r, "word_count", default=0),
            "tags": _semi_list(r, "tags"),
            "published_at": opt_str(r, "published_at", default="") or None,
        }
        for r in rows
    ]


def _coerce_comments(rows: Iterable[Row]) -> List[Row]:
    return [
        {**_strip_ctx(r), "id": opt_int(r, "id", default=0),
         "document_id": opt_int(r, "document_id", default=0),
         "resolved": strict_bool(r, "resolved")}
        for r in rows
    ]


def _coerce_buckets(rows: Iterable[Row]) -> List[Row]:
    return [
        {**_strip_ctx(r), "public": strict_bool(r, "public"),
         "file_size_limit": opt_int(r, "file_size_limit", default=None),
         "allowed_mime_types": _semi_list(r, "allowed_mime_types")}
        for r in rows
    ]


def _coerce_objects(rows: Iterable[Row]) -> List[Row]:
    return [{**_strip_ctx(r), "size": opt_int(r, "size", default=0)} for r in rows]


def _coerce_functions(rows: Iterable[Row]) -> List[Row]:
    return [
        {**_strip_ctx(r), "version": opt_int(r, "version", default=1),
         "verify_jwt": strict_bool(r, "verify_jwt"),
         "import_map": opt_bool(r, "import_map", default=False)}
        for r in rows
    ]


def _coerce_channels(rows: Iterable[Row]) -> List[Row]:
    return [
        {**_strip_ctx(r), "subscriber_count": opt_int(r, "subscriber_count", default=0),
         "is_private": strict_bool(r, "is_private"),
         "event_filter": _semi_list(r, "event_filter")}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# PostgREST query grammar -- pure functions
# ---------------------------------------------------------------------------


def parse_select(spec: Optional[str]) -> tuple:
    """Split a select spec into plain columns and embedded resources.

    ``id,title,comments(id,body)`` -> ``(["id","title"], [("comments",["id","body"])])``
    """
    columns: List[str] = []
    embeds: List[tuple] = []
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


def _project(row: Row, columns: Sequence[str]) -> Row:
    if not columns or "*" in columns:
        return dict(row)
    return {c: row.get(c) for c in columns}


def _like_to_regex(pattern: str) -> str:
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


def _coerce_operand(sample: Any, raw: Any) -> Any:
    """Coerce a query-string operand to the type of the column it is compared to.

    Everything arrives as text, so ``?star_count=gt.100`` would otherwise compare
    a str to an int and raise. Sampling the stored value is what makes numeric
    and boolean filters behave like the real thing.
    """
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


def _match(value: Any, op: str, operand: str) -> bool:
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


def _sort_key(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return str(value)


def _apply_order(rows: List[Row], order: Optional[str]) -> List[Row]:
    """``order=col.desc`` / ``col.asc.nullslast`` / ``col`` (asc by default).

    Applied right-to-left so a multi-column order sorts by the first clause last,
    which -- Python's sort being stable -- makes it the primary key.
    """
    if not order:
        return rows
    out = list(rows)
    for clause in reversed([c.strip() for c in order.split(",") if c.strip()]):
        parts = clause.split(".")
        column, descending = parts[0], "desc" in parts[1:]
        out.sort(key=lambda r: (r.get(column) is None, _sort_key(r.get(column))),
                 reverse=descending)
    return out


def _slugify(text: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def _error(message: str, code: str, details: Any = None, hint: Any = None) -> Row:
    """PostgREST-shaped error body. The ``code`` drives the HTTP status upstream."""
    return {"error": message, "code": code, "details": details, "hint": hint,
            "message": message}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# The data layer
# ---------------------------------------------------------------------------


class SupabaseData:
    """Instance-scoped Supabase state, backed by the hub's mutable store."""

    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx
        self.store = ctx.store
        self._register_tables()

    # -- registration ------------------------------------------------------

    def _register_tables(self) -> None:
        """Declare tables and their loaders. Loaders run at ``eager_load``, not here.

        ``signed_urls`` and ``invocations`` are born empty: they only ever hold
        rows created at runtime, and seeding them would invent history that the
        real project would not have.
        """
        seed = self.ctx.seed
        register = self.ctx.register_table
        register("profiles", "id", lambda: _coerce_profiles(seed("profiles.json", "profiles")))
        register("projects", "id", lambda: _coerce_projects(seed("projects.json", "projects")))
        register("documents", "id", lambda: _coerce_documents(seed("documents.json", "documents")))
        register("comments", "id", lambda: _coerce_comments(seed("comments.json", "comments")))
        register("buckets", "id", lambda: _coerce_buckets(seed("buckets.json", "buckets")))
        register("objects", "id", lambda: _coerce_objects(seed("objects.json", "objects")))
        register("functions", "id", lambda: _coerce_functions(seed("functions.json", "functions")))
        register("channels", "id", lambda: _coerce_channels(seed("channels.json", "channels")))
        register("signed_urls", "token", list)
        register("invocations", "invocation_id", list)
        self.ctx.register_document("settings", self._load_settings)

    def _load_settings(self) -> Dict[str, Any]:
        with open(self.ctx.data_dir / "settings.json", encoding="utf-8") as handle:
            return json.load(handle)

    # -- store helpers -----------------------------------------------------

    def rows(self, table: str) -> List[Row]:
        return self.store.table(table).rows()

    def settings(self) -> Dict[str, Any]:
        return self.store.document("settings").get()

    def _insert(self, table: str, row: Row) -> Row:
        """Persist a new row, synthesising the registered PK from ``id`` if needed."""
        handle = self.store.table(table)
        if handle.primary_key not in row and "id" in row:
            row = {**row, handle.primary_key: row["id"]}
        return handle.upsert(row)

    def _next_serial(self, table: str) -> int:
        """Next bigint identity for a table with an integer PK.

        Scans live rows rather than caching a counter: rows can be injected out
        of band by a drift script, and a cached counter would collide with them.
        """
        ids = [r["id"] for r in self.rows(table) if isinstance(r.get("id"), int)]
        return (max(ids) + 1) if ids else 1

    # -- roles / RLS -------------------------------------------------------

    def resolve_role(self, apikey: Optional[str] = None,
                     authorization: Optional[str] = None) -> str:
        """Map an apikey / bearer token onto a Postgres role.

        Any unfamiliar token resolves to ``authenticated`` rather than being
        rejected. That is a deliberate fleet-wide rule: a simulator that 401s an
        unrecognised token turns every task into a credential hunt, whereas
        mapping tokens onto *roles* keeps the auth layer observable and the
        service reachable.
        """
        token = (apikey or "").strip()
        if not token and authorization:
            parts = str(authorization).split(None, 1)
            token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""
        if not token:
            return ANON_ROLE
        api = self.settings().get("api", {})
        if token == api.get("service_role_key"):
            return SERVICE_ROLE
        if token == api.get("anon_key"):
            return ANON_ROLE
        return AUTHENTICATED_ROLE

    def _visible(self, table: str, row: Row, role: str) -> bool:
        """Row-level visibility standing in for the project's RLS policies."""
        if role in (AUTHENTICATED_ROLE, SERVICE_ROLE):
            return True
        if table == "projects":
            return row.get("visibility") == "public"
        if table == "documents":
            return row.get("status") == "published"
        if table == "comments":
            parent = self.store.table("documents").get(row.get("document_id"))
            return bool(parent) and parent.get("status") == "published"
        return True

    def _apply_rls(self, table: str, rows: List[Row], role: str) -> List[Row]:
        return [r for r in rows if self._visible(table, r, role)]

    def _apply_filters(self, rows: List[Row], filters: Optional[Dict[str, Any]]) -> tuple:
        """Apply ``col=[not.]op.operand`` filters. Returns ``(rows, error_or_None)``."""
        out = list(rows)
        for column, raw in (filters or {}).items():
            if column in RESERVED_PARAMS or column.startswith("__"):
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

    def _embed(self, parent_table: str, sources: List[Row], targets: List[Row],
               embeds: List[tuple], role: str) -> List[Row]:
        """Attach embedded resources to each projected row.

        The join key is read from the *source* row, not the projected one, so
        ``select=id,title,profiles(username)`` still resolves the author even
        though ``author_id`` was projected away. Unknown relationships are
        skipped rather than erroring, matching PostgREST's tolerance.
        """
        for name, sub_columns in embeds:
            rel = EMBEDS.get((parent_table, name))
            if not rel:
                continue
            parent_col, child_col, cardinality = rel
            children = self._apply_rls(name, self.rows(name), role) if name in REST_TABLES else []
            for source, target in zip(sources, targets):
                key = source.get(parent_col)
                matched = [_project(c, sub_columns) for c in children if c.get(child_col) == key]
                target[name] = matched if cardinality == "many" else (matched[0] if matched else None)
        return targets

    # -- REST (PostgREST) --------------------------------------------------

    def rest_root(self) -> Dict[str, Any]:
        """PostgREST root: the schema the API exposes."""
        settings = self.settings()
        return {
            "swagger": "2.0",
            "info": {
                "title": "standard public schema",
                "description": "PostgREST API simulator for the self-hosted Supabase "
                               f"project {settings.get('ref')}",
                "version": settings.get("services", {}).get("rest", {}).get("version", "v12.2.0"),
            },
            "host": settings.get("db", {}).get("host", "supabase-db"),
            "basePath": "/rest/v1",
            "schemes": ["http"],
            "definitions": {name: {"type": "array"} for name in REST_TABLES},
            "paths": {f"/{name}": {} for name in REST_TABLES},
        }

    def select_rows(self, table: str, filters: Optional[Dict[str, Any]] = None,
                    select: Optional[str] = None, order: Optional[str] = None,
                    limit: Optional[int] = None, offset: int = 0,
                    role: str = ANON_ROLE) -> Row:
        """PostgREST GET. Returns an internal envelope the route layer unwraps."""
        if table not in REST_TABLES:
            return _error(f'relation "public.{table}" does not exist', "42P01",
                          hint="Verify the table name and the exposed schema.")
        columns, embeds = parse_select(select or "*")
        rows = self._apply_rls(table, self.rows(table), role)
        rows, err = self._apply_filters(rows, filters)
        if err:
            return err
        total = len(rows)
        rows = _apply_order(rows, order)
        start = int(offset or 0)
        rows = rows[start:start + int(limit)] if limit is not None else rows[start:]
        data = self._embed(table, rows, [_project(r, columns) for r in rows], embeds, role)
        span = f"{start}-{start + len(data) - 1}" if data else "*"
        return {"data": data, "count": total, "content_range": f"{span}/{total}"}

    def insert_rows(self, table: str, payload: Any, role: str = ANON_ROLE,
                    prefer: str = "return=representation") -> Row:
        """PostgREST POST. Accepts a single object or an array of objects."""
        if table not in REST_TABLES:
            return _error(f'relation "public.{table}" does not exist', "42P01")
        if role == ANON_ROLE:
            return _error(f'new row violates row-level security policy for table "{table}"',
                          "42501", hint="Send an apikey header with a writable role.")
        records = payload if isinstance(payload, list) else [payload]
        created: List[Row] = []
        for record in records:
            if not isinstance(record, dict):
                return _error("expected a JSON object or an array of objects", "PGRST102")
            row = self._new_row(table, record)
            if "error" in row:
                return row
            self._insert(table, row)
            created.append(row)
        data = created if "return=minimal" not in (prefer or "") else []
        return {"data": data, "count": len(created), "content_range": f"*/{len(created)}"}

    def _new_row(self, table: str, record: Row) -> Row:
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
                "id": int(record["id"]) if record.get("id") is not None
                else self._next_serial("projects"),
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
            if project_id is not None and not self.store.table("projects").get(int(project_id)):
                return _error(
                    'insert or update on table "documents" violates foreign key '
                    'constraint "documents_project_id_fkey"', "23503",
                    details=f'Key (project_id)=({project_id}) is not present in table "projects".')
            return {
                "id": int(record["id"]) if record.get("id") is not None
                else self._next_serial("documents"),
                "project_id": int(project_id) if project_id is not None else None,
                "author_id": record.get("author_id", ""),
                "title": record.get("title", ""),
                "slug": record.get("slug") or _slugify(record.get("title", "")),
                "body": record.get("body", ""),
                "status": record.get("status", "draft"),
                "word_count": int(record.get("word_count")
                                  or len(str(record.get("body", "")).split())),
                "tags": record.get("tags") or [],
                "created_at": now,
                "updated_at": now,
                "published_at": record.get("published_at"),
            }
        document_id = record.get("document_id")
        if document_id is not None and not self.store.table("documents").get(int(document_id)):
            return _error(
                'insert or update on table "comments" violates foreign key '
                'constraint "comments_document_id_fkey"', "23503",
                details=f'Key (document_id)=({document_id}) is not present in table "documents".')
        return {
            "id": int(record["id"]) if record.get("id") is not None
            else self._next_serial("comments"),
            "document_id": int(document_id) if document_id is not None else None,
            "author_id": record.get("author_id", ""),
            "body": record.get("body", ""),
            "resolved": bool(record.get("resolved", False)),
            "created_at": now,
        }

    def update_rows(self, table: str, patch: Any, filters: Optional[Dict[str, Any]] = None,
                    role: str = ANON_ROLE, prefer: str = "return=representation") -> Row:
        """PostgREST PATCH. The filter set selects the rows to update."""
        if table not in REST_TABLES:
            return _error(f'relation "public.{table}" does not exist', "42P01")
        if role == ANON_ROLE:
            return _error(f'permission denied for table "{table}"', "42501",
                          hint="Send an apikey header with a writable role.")
        if not isinstance(patch, dict) or not patch:
            return _error("expected a non-empty JSON object", "PGRST102")
        targets, err = self._apply_filters(self.rows(table), filters)
        if err:
            return err
        fields = {k: v for k, v in patch.items() if k != "id"}
        if table in ("projects", "documents"):
            fields.setdefault("updated_at", _now_iso())
        updated = [self.store.table(table).patch(row["id"], fields) for row in targets]
        updated = [r for r in updated if r]
        data = updated if "return=minimal" not in (prefer or "") else []
        return {"data": data, "count": len(updated), "content_range": f"*/{len(updated)}"}

    def delete_rows(self, table: str, filters: Optional[Dict[str, Any]] = None,
                    role: str = ANON_ROLE, prefer: str = "return=representation") -> Row:
        """PostgREST DELETE. Refuses an unfiltered delete, as a safety rail."""
        if table not in REST_TABLES:
            return _error(f'relation "public.{table}" does not exist', "42P01")
        if role != SERVICE_ROLE:
            return _error(f'permission denied for table "{table}"', "42501",
                          hint="Deletes require the service_role key.")
        scoped = {k: v for k, v in (filters or {}).items() if k not in RESERVED_PARAMS}
        if not scoped:
            return _error("delete requires at least one filter", "PGRST109",
                          hint="Add a filter such as ?id=eq.101.")
        targets, err = self._apply_filters(self.rows(table), scoped)
        if err:
            return err
        deleted = [row for row in targets if self.store.table(table).delete(row["id"])]
        data = deleted if "return=minimal" not in (prefer or "") else []
        return {"data": data, "count": len(deleted), "content_range": f"*/{len(deleted)}"}

    # -- RPC ---------------------------------------------------------------

    def call_rpc(self, name: str, args: Optional[Row] = None, role: str = ANON_ROLE) -> Any:
        args = args or {}
        handler: Optional[Callable[[Row, str], Any]] = {
            "project_stats": self._rpc_project_stats,
            "search_documents": self._rpc_search_documents,
            "publish_document": self._rpc_publish_document,
        }.get(name)
        if handler is None:
            return _error(f"Could not find the function public.{name} in the schema cache",
                          "PGRST202", hint="Verify the function name and argument names.")
        return handler(args, role)

    def _rpc_project_stats(self, args: Row, role: str) -> Any:
        project_id = args.get("project_id")
        if project_id is None:
            return _error("missing required argument: project_id", "PGRST202")
        project = self.store.table("projects").get(int(project_id))
        if not project or not self._visible("projects", project, role):
            return _error(f"project {project_id} not found", "PGRST116")
        documents = [d for d in self._apply_rls("documents", self.rows("documents"), role)
                     if d["project_id"] == int(project_id)]
        document_ids = {d["id"] for d in documents}
        comments = [c for c in self.rows("comments") if c["document_id"] in document_ids]
        return {
            "project_id": project["id"],
            "name": project["name"],
            "document_count": len(documents),
            "published_count": len([d for d in documents if d["status"] == "published"]),
            "comment_count": len(comments),
            "unresolved_comment_count": len([c for c in comments if not c["resolved"]]),
            "total_words": sum(d["word_count"] for d in documents),
        }

    def _rpc_search_documents(self, args: Row, role: str) -> Any:
        query = str(args.get("query") or "").strip().lower()
        if not query:
            return _error("missing required argument: query", "PGRST202")
        limit = int(args.get("limit") or 10)
        hits = []
        for doc in self._apply_rls("documents", self.rows("documents"), role):
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

    def _rpc_publish_document(self, args: Row, role: str) -> Any:
        document_id = args.get("document_id")
        if document_id is None:
            return _error("missing required argument: document_id", "PGRST202")
        if role == ANON_ROLE:
            return _error("permission denied for function public.publish_document", "42501")
        doc = self.store.table("documents").get(int(document_id))
        if not doc:
            return _error(f"document {document_id} not found", "PGRST116")
        if doc["status"] == "published":
            return _error(f"document {document_id} is already published", "P0001")
        now = _now_iso()
        return self.store.table("documents").patch(
            int(document_id), {"status": "published", "published_at": now, "updated_at": now})

    # -- Storage -----------------------------------------------------------

    def list_buckets(self, role: str = ANON_ROLE) -> List[Row]:
        rows = self.rows("buckets")
        return rows if role != ANON_ROLE else [b for b in rows if b["public"]]

    def get_bucket(self, bucket_id: str, role: str = ANON_ROLE) -> Row:
        bucket = self.store.table("buckets").get(bucket_id)
        if not bucket or (role == ANON_ROLE and not bucket["public"]):
            return _error("Bucket not found", "404")
        return bucket

    def create_bucket(self, bucket_id: str, name: Optional[str] = None, public: bool = False,
                      file_size_limit: Optional[int] = None,
                      allowed_mime_types: Optional[List[str]] = None,
                      role: str = ANON_ROLE) -> Row:
        if role == ANON_ROLE:
            return _error("new row violates row-level security policy", "42501")
        if not bucket_id:
            return _error("id is required", "InvalidRequest")
        if self.store.table("buckets").get(bucket_id):
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
        self._insert("buckets", bucket)
        return {"name": bucket["name"]}

    def delete_bucket(self, bucket_id: str, role: str = ANON_ROLE) -> Row:
        if role != SERVICE_ROLE:
            return _error("new row violates row-level security policy", "42501")
        if not self.store.table("buckets").get(bucket_id):
            return _error("Bucket not found", "404")
        if self.store.table("objects").find(lambda o: o["bucket_id"] == bucket_id):
            return _error("The bucket you tried to delete is not empty", "409")
        self.store.table("buckets").delete(bucket_id)
        return {"message": "Successfully deleted"}

    def list_objects(self, bucket_id: str, prefix: str = "", limit: int = 100,
                     offset: int = 0, role: str = ANON_ROLE) -> Any:
        bucket = self.get_bucket(bucket_id, role=role)
        if "error" in bucket:
            return bucket
        rows = [o for o in self.rows("objects")
                if o["bucket_id"] == bucket_id and o["name"].startswith(prefix or "")]
        rows.sort(key=lambda o: o["name"])
        start = int(offset or 0)
        return rows[start:start + int(limit or 100)]

    def get_object_info(self, bucket_id: str, path: str, role: str = ANON_ROLE) -> Row:
        bucket = self.get_bucket(bucket_id, role=role)
        if "error" in bucket:
            return bucket
        obj = self.store.table("objects").find_one(
            lambda o: o["bucket_id"] == bucket_id and o["name"] == path)
        return obj if obj else _error("Object not found", "404")

    def sign_object(self, bucket_id: str, path: str, expires_in: int = 3600,
                    role: str = ANON_ROLE) -> Row:
        if role == ANON_ROLE:
            return _error("new row violates row-level security policy", "42501")
        obj = self.get_object_info(bucket_id, path, role=role)
        if "error" in obj:
            return obj
        token = uuid.uuid4().hex
        self.store.table("signed_urls").upsert({
            "token": token,
            "bucket_id": bucket_id,
            "object_name": path,
            "expires_in": int(expires_in or 3600),
            "expires_at": int(time.time()) + int(expires_in or 3600),
            "created_at": _now_iso(),
        })
        return {"signedURL": f"/storage/v1/object/sign/{bucket_id}/{path}?token={token}"}

    def delete_object(self, bucket_id: str, path: str, role: str = ANON_ROLE) -> Row:
        if role != SERVICE_ROLE:
            return _error("new row violates row-level security policy", "42501")
        obj = self.store.table("objects").find_one(
            lambda o: o["bucket_id"] == bucket_id and o["name"] == path)
        if not obj:
            return _error("Object not found", "404")
        self.store.table("objects").delete(obj["id"])
        return {"message": "Successfully deleted"}

    # -- Edge Functions ----------------------------------------------------

    def list_functions(self) -> List[Row]:
        return self.rows("functions")

    def invoke_function(self, slug: str, payload: Optional[Row] = None,
                        role: str = ANON_ROLE) -> Row:
        fn = self.store.table("functions").find_one(lambda f: f["slug"] == slug)
        if not fn:
            return _error(f"Function not found: {slug}", "FunctionNotFound")
        if fn["verify_jwt"] and role == ANON_ROLE:
            return _error("Missing authorization header", "401")
        if fn["status"] == "THROTTLED":
            return _error(f"Function {slug} is throttled; retry after the cooldown", "429")
        body = self._function_body(slug, payload or {})
        invocation = {
            "invocation_id": _new_id("inv"),
            "function_id": fn["id"],
            "slug": slug,
            "version": fn["version"],
            "status_code": 200,
            "invoked_at": _now_iso(),
        }
        self.store.table("invocations").upsert(invocation)
        return {"invocation_id": invocation["invocation_id"], "slug": slug,
                "version": fn["version"], "data": body}

    def _function_body(self, slug: str, payload: Row) -> Row:
        if slug == "send-welcome-email":
            return {"queued": True, "to": payload.get("email", ""),
                    "template": "welcome-v3", "message_id": _new_id("msg")}
        if slug == "billing-webhook":
            return {"received": True, "event": payload.get("type", "invoice.updated"),
                    "processed_at": _now_iso()}
        if slug == "generate-report":
            docs = self.rows("documents")
            return {"report_id": _new_id("rep"), "period": payload.get("period", "2026-05"),
                    "documents": len(docs),
                    "published": len([d for d in docs if d["status"] == "published"]),
                    "total_words": sum(d["word_count"] for d in docs)}
        return {"ok": True, "echo": payload}

    # -- Realtime ----------------------------------------------------------

    def list_channels(self) -> List[Row]:
        return self.rows("channels")

    def broadcast(self, messages: List[Row], role: str = ANON_ROLE) -> Row:
        if not messages:
            return _error("messages is required", "InvalidRequest")
        accepted = 0
        for message in messages:
            topic = message.get("topic")
            if not topic:
                return _error("each message requires a topic", "InvalidRequest")
            channel = self.store.table("channels").find_one(lambda c: c["name"] == topic)
            if channel and channel["is_private"] and role == ANON_ROLE:
                return _error(f"Unauthorized broadcast to private channel {topic}", "401")
            accepted += 1
        return {"message": "ok", "accepted": accepted}

    # -- Project read model ------------------------------------------------

    def get_settings(self) -> Dict[str, Any]:
        """Project settings with the service key masked, as the dashboard shows it."""
        settings = self.settings()
        api = dict(settings.get("api", {}))
        api["service_role_key"] = _mask(api.get("service_role_key", ""))
        return {**settings, "api": api}

    def list_projects(self) -> List[Row]:
        settings = self.settings()
        return [{"id": settings["ref"], "name": settings["name"],
                 "organization": settings["organization"], "region": settings["region"],
                 "status": settings["status"], "created_at": settings["created_at"]}]


def _mask(secret: str) -> str:
    return f"{secret[:12]}...{secret[-6:]}" if len(secret) > 24 else "***"
