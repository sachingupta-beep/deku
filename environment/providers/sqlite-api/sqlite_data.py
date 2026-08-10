"""Data access module for the SQLite API mock service.

Exposes a real SQLite database over HTTP -- the Orbit Labs field-service
database that the technician tablets sync against. Statements run through
`sql_engine`, which materializes the shared store into an in-memory SQLite
database per request, executes genuine SQL, and syncs writes back to the store
so the admin plane can still drift a row mid-run.

The surface is SQLite-flavoured throughout: `EXPLAIN QUERY PLAN`, PRAGMAs,
`sqlite_master` DDL, `PRAGMA integrity_check`, rowid semantics and WAL settings.
Mutations are held in process memory and reset on restart.
"""

import json
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_float, opt_int, opt_str)

import sql_engine
from sql_engine import SqlError

_store = get_store("sqlite-api")
_API = "sqlite-api"


def _load_database():
    with open(DATA_DIR / "database.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("technicians", primary_key="id",
                initial_loader=lambda: _coerce_technicians(_load("technicians.json", "technicians")))
_store.register("sites", primary_key="id",
                initial_loader=lambda: _coerce_sites(_load("sites.json", "sites")))
_store.register("parts", primary_key="id",
                initial_loader=lambda: _coerce_parts(_load("parts.json", "parts")))
_store.register("work_orders", primary_key="id",
                initial_loader=lambda: _coerce_work_orders(_load("work_orders.json", "work_orders")))
_store.register("work_order_parts", primary_key="id",
                initial_loader=lambda: _coerce_work_order_parts(_load("work_order_parts.json", "work_order_parts")))
_store.register("sync_log", primary_key="id",
                initial_loader=lambda: _coerce_sync_log(_load("sync_log.json", "sync_log")))
_store.register_document("database", initial_loader=_load_database)


def _technicians_rows():
    return _store.table("technicians").rows()


def _sites_rows():
    return _store.table("sites").rows()


def _parts_rows():
    return _store.table("parts").rows()


def _work_orders_rows():
    return _store.table("work_orders").rows()


def _work_order_parts_rows():
    return _store.table("work_order_parts").rows()


def _sync_log_rows():
    return _store.table("sync_log").rows()


def _database_doc():
    return _store.document("database").get()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


# ---------------------------------------------------------------------------
# Load + coerce
#
# Every column is a SQLite scalar: INTEGER, REAL or TEXT. Booleans are stored as
# 0/1 the way SQLite stores them, and empty strings become NULL so the NOT NULL
# and IS NULL semantics in the schema behave as they would in a real database.
# ---------------------------------------------------------------------------

def _null_if_blank(row, column):
    value = opt_str(row, column, default="")
    return value if value else None


def _coerce_technicians(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "active": opt_int(r, "active", default=1)} for r in rows]


def _coerce_sites(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "latitude": opt_float(r, "latitude", default=None),
             "longitude": opt_float(r, "longitude", default=None)} for r in rows]


def _coerce_parts(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "unit_cost_cents": opt_int(r, "unit_cost_cents", default=0),
             "stock_qty": opt_int(r, "stock_qty", default=0),
             "reorder_level": opt_int(r, "reorder_level", default=0)} for r in rows]


def _coerce_work_orders(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "site_id": opt_int(r, "site_id", default=None),
             "technician_id": opt_int(r, "technician_id", default=None),
             "closed_at": _null_if_blank(r, "closed_at"),
             "minutes_spent": opt_int(r, "minutes_spent", default=0),
             "billable": opt_int(r, "billable", default=1)} for r in rows]


def _coerce_work_order_parts(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "work_order_id": opt_int(r, "work_order_id", default=None),
             "part_id": opt_int(r, "part_id", default=None),
             "quantity": opt_int(r, "quantity", default=1),
             "unit_cost_cents": opt_int(r, "unit_cost_cents", default=0)} for r in rows]


def _coerce_sync_log(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "conflict": opt_int(r, "conflict", default=0)} for r in rows]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = [
    """CREATE TABLE technicians (
        id            INTEGER PRIMARY KEY,
        name          TEXT    NOT NULL,
        email         TEXT    NOT NULL UNIQUE,
        region        TEXT    NOT NULL,
        certification TEXT    NOT NULL DEFAULT 'standard',
        active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
        hired_on      TEXT    NOT NULL
    )""",
    """CREATE TABLE sites (
        id        INTEGER PRIMARY KEY,
        name      TEXT NOT NULL,
        customer  TEXT NOT NULL,
        address   TEXT,
        region    TEXT NOT NULL,
        latitude  REAL,
        longitude REAL,
        timezone  TEXT
    )""",
    """CREATE TABLE parts (
        id              INTEGER PRIMARY KEY,
        sku             TEXT    NOT NULL UNIQUE,
        name            TEXT    NOT NULL,
        category        TEXT    NOT NULL,
        unit_cost_cents INTEGER NOT NULL CHECK (unit_cost_cents >= 0),
        stock_qty       INTEGER NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
        reorder_level   INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE work_orders (
        id            INTEGER PRIMARY KEY,
        site_id       INTEGER NOT NULL REFERENCES sites(id),
        technician_id INTEGER REFERENCES technicians(id),
        status        TEXT    NOT NULL CHECK (status IN
                          ('open', 'in_progress', 'on_hold', 'closed', 'cancelled')),
        priority      TEXT    NOT NULL CHECK (priority IN ('P1', 'P2', 'P3', 'P4')),
        summary       TEXT    NOT NULL,
        opened_at     TEXT    NOT NULL,
        closed_at     TEXT,
        minutes_spent INTEGER NOT NULL DEFAULT 0,
        billable      INTEGER NOT NULL DEFAULT 1 CHECK (billable IN (0, 1))
    )""",
    """CREATE TABLE work_order_parts (
        id              INTEGER PRIMARY KEY,
        work_order_id   INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
        part_id         INTEGER NOT NULL REFERENCES parts(id),
        quantity        INTEGER NOT NULL CHECK (quantity > 0),
        unit_cost_cents INTEGER NOT NULL,
        UNIQUE (work_order_id, part_id)
    )""",
    """CREATE TABLE sync_log (
        id         INTEGER PRIMARY KEY,
        table_name TEXT    NOT NULL,
        operation  TEXT    NOT NULL CHECK (operation IN ('insert', 'update', 'delete')),
        row_id     TEXT    NOT NULL,
        direction  TEXT    NOT NULL CHECK (direction IN ('push', 'pull')),
        device_id  TEXT    NOT NULL,
        synced_at  TEXT    NOT NULL,
        conflict   INTEGER NOT NULL DEFAULT 0 CHECK (conflict IN (0, 1))
    )""",
    "CREATE INDEX idx_work_orders_site ON work_orders(site_id)",
    "CREATE INDEX idx_work_orders_status ON work_orders(status, priority)",
    "CREATE INDEX idx_work_order_parts_wo ON work_order_parts(work_order_id)",
    "CREATE INDEX idx_sync_log_synced_at ON sync_log(synced_at DESC)",
    """CREATE VIEW open_work_orders AS
        SELECT w.id, w.priority, w.summary, s.name AS site_name, s.customer,
               t.name AS technician
        FROM work_orders w
        JOIN sites s ON s.id = w.site_id
        LEFT JOIN technicians t ON t.id = w.technician_id
        WHERE w.status IN ('open', 'in_progress', 'on_hold')""",
]

TABLES = {
    "technicians": _technicians_rows,
    "sites": _sites_rows,
    "parts": _parts_rows,
    "work_orders": _work_orders_rows,
    "work_order_parts": _work_order_parts_rows,
    "sync_log": _sync_log_rows,
}

_db = sql_engine.Database("orbit_field", DDL, TABLES, _store)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

# SQLite reports failures as an extended result code plus a message; these are
# the codes the shell and the C API surface for each class of failure.
_SQLITE_CODES = {
    sql_engine.UNIQUE_VIOLATION: ("SQLITE_CONSTRAINT_UNIQUE", 2067, 400),
    sql_engine.FOREIGN_KEY_VIOLATION: ("SQLITE_CONSTRAINT_FOREIGNKEY", 787, 409),
    sql_engine.NOT_NULL_VIOLATION: ("SQLITE_CONSTRAINT_NOTNULL", 1299, 400),
    sql_engine.CHECK_VIOLATION: ("SQLITE_CONSTRAINT_CHECK", 275, 400),
    sql_engine.UNDEFINED_TABLE: ("SQLITE_ERROR", 1, 400),
    sql_engine.UNDEFINED_COLUMN: ("SQLITE_ERROR", 1, 400),
    sql_engine.SYNTAX_ERROR: ("SQLITE_ERROR", 1, 400),
    sql_engine.DATATYPE_MISMATCH: ("SQLITE_MISMATCH", 20, 400),
    sql_engine.FEATURE_NOT_SUPPORTED: ("SQLITE_AUTH", 23, 403),
    sql_engine.INTERNAL_ERROR: ("SQLITE_INTERNAL", 2, 500),
}


def _sql_error(exc):
    code, errno, status = _SQLITE_CODES.get(exc.kind, ("SQLITE_ERROR", 1, 400))
    body = {"error": exc.message, "code": code, "errno": errno,
            "kind": exc.kind, "status": status}
    if exc.statement:
        body["statement"] = exc.statement
    index = getattr(exc, "statement_index", None)
    if index is not None:
        body["statement_index"] = index
    return body


def _error(status, code, message):
    return {"error": message, "code": code, "errno": 0, "kind": code,
            "status": status}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def resolve_access(api_key=None, authorization=None):
    """Map a key onto ('read_write' | 'read_only').

    The read-only key rejects any statement that writes. Any other token grants
    read/write, keeping the fleet convention that any token is accepted.
    """
    token = (api_key or "").strip()
    if not token and authorization:
        raw = str(authorization).strip()
        token = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    keys = _database_doc().get("auth", {})
    if token and token == keys.get("readonly_key"):
        return "read_only"
    return "read_write"


# ---------------------------------------------------------------------------
# Query surface
# ---------------------------------------------------------------------------

def query(sql, params=None, max_rows=1000, access="read_write"):
    """Read-only statement execution."""
    try:
        result = _db.execute(sql, params=params, readonly=True, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result)


def execute(sql, params=None, max_rows=1000, access="read_write"):
    """Statement execution that may write."""
    if access == "read_only" and _db.is_write(sql or ""):
        return _error(403, "SQLITE_READONLY",
                      "attempt to write a readonly database")
    try:
        result = _db.execute(sql, params=params, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result)


def transaction(statements, atomic=True, max_rows=1000, access="read_write"):
    """Run several statements on one connection, atomically by default."""
    if not statements:
        return _error(400, "SQLITE_MISUSE", "no statements supplied")
    if access == "read_only" and any(_db.is_write(s.get("sql") or "")
                                     for s in statements):
        return _error(403, "SQLITE_READONLY",
                      "attempt to write a readonly database")
    try:
        results = _db.execute_many(statements, atomic=atomic, max_rows=max_rows)
    except SqlError as exc:
        body = _sql_error(exc)
        body["rolled_back"] = True
        return body
    envelopes = [_result_envelope(r) for r in results]
    return {"results": envelopes, "statement_count": len(envelopes),
            "failed_count": len([e for e in envelopes if "error" in e]),
            "rolled_back": False}


def _result_envelope(result):
    """The shape a SQLite HTTP service returns: columns, types and value rows.

    A non-atomic batch keeps going after a failure, so an entry may be a
    per-statement error instead of a result set.
    """
    if "error" in result:
        code, errno, _status = _SQLITE_CODES.get(result["error"],
                                                 ("SQLITE_ERROR", 1, 400))
        return {"error": result["message"], "code": code, "errno": errno,
                "kind": result["error"],
                "statement_index": result.get("statement_index")}
    return {
        "columns": result["columns"],
        "types": result["types"],
        "values": result["rows"],
        "row_count": result["row_count"],
        "rows_affected": result["rows_affected"],
        "last_insert_rowid": result["last_insert_id"],
        "statement_type": result["statement_type"],
        "truncated": result["truncated"],
        "time_ms": result["duration_ms"],
        **({"statement_index": result["statement_index"]}
           if "statement_index" in result else {}),
    }


def explain(sql, params=None):
    """`EXPLAIN QUERY PLAN` -- SQLite's plan format, not a cost-based tree."""
    try:
        plan = _db.explain(sql, params=params)
    except SqlError as exc:
        return _sql_error(exc)
    return {"query": sql, "plan": plan,
            "uses_index": any("USING INDEX" in str(step.get("detail", ""))
                              for step in plan),
            "scans": [step["detail"] for step in plan
                      if str(step.get("detail", "")).startswith("SCAN")]}


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------

def list_tables(include_views=True):
    kinds = "('table', 'view')" if include_views else "('table')"
    rows = _db.query_all(
        f"SELECT name, type, sql FROM sqlite_master WHERE type IN {kinds} "
        f"AND name NOT LIKE 'sqlite_%' ORDER BY type, name")
    out = []
    for row in rows:
        entry = {"name": row["name"], "type": row["type"], "sql": row["sql"]}
        if row["type"] == "table":
            entry["row_count"] = _db.query_all(
                f'SELECT COUNT(*) AS n FROM "{row["name"]}"')[0]["n"]
        out.append(entry)
    return {"tables": out, "count": len(out)}


def describe_table(name):
    exists = _db.query_all(
        "SELECT name, type, sql FROM sqlite_master WHERE name = ? "
        "AND type IN ('table', 'view')", [name])
    if not exists:
        return _error(404, "SQLITE_ERROR", f"no such table: {name}")
    columns = _db.query_all(f'PRAGMA table_info("{name}")')
    foreign_keys = _db.query_all(f'PRAGMA foreign_key_list("{name}")')
    indexes = _db.query_all(f'PRAGMA index_list("{name}")')
    for index in indexes:
        index["columns"] = [c["name"] for c in
                            _db.query_all(f'PRAGMA index_info("{index["name"]}")')]
    return {"name": name, "type": exists[0]["type"], "sql": exists[0]["sql"],
            "columns": columns, "foreign_keys": foreign_keys, "indexes": indexes,
            "row_count": _db.query_all(f'SELECT COUNT(*) AS n FROM "{name}"')[0]["n"]
            if exists[0]["type"] == "table" else None}


def list_indexes():
    rows = _db.query_all(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY tbl_name, name")
    for row in rows:
        row["columns"] = [c["name"] for c in
                          _db.query_all(f'PRAGMA index_info("{row["name"]}")')]
    return {"indexes": rows, "count": len(rows)}


def dump_schema():
    rows = _db.query_all(
        "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL "
        "AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 "
        "WHEN 'index' THEN 1 ELSE 2 END, name")
    return {"schema": "\n".join(f"{row['sql']};" for row in rows),
            "objects": [{"type": r["type"], "name": r["name"]} for r in rows]}


# ---------------------------------------------------------------------------
# PRAGMAs and database file
# ---------------------------------------------------------------------------

# Pragmas answered from the seeded database file description rather than from the
# throwaway in-memory database, which would report its own settings.
_FILE_PRAGMAS = {"page_size", "page_count", "freelist_count", "journal_mode",
                 "synchronous", "auto_vacuum", "busy_timeout", "cache_size",
                 "temp_store", "user_version", "application_id", "encoding",
                 "foreign_keys"}

_LIVE_PRAGMAS = {"integrity_check", "quick_check", "foreign_key_check",
                 "table_list", "compile_options", "database_list"}


def pragma(name):
    key = str(name or "").strip().lower()
    document = _database_doc()
    if key in _FILE_PRAGMAS:
        return {"pragma": key, "value": document.get(key), "source": "database_file"}
    if key in _LIVE_PRAGMAS:
        rows = _db.query_all(f"PRAGMA {key}")
        return {"pragma": key, "rows": rows, "source": "live"}
    return _error(400, "SQLITE_ERROR", f"unknown or unsupported pragma: {name}")


def database_info():
    document = _database_doc()
    tables = list_tables(include_views=False)["tables"]
    return {
        "name": document["name"],
        "path": document["path"],
        "sqlite_version": document["sqlite_version"],
        "service_version": document["service_version"],
        "size_bytes": document["page_size"] * document["page_count"],
        "page_size": document["page_size"],
        "page_count": document["page_count"],
        "freelist_count": document["freelist_count"],
        "encoding": document["encoding"],
        "journal_mode": document["journal_mode"],
        "synchronous": document["synchronous"],
        "auto_vacuum": document["auto_vacuum"],
        "foreign_keys": bool(document["foreign_keys"]),
        "user_version": document["user_version"],
        "application_id": document["application_id"],
        "wal": document["wal"],
        "last_backup_at": document["last_backup_at"],
        "table_count": len(tables),
        "total_rows": sum(t["row_count"] for t in tables),
    }


def integrity_check():
    rows = _db.query_all("PRAGMA integrity_check")
    foreign_keys = _db.query_all("PRAGMA foreign_key_check")
    results = [row["integrity_check"] for row in rows]
    return {"integrity_check": results, "ok": results == ["ok"],
            "foreign_key_violations": foreign_keys}


def health():
    return {"status": "ok"}


def health_db():
    document = _database_doc()
    started = time.perf_counter()
    tables = _db.query_all("SELECT COUNT(*) AS n FROM sqlite_master "
                           "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    return {"status": "ok", "engine": "sqlite",
            "sqlite_version": document["sqlite_version"],
            "journal_mode": document["journal_mode"],
            "tables": tables[0]["n"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


_store.eager_load()
