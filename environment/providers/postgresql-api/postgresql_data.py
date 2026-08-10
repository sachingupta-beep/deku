"""Data access module for the PostgreSQL API mock service.

Exposes a PostgreSQL database over HTTP -- `orbit_core`, the API-platform
database behind the Orbit Labs product. Statements run through `sql_engine`,
which materializes the shared store into an in-memory SQLite database per
request, executes genuine SQL, and syncs writes back so the admin plane can
still drift a row mid-run.

Everything above the engine is PostgreSQL: SQLSTATE error codes with the
severity/detail/hint/constraint fields a driver reports, `information_schema`
and `pg_catalog` views, `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` node trees,
role-based GRANTs, extensions, settings and replication state.

A small dialect rewriter translates the PostgreSQL-only syntax an agent is
likely to send -- `::` casts, `ILIKE`, `$1` placeholders, `NOW()` -- into the
engine's SQL. Constructs outside that set are reported as syntax errors rather
than silently mistranslated.
"""

import json
import re
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_float, opt_int, opt_str)

import sql_engine
from sql_engine import SqlError

_store = get_store("postgresql-api")
_API = "postgresql-api"


def _load_cluster():
    with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("organizations", primary_key="id",
                initial_loader=lambda: _coerce_organizations(_load("organizations.json", "organizations")))
_store.register("api_keys", primary_key="id",
                initial_loader=lambda: _coerce_api_keys(_load("api_keys.json", "api_keys")))
_store.register("api_key_scopes", primary_key="id",
                initial_loader=lambda: _coerce_scopes(_load("api_key_scopes.json", "api_key_scopes")))
_store.register("endpoints", primary_key="id",
                initial_loader=lambda: _coerce_endpoints(_load("endpoints.json", "endpoints")))
_store.register("request_stats", primary_key="id",
                initial_loader=lambda: _coerce_request_stats(_load("request_stats.json", "request_stats")))
_store.register("webhooks", primary_key="id",
                initial_loader=lambda: _coerce_webhooks(_load("webhooks.json", "webhooks")))
_store.register("webhook_deliveries", primary_key="id",
                initial_loader=lambda: _coerce_deliveries(_load("webhook_deliveries.json", "webhook_deliveries")))
_store.register("pg_roles", primary_key="rolname",
                initial_loader=lambda: _coerce_roles(_load("roles.json", "pg_roles")))
_store.register("pg_grants", primary_key="id",
                initial_loader=lambda: _coerce_grants(_load("grants.json", "pg_grants")))
_store.register("pg_stat_activity", primary_key="pid",
                initial_loader=lambda: _coerce_activity(_load("activity.json", "pg_stat_activity")))
_store.register("pg_stat_statements", primary_key="queryid",
                initial_loader=lambda: _coerce_statements(_load("statements.json", "pg_stat_statements")))
_store.register("pg_stat_user_tables", primary_key="relname",
                initial_loader=lambda: _coerce_table_stats(_load("table_stats.json", "pg_stat_user_tables")))
_store.register_document("cluster", initial_loader=_load_cluster)


def _organizations_rows():
    return _store.table("organizations").rows()


def _api_keys_rows():
    return _store.table("api_keys").rows()


def _scopes_rows():
    return _store.table("api_key_scopes").rows()


def _endpoints_rows():
    return _store.table("endpoints").rows()


def _request_stats_rows():
    return _store.table("request_stats").rows()


def _webhooks_rows():
    return _store.table("webhooks").rows()


def _deliveries_rows():
    return _store.table("webhook_deliveries").rows()


def _roles_rows():
    return _store.table("pg_roles").rows()


def _grants_rows():
    return _store.table("pg_grants").rows()


def _activity_rows():
    return _store.table("pg_stat_activity").rows()


def _statements_rows():
    return _store.table("pg_stat_statements").rows()


def _table_stats_rows():
    return _store.table("pg_stat_user_tables").rows()


def _cluster_doc():
    return _store.document("cluster").get()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _null_if_blank(row, column):
    value = opt_str(row, column, default="")
    return value if value else None


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

def _coerce_organizations(rows):
    return [{**_strip_ctx(r), "seats": opt_int(r, "seats", default=0),
             "mrr_cents": opt_int(r, "mrr_cents", default=0),
             "suspended_at": _null_if_blank(r, "suspended_at")} for r in rows]


def _coerce_api_keys(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "revoked_at": _null_if_blank(r, "revoked_at")} for r in rows]


def _coerce_scopes(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "api_key_id": opt_int(r, "api_key_id", default=0)} for r in rows]


def _coerce_endpoints(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "deprecated": opt_int(r, "deprecated", default=0),
             "rate_limit_per_min": opt_int(r, "rate_limit_per_min", default=0)}
            for r in rows]


def _coerce_request_stats(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "endpoint_id": opt_int(r, "endpoint_id", default=0),
             "requests": opt_int(r, "requests", default=0),
             "errors": opt_int(r, "errors", default=0),
             "p95_ms": opt_float(r, "p95_ms", default=0.0),
             "bytes_out": opt_int(r, "bytes_out", default=0)} for r in rows]


def _coerce_webhooks(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "active": opt_int(r, "active", default=1),
             "failure_count": opt_int(r, "failure_count", default=0)} for r in rows]


def _coerce_deliveries(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "webhook_id": opt_int(r, "webhook_id", default=0),
             "attempts": opt_int(r, "attempts", default=0),
             "response_code": opt_int(r, "response_code", default=None),
             "delivered_at": _null_if_blank(r, "delivered_at")} for r in rows]


def _coerce_roles(rows):
    flags = ("rolsuper", "rolcreaterole", "rolcreatedb", "rolcanlogin",
             "rolreplication", "rolbypassrls")
    return [{**_strip_ctx(r), **{f: bool(opt_int(r, f, default=0)) for f in flags},
             "rolconnlimit": opt_int(r, "rolconnlimit", default=-1)} for r in rows]


def _coerce_grants(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "privileges": [p for p in opt_str(r, "privileges", default="").split(";") if p]}
            for r in rows]


def _coerce_activity(rows):
    return [{**_strip_ctx(r), "pid": opt_int(r, "pid", default=0)} for r in rows]


def _coerce_statements(rows):
    numeric = ("total_exec_time", "mean_exec_time", "max_exec_time")
    integer = ("calls", "rows", "shared_blks_hit", "shared_blks_read")
    return [{**_strip_ctx(r), **{f: opt_float(r, f, default=0.0) for f in numeric},
             **{f: opt_int(r, f, default=0) for f in integer}} for r in rows]


def _coerce_table_stats(rows):
    integer = ("seq_scan", "seq_tup_read", "idx_scan", "idx_tup_fetch", "n_tup_ins",
               "n_tup_upd", "n_tup_del", "n_live_tup", "n_dead_tup",
               "table_size_bytes", "index_size_bytes")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integer},
             "last_autovacuum": _null_if_blank(r, "last_autovacuum")} for r in rows]


# ---------------------------------------------------------------------------
# Schema
#
# SQLite records the declared type verbatim and applies affinity, so the
# PostgreSQL type names below are what `information_schema.columns` reports.
# ---------------------------------------------------------------------------

DDL = [
    """CREATE TABLE organizations (
        id           uuid        PRIMARY KEY,
        name         text        NOT NULL,
        slug         text        NOT NULL UNIQUE,
        plan         text        NOT NULL CHECK (plan IN ('starter', 'pro', 'enterprise')),
        seats        integer     NOT NULL DEFAULT 1 CHECK (seats > 0),
        region       text        NOT NULL,
        settings     jsonb       NOT NULL DEFAULT '{}',
        mrr_cents    bigint      NOT NULL DEFAULT 0,
        created_at   timestamptz NOT NULL,
        suspended_at timestamptz
    )""",
    """CREATE TABLE api_keys (
        id           integer     PRIMARY KEY,
        org_id       uuid        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        name         text        NOT NULL,
        prefix       text        NOT NULL UNIQUE,
        environment  text        NOT NULL CHECK (environment IN ('live', 'test')),
        last_used_at timestamptz,
        created_at   timestamptz NOT NULL,
        revoked_at   timestamptz
    )""",
    """CREATE TABLE api_key_scopes (
        id         integer PRIMARY KEY,
        api_key_id integer NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
        scope      text    NOT NULL CHECK (scope IN ('read', 'write', 'admin')),
        UNIQUE (api_key_id, scope)
    )""",
    """CREATE TABLE endpoints (
        id                 integer PRIMARY KEY,
        method             text    NOT NULL,
        path               text    NOT NULL,
        version            text    NOT NULL,
        deprecated         boolean NOT NULL DEFAULT false,
        rate_limit_per_min integer NOT NULL DEFAULT 60,
        UNIQUE (method, path)
    )""",
    """CREATE TABLE request_stats (
        id          integer       PRIMARY KEY,
        org_id      uuid          NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        endpoint_id integer       NOT NULL REFERENCES endpoints(id),
        day         date          NOT NULL,
        requests    bigint        NOT NULL DEFAULT 0 CHECK (requests >= 0),
        errors      bigint        NOT NULL DEFAULT 0 CHECK (errors >= 0),
        p95_ms      numeric(10,2) NOT NULL DEFAULT 0,
        bytes_out   bigint        NOT NULL DEFAULT 0,
        UNIQUE (org_id, endpoint_id, day)
    )""",
    """CREATE TABLE webhooks (
        id            integer     PRIMARY KEY,
        org_id        uuid        NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        url           text        NOT NULL,
        description   text,
        active        boolean     NOT NULL DEFAULT true,
        failure_count integer     NOT NULL DEFAULT 0,
        created_at    timestamptz NOT NULL
    )""",
    """CREATE TABLE webhook_deliveries (
        id            integer     PRIMARY KEY,
        webhook_id    integer     NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
        event         text        NOT NULL,
        status        text        NOT NULL CHECK (status IN
                          ('pending', 'retrying', 'delivered', 'failed')),
        attempts      integer     NOT NULL DEFAULT 0,
        response_code integer,
        payload       jsonb       NOT NULL DEFAULT '{}',
        queued_at     timestamptz NOT NULL,
        delivered_at  timestamptz
    )""",
    "CREATE INDEX idx_api_keys_org ON api_keys(org_id)",
    "CREATE INDEX idx_request_stats_org_day ON request_stats(org_id, day)",
    "CREATE INDEX idx_request_stats_day ON request_stats(day)",
    "CREATE INDEX idx_webhooks_org ON webhooks(org_id)",
    "CREATE INDEX idx_deliveries_status ON webhook_deliveries(status, queued_at)",
    """CREATE VIEW active_api_keys AS
        SELECT k.id, k.prefix, k.environment, o.name AS organization, o.plan
        FROM api_keys k
        JOIN organizations o ON o.id = k.org_id
        WHERE k.revoked_at IS NULL""",
]

TABLES = {
    "organizations": _organizations_rows,
    "api_keys": _api_keys_rows,
    "api_key_scopes": _scopes_rows,
    "endpoints": _endpoints_rows,
    "request_stats": _request_stats_rows,
    "webhooks": _webhooks_rows,
    "webhook_deliveries": _deliveries_rows,
}


# ---------------------------------------------------------------------------
# Dialect rewriting
# ---------------------------------------------------------------------------

_CAST_RE = re.compile(r"::\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)")
_PLACEHOLDER_RE = re.compile(r"\$\d+")


def rewrite(sql):
    """Translate the PostgreSQL-only syntax an agent is likely to send.

    Handled: `ILIKE`, `$n` placeholders, `NOW()`/`CURRENT_TIMESTAMP`, and the
    `value::type` cast form. Everything else is passed through, so unsupported
    PostgreSQL constructs surface as an honest syntax error instead of being
    silently mistranslated.
    """
    out = _split_preserving_literals(sql)
    return "".join(part if quoted else _rewrite_fragment(part) for part, quoted in out)


def _split_preserving_literals(sql):
    """Split into (fragment, is_quoted) so rewrites never touch string literals."""
    parts, buffer, quote = [], "", None
    for char in sql or "":
        if quote:
            buffer += char
            if char == quote:
                parts.append((buffer, True))
                buffer, quote = "", None
            continue
        if char in ("'", '"'):
            if buffer:
                parts.append((buffer, False))
            buffer, quote = char, char
            continue
        buffer += char
    if buffer:
        parts.append((buffer, quote is not None))
    return parts


def _rewrite_fragment(fragment):
    fragment = _PLACEHOLDER_RE.sub("?", fragment)
    fragment = re.sub(r"\bILIKE\b", "LIKE", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"\bNOW\s*\(\s*\)", "datetime('now')", fragment,
                      flags=re.IGNORECASE)
    fragment = re.sub(r"\bCURRENT_TIMESTAMP\b", "datetime('now')", fragment,
                      flags=re.IGNORECASE)
    # `expr::type` -> `CAST(expr AS type)` for the simple operand forms.
    while True:
        match = _CAST_RE.search(fragment)
        if not match:
            break
        start = _cast_operand_start(fragment, match.start())
        if start is None:
            fragment = fragment[:match.start()] + " " + fragment[match.end():]
            continue
        operand = fragment[start:match.start()]
        target = _cast_type(match.group(1))
        fragment = (fragment[:start] + f"CAST({operand} AS {target})"
                    + fragment[match.end():])
    return fragment


def _cast_operand_start(fragment, cast_at):
    """Walk left from `::` to the start of the operand it applies to."""
    index = cast_at - 1
    while index >= 0 and fragment[index].isspace():
        index -= 1
    if index < 0:
        return None
    if fragment[index] == ")":
        depth = 0
        while index >= 0:
            if fragment[index] == ")":
                depth += 1
            elif fragment[index] == "(":
                depth -= 1
                if depth == 0:
                    break
            index -= 1
        while index - 1 >= 0 and (fragment[index - 1].isalnum()
                                  or fragment[index - 1] == "_"):
            index -= 1
        return max(index, 0)
    while index >= 0 and (fragment[index].isalnum() or fragment[index] in "_.$?"):
        index -= 1
    return index + 1


_CAST_TYPES = {"int": "INTEGER", "int4": "INTEGER", "int8": "INTEGER",
               "integer": "INTEGER", "bigint": "INTEGER", "smallint": "INTEGER",
               "numeric": "REAL", "decimal": "REAL", "float8": "REAL",
               "double precision": "REAL", "real": "REAL",
               "text": "TEXT", "varchar": "TEXT", "uuid": "TEXT", "date": "TEXT",
               "timestamptz": "TEXT", "timestamp": "TEXT", "jsonb": "TEXT",
               "json": "TEXT", "boolean": "INTEGER", "bool": "INTEGER"}


def _cast_type(declared):
    base = re.sub(r"\s*\(.*\)$", "", declared).strip().lower()
    return _CAST_TYPES.get(base, "TEXT")


_db = sql_engine.Database("orbit_core", DDL, TABLES, _store, rewriter=rewrite)


# ---------------------------------------------------------------------------
# Errors -- PostgreSQL SQLSTATE with the fields a driver reports
# ---------------------------------------------------------------------------

_SQLSTATE = {
    sql_engine.UNIQUE_VIOLATION: ("23505", "unique_violation", 409),
    sql_engine.FOREIGN_KEY_VIOLATION: ("23503", "foreign_key_violation", 409),
    sql_engine.NOT_NULL_VIOLATION: ("23502", "not_null_violation", 400),
    sql_engine.CHECK_VIOLATION: ("23514", "check_violation", 400),
    sql_engine.UNDEFINED_TABLE: ("42P01", "undefined_table", 404),
    sql_engine.UNDEFINED_COLUMN: ("42703", "undefined_column", 400),
    sql_engine.SYNTAX_ERROR: ("42601", "syntax_error", 400),
    sql_engine.DATATYPE_MISMATCH: ("42804", "datatype_mismatch", 400),
    sql_engine.FEATURE_NOT_SUPPORTED: ("0A000", "feature_not_supported", 403),
    sql_engine.INTERNAL_ERROR: ("XX000", "internal_error", 500),
}

_UNIQUE_TARGET = re.compile(r"UNIQUE constraint failed: ([\w.]+(?:, [\w.]+)*)")
_NOT_NULL_TARGET = re.compile(r"NOT NULL constraint failed: (\w+)\.(\w+)")
_RELATION_TARGET = re.compile(r"no such table: (\S+)")
_COLUMN_TARGET = re.compile(r"no such column: (\S+)")


def _sql_error(exc):
    """Render a neutral engine failure as a PostgreSQL error report."""
    code, name, status = _SQLSTATE.get(exc.kind, ("XX000", "internal_error", 500))
    message, detail, hint, constraint, table, column = exc.message, None, None, None, None, None

    unique = _UNIQUE_TARGET.search(exc.message)
    if unique:
        targets = [t.strip() for t in unique.group(1).split(",")]
        table = targets[0].split(".")[0]
        columns = [t.split(".")[1] for t in targets if "." in t]
        constraint = f"{table}_{'_'.join(columns)}_key"
        message = f'duplicate key value violates unique constraint "{constraint}"'
        detail = f"Key ({', '.join(columns)}) already exists."
    elif exc.kind == sql_engine.FOREIGN_KEY_VIOLATION:
        message = ("insert or update on table violates foreign key constraint")
        detail = "Key is not present in the referenced table."
        hint = "Insert the referenced row first, or remove the reference."
    else:
        not_null = _NOT_NULL_TARGET.search(exc.message)
        relation = _RELATION_TARGET.search(exc.message)
        column_miss = _COLUMN_TARGET.search(exc.message)
        if not_null:
            table, column = not_null.group(1), not_null.group(2)
            message = f'null value in column "{column}" of relation "{table}" ' \
                      f"violates not-null constraint"
        elif relation:
            table = relation.group(1)
            message = f'relation "{table}" does not exist'
        elif column_miss:
            column = column_miss.group(1)
            message = f'column "{column}" does not exist'
            hint = "Perhaps you meant to reference a column in another relation."
        elif exc.kind == sql_engine.CHECK_VIOLATION:
            message = "new row for relation violates check constraint"
            detail = exc.message

    body = {"error": message, "severity": "ERROR", "code": code, "sqlstate": code,
            "condition": name, "message": message, "status": status}
    for key, value in (("detail", detail), ("hint", hint), ("constraint", constraint),
                       ("table", table), ("column", column),
                       ("schema", "public" if table else None)):
        if value:
            body[key] = value
    if exc.statement:
        body["statement"] = exc.statement
    index = getattr(exc, "statement_index", None)
    if index is not None:
        body["statement_index"] = index
    return body


def _error(status, code, condition, message, **fields):
    body = {"error": message, "severity": "ERROR", "code": code, "sqlstate": code,
            "condition": condition, "message": message, "status": status}
    body.update({k: v for k, v in fields.items() if v is not None})
    return body


# ---------------------------------------------------------------------------
# Roles, privileges
# ---------------------------------------------------------------------------

_TABLE_REF = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+([\"\w.]+)", re.IGNORECASE)

_WRITE_PRIVILEGE = {"insert": "INSERT", "update": "UPDATE", "delete": "DELETE",
                    "replace": "INSERT"}


def resolve_role(db_role=None, authorization=None):
    """Map the `X-DB-Role` header (or a bearer token) onto a cluster role.

    An unknown or absent role falls back to the cluster's default application
    role, keeping the fleet convention that a request is never simply rejected
    for lacking a credential.
    """
    name = (db_role or "").strip()
    if not name and authorization:
        raw = str(authorization).strip()
        name = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    row = _store.table("pg_roles").get(name) if name else None
    if row:
        return row["rolname"]
    return _cluster_doc()["auth"]["default_role"]


def _is_superuser(role):
    row = _store.table("pg_roles").get(role)
    return bool(row and row["rolsuper"])


def _privileges(role, table):
    if _is_superuser(role):
        return {"SELECT", "INSERT", "UPDATE", "DELETE"}
    grant = _store.table("pg_grants").find_one(
        lambda g: g["grantee"] == role and g["table_name"] == table)
    return set(grant["privileges"]) if grant else set()


def _referenced_tables(sql):
    names = set()
    for match in _TABLE_REF.finditer(sql or ""):
        name = match.group(1).strip('"').split(".")[-1].lower()
        if name in TABLES:
            names.add(name)
    return names


def check_privileges(sql, role):
    """Enforce table-level GRANTs the way PostgreSQL would."""
    statement = (sql or "").strip()
    required = _WRITE_PRIVILEGE.get(sql_engine._statement_type(statement), "SELECT")
    for table in _referenced_tables(statement):
        held = _privileges(role, table)
        if required not in held:
            return _error(403, "42501", "insufficient_privilege",
                          f'permission denied for table {table}',
                          table=table, schema="public",
                          detail=f'Role "{role}" lacks {required} on public.{table}.')
        # A write also reads the row it targets.
        if required != "SELECT" and "SELECT" not in held:
            return _error(403, "42501", "insufficient_privilege",
                          f'permission denied for table {table}',
                          table=table, schema="public")
    return None


# ---------------------------------------------------------------------------
# Query surface
# ---------------------------------------------------------------------------

def query(sql, params=None, max_rows=1000, role="orbit_app"):
    denied = check_privileges(sql, role)
    if denied:
        return denied
    try:
        result = _db.execute(sql, params=params, readonly=True, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result, role)


def execute(sql, params=None, max_rows=1000, role="orbit_app"):
    denied = check_privileges(sql, role)
    if denied:
        return denied
    try:
        result = _db.execute(sql, params=params, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result, role)


_ISOLATION_LEVELS = ("read committed", "repeatable read", "serializable",
                     "read uncommitted")


def transaction(statements, isolation_level="read committed", role="orbit_app"):
    if not statements:
        return _error(400, "42601", "syntax_error", "no statements supplied")
    level = str(isolation_level or "read committed").lower()
    if level not in _ISOLATION_LEVELS:
        return _error(400, "0A000", "feature_not_supported",
                      f'invalid value for parameter "transaction_isolation": '
                      f'"{isolation_level}"',
                      hint="Available values: " + ", ".join(_ISOLATION_LEVELS))
    for entry in statements:
        denied = check_privileges(entry.get("sql"), role)
        if denied:
            return denied
    try:
        results = _db.execute_many(statements, atomic=True)
    except SqlError as exc:
        body = _sql_error(exc)
        body["rolled_back"] = True
        body["in_failed_transaction"] = True
        return body
    return {"results": [_result_envelope(r, role) for r in results],
            "statement_count": len(results), "isolation_level": level,
            "rolled_back": False, "committed": True}


def _result_envelope(result, role):
    return {
        "command": result["statement_type"].upper(),
        "fields": [{"name": name, "type": _pg_type(kind)}
                   for name, kind in zip(result["columns"], result["types"])],
        "rows": [dict(zip(result["columns"], row)) for row in result["rows"]],
        "row_count": result["row_count"],
        "rows_affected": result["rows_affected"],
        "truncated": result["truncated"],
        "duration_ms": result["duration_ms"],
        "role": role,
        **({"statement_index": result["statement_index"]}
           if "statement_index" in result else {}),
    }


_PG_TYPES = {"integer": "int8", "real": "numeric", "text": "text", "null": "text",
             "blob": "bytea"}


def _pg_type(kind):
    return _PG_TYPES.get(kind, "text")


# ---------------------------------------------------------------------------
# EXPLAIN
# ---------------------------------------------------------------------------

def explain(sql, analyze=False, buffers=False, fmt="json", role="orbit_app"):
    denied = check_privileges(sql, role)
    if denied:
        return denied
    try:
        plan = _db.explain(sql)
        started = time.perf_counter()
        rows = _db.query_all(rewrite(sql)) if analyze else []
        elapsed = round((time.perf_counter() - started) * 1000, 3)
    except SqlError as exc:
        return _sql_error(exc)
    node = _plan_tree(plan, analyze, len(rows), elapsed, buffers)
    if str(fmt).lower() == "text":
        return {"format": "text", "plan": _plan_text(node)}
    return {"format": "json", "plan": [node],
            "planning_time_ms": 0.184,
            **({"execution_time_ms": elapsed} if analyze else {})}


def _plan_tree(steps, analyze, row_count, elapsed, buffers):
    """Render the engine's plan steps as a PostgreSQL-style node tree."""
    children = []
    for step in steps:
        detail = str(step.get("detail", ""))
        if detail.startswith("SEARCH"):
            node_type, index = "Index Scan", _index_name(detail)
        elif detail.startswith("SCAN"):
            node_type, index = "Seq Scan", None
        elif "USE TEMP B-TREE" in detail:
            node_type, index = "Sort", None
        else:
            node_type, index = "Nested Loop", None
        node = {"Node Type": node_type,
                "Relation Name": _relation_name(detail),
                "Startup Cost": 0.0,
                "Total Cost": round(1.0 + len(detail) * 0.37, 2),
                "Plan Rows": max(row_count, 1),
                "Plan Width": 64}
        if index:
            node["Index Name"] = index
            node["Scan Direction"] = "Forward"
        if analyze:
            node["Actual Startup Time"] = 0.012
            node["Actual Total Time"] = elapsed
            node["Actual Rows"] = row_count
            node["Actual Loops"] = 1
        if buffers:
            node["Shared Hit Blocks"] = 12
            node["Shared Read Blocks"] = 0
            node["Temp Read Blocks"] = 0
        children.append(node)
    if len(children) == 1:
        return children[0]
    return {"Node Type": "Nested Loop", "Join Type": "Inner",
            "Startup Cost": 0.0, "Total Cost": round(
                sum(c["Total Cost"] for c in children), 2),
            "Plan Rows": max(row_count, 1), "Plan Width": 64,
            "Plans": children or [{"Node Type": "Result", "Total Cost": 0.01,
                                   "Plan Rows": 1, "Plan Width": 0}]}


def _index_name(detail):
    match = re.search(r"USING (?:COVERING )?INDEX (\w+)", detail)
    return match.group(1) if match else None


def _relation_name(detail):
    match = re.search(r"(?:SCAN|SEARCH) (\w+)", detail)
    return match.group(1) if match else None


def _plan_text(node, depth=0):
    prefix = "  " * depth + ("-> " if depth else "")
    label = node["Node Type"]
    if node.get("Relation Name"):
        label += f" on {node['Relation Name']}"
    if node.get("Index Name"):
        label += f" using {node['Index Name']}"
    line = (f"{prefix}{label}  (cost={node['Startup Cost']:.2f}.."
            f"{node['Total Cost']:.2f} rows={node['Plan Rows']} "
            f"width={node['Plan Width']})")
    if "Actual Total Time" in node:
        line += (f" (actual time={node['Actual Startup Time']:.3f}.."
                 f"{node['Actual Total Time']:.3f} rows={node['Actual Rows']} "
                 f"loops={node['Actual Loops']})")
    lines = [line]
    for child in node.get("Plans", []):
        lines.append(_plan_text(child, depth + 1))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# information_schema / pg_catalog
# ---------------------------------------------------------------------------

def list_schemas():
    return {"schemas": [
        {"schema_name": "public", "schema_owner": "orbit_app",
         "table_count": len(TABLES)},
        {"schema_name": "information_schema", "schema_owner": "postgres",
         "table_count": 0},
        {"schema_name": "pg_catalog", "schema_owner": "postgres", "table_count": 0},
    ]}


def list_tables(role="orbit_app"):
    rows = _db.query_all(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY type, name")
    stats = {s["relname"]: s for s in _table_stats_rows()}
    out = []
    for row in rows:
        entry = {"table_schema": "public", "table_name": row["name"],
                 "table_type": "BASE TABLE" if row["type"] == "table" else "VIEW",
                 "privileges": sorted(_privileges(role, row["name"]))}
        if row["type"] == "table":
            entry["row_count"] = _db.query_all(
                f'SELECT COUNT(*) AS n FROM "{row["name"]}"')[0]["n"]
            stat = stats.get(row["name"])
            if stat:
                entry["table_size_bytes"] = stat["table_size_bytes"]
                entry["index_size_bytes"] = stat["index_size_bytes"]
                entry["n_dead_tup"] = stat["n_dead_tup"]
        out.append(entry)
    return {"tables": out, "count": len(out)}


def describe_table(name, role="orbit_app"):
    exists = _db.query_all(
        "SELECT name, type, sql FROM sqlite_master WHERE name = ? "
        "AND type IN ('table', 'view')", [name])
    if not exists:
        return _error(404, "42P01", "undefined_table",
                      f'relation "{name}" does not exist', table=name)
    columns = []
    for column in _db.query_all(f'PRAGMA table_info("{name}")'):
        columns.append({
            "ordinal_position": column["cid"] + 1,
            "column_name": column["name"],
            "data_type": column["type"].lower() or "text",
            "is_nullable": "NO" if column["notnull"] or column["pk"] else "YES",
            "column_default": column["dflt_value"],
            "is_primary_key": bool(column["pk"]),
        })
    constraints = _db.query_all(f'PRAGMA foreign_key_list("{name}")')
    indexes = []
    for index in _db.query_all(f'PRAGMA index_list("{name}")'):
        indexes.append({
            "indexname": index["name"],
            "is_unique": bool(index["unique"]),
            "is_primary": index["origin"] == "pk",
            "columns": [c["name"] for c in
                        _db.query_all(f'PRAGMA index_info("{index["name"]}")')],
        })
    return {"table_schema": "public", "table_name": name,
            "table_type": "BASE TABLE" if exists[0]["type"] == "table" else "VIEW",
            "definition": exists[0]["sql"], "columns": columns,
            "foreign_keys": [{"column": c["from"], "references_table": c["table"],
                              "references_column": c["to"],
                              "on_delete": c["on_delete"], "on_update": c["on_update"]}
                             for c in constraints],
            "indexes": indexes,
            "privileges": sorted(_privileges(role, name))}


def list_indexes():
    rows = _db.query_all(
        "SELECT name, tbl_name FROM sqlite_master WHERE type = 'index' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY tbl_name, name")
    out = []
    for row in rows:
        columns = [c["name"] for c in
                   _db.query_all(f'PRAGMA index_info("{row["name"]}")')]
        out.append({"schemaname": "public", "tablename": row["tbl_name"],
                    "indexname": row["name"],
                    "indexdef": f'CREATE INDEX {row["name"]} ON public.'
                                f'{row["tbl_name"]} USING btree '
                                f'({", ".join(columns)})',
                    "columns": columns})
    return {"indexes": out, "count": len(out)}


def stat_activity(role="orbit_app"):
    """`pg_stat_activity`. A non-superuser cannot read another session's query."""
    superuser = _is_superuser(role)
    rows = []
    for row in _activity_rows():
        entry = dict(row)
        if not superuser and entry["usename"] != role:
            entry["query"] = "<insufficient privilege>"
        rows.append(entry)
    return {"rows": rows, "count": len(rows), "role": role,
            "note": None if superuser else
            "query text of other roles' sessions is masked without superuser"}


def stat_statements(order_by="total_exec_time", limit=10, role="orbit_app"):
    if not _is_superuser(role) and role != "orbit_app":
        return _error(403, "42501", "insufficient_privilege",
                      "permission denied for view pg_stat_statements",
                      detail="pg_stat_statements requires pg_read_all_stats.")
    allowed = {"total_exec_time", "mean_exec_time", "max_exec_time", "calls", "rows"}
    if order_by not in allowed:
        return _error(400, "42703", "undefined_column",
                      f'column "{order_by}" does not exist',
                      hint="Available columns: " + ", ".join(sorted(allowed)))
    rows = sorted(_statements_rows(), key=lambda r: r[order_by], reverse=True)
    return {"rows": rows[:int(limit)], "count": len(rows), "order_by": order_by}


def stat_user_tables():
    rows = sorted(_table_stats_rows(), key=lambda r: r["relname"])
    return {"rows": rows, "count": len(rows)}


def stat_replication(role="orbit_app"):
    replication = _cluster_doc()["replication"]
    return {"role": replication["role"], "wal_lsn": replication["wal_lsn"],
            "standbys": replication["standbys"],
            "count": len(replication["standbys"])}


def list_settings(name=None):
    settings = _cluster_doc()["settings"]
    if name:
        match = next((s for s in settings if s["name"] == name), None)
        if not match:
            return _error(404, "42704", "undefined_object",
                          f'unrecognized configuration parameter "{name}"')
        return match
    return {"settings": settings, "count": len(settings)}


def list_extensions():
    extensions = _cluster_doc()["extensions"]
    return {"extensions": extensions, "count": len(extensions)}


def list_roles():
    return {"roles": _roles_rows(), "count": len(_roles_rows())}


def list_grants(role=None):
    rows = _grants_rows()
    if role:
        rows = [g for g in rows if g["grantee"] == role]
    return {"grants": rows, "count": len(rows)}


def database_info():
    cluster = _cluster_doc()
    tables = [t for t in list_tables()["tables"] if t["table_type"] == "BASE TABLE"]
    return {
        "version": cluster["version"],
        "server_version": cluster["server_version"],
        "server_version_num": cluster["server_version_num"],
        "database": cluster["database"],
        "schema": cluster["schema"],
        "search_path": cluster["search_path"],
        "encoding": cluster["encoding"],
        "collate": cluster["collate"],
        "ctype": cluster["ctype"],
        "size_bytes": cluster["size_bytes"],
        "started_at": cluster["started_at"],
        "uptime_seconds": cluster["uptime_seconds"],
        "max_connections": cluster["max_connections"],
        "connections": cluster["connections"],
        "replication_role": cluster["replication"]["role"],
        "table_count": len(tables),
        "total_rows": sum(t["row_count"] for t in tables),
    }


def version():
    cluster = _cluster_doc()
    return {"version": cluster["version"], "server_version": cluster["server_version"],
            "server_version_num": cluster["server_version_num"]}


def health():
    return {"status": "ok"}


def health_db():
    cluster = _cluster_doc()
    started = time.perf_counter()
    _db.query_all("SELECT 1")
    lag = max((s["replay_lag_ms"] for s in cluster["replication"]["standbys"]),
              default=0)
    return {"status": "ok", "engine": "postgresql",
            "server_version": cluster["server_version"],
            "database": cluster["database"],
            "connections": cluster["connections"],
            "max_replication_lag_ms": lag,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


_store.eager_load()
