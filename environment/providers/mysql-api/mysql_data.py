"""Data access module for the MySQL API mock service.

Exposes a MySQL 8 database over HTTP -- `orbit_shop`, the storefront behind the
Orbit Labs self-serve shop. Statements run through `sql_engine`, which
materializes the shared store into an in-memory SQLite database per request,
executes genuine SQL, and syncs writes back so the admin plane can still drift a
row mid-run.

Everything above the engine is MySQL: vendor error numbers alongside SQLSTATE,
`SHOW`-style metadata (tables, columns, indexes, variables, status, processlist,
engines, replica status), `information_schema.TABLES` with engine/row/length
columns, `EXPLAIN` in the traditional column format or as JSON, and
`'user'@'host'` accounts with per-table grants.

MySQL functions SQLite lacks are registered on every connection rather than
rewritten, so `CONCAT`, `DATE_FORMAT`, `UNIX_TIMESTAMP` and friends behave.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

import sql_engine
from sql_engine import SqlError

_store = get_store("mysql-api")
_API = "mysql-api"


def _load_server_info():
    with open(DATA_DIR / "server_info.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("customers", primary_key="id",
                initial_loader=lambda: _coerce_customers(_load("customers.json", "customers")))
_store.register("products", primary_key="id",
                initial_loader=lambda: _coerce_products(_load("products.json", "products")))
_store.register("inventory", primary_key="product_id",
                initial_loader=lambda: _coerce_inventory(_load("inventory.json", "inventory")))
_store.register("orders", primary_key="id",
                initial_loader=lambda: _coerce_orders(_load("orders.json", "orders")))
_store.register("order_items", primary_key="id",
                initial_loader=lambda: _coerce_order_items(_load("order_items.json", "order_items")))
_store.register("shipments", primary_key="id",
                initial_loader=lambda: _coerce_shipments(_load("shipments.json", "shipments")))
_store.register("mysql_user", primary_key="user",
                initial_loader=lambda: _coerce_users(_load("users.json", "mysql_user")))
_store.register("table_grants", primary_key="id",
                initial_loader=lambda: _coerce_grants(_load("table_grants.json", "table_grants")))
_store.register("processlist", primary_key="id",
                initial_loader=lambda: _coerce_processlist(_load("processlist.json", "processlist")))
_store.register_document("server_info", initial_loader=_load_server_info)


def _customers_rows():
    return _store.table("customers").rows()


def _products_rows():
    return _store.table("products").rows()


def _inventory_rows():
    return _store.table("inventory").rows()


def _orders_rows():
    return _store.table("orders").rows()


def _order_items_rows():
    return _store.table("order_items").rows()


def _shipments_rows():
    return _store.table("shipments").rows()


def _users_rows():
    return _store.table("mysql_user").rows()


def _grants_rows():
    return _store.table("table_grants").rows()


def _processlist_rows():
    return _store.table("processlist").rows()


def _server_info():
    return _store.document("server_info").get()


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

def _coerce_customers(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "marketing_opt_in": opt_int(r, "marketing_opt_in", default=0),
             "vat_number": _null_if_blank(r, "vat_number"),
             "last_order_at": _null_if_blank(r, "last_order_at")} for r in rows]


def _coerce_products(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "price_cents": opt_int(r, "price_cents", default=0),
             "weight_grams": opt_int(r, "weight_grams", default=0),
             "active": opt_int(r, "active", default=1)} for r in rows]


def _coerce_inventory(rows):
    return [{**_strip_ctx(r), "product_id": opt_int(r, "product_id", default=0),
             "on_hand": opt_int(r, "on_hand", default=0),
             "reserved": opt_int(r, "reserved", default=0),
             "reorder_point": opt_int(r, "reorder_point", default=0)} for r in rows]


def _coerce_orders(rows):
    integers = ("id", "customer_id", "subtotal_cents", "shipping_cents",
                "tax_cents", "total_cents")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers},
             "payment_reference": _null_if_blank(r, "payment_reference")}
            for r in rows]


def _coerce_order_items(rows):
    integers = ("id", "order_id", "product_id", "quantity", "unit_price_cents",
                "discount_cents")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers}}
            for r in rows]


def _coerce_shipments(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "order_id": opt_int(r, "order_id", default=0),
             "delivered_at": _null_if_blank(r, "delivered_at")} for r in rows]


def _coerce_users(rows):
    return [{**_strip_ctx(r), "account_locked": opt_int(r, "account_locked", default=0),
             "max_connections": opt_int(r, "max_connections", default=0),
             "privileges": [p for p in opt_str(r, "privileges", default="").split(";") if p]}
            for r in rows]


def _coerce_grants(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "privileges": [p for p in opt_str(r, "privileges", default="").split(";") if p]}
            for r in rows]


def _coerce_processlist(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "time": opt_int(r, "time", default=0)} for r in rows]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = [
    """CREATE TABLE customers (
        id               int          NOT NULL PRIMARY KEY,
        email            varchar(255) NOT NULL UNIQUE,
        name             varchar(255) NOT NULL,
        country          char(2)      NOT NULL,
        vat_number       varchar(32),
        marketing_opt_in tinyint      NOT NULL DEFAULT 0,
        created_at       datetime     NOT NULL,
        last_order_at    datetime
    )""",
    """CREATE TABLE products (
        id           int          NOT NULL PRIMARY KEY,
        sku          varchar(32)  NOT NULL UNIQUE,
        name         varchar(255) NOT NULL,
        category     varchar(32)  NOT NULL,
        price_cents  int          NOT NULL CHECK (price_cents >= 0),
        weight_grams int          NOT NULL DEFAULT 0,
        active       tinyint      NOT NULL DEFAULT 1,
        created_at   datetime     NOT NULL
    )""",
    """CREATE TABLE inventory (
        product_id    int         NOT NULL PRIMARY KEY REFERENCES products(id)
                                  ON DELETE CASCADE,
        warehouse     varchar(16) NOT NULL,
        on_hand       int         NOT NULL DEFAULT 0 CHECK (on_hand >= 0),
        reserved      int         NOT NULL DEFAULT 0 CHECK (reserved >= 0),
        reorder_point int         NOT NULL DEFAULT 0,
        updated_at    datetime    NOT NULL
    )""",
    """CREATE TABLE orders (
        id                int         NOT NULL PRIMARY KEY,
        customer_id       int         NOT NULL REFERENCES customers(id),
        status            varchar(16) NOT NULL CHECK (status IN
                              ('pending', 'processing', 'shipped', 'delivered',
                               'cancelled', 'refunded')),
        currency          char(3)     NOT NULL,
        subtotal_cents    int         NOT NULL DEFAULT 0,
        shipping_cents    int         NOT NULL DEFAULT 0,
        tax_cents         int         NOT NULL DEFAULT 0,
        total_cents       int         NOT NULL DEFAULT 0,
        placed_at         datetime    NOT NULL,
        payment_reference varchar(64),
        notes             text
    )""",
    """CREATE TABLE order_items (
        id               int NOT NULL PRIMARY KEY,
        order_id         int NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        product_id       int NOT NULL REFERENCES products(id),
        quantity         int NOT NULL CHECK (quantity > 0),
        unit_price_cents int NOT NULL,
        discount_cents   int NOT NULL DEFAULT 0,
        UNIQUE (order_id, product_id)
    )""",
    """CREATE TABLE shipments (
        id              int          NOT NULL PRIMARY KEY,
        order_id        int          NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        carrier         varchar(32)  NOT NULL,
        tracking_number varchar(64)  NOT NULL UNIQUE,
        status          varchar(16)  NOT NULL CHECK (status IN
                            ('label_created', 'in_transit', 'delivered', 'returned')),
        shipped_at      datetime     NOT NULL,
        delivered_at    datetime
    )""",
    "CREATE INDEX idx_orders_customer ON orders(customer_id)",
    "CREATE INDEX idx_orders_status ON orders(status, placed_at)",
    "CREATE INDEX idx_order_items_order ON order_items(order_id)",
    "CREATE INDEX idx_order_items_product ON order_items(product_id)",
    "CREATE INDEX idx_shipments_order ON shipments(order_id)",
    """CREATE VIEW order_totals AS
        SELECT o.id AS order_id, c.name AS customer, o.status, o.currency,
               COUNT(i.id) AS line_items,
               SUM(i.quantity * i.unit_price_cents - i.discount_cents) AS computed_cents,
               o.total_cents
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        LEFT JOIN order_items i ON i.order_id = o.id
        GROUP BY o.id""",
]

TABLES = {
    "customers": _customers_rows,
    "products": _products_rows,
    "inventory": _inventory_rows,
    "orders": _orders_rows,
    "order_items": _order_items_rows,
    "shipments": _shipments_rows,
}


# ---------------------------------------------------------------------------
# MySQL functions and dialect rewriting
# ---------------------------------------------------------------------------

def _mysql_concat(*args):
    return None if any(a is None for a in args) else "".join(str(a) for a in args)


def _mysql_concat_ws(separator, *args):
    if separator is None:
        return None
    return str(separator).join(str(a) for a in args if a is not None)


def _mysql_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _mysql_curdate():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _mysql_unix_timestamp(value=None):
    if value is None:
        return int(time.time())
    try:
        return int(datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
                   .replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


_DATE_FORMAT_MAP = [("%Y", "%Y"), ("%y", "%y"), ("%m", "%m"), ("%d", "%d"),
                    ("%H", "%H"), ("%i", "%M"), ("%s", "%S"), ("%S", "%S"),
                    ("%M", "%B"), ("%b", "%b"), ("%W", "%A"), ("%a", "%a"),
                    ("%j", "%j"), ("%p", "%p")]


def _mysql_date_format(value, spec):
    if value is None or spec is None:
        return None
    try:
        parsed = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            parsed = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    out = str(spec)
    for mysql_token, python_token in _DATE_FORMAT_MAP:
        out = out.replace(mysql_token, parsed.strftime(python_token))
    return out


def _mysql_year(value):
    return int(str(value)[:4]) if value else None


def _mysql_month(value):
    return int(str(value)[5:7]) if value else None


def _mysql_locate(needle, haystack, start=1):
    if needle is None or haystack is None:
        return None
    index = str(haystack).find(str(needle), max(int(start) - 1, 0))
    return index + 1


def _mysql_greatest(*args):
    values = [a for a in args if a is not None]
    return max(values) if values else None


def _mysql_least(*args):
    values = [a for a in args if a is not None]
    return min(values) if values else None


# MySQL builtins SQLite either lacks or spells differently, registered on every
# connection so a statement written for MySQL runs unchanged.
FUNCTIONS = {
    "CONCAT": (-1, _mysql_concat),
    "CONCAT_WS": (-1, _mysql_concat_ws),
    "NOW": (0, _mysql_now),
    "CURDATE": (0, _mysql_curdate),
    "UNIX_TIMESTAMP": (-1, _mysql_unix_timestamp),
    "DATE_FORMAT": (2, _mysql_date_format),
    "YEAR": (1, _mysql_year),
    "MONTH": (1, _mysql_month),
    "LOCATE": (-1, _mysql_locate),
    "GREATEST": (-1, _mysql_greatest),
    "LEAST": (-1, _mysql_least),
}


def rewrite(sql):
    """Translate the MySQL-only syntax the engine cannot parse as written.

    Backtick identifiers and `LIMIT offset, count` are already accepted, and the
    MySQL functions above are registered rather than rewritten, so the surface
    left to translate is small: `IF()` (a keyword in SQLite) becomes `IIF()`, and
    the MySQL-specific `<=>` null-safe equality becomes `IS`.
    """
    out = []
    for fragment, quoted in _split_preserving_literals(sql):
        if quoted:
            out.append(fragment)
            continue
        fragment = re.sub(r"\bIF\s*\(", "IIF(", fragment, flags=re.IGNORECASE)
        fragment = fragment.replace("<=>", " IS ")
        out.append(fragment)
    return "".join(out)


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
        if char in ("'", '"', "`"):
            if buffer:
                parts.append((buffer, False))
            buffer, quote = char, char
            continue
        buffer += char
    if buffer:
        parts.append((buffer, quote is not None))
    return parts


_db = sql_engine.Database("orbit_shop", DDL, TABLES, _store, rewriter=rewrite,
                          functions=FUNCTIONS)


# ---------------------------------------------------------------------------
# Errors -- MySQL error numbers plus SQLSTATE
# ---------------------------------------------------------------------------

_MYSQL_ERRORS = {
    sql_engine.UNIQUE_VIOLATION: (1062, "23000", "ER_DUP_ENTRY", 409),
    sql_engine.FOREIGN_KEY_VIOLATION: (1452, "23000", "ER_NO_REFERENCED_ROW_2", 409),
    sql_engine.NOT_NULL_VIOLATION: (1048, "23000", "ER_BAD_NULL_ERROR", 400),
    sql_engine.CHECK_VIOLATION: (3819, "HY000", "ER_CHECK_CONSTRAINT_VIOLATED", 400),
    sql_engine.UNDEFINED_TABLE: (1146, "42S02", "ER_NO_SUCH_TABLE", 404),
    sql_engine.UNDEFINED_COLUMN: (1054, "42S22", "ER_BAD_FIELD_ERROR", 400),
    sql_engine.SYNTAX_ERROR: (1064, "42000", "ER_PARSE_ERROR", 400),
    sql_engine.DATATYPE_MISMATCH: (1366, "HY000", "ER_TRUNCATED_WRONG_VALUE", 400),
    sql_engine.FEATURE_NOT_SUPPORTED: (1235, "42000", "ER_NOT_SUPPORTED_YET", 403),
    sql_engine.INTERNAL_ERROR: (1105, "HY000", "ER_UNKNOWN_ERROR", 500),
}

_UNIQUE_TARGET = re.compile(r"UNIQUE constraint failed: ([\w.]+(?:, [\w.]+)*)")
_NOT_NULL_TARGET = re.compile(r"NOT NULL constraint failed: (\w+)\.(\w+)")
_NO_TABLE_TARGET = re.compile(r"no such table: (\S+)")
_NO_COLUMN_TARGET = re.compile(r"no such column: (\S+)")


def _sql_error(exc):
    errno, sqlstate, name, status = _MYSQL_ERRORS.get(
        exc.kind, (1105, "HY000", "ER_UNKNOWN_ERROR", 500))
    message = exc.message
    database = _server_info()["database"]

    unique = _UNIQUE_TARGET.search(exc.message)
    not_null = _NOT_NULL_TARGET.search(exc.message)
    missing_table = _NO_TABLE_TARGET.search(exc.message)
    missing_column = _NO_COLUMN_TARGET.search(exc.message)
    if unique:
        targets = [t.strip() for t in unique.group(1).split(",")]
        table = targets[0].split(".")[0]
        columns = [t.split(".")[1] for t in targets if "." in t]
        key = "PRIMARY" if columns == ["id"] else "_".join(columns)
        message = f"Duplicate entry for key '{table}.{key}'"
    elif exc.kind == sql_engine.FOREIGN_KEY_VIOLATION:
        message = ("Cannot add or update a child row: a foreign key constraint "
                   "fails")
    elif not_null:
        message = f"Column '{not_null.group(2)}' cannot be null"
    elif missing_table:
        message = f"Table '{database}.{missing_table.group(1)}' doesn't exist"
    elif missing_column:
        message = f"Unknown column '{missing_column.group(1)}' in 'field list'"
    elif exc.kind == sql_engine.SYNTAX_ERROR:
        message = (f"You have an error in your SQL syntax; check the manual that "
                   f"corresponds to your MySQL server version. {exc.message}")

    body = {"error": message, "errno": errno, "sqlstate": sqlstate,
            "error_name": name, "message": message, "status": status}
    if exc.statement:
        body["statement"] = exc.statement
    index = getattr(exc, "statement_index", None)
    if index is not None:
        body["statement_index"] = index
    return body


def _error(status, errno, sqlstate, name, message, **fields):
    body = {"error": message, "errno": errno, "sqlstate": sqlstate,
            "error_name": name, "message": message, "status": status}
    body.update({k: v for k, v in fields.items() if v is not None})
    return body


# ---------------------------------------------------------------------------
# Accounts and grants
# ---------------------------------------------------------------------------

_TABLE_REF = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+([`\"\w.]+)", re.IGNORECASE)

_WRITE_PRIVILEGE = {"insert": "INSERT", "update": "UPDATE", "delete": "DELETE",
                    "replace": "INSERT"}


def resolve_user(mysql_user=None, authorization=None):
    """Map the `X-MySQL-User` header (or a bearer token) onto an account.

    An unknown or absent user falls back to the server's default account, so a
    request is never rejected purely for lacking a credential.
    """
    name = (mysql_user or "").strip()
    if not name and authorization:
        raw = str(authorization).strip()
        name = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    name = name.split("@")[0]
    row = _store.table("mysql_user").get(name) if name else None
    if row:
        return row["user"]
    return _server_info()["auth"]["default_user"]


def _account(user):
    return _store.table("mysql_user").get(user)


def _privileges(user, table):
    account = _account(user)
    if not account:
        return set()
    if account["account_locked"]:
        return set()
    specific = _store.table("table_grants").find_one(
        lambda g: g["grantee"] == user and g["table_name"] == table)
    if specific:
        return set(specific["privileges"])
    # No table-level grant row means the account's database-wide grant applies,
    # unless the account is one that only holds table grants.
    if any(g["grantee"] == user for g in _grants_rows()):
        return set()
    return set(account["privileges"])


def _referenced_tables(sql):
    names = set()
    for match in _TABLE_REF.finditer(sql or ""):
        name = match.group(1).strip('`"').split(".")[-1].lower()
        if name in TABLES:
            names.add(name)
    return names


def check_privileges(sql, user):
    account = _account(user)
    if account and account["account_locked"]:
        return _error(403, 3118, "HY000", "ER_ACCOUNT_HAS_BEEN_LOCKED",
                      f"Access denied for user '{user}'@'{account['host']}'. "
                      f"Account is locked.")
    database = _server_info()["database"]
    required = _WRITE_PRIVILEGE.get(sql_engine._statement_type(sql or ""), "SELECT")
    for table in _referenced_tables(sql):
        if required not in _privileges(user, table):
            host = account["host"] if account else "%"
            return _error(403, 1142, "42000", "ER_TABLEACCESS_DENIED_ERROR",
                          f"{required} command denied to user '{user}'@'{host}' "
                          f"for table '{table}'",
                          table=table, database=database)
    return None


# ---------------------------------------------------------------------------
# Query surface
# ---------------------------------------------------------------------------

def query(sql, params=None, max_rows=1000, user="orbit_shop"):
    denied = check_privileges(sql, user)
    if denied:
        return denied
    try:
        result = _db.execute(sql, params=params, readonly=True, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result, user)


def execute(sql, params=None, max_rows=1000, user="orbit_shop"):
    denied = check_privileges(sql, user)
    if denied:
        return denied
    try:
        result = _db.execute(sql, params=params, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result, user)


_ISOLATION_LEVELS = ("READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ",
                     "SERIALIZABLE")


def transaction(statements, isolation_level="REPEATABLE READ", user="orbit_shop"):
    if not statements:
        return _error(400, 1064, "42000", "ER_PARSE_ERROR", "no statements supplied")
    level = str(isolation_level or "REPEATABLE READ").upper().replace("-", " ")
    if level not in _ISOLATION_LEVELS:
        return _error(400, 1231, "42000", "ER_WRONG_VALUE_FOR_VAR",
                      f"Variable 'transaction_isolation' can't be set to the value "
                      f"of '{isolation_level}'",
                      allowed=list(_ISOLATION_LEVELS))
    for entry in statements:
        denied = check_privileges(entry.get("sql"), user)
        if denied:
            return denied
    try:
        results = _db.execute_many(statements, atomic=True)
    except SqlError as exc:
        body = _sql_error(exc)
        body["rolled_back"] = True
        return body
    return {"results": [_result_envelope(r, user) for r in results],
            "statement_count": len(results), "isolation_level": level,
            "rolled_back": False, "committed": True}


def _result_envelope(result, user):
    return {
        "command": result["statement_type"].upper(),
        "columns": [{"name": name, "type": _mysql_type(kind)}
                    for name, kind in zip(result["columns"], result["types"])],
        "rows": [dict(zip(result["columns"], row)) for row in result["rows"]],
        "row_count": result["row_count"],
        "affected_rows": result["rows_affected"],
        "insert_id": result["last_insert_id"] or 0,
        "warnings": 0,
        "truncated": result["truncated"],
        "duration_ms": result["duration_ms"],
        "user": user,
        **({"statement_index": result["statement_index"]}
           if "statement_index" in result else {}),
    }


_MYSQL_TYPES = {"integer": "BIGINT", "real": "DECIMAL", "text": "VARCHAR",
                "null": "NULL", "blob": "BLOB"}


def _mysql_type(kind):
    return _MYSQL_TYPES.get(kind, "VARCHAR")


# ---------------------------------------------------------------------------
# EXPLAIN
# ---------------------------------------------------------------------------

def explain(sql, fmt="traditional", user="orbit_shop"):
    denied = check_privileges(sql, user)
    if denied:
        return denied
    try:
        steps = _db.explain(sql)
    except SqlError as exc:
        return _sql_error(exc)
    rows = [_explain_row(index + 1, step) for index, step in enumerate(steps)]
    if str(fmt).lower() == "json":
        return {"format": "json", "EXPLAIN": {"query_block": {
            "select_id": 1,
            "cost_info": {"query_cost": round(sum(r["rows"] for r in rows) * 1.2, 2)},
            "table": [{"table_name": r["table"], "access_type": r["type"],
                       "key": r["key"], "rows_examined_per_scan": r["rows"],
                       "filtered": r["filtered"],
                       "possible_keys": [r["possible_keys"]] if r["possible_keys"] else None}
                      for r in rows]}}}
    return {"format": "traditional", "rows": rows}


def _explain_row(seq, step):
    """Render an engine plan step in MySQL's EXPLAIN column format."""
    detail = str(step.get("detail", ""))
    table = _relation(detail)
    index = _index_name(detail)
    if index and "PRIMARY" in index.upper():
        access = "const"
    elif index:
        access = "ref"
    elif detail.startswith("SCAN"):
        access = "ALL"
    else:
        access = "index"
    return {"id": 1, "select_type": "SIMPLE" if seq == 1 else "SIMPLE",
            "table": table, "partitions": None, "type": access,
            "possible_keys": index, "key": index,
            "key_len": 4 if index else None, "ref": "const" if index else None,
            "rows": 1 if access in ("const", "ref") else 100,
            "filtered": 100.0,
            "Extra": "Using where" if access == "ALL" else "Using index condition"}


def _index_name(detail):
    match = re.search(r"USING (?:COVERING )?INDEX (\w+)", detail)
    if match:
        return match.group(1)
    return "PRIMARY" if "USING INTEGER PRIMARY KEY" in detail else None


def _relation(detail):
    match = re.search(r"(?:SCAN|SEARCH) (\w+)", detail)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# SHOW / information_schema
# ---------------------------------------------------------------------------

def list_databases():
    info = _server_info()
    return {"databases": info["databases"], "current": info["database"],
            "count": len(info["databases"])}


def list_tables(user="orbit_shop"):
    info = _server_info()
    meta = {m["TABLE_NAME"]: m for m in info["table_meta"]}
    rows = _db.query_all(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') "
        "AND name NOT LIKE 'sqlite_%' ORDER BY type, name")
    out = []
    for row in rows:
        entry = {"TABLE_SCHEMA": info["database"], "TABLE_NAME": row["name"],
                 "TABLE_TYPE": "BASE TABLE" if row["type"] == "table" else "VIEW",
                 "privileges": sorted(_privileges(user, row["name"]))}
        if row["type"] == "table":
            entry["live_rows"] = _db.query_all(
                f'SELECT COUNT(*) AS n FROM "{row["name"]}"')[0]["n"]
            entry.update({k: v for k, v in meta.get(row["name"], {}).items()
                          if k != "TABLE_NAME"})
        out.append(entry)
    return {"tables": out, "count": len(out), "database": info["database"]}


def describe_table(name, user="orbit_shop"):
    exists = _db.query_all(
        "SELECT name, type, sql FROM sqlite_master WHERE name = ? "
        "AND type IN ('table', 'view')", [name])
    if not exists:
        return _error(404, 1146, "42S02", "ER_NO_SUCH_TABLE",
                      f"Table '{_server_info()['database']}.{name}' doesn't exist",
                      table=name)
    columns = []
    for column in _db.query_all(f'PRAGMA table_info("{name}")'):
        columns.append({
            "Field": column["name"],
            "Type": (column["type"] or "varchar(255)").lower(),
            "Null": "NO" if column["notnull"] or column["pk"] else "YES",
            "Key": "PRI" if column["pk"] else "",
            "Default": column["dflt_value"],
            "Extra": "",
        })
    for index in _db.query_all(f'PRAGMA index_list("{name}")'):
        index_columns = [c["name"] for c in
                         _db.query_all(f'PRAGMA index_info("{index["name"]}")')]
        for column in columns:
            if column["Field"] in index_columns and not column["Key"]:
                column["Key"] = "UNI" if index["unique"] else "MUL"
    meta = next((m for m in _server_info()["table_meta"]
                 if m["TABLE_NAME"] == name), {})
    return {"TABLE_SCHEMA": _server_info()["database"], "TABLE_NAME": name,
            "TABLE_TYPE": "BASE TABLE" if exists[0]["type"] == "table" else "VIEW",
            "columns": columns,
            "create_statement": exists[0]["sql"],
            "foreign_keys": [
                {"column": c["from"], "referenced_table": c["table"],
                 "referenced_column": c["to"], "on_delete": c["on_delete"],
                 "on_update": c["on_update"]}
                for c in _db.query_all(f'PRAGMA foreign_key_list("{name}")')],
            "privileges": sorted(_privileges(user, name)),
            **meta}


def table_indexes(name):
    exists = _db.query_all(
        "SELECT name FROM sqlite_master WHERE name = ? AND type = 'table'", [name])
    if not exists:
        return _error(404, 1146, "42S02", "ER_NO_SUCH_TABLE",
                      f"Table '{_server_info()['database']}.{name}' doesn't exist",
                      table=name)
    rows = []
    for index in _db.query_all(f'PRAGMA index_list("{name}")'):
        for position, column in enumerate(
                _db.query_all(f'PRAGMA index_info("{index["name"]}")'), start=1):
            rows.append({"Table": name, "Non_unique": 0 if index["unique"] else 1,
                         "Key_name": index["name"], "Seq_in_index": position,
                         "Column_name": column["name"], "Collation": "A",
                         "Index_type": "BTREE", "Null": ""})
    return {"table": name, "indexes": rows, "count": len(rows)}


def show_variables(like=None):
    variables = _server_info()["variables"]
    if like:
        pattern = str(like).replace("%", ".*").replace("_", ".")
        variables = [v for v in variables
                     if re.match(f"^{pattern}$", v["Variable_name"], re.IGNORECASE)]
    return {"variables": variables, "count": len(variables)}


def show_status(like=None):
    status = _server_info()["status"]
    if like:
        pattern = str(like).replace("%", ".*").replace("_", ".")
        status = [s for s in status
                  if re.match(f"^{pattern}$", s["Variable_name"], re.IGNORECASE)]
    return {"status": status, "count": len(status)}


def show_processlist(user="orbit_shop"):
    """`SHOW PROCESSLIST`. Without PROCESS privilege only your own threads show."""
    account = _account(user)
    can_see_all = bool(account and "PROCESS" in account["privileges"])
    rows = _processlist_rows() if can_see_all else \
        [p for p in _processlist_rows() if p["user"] == user]
    return {"processlist": rows, "count": len(rows), "user": user,
            "full_visibility": can_see_all,
            "note": None if can_see_all else
            "only your own threads are shown; the PROCESS privilege is required "
            "to see all connections"}


def show_engines():
    engines = _server_info()["engines"]
    return {"engines": engines, "count": len(engines)}


def show_replication(user="orbit_shop"):
    account = _account(user)
    if not account or "REPLICATION CLIENT" not in account["privileges"]:
        return _error(403, 1227, "42000", "ER_SPECIFIC_ACCESS_DENIED_ERROR",
                      "Access denied; you need (at least one of) the SUPER, "
                      "REPLICATION CLIENT privilege(s) for this operation")
    replication = _server_info()["replication"]
    return {"source_status": replication["source"], "replicas": replication["replicas"],
            "replica_count": len(replication["replicas"])}


def list_users(user="orbit_shop"):
    account = _account(user)
    if not account or "SELECT" not in account["privileges"] or \
            "SUPER" not in account["privileges"]:
        # Non-superusers see only their own row, as they would in mysql.user.
        rows = [u for u in _users_rows() if u["user"] == user]
    else:
        rows = _users_rows()
    return {"users": [{k: v for k, v in u.items() if k != "privileges"}
                      for u in rows],
            "count": len(rows)}


def show_grants(target=None, user="orbit_shop"):
    name = target or user
    account = _account(name)
    if not account:
        return _error(404, 1141, "42000", "ER_NONEXISTING_GRANT",
                      f"There is no such grant defined for user '{name}'")
    if name != user and (not _account(user) or
                         "SUPER" not in _account(user)["privileges"]):
        return _error(403, 1227, "42000", "ER_SPECIFIC_ACCESS_DENIED_ERROR",
                      "Access denied; you need the SUPER privilege to view "
                      "another account's grants")
    grants = [f"GRANT {account['grants']} TO '{account['user']}'@'{account['host']}'"]
    for row in _grants_rows():
        if row["grantee"] == name:
            grants.append(
                f"GRANT {', '.join(row['privileges'])} ON "
                f"`{_server_info()['database']}`.`{row['table_name']}` TO "
                f"'{account['user']}'@'{account['host']}'")
    return {"user": f"'{account['user']}'@'{account['host']}'", "grants": grants,
            "count": len(grants)}


def server_status():
    info = _server_info()
    tables = [t for t in list_tables()["tables"] if t["TABLE_TYPE"] == "BASE TABLE"]
    return {
        "version": info["version"],
        "version_comment": info["version_comment"],
        "database": info["database"],
        "character_set_server": info["character_set_server"],
        "collation_server": info["collation_server"],
        "default_storage_engine": info["default_storage_engine"],
        "sql_mode": info["sql_mode"],
        "port": info["port"],
        "socket": info["socket"],
        "data_dir": info["data_dir"],
        "uptime_seconds": info["uptime_seconds"],
        "threads_connected": next(
            (int(s["Value"]) for s in info["status"]
             if s["Variable_name"] == "Threads_connected"), 0),
        "table_count": len(tables),
        "total_rows": sum(t["live_rows"] for t in tables),
    }


def version():
    info = _server_info()
    return {"version": info["version"], "version_comment": info["version_comment"],
            "version_compile_os": info["version_compile_os"],
            "version_compile_machine": info["version_compile_machine"]}


def health():
    return {"status": "ok"}


def health_db():
    info = _server_info()
    started = time.perf_counter()
    _db.query_all("SELECT 1")
    lagging = [r for r in info["replication"]["replicas"]
               if r["Replica_SQL_Running"] != "Yes"]
    return {"status": "ok", "engine": "mysql", "version": info["version"],
            "database": info["database"],
            "threads_connected": next(
                (int(s["Value"]) for s in info["status"]
                 if s["Variable_name"] == "Threads_connected"), 0),
            "replicas_healthy": len(info["replication"]["replicas"]) - len(lagging),
            "replicas_total": len(info["replication"]["replicas"]),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


_store.eager_load()
