"""Data access module for the CockroachDB API mock service.

Exposes a CockroachDB 23.2 cluster over HTTP -- `orbit_fleet`, the multi-region
device registry. Statements run through `sql_engine`, which materializes the
shared store into an in-memory SQLite database per request, executes genuine
SQL, and syncs writes back so the admin plane can still drift a row mid-run.

CockroachDB speaks the PostgreSQL wire protocol, so the SQLSTATE vocabulary is
shared. What is modelled here is what makes it *distributed*, and each of these
changes behaviour rather than just adding a field:

* **SERIALIZABLE by default, with real retry errors.** A transaction touching a
  contended row fails its first attempt with 40001
  `TransactionRetryWithProtoRefreshError`. Passing `max_retries` runs the retry
  loop a driver would run, and the response reports how many retries it took.
* **`AS OF SYSTEM TIME`.** Historical reads are served from the snapshot taken
  at process start, so a row mutated during a run still reads its original
  value as of an earlier timestamp.
* **Ranges, nodes and regions.** `SHOW RANGES` with lease holders and replica
  localities, `SHOW NODES` with one node deliberately down, and per-table
  localities (`REGIONAL BY ROW`, `GLOBAL`).
"""

import copy
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

_store = get_store("cockroachdb-api")
_API = "cockroachdb-api"


def _load_cluster():
    with open(DATA_DIR / "cluster.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("devices", primary_key="id",
                initial_loader=lambda: _coerce_devices(_load("devices.json", "devices")))
_store.register("device_events", primary_key="id",
                initial_loader=lambda: _coerce_events(_load("device_events.json", "device_events")))
_store.register("firmware_releases", primary_key="version",
                initial_loader=lambda: _coerce_firmware(_load("firmware_releases.json", "firmware_releases")))
_store.register("rollouts", primary_key="id",
                initial_loader=lambda: _coerce_rollouts(_load("rollouts.json", "rollouts")))
_store.register("crdb_nodes", primary_key="node_id",
                initial_loader=lambda: _coerce_nodes(_load("nodes.json", "crdb_nodes")))
_store.register("crdb_ranges", primary_key="range_id",
                initial_loader=lambda: _coerce_ranges(_load("ranges.json", "crdb_ranges")))
_store.register("crdb_jobs", primary_key="job_id",
                initial_loader=lambda: _coerce_jobs(_load("jobs.json", "crdb_jobs")))
_store.register("crdb_users", primary_key="username",
                initial_loader=lambda: _coerce_users(_load("users.json", "crdb_users")))
_store.register("crdb_statement_stats", primary_key="fingerprint_id",
                initial_loader=lambda: _coerce_statement_stats(_load("statement_stats.json", "crdb_statement_stats")))
_store.register_document("cluster", initial_loader=_load_cluster)


def _devices_rows():
    return _store.table("devices").rows()


def _events_rows():
    return _store.table("device_events").rows()


def _firmware_rows():
    return _store.table("firmware_releases").rows()


def _rollouts_rows():
    return _store.table("rollouts").rows()


def _nodes_rows():
    return _store.table("crdb_nodes").rows()


def _ranges_rows():
    return _store.table("crdb_ranges").rows()


def _jobs_rows():
    return _store.table("crdb_jobs").rows()


def _users_rows():
    return _store.table("crdb_users").rows()


def _statement_stats_rows():
    return _store.table("crdb_statement_stats").rows()


def _cluster_doc():
    return _store.document("cluster").get()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _null_if_blank(row, column):
    value = opt_str(row, column, default="")
    return value if value else None


def _semi_list(row, column):
    raw = opt_str(row, column, default="")
    return [part for part in raw.split(";") if part]


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

def _coerce_devices(rows):
    return [{**_strip_ctx(r), "battery_pct": opt_int(r, "battery_pct", default=None)}
            for r in rows]


def _coerce_events(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0)} for r in rows]


def _coerce_firmware(rows):
    return [{**_strip_ctx(r), "size_bytes": opt_int(r, "size_bytes", default=0),
             "yanked": opt_int(r, "yanked", default=0)} for r in rows]


def _coerce_rollouts(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "percent": opt_int(r, "percent", default=0),
             "completed_at": _null_if_blank(r, "completed_at")} for r in rows]


def _coerce_nodes(rows):
    integers = ("node_id", "ranges", "leases", "used_bytes", "capacity_bytes")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers},
             "is_live": bool(opt_int(r, "is_live", default=0)),
             "is_available": bool(opt_int(r, "is_available", default=0)),
             "cpu_percent": opt_float(r, "cpu_percent", default=0.0)} for r in rows]


def _coerce_ranges(rows):
    return [{**_strip_ctx(r), "range_id": opt_int(r, "range_id", default=0),
             "lease_holder": opt_int(r, "lease_holder", default=0),
             "range_size_mb": opt_float(r, "range_size_mb", default=0.0),
             "replicas": [int(v) for v in _semi_list(r, "replicas")],
             "replica_localities": _semi_list(r, "replica_localities"),
             "voting_replicas": [int(v) for v in _semi_list(r, "voting_replicas")],
             "non_voting_replicas": [int(v) for v in _semi_list(r, "non_voting_replicas")]}
            for r in rows]


def _coerce_jobs(rows):
    return [{**_strip_ctx(r),
             "fraction_completed": opt_float(r, "fraction_completed", default=0.0),
             "finished": _null_if_blank(r, "finished"),
             "high_water_timestamp": _null_if_blank(r, "high_water_timestamp"),
             "error": opt_str(r, "error", default="")} for r in rows]


def _coerce_users(rows):
    return [{**_strip_ctx(r), "login": bool(opt_int(r, "login", default=0)),
             "privileges": _semi_list(r, "privileges")} for r in rows]


def _coerce_statement_stats(rows):
    floats = ("service_lat_avg_ms", "service_lat_p99_ms", "rows_avg")
    integers = ("count", "retries")
    return [{**_strip_ctx(r), **{f: opt_float(r, f, default=0.0) for f in floats},
             **{f: opt_int(r, f, default=0) for f in integers},
             "full_scan": bool(opt_int(r, "full_scan", default=0)),
             "distributed": bool(opt_int(r, "distributed", default=0)),
             "implicit_txn": bool(opt_int(r, "implicit_txn", default=0))} for r in rows]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = [
    """CREATE TABLE devices (
        id               uuid        NOT NULL PRIMARY KEY,
        serial           string      NOT NULL UNIQUE,
        customer         string      NOT NULL,
        crdb_region      string      NOT NULL,
        model            string      NOT NULL,
        firmware_version string      NOT NULL REFERENCES firmware_releases(version),
        status           string      NOT NULL CHECK (status IN
                             ('online', 'degraded', 'offline', 'quarantined')),
        enrolled_at      timestamptz NOT NULL,
        last_seen_at     timestamptz,
        battery_pct      int8        CHECK (battery_pct BETWEEN 0 AND 100)
    )""",
    """CREATE TABLE device_events (
        id          int8        NOT NULL PRIMARY KEY,
        device_id   uuid        NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        kind        string      NOT NULL,
        severity    string      NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
        detail      string,
        occurred_at timestamptz NOT NULL
    )""",
    """CREATE TABLE firmware_releases (
        version       string      NOT NULL PRIMARY KEY,
        channel       string      NOT NULL CHECK (channel IN ('stable', 'beta')),
        sha256        string      NOT NULL,
        size_bytes    int8        NOT NULL,
        published_at  timestamptz NOT NULL,
        yanked        bool        NOT NULL DEFAULT false,
        min_hardware  string      NOT NULL
    )""",
    """CREATE TABLE rollouts (
        id               int8        NOT NULL PRIMARY KEY,
        firmware_version string      NOT NULL REFERENCES firmware_releases(version),
        crdb_region      string      NOT NULL,
        percent          int8        NOT NULL CHECK (percent BETWEEN 0 AND 100),
        status           string      NOT NULL CHECK (status IN
                             ('in_progress', 'paused', 'completed', 'rolled_back')),
        started_at       timestamptz NOT NULL,
        completed_at     timestamptz,
        UNIQUE (firmware_version, crdb_region)
    )""",
    "CREATE INDEX idx_devices_region_status ON devices(crdb_region, status)",
    "CREATE INDEX idx_devices_customer ON devices(customer)",
    "CREATE INDEX idx_events_device ON device_events(device_id, occurred_at)",
    "CREATE INDEX idx_events_severity ON device_events(severity, occurred_at)",
    """CREATE VIEW fleet_by_region AS
        SELECT crdb_region, count(*) AS devices,
               sum(CASE WHEN status = 'online' THEN 1 ELSE 0 END) AS online,
               sum(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) AS offline
        FROM devices GROUP BY crdb_region""",
]

TABLES = {
    "devices": _devices_rows,
    "device_events": _events_rows,
    "firmware_releases": _firmware_rows,
    "rollouts": _rollouts_rows,
}


# ---------------------------------------------------------------------------
# Dialect
# ---------------------------------------------------------------------------

_CAST_RE = re.compile(r"::\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?)")
_PLACEHOLDER_RE = re.compile(r"\$\d+")
_AOST_RE = re.compile(r"\bAS\s+OF\s+SYSTEM\s+TIME\s+('[^']*'|[\w.]+\s*\(\s*\))",
                      re.IGNORECASE)

_CAST_TYPES = {"int": "INTEGER", "int2": "INTEGER", "int4": "INTEGER",
               "int8": "INTEGER", "integer": "INTEGER", "bigint": "INTEGER",
               "decimal": "REAL", "float8": "REAL", "numeric": "REAL",
               "string": "TEXT", "text": "TEXT", "varchar": "TEXT", "uuid": "TEXT",
               "date": "TEXT", "timestamptz": "TEXT", "timestamp": "TEXT",
               "jsonb": "TEXT", "bool": "INTEGER", "boolean": "INTEGER"}


def strip_as_of_system_time(sql):
    """Remove the AOST clause and report the timestamp it named."""
    match = _AOST_RE.search(sql or "")
    if not match:
        return sql, None
    return (_AOST_RE.sub("", sql).strip(), match.group(1).strip("'"))


def rewrite(sql):
    """Translate the PostgreSQL/CockroachDB syntax the engine cannot parse."""
    out = []
    for fragment, quoted in _split_preserving_literals(sql):
        if quoted:
            out.append(fragment)
            continue
        fragment = _PLACEHOLDER_RE.sub("?", fragment)
        fragment = re.sub(r"\bILIKE\b", "LIKE", fragment, flags=re.IGNORECASE)
        fragment = re.sub(r"\bnow\s*\(\s*\)", "datetime('now')", fragment,
                          flags=re.IGNORECASE)
        fragment = re.sub(r"\bcurrent_timestamp\b", "datetime('now')", fragment,
                          flags=re.IGNORECASE)
        fragment = re.sub(r"\bIF\s*\(", "IIF(", fragment, flags=re.IGNORECASE)
        while True:
            match = _CAST_RE.search(fragment)
            if not match:
                break
            start = _cast_operand_start(fragment, match.start())
            if start is None:
                fragment = fragment[:match.start()] + " " + fragment[match.end():]
                continue
            operand = fragment[start:match.start()]
            target = _CAST_TYPES.get(
                re.sub(r"\s*\(.*\)$", "", match.group(1)).strip().lower(), "TEXT")
            fragment = (fragment[:start] + f"CAST({operand} AS {target})"
                        + fragment[match.end():])
        out.append(fragment)
    return "".join(out)


def _cast_operand_start(fragment, cast_at):
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


def _split_preserving_literals(sql):
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


def _gen_random_uuid():
    import uuid as _uuid
    return str(_uuid.uuid4())


def _unique_rowid():
    return int(time.time() * 1_000_000) & 0x7FFFFFFFFFFFFFFF


FUNCTIONS = {
    "gen_random_uuid": (0, _gen_random_uuid),
    "unique_rowid": (0, _unique_rowid),
}

_db = sql_engine.Database("orbit_fleet", DDL, TABLES, _store, rewriter=rewrite,
                          functions=FUNCTIONS)

# Historical snapshot for AS OF SYSTEM TIME. Captured once at import, before any
# request can mutate the store, so a time-travel read genuinely differs from the
# live tables after a write.
_HISTORICAL = {}


def _capture_historical():
    for name, loader in TABLES.items():
        _HISTORICAL[name] = copy.deepcopy(loader())


_historical_db = sql_engine.Database(
    "orbit_fleet@historical", DDL,
    {name: (lambda n=name: copy.deepcopy(_HISTORICAL.get(n, []))) for name in TABLES},
    _store, rewriter=rewrite, functions=FUNCTIONS)


# ---------------------------------------------------------------------------
# Errors
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
_NO_TABLE_TARGET = re.compile(r"no such table: (\S+)")
_NO_COLUMN_TARGET = re.compile(r"no such column: (\S+)")


def _sql_error(exc):
    code, condition, status = _SQLSTATE.get(exc.kind, ("XX000", "internal_error", 500))
    message = exc.message
    unique = _UNIQUE_TARGET.search(exc.message)
    missing_table = _NO_TABLE_TARGET.search(exc.message)
    missing_column = _NO_COLUMN_TARGET.search(exc.message)
    if unique:
        targets = [t.strip() for t in unique.group(1).split(",")]
        table = targets[0].split(".")[0]
        columns = [t.split(".")[1] for t in targets if "." in t]
        constraint = "primary" if columns == ["id"] else f"{table}_{'_'.join(columns)}_key"
        message = (f'duplicate key value violates unique constraint "{constraint}"')
    elif exc.kind == sql_engine.FOREIGN_KEY_VIOLATION:
        message = "insert or update violates foreign key constraint"
    elif missing_table:
        message = f'relation "{missing_table.group(1)}" does not exist'
    elif missing_column:
        message = f'column "{missing_column.group(1)}" does not exist'

    body = {"error": message, "severity": "ERROR", "code": code, "sqlstate": code,
            "condition": condition, "message": message, "status": status}
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


def _retry_error(attempt, contended):
    """The 40001 a serializable transaction gets when it loses a race."""
    return {
        "error": "restart transaction: TransactionRetryWithProtoRefreshError: "
                 "TransactionRetryError: retry txn (RETRY_SERIALIZABLE - "
                 "failed preemptive refresh)",
        "severity": "ERROR", "code": "40001", "sqlstate": "40001",
        "condition": "serialization_failure",
        "message": "restart transaction: TransactionRetryWithProtoRefreshError: "
                   "TransactionRetryError: retry txn (RETRY_SERIALIZABLE)",
        "status": 409,
        "hint": "The transaction must be retried by the client. Re-send it with "
                "max_retries set, or implement a retry loop keyed on SQLSTATE 40001.",
        "detail": {"attempt": attempt, "contended_rows": contended,
                   "isolation_level": "SERIALIZABLE"},
        "retryable": True,
    }


# ---------------------------------------------------------------------------
# Users and privileges
# ---------------------------------------------------------------------------

_TABLE_REF = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+([\"\w.]+)", re.IGNORECASE)

_WRITE_PRIVILEGE = {"insert": "INSERT", "update": "UPDATE", "delete": "DELETE",
                    "upsert": "INSERT", "replace": "INSERT"}


def resolve_user(crdb_user=None, authorization=None):
    name = (crdb_user or "").strip()
    if not name and authorization:
        raw = str(authorization).strip()
        name = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    row = _store.table("crdb_users").get(name) if name else None
    if row:
        return row["username"]
    return _cluster_doc()["auth"]["default_user"]


def _account(user):
    return _store.table("crdb_users").get(user)


def check_privileges(sql, user):
    account = _account(user)
    if account and not account["login"]:
        return _error(403, "28000", "invalid_authorization_specification",
                      f'user {user} does not have login privilege')
    if not account:
        return None
    if "ALL" in account["privileges"]:
        return None
    required = _WRITE_PRIVILEGE.get(sql_engine._statement_type(sql or ""), "SELECT")
    for table in _referenced_tables(sql):
        if required not in account["privileges"]:
            return _error(403, "42501", "insufficient_privilege",
                          f'user {user} does not have {required} privilege on '
                          f'relation {table}', table=table)
    return None


def _referenced_tables(sql):
    names = set()
    for match in _TABLE_REF.finditer(sql or ""):
        name = match.group(1).strip('"').split(".")[-1].lower()
        if name in TABLES:
            names.add(name)
    return names


# ---------------------------------------------------------------------------
# Contention
# ---------------------------------------------------------------------------

def _contended_rows(statements):
    """Which seeded hot rows this batch touches."""
    contention = _cluster_doc().get("contention", {})
    hits = []
    for entry in statements:
        text = (entry.get("sql") or "")
        if not _db.is_write(text):
            continue
        for table, keys in contention.items():
            if table == "note" or table not in _referenced_tables(text):
                continue
            for key in keys:
                if key in text:
                    hits.append({"table": table, "key": key})
    return hits


# ---------------------------------------------------------------------------
# Query surface
# ---------------------------------------------------------------------------

def query(sql, params=None, max_rows=1000, as_of_system_time=None,
          user="orbit_app"):
    denied = check_privileges(sql, user)
    if denied:
        return denied
    statement, inline_aost = strip_as_of_system_time(sql)
    aost = as_of_system_time or inline_aost
    engine = _historical_db if aost else _db
    try:
        result = engine.execute(statement, params=params, readonly=True,
                                max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    envelope = _result_envelope(result, user)
    if aost:
        envelope["as_of_system_time"] = aost
        envelope["read_type"] = "historical"
        envelope["note"] = ("historical reads are served from the snapshot taken "
                            "when the process started")
    return envelope


def execute(sql, params=None, max_rows=1000, user="orbit_app"):
    denied = check_privileges(sql, user)
    if denied:
        return denied
    statement, aost = strip_as_of_system_time(sql)
    if aost and _db.is_write(statement):
        return _error(400, "0A000", "feature_not_supported",
                      "AS OF SYSTEM TIME is only supported for reads")
    try:
        result = _db.execute(statement, params=params, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result, user)


_PRIORITIES = ("LOW", "NORMAL", "HIGH")


def transaction(statements, priority="NORMAL", max_retries=0, user="orbit_app"):
    """Serializable by default, with the retry behaviour that implies.

    A batch touching a contended row fails its first attempt with 40001. That is
    not a simulation detail an agent can ignore -- CockroachDB clients are
    expected to retry, so `max_retries` runs the loop and reports the count.
    """
    if not statements:
        return _error(400, "42601", "syntax_error", "no statements supplied")
    if str(priority).upper() not in _PRIORITIES:
        return _error(400, "0A000", "feature_not_supported",
                      f'invalid transaction priority "{priority}"',
                      hint="Valid priorities: LOW, NORMAL, HIGH")
    for entry in statements:
        denied = check_privileges(entry.get("sql"), user)
        if denied:
            return denied

    contended = _contended_rows(statements)
    attempts = 0
    if contended:
        # The first attempt always loses the race; each retry consumes one budget.
        attempts = 1
        if int(max_retries or 0) < 1:
            return _retry_error(attempts, contended)
        attempts += 1

    try:
        results = _db.execute_many(statements, atomic=True)
    except SqlError as exc:
        body = _sql_error(exc)
        body["rolled_back"] = True
        return body
    return {"results": [_result_envelope(r, user) for r in results],
            "statement_count": len(results),
            "isolation_level": "SERIALIZABLE",
            "priority": str(priority).upper(),
            "retries": max(attempts - 1, 0),
            "contended_rows": contended,
            "rolled_back": False, "committed": True}


def _result_envelope(result, user):
    return {
        "command": result["statement_type"].upper(),
        "columns": [{"name": name, "type": _crdb_type(kind)}
                    for name, kind in zip(result["columns"], result["types"])],
        "rows": [dict(zip(result["columns"], row)) for row in result["rows"]],
        "row_count": result["row_count"],
        "rows_affected": result["rows_affected"],
        "truncated": result["truncated"],
        "duration_ms": result["duration_ms"],
        "user": user,
        **({"statement_index": result["statement_index"]}
           if "statement_index" in result else {}),
    }


_CRDB_TYPES = {"integer": "INT8", "real": "DECIMAL", "text": "STRING",
               "null": "NULL", "blob": "BYTES"}


def _crdb_type(kind):
    return _CRDB_TYPES.get(kind, "STRING")


# ---------------------------------------------------------------------------
# EXPLAIN
# ---------------------------------------------------------------------------

def explain(sql, analyze=False, verbose=False, user="orbit_app"):
    denied = check_privileges(sql, user)
    if denied:
        return denied
    statement, _ = strip_as_of_system_time(sql)
    try:
        steps = _db.explain(statement)
        measured = len(_db.query_all(rewrite(statement))) if analyze else None
    except SqlError as exc:
        return _sql_error(exc)
    plan = []
    distributed = False
    for step in steps:
        detail = str(step.get("detail", ""))
        index = _index_name(detail)
        table = _relation(detail)
        node = {"operator": "scan", "table": table,
                "spans": "FULL SCAN" if detail.startswith("SCAN") else "1 span",
                "index": index or (f"{table}@primary" if table else None),
                "estimated_row_count": measured if analyze else 100}
        if detail.startswith("SCAN"):
            distributed = True
            node["warning"] = "full scan"
        if analyze:
            node["actual_row_count"] = measured
            node["execution_time_ms"] = 0.412
            node["kv_rows_read"] = measured
            node["kv_bytes_read"] = (measured or 0) * 128
        if verbose:
            node["columns"] = "all"
            node["ordering"] = "+id"
        plan.append(node)
    return {"plan": plan,
            "distribution": "full" if distributed else "local",
            "vectorized": True,
            "planning_time_ms": 0.184,
            **({"execution_time_ms": 0.412, "max_memory_used_kb": 20,
                "network_bytes_sent": 0} if analyze else {})}


def _index_name(detail):
    match = re.search(r"USING (?:COVERING )?INDEX (\w+)", detail)
    return match.group(1) if match else None


def _relation(detail):
    match = re.search(r"(?:SCAN|SEARCH) (\w+)", detail)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Cluster surface
# ---------------------------------------------------------------------------

def list_databases():
    cluster = _cluster_doc()
    return {"databases": ["defaultdb", "postgres", "system", cluster["database"]],
            "current": cluster["database"]}


def list_tables():
    cluster = _cluster_doc()
    localities = cluster["table_localities"]
    rows = _db.query_all(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY type, name")
    out = []
    for row in rows:
        entry = {"database_name": cluster["database"], "schema_name": "public",
                 "table_name": row["name"],
                 "type": "table" if row["type"] == "table" else "view",
                 "locality": localities.get(row["name"])}
        if row["type"] == "table":
            entry["estimated_row_count"] = _db.query_all(
                f'SELECT COUNT(*) AS n FROM "{row["name"]}"')[0]["n"]
            entry["ranges"] = len([r for r in _ranges_rows()
                                   if r["table_name"] == row["name"]])
        out.append(entry)
    return {"tables": out, "count": len(out)}


def describe_table(name):
    exists = _db.query_all(
        "SELECT name, type, sql FROM sqlite_master WHERE name = ? "
        "AND type IN ('table', 'view')", [name])
    if not exists:
        return _error(404, "42P01", "undefined_table",
                      f'relation "{name}" does not exist', table=name)
    columns = []
    for column in _db.query_all(f'PRAGMA table_info("{name}")'):
        columns.append({"column_name": column["name"],
                        "data_type": (column["type"] or "string").lower(),
                        "is_nullable": not (column["notnull"] or column["pk"]),
                        "column_default": column["dflt_value"],
                        "is_hidden": False})
    indexes = []
    for index in _db.query_all(f'PRAGMA index_list("{name}")'):
        indexes.append({"index_name": index["name"], "unique": bool(index["unique"]),
                        "columns": [c["name"] for c in
                                    _db.query_all(f'PRAGMA index_info("{index["name"]}")')]})
    cluster = _cluster_doc()
    return {"database_name": cluster["database"], "schema_name": "public",
            "table_name": name, "create_statement": exists[0]["sql"],
            "locality": cluster["table_localities"].get(name),
            "columns": columns, "indexes": indexes,
            "foreign_keys": [
                {"column": c["from"], "references_table": c["table"],
                 "references_column": c["to"], "on_delete": c["on_delete"]}
                for c in _db.query_all(f'PRAGMA foreign_key_list("{name}")')],
            "ranges": len([r for r in _ranges_rows() if r["table_name"] == name])}


def show_ranges(table=None):
    rows = _ranges_rows()
    if table:
        if table not in TABLES:
            return _error(404, "42P01", "undefined_table",
                          f'relation "{table}" does not exist', table=table)
        rows = [r for r in rows if r["table_name"] == table]
    return {"ranges": rows, "count": len(rows),
            "total_size_mb": round(sum(r["range_size_mb"] for r in rows), 1)}


def show_nodes():
    rows = _nodes_rows()
    dead = [n for n in rows if not n["is_live"]]
    return {"nodes": rows, "count": len(rows),
            "live_count": len(rows) - len(dead),
            "dead_nodes": [n["node_id"] for n in dead]}


def show_regions():
    cluster = _cluster_doc()
    nodes = _nodes_rows()
    regions = []
    for region in cluster["regions"]:
        members = [n for n in nodes if f"region={region['region']}" in n["locality"]]
        regions.append({**region,
                        "live_nodes": len([n for n in members if n["is_live"]]),
                        "node_ids": [n["node_id"] for n in members]})
    return {"regions": regions, "primary_region": cluster["primary_region"],
            "survival_goal": cluster["survival_goal"], "count": len(regions)}


def show_jobs(status=None, job_type=None):
    rows = _jobs_rows()
    if status:
        rows = [j for j in rows if j["status"] == status]
    if job_type:
        rows = [j for j in rows if j["job_type"] == job_type.upper()]
    rows.sort(key=lambda j: j["created"], reverse=True)
    return {"jobs": rows, "count": len(rows)}


def cluster_settings(name=None):
    settings = _cluster_doc()["settings"]
    if name:
        match = next((s for s in settings if s["variable"] == name), None)
        if not match:
            return _error(404, "42704", "undefined_object",
                          f'unknown cluster setting "{name}"')
        return match
    return {"settings": settings, "count": len(settings)}


def cluster_status():
    cluster = _cluster_doc()
    nodes = _nodes_rows()
    ranges = _ranges_rows()
    return {"cluster_id": cluster["cluster_id"], "cluster_name": cluster["cluster_name"],
            "version": cluster["version"], "server_version": cluster["server_version"],
            "license_type": cluster["license_type"], "database": cluster["database"],
            "primary_region": cluster["primary_region"],
            "survival_goal": cluster["survival_goal"],
            "regions": len(cluster["regions"]),
            "nodes": len(nodes),
            "live_nodes": len([n for n in nodes if n["is_live"]]),
            "ranges": len(ranges),
            "total_range_size_mb": round(sum(r["range_size_mb"] for r in ranges), 1),
            "used_bytes": sum(n["used_bytes"] for n in nodes),
            "capacity_bytes": sum(n["capacity_bytes"] for n in nodes),
            "default_isolation_level": "SERIALIZABLE"}


def statement_statistics(order_by="count", limit=10):
    allowed = {"count", "service_lat_avg_ms", "service_lat_p99_ms", "retries",
               "rows_avg"}
    if order_by not in allowed:
        return _error(400, "42703", "undefined_column",
                      f'column "{order_by}" does not exist',
                      hint="Available columns: " + ", ".join(sorted(allowed)))
    rows = sorted(_statement_stats_rows(), key=lambda r: r[order_by], reverse=True)
    return {"statements": rows[:int(limit)], "count": len(rows),
            "order_by": order_by}


def list_users():
    return {"users": [{k: v for k, v in u.items() if k != "privileges"}
                      for u in _users_rows()], "count": len(_users_rows())}


def show_grants(user=None):
    rows = _users_rows()
    if user:
        rows = [u for u in rows if u["username"] == user]
        if not rows:
            return _error(404, "42704", "undefined_object",
                          f'role/user "{user}" does not exist')
    cluster = _cluster_doc()
    grants = []
    for row in rows:
        for privilege in row["privileges"]:
            grants.append({"database_name": cluster["database"],
                           "schema_name": "public", "grantee": row["username"],
                           "privilege_type": privilege})
    return {"grants": grants, "count": len(grants)}


def version():
    cluster = _cluster_doc()
    return {"version": cluster["version"], "server_version": cluster["server_version"],
            "cluster_id": cluster["cluster_id"], "license_type": cluster["license_type"]}


def health():
    return {"status": "ok"}


def health_db():
    cluster = _cluster_doc()
    nodes = _nodes_rows()
    started = time.perf_counter()
    _db.query_all("SELECT 1")
    dead = [n["node_id"] for n in nodes if not n["is_live"]]
    return {"status": "ok" if not dead else "degraded",
            "engine": "cockroachdb", "server_version": cluster["server_version"],
            "database": cluster["database"],
            "nodes_live": len(nodes) - len(dead), "nodes_total": len(nodes),
            "dead_nodes": dead,
            "survival_goal": cluster["survival_goal"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


_store.eager_load()
_capture_historical()
