"""Data access module for the MariaDB API mock service.

Exposes a MariaDB 10.11 database over HTTP -- `orbit_forum`, the Orbit Labs
community forum and knowledge base. Statements run through `sql_engine`, which
materializes the shared store into an in-memory SQLite database per request,
executes genuine SQL, and syncs writes back so the admin plane can still drift a
row mid-run.

The surface is MySQL-compatible where MariaDB is, and diverges where MariaDB
does. The three divergences modelled here are the ones that actually change
behaviour rather than just strings:

* **Sequences.** `NEXT VALUE FOR seq` / `NEXTVAL(seq)` / `LASTVAL(seq)` /
  `SETVAL(seq, n)` are real, backed by `sequences` rows, with cycling and
  exhaustion. MySQL has no sequences at all.
* **RETURNING.** Supported on INSERT and DELETE. `UPDATE ... RETURNING` is
  rejected, because MariaDB does not implement it either.
* **Non-transactional Aria tables.** `page_views` is an Aria table, so a write
  to it survives a rolled-back transaction -- which is exactly what a
  non-transactional engine does, and a common source of surprise.
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

_store = get_store("mariadb-api")
_API = "mariadb-api"


def _load_server_info():
    with open(DATA_DIR / "server_info.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("forum_users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("forum_users.json", "forum_users")))
_store.register("categories", primary_key="id",
                initial_loader=lambda: _coerce_categories(_load("categories.json", "categories")))
_store.register("threads", primary_key="id",
                initial_loader=lambda: _coerce_threads(_load("threads.json", "threads")))
_store.register("posts", primary_key="id",
                initial_loader=lambda: _coerce_posts(_load("posts.json", "posts")))
_store.register("kb_articles", primary_key="id",
                initial_loader=lambda: _coerce_articles(_load("kb_articles.json", "kb_articles")))
_store.register("article_revisions", primary_key="id",
                initial_loader=lambda: _coerce_revisions(_load("article_revisions.json", "article_revisions")))
_store.register("page_views", primary_key="id",
                initial_loader=lambda: _coerce_page_views(_load("page_views.json", "page_views")))
_store.register("sequences", primary_key="name",
                initial_loader=lambda: _coerce_sequences(_load("sequences.json", "sequences")))
_store.register("mysql_global_priv", primary_key="user",
                initial_loader=lambda: _coerce_accounts(_load("accounts.json", "mysql_global_priv")))
_store.register("table_grants", primary_key="id",
                initial_loader=lambda: _coerce_grants(_load("table_grants.json", "table_grants")))
_store.register_document("server_info", initial_loader=_load_server_info)


def _users_rows():
    return _store.table("forum_users").rows()


def _categories_rows():
    return _store.table("categories").rows()


def _threads_rows():
    return _store.table("threads").rows()


def _posts_rows():
    return _store.table("posts").rows()


def _articles_rows():
    return _store.table("kb_articles").rows()


def _revisions_rows():
    return _store.table("article_revisions").rows()


def _page_views_rows():
    return _store.table("page_views").rows()


def _sequences_rows():
    return _store.table("sequences").rows()


def _accounts_rows():
    return _store.table("mysql_global_priv").rows()


def _grants_rows():
    return _store.table("table_grants").rows()


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

def _coerce_users(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "reputation": opt_int(r, "reputation", default=0),
             "banned": opt_int(r, "banned", default=0)} for r in rows]


def _coerce_categories(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "sort_order": opt_int(r, "sort_order", default=0),
             "locked": opt_int(r, "locked", default=0)} for r in rows]


def _coerce_threads(rows):
    integers = ("id", "category_id", "author_id", "views", "reply_count", "pinned")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers}}
            for r in rows]


def _coerce_posts(rows):
    integers = ("id", "thread_id", "author_id", "score", "accepted")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers},
             "edited_at": _null_if_blank(r, "edited_at")} for r in rows]


def _coerce_articles(rows):
    integers = ("id", "author_id", "version", "helpful_votes")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers}}
            for r in rows]


def _coerce_revisions(rows):
    integers = ("id", "article_id", "version", "editor_id")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers}}
            for r in rows]


def _coerce_page_views(rows):
    integers = ("id", "views", "unique_visitors")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers}}
            for r in rows]


def _coerce_sequences(rows):
    integers = ("start_value", "minimum_value", "maximum_value", "increment",
                "cache_size", "cycle_option", "next_not_cached_value", "last_value")
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in integers}}
            for r in rows]


def _coerce_accounts(rows):
    return [{**_strip_ctx(r), "account_locked": opt_int(r, "account_locked", default=0),
             "max_connections": opt_int(r, "max_connections", default=0),
             "privileges": [p for p in opt_str(r, "privileges", default="").split(";") if p]}
            for r in rows]


def _coerce_grants(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "privileges": [p for p in opt_str(r, "privileges", default="").split(";") if p]}
            for r in rows]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = [
    """CREATE TABLE forum_users (
        id           int          NOT NULL PRIMARY KEY,
        username     varchar(64)  NOT NULL UNIQUE,
        email        varchar(255) NOT NULL UNIQUE,
        display_name varchar(128) NOT NULL,
        role         varchar(16)  NOT NULL CHECK (role IN ('member', 'moderator', 'staff')),
        reputation   int          NOT NULL DEFAULT 0,
        joined_at    datetime     NOT NULL,
        banned       tinyint      NOT NULL DEFAULT 0,
        last_seen_at datetime
    )""",
    """CREATE TABLE categories (
        id          int          NOT NULL PRIMARY KEY,
        slug        varchar(64)  NOT NULL UNIQUE,
        name        varchar(128) NOT NULL,
        description text,
        sort_order  int          NOT NULL DEFAULT 0,
        locked      tinyint      NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE threads (
        id           int          NOT NULL PRIMARY KEY,
        category_id  int          NOT NULL REFERENCES categories(id),
        author_id    int          NOT NULL REFERENCES forum_users(id),
        title        varchar(255) NOT NULL,
        slug         varchar(255) NOT NULL UNIQUE,
        status       varchar(16)  NOT NULL CHECK (status IN
                         ('open', 'answered', 'locked', 'spam')),
        views        int          NOT NULL DEFAULT 0,
        reply_count  int          NOT NULL DEFAULT 0,
        pinned       tinyint      NOT NULL DEFAULT 0,
        created_at   datetime     NOT NULL,
        last_post_at datetime     NOT NULL
    )""",
    """CREATE TABLE posts (
        id         int      NOT NULL PRIMARY KEY,
        thread_id  int      NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
        author_id  int      NOT NULL REFERENCES forum_users(id),
        body       text     NOT NULL,
        score      int      NOT NULL DEFAULT 0,
        accepted   tinyint  NOT NULL DEFAULT 0,
        created_at datetime NOT NULL,
        edited_at  datetime
    )""",
    """CREATE TABLE kb_articles (
        id            int          NOT NULL PRIMARY KEY,
        slug          varchar(128) NOT NULL UNIQUE,
        title         varchar(255) NOT NULL,
        body          text         NOT NULL,
        status        varchar(16)  NOT NULL CHECK (status IN
                          ('draft', 'published', 'archived')),
        author_id     int          NOT NULL REFERENCES forum_users(id),
        version       int          NOT NULL DEFAULT 1,
        helpful_votes int          NOT NULL DEFAULT 0,
        updated_at    datetime     NOT NULL
    )""",
    """CREATE TABLE article_revisions (
        id         int          NOT NULL PRIMARY KEY,
        article_id int          NOT NULL REFERENCES kb_articles(id) ON DELETE CASCADE,
        version    int          NOT NULL,
        editor_id  int          NOT NULL REFERENCES forum_users(id),
        summary    varchar(255) NOT NULL,
        changed_at datetime     NOT NULL,
        UNIQUE (article_id, version)
    )""",
    """CREATE TABLE page_views (
        id              int         NOT NULL PRIMARY KEY,
        path            varchar(255) NOT NULL,
        viewed_on       date        NOT NULL,
        views           int         NOT NULL DEFAULT 0,
        unique_visitors int         NOT NULL DEFAULT 0,
        UNIQUE (path, viewed_on)
    )""",
    "CREATE INDEX idx_threads_category ON threads(category_id, last_post_at)",
    "CREATE INDEX idx_threads_status ON threads(status)",
    "CREATE INDEX idx_posts_thread ON posts(thread_id)",
    "CREATE INDEX idx_revisions_article ON article_revisions(article_id, version)",
    "CREATE INDEX idx_page_views_day ON page_views(viewed_on)",
    """CREATE VIEW thread_activity AS
        SELECT t.id, t.title, c.name AS category, u.display_name AS author,
               t.status, t.views, t.reply_count, t.last_post_at
        FROM threads t
        JOIN categories c ON c.id = t.category_id
        JOIN forum_users u ON u.id = t.author_id""",
]

TABLES = {
    "forum_users": _users_rows,
    "categories": _categories_rows,
    "threads": _threads_rows,
    "posts": _posts_rows,
    "kb_articles": _articles_rows,
    "article_revisions": _revisions_rows,
    "page_views": _page_views_rows,
}

# Tables on a non-transactional engine. A write here is not rolled back.
ARIA_TABLES = {name for name, engine in
               _load_server_info()["table_engines"].items() if engine == "Aria"}


# ---------------------------------------------------------------------------
# MariaDB functions and dialect rewriting
# ---------------------------------------------------------------------------

def _concat(*args):
    return None if any(a is None for a in args) else "".join(str(a) for a in args)


def _concat_ws(separator, *args):
    if separator is None:
        return None
    return str(separator).join(str(a) for a in args if a is not None)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _curdate():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


_DATE_TOKENS = [("%Y", "%Y"), ("%y", "%y"), ("%m", "%m"), ("%d", "%d"),
                ("%H", "%H"), ("%i", "%M"), ("%s", "%S"), ("%S", "%S"),
                ("%M", "%B"), ("%b", "%b"), ("%W", "%A"), ("%a", "%a")]


def _date_format(value, spec):
    if value is None or spec is None:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(str(value)[:len(pattern) + 2].strip(), pattern)
            break
        except ValueError:
            continue
    else:
        return None
    out = str(spec)
    for mariadb_token, python_token in _DATE_TOKENS:
        out = out.replace(mariadb_token, parsed.strftime(python_token))
    return out


def _year(value):
    return int(str(value)[:4]) if value else None


def _greatest(*args):
    values = [a for a in args if a is not None]
    return max(values) if values else None


def _least(*args):
    values = [a for a in args if a is not None]
    return min(values) if values else None


FUNCTIONS = {
    "CONCAT": (-1, _concat),
    "CONCAT_WS": (-1, _concat_ws),
    "NOW": (0, _now),
    "CURDATE": (0, _curdate),
    "DATE_FORMAT": (2, _date_format),
    "YEAR": (1, _year),
    "GREATEST": (-1, _greatest),
    "LEAST": (-1, _least),
}


def rewrite(sql):
    """Translate the MariaDB-only syntax the engine cannot parse as written."""
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


_db = sql_engine.Database("orbit_forum", DDL, TABLES, _store, rewriter=rewrite,
                          functions=FUNCTIONS)


# ---------------------------------------------------------------------------
# Sequences -- a MariaDB feature MySQL does not have
# ---------------------------------------------------------------------------

_NEXT_VALUE_FOR = re.compile(r"\bNEXT\s+VALUE\s+FOR\s+`?(\w+)`?", re.IGNORECASE)
_NEXTVAL = re.compile(r"\bNEXTVAL\s*\(\s*`?(\w+)`?\s*\)", re.IGNORECASE)
_LASTVAL = re.compile(r"\bLASTVAL\s*\(\s*`?(\w+)`?\s*\)", re.IGNORECASE)
_SETVAL = re.compile(r"\bSETVAL\s*\(\s*`?(\w+)`?\s*,\s*(-?\d+)\s*\)", re.IGNORECASE)


class SequenceError(Exception):
    """A sequence reference that cannot be satisfied."""

    def __init__(self, errno, sqlstate, name, message):
        super().__init__(message)
        self.errno = errno
        self.sqlstate = sqlstate
        self.error_name = name
        self.message = message


def _sequence(name):
    row = _store.table("sequences").get(name)
    if not row:
        raise SequenceError(1146, "42S02", "ER_NO_SUCH_TABLE",
                            f"Table '{_server_info()['database']}.{name}' doesn't exist")
    return row


def next_value(name):
    """Allocate the next value, honouring the cycle option and the maximum."""
    sequence = _sequence(name)
    value = sequence["next_not_cached_value"]
    if value > sequence["maximum_value"]:
        if not sequence["cycle_option"]:
            raise SequenceError(4084, "HY000", "ER_SEQUENCE_RUN_OUT",
                                f"Sequence '{_server_info()['database']}.{name}' "
                                f"has run out")
        value = sequence["minimum_value"]
    following = value + sequence["increment"]
    if following > sequence["maximum_value"] and sequence["cycle_option"]:
        following = sequence["minimum_value"]
    _store.table("sequences").patch(name, {"last_value": value,
                                           "next_not_cached_value": following})
    return value


def last_value(name):
    return _sequence(name)["last_value"]


def set_value(name, value):
    sequence = _sequence(name)
    if value < sequence["minimum_value"] or value > sequence["maximum_value"]:
        raise SequenceError(4086, "HY000", "ER_SEQUENCE_INVALID_DATA",
                            f"Sequence '{_server_info()['database']}.{name}' "
                            f"values are conflicting")
    _store.table("sequences").patch(name, {"last_value": value,
                                           "next_not_cached_value":
                                           value + sequence["increment"]})
    return value


def _expand_sequences(sql):
    """Replace sequence expressions with the values they allocate.

    Returns (sql, allocations). Allocation is a real side effect -- that is what
    a sequence does, and it is why a rolled-back transaction still consumes
    values in MariaDB.
    """
    allocations = []
    text = sql or ""

    def take_next(match):
        name = match.group(1)
        value = next_value(name)
        allocations.append({"sequence": name, "value": value, "operation": "nextval"})
        return str(value)

    def take_last(match):
        name = match.group(1)
        value = last_value(name)
        allocations.append({"sequence": name, "value": value, "operation": "lastval"})
        return str(value)

    def take_set(match):
        name, target = match.group(1), int(match.group(2))
        value = set_value(name, target)
        allocations.append({"sequence": name, "value": value, "operation": "setval"})
        return str(value)

    text = _SETVAL.sub(take_set, text)
    text = _NEXT_VALUE_FOR.sub(take_next, text)
    text = _NEXTVAL.sub(take_next, text)
    text = _LASTVAL.sub(take_last, text)
    return text, allocations


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

_MARIADB_ERRORS = {
    sql_engine.UNIQUE_VIOLATION: (1062, "23000", "ER_DUP_ENTRY", 409),
    sql_engine.FOREIGN_KEY_VIOLATION: (1452, "23000", "ER_NO_REFERENCED_ROW_2", 409),
    sql_engine.NOT_NULL_VIOLATION: (1048, "23000", "ER_BAD_NULL_ERROR", 400),
    sql_engine.CHECK_VIOLATION: (4025, "23000", "ER_CONSTRAINT_FAILED", 400),
    sql_engine.UNDEFINED_TABLE: (1146, "42S02", "ER_NO_SUCH_TABLE", 404),
    sql_engine.UNDEFINED_COLUMN: (1054, "42S22", "ER_BAD_FIELD_ERROR", 400),
    sql_engine.SYNTAX_ERROR: (1064, "42000", "ER_PARSE_ERROR", 400),
    sql_engine.DATATYPE_MISMATCH: (1366, "22007", "ER_TRUNCATED_WRONG_VALUE", 400),
    sql_engine.FEATURE_NOT_SUPPORTED: (1235, "42000", "ER_NOT_SUPPORTED_YET", 403),
    sql_engine.INTERNAL_ERROR: (1105, "HY000", "ER_UNKNOWN_ERROR", 500),
}

_UNIQUE_TARGET = re.compile(r"UNIQUE constraint failed: ([\w.]+(?:, [\w.]+)*)")
_NOT_NULL_TARGET = re.compile(r"NOT NULL constraint failed: (\w+)\.(\w+)")
_NO_TABLE_TARGET = re.compile(r"no such table: (\S+)")
_NO_COLUMN_TARGET = re.compile(r"no such column: (\S+)")


def _sql_error(exc):
    errno, sqlstate, name, status = _MARIADB_ERRORS.get(
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
        message = f"Duplicate entry for key '{key}'"
    elif exc.kind == sql_engine.FOREIGN_KEY_VIOLATION:
        message = ("Cannot add or update a child row: a foreign key constraint "
                   "fails")
    elif not_null:
        message = f"Column '{not_null.group(2)}' cannot be null"
    elif missing_table:
        message = f"Table '{database}.{missing_table.group(1)}' doesn't exist"
    elif missing_column:
        message = f"Unknown column '{missing_column.group(1)}' in 'field list'"
    elif exc.kind == sql_engine.CHECK_VIOLATION:
        message = f"CONSTRAINT failed for `{database}`"
    elif exc.kind == sql_engine.SYNTAX_ERROR:
        message = (f"You have an error in your SQL syntax; check the manual that "
                   f"corresponds to your MariaDB server version. {exc.message}")

    body = {"error": message, "errno": errno, "sqlstate": sqlstate,
            "error_name": name, "message": message, "status": status}
    if exc.statement:
        body["statement"] = exc.statement
    index = getattr(exc, "statement_index", None)
    if index is not None:
        body["statement_index"] = index
    return body


def _sequence_error(exc):
    return {"error": exc.message, "errno": exc.errno, "sqlstate": exc.sqlstate,
            "error_name": exc.error_name, "message": exc.message,
            "status": 404 if exc.errno == 1146 else 400}


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


def resolve_user(mariadb_user=None, authorization=None):
    name = (mariadb_user or "").strip()
    if not name and authorization:
        raw = str(authorization).strip()
        name = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
    name = name.split("@")[0]
    row = _store.table("mysql_global_priv").get(name) if name else None
    if row:
        return row["user"]
    return _server_info()["auth"]["default_user"]


def _account(user):
    return _store.table("mysql_global_priv").get(user)


def _privileges(user, table):
    account = _account(user)
    if not account or account["account_locked"]:
        return set()
    specific = _store.table("table_grants").find_one(
        lambda g: g["grantee"] == user and g["table_name"] == table)
    if specific:
        return set(specific["privileges"])
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
        return _error(403, 4151, "HY000", "ER_ACCOUNT_HAS_BEEN_LOCKED",
                      f"Access denied, this account is locked")
    required = _WRITE_PRIVILEGE.get(sql_engine._statement_type(sql or ""), "SELECT")
    for table in _referenced_tables(sql):
        if required not in _privileges(user, table):
            host = account["host"] if account else "%"
            return _error(403, 1142, "42000", "ER_TABLEACCESS_DENIED_ERROR",
                          f"{required} command denied to user '{user}'@'{host}' "
                          f"for table `{_server_info()['database']}`.`{table}`",
                          table=table, database=_server_info()["database"])
    return None


# ---------------------------------------------------------------------------
# Query surface
# ---------------------------------------------------------------------------

_UPDATE_RETURNING = re.compile(r"^\s*UPDATE\b.*\bRETURNING\b", re.IGNORECASE | re.DOTALL)


def _guard_update_returning(sql):
    """MariaDB implements RETURNING for INSERT and DELETE, but not UPDATE."""
    if _UPDATE_RETURNING.match(sql or ""):
        return _error(400, 1064, "42000", "ER_PARSE_ERROR",
                      "You have an error in your SQL syntax; RETURNING is not "
                      "supported for UPDATE in MariaDB",
                      hint="RETURNING is available on INSERT and DELETE only")
    return None


def query(sql, params=None, max_rows=1000, user="forum_app"):
    denied = check_privileges(sql, user)
    if denied:
        return denied
    try:
        prepared, allocations = _expand_sequences(sql)
    except SequenceError as exc:
        return _sequence_error(exc)
    try:
        result = _db.execute(prepared, params=params, readonly=True, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result, user, allocations)


def execute(sql, params=None, max_rows=1000, user="forum_app"):
    denied = check_privileges(sql, user) or _guard_update_returning(sql)
    if denied:
        return denied
    try:
        prepared, allocations = _expand_sequences(sql)
    except SequenceError as exc:
        return _sequence_error(exc)
    try:
        result = _db.execute(prepared, params=params, max_rows=max_rows)
    except SqlError as exc:
        return _sql_error(exc)
    return _result_envelope(result, user, allocations)


_ISOLATION_LEVELS = ("READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ",
                     "SERIALIZABLE")


def transaction(statements, isolation_level="REPEATABLE READ", user="forum_app"):
    """Atomic across InnoDB tables; Aria writes survive a rollback.

    That asymmetry is the point: MariaDB's Aria engine is not transactional, so a
    counter bumped inside a transaction that later fails stays bumped.
    """
    if not statements:
        return _error(400, 1064, "42000", "ER_PARSE_ERROR", "no statements supplied")
    level = str(isolation_level or "REPEATABLE READ").upper().replace("-", " ")
    if level not in _ISOLATION_LEVELS:
        return _error(400, 1231, "42000", "ER_WRONG_VALUE_FOR_VAR",
                      f"Variable 'transaction_isolation' can't be set to the value "
                      f"of '{isolation_level}'", allowed=list(_ISOLATION_LEVELS))
    for entry in statements:
        denied = check_privileges(entry.get("sql"), user) or \
            _guard_update_returning(entry.get("sql"))
        if denied:
            return denied

    prepared, allocations = [], []
    try:
        for entry in statements:
            text, allocated = _expand_sequences(entry.get("sql"))
            prepared.append({"sql": text, "params": entry.get("params")})
            allocations.extend(allocated)
    except SequenceError as exc:
        return _sequence_error(exc)

    try:
        results = _db.execute_many(prepared, atomic=True)
    except SqlError as exc:
        body = _sql_error(exc)
        body["rolled_back"] = True
        replayed = _replay_non_transactional(prepared, exc)
        if replayed:
            body["non_transactional_writes_kept"] = replayed
            body["warning"] = (
                "statements against Aria tables are not transactional and were "
                "not rolled back")
        if allocations:
            body["sequence_allocations"] = allocations
            body["sequence_note"] = (
                "sequence values allocated by this transaction are not returned "
                "on rollback")
        return body
    envelope = {"results": [_result_envelope(r, user) for r in results],
                "statement_count": len(results), "isolation_level": level,
                "rolled_back": False, "committed": True}
    if allocations:
        envelope["sequence_allocations"] = allocations
    return envelope


def _replay_non_transactional(statements, failure):
    """Re-apply Aria writes the rollback discarded, up to the failing statement."""
    failed_at = getattr(failure, "statement_index", len(statements))
    replayed = []
    for index, entry in enumerate(statements):
        if index >= failed_at:
            break
        text = entry.get("sql") or ""
        if not _db.is_write(text):
            continue
        if not (_referenced_tables(text) & ARIA_TABLES):
            continue
        try:
            _db.execute(text, params=entry.get("params"))
        except SqlError:
            continue
        replayed.append({"statement_index": index, "sql": text,
                         "tables": sorted(_referenced_tables(text) & ARIA_TABLES)})
    return replayed


def _result_envelope(result, user, allocations=None):
    envelope = {
        "command": result["statement_type"].upper(),
        "columns": [{"name": name, "type": _mariadb_type(kind)}
                    for name, kind in zip(result["columns"], result["types"])],
        "rows": [dict(zip(result["columns"], row)) for row in result["rows"]],
        "row_count": result["row_count"],
        "affected_rows": result["rows_affected"],
        "insert_id": result["last_insert_id"] or 0,
        "warnings": 0,
        "truncated": result["truncated"],
        "duration_ms": result["duration_ms"],
        "user": user,
    }
    if "statement_index" in result:
        envelope["statement_index"] = result["statement_index"]
    if allocations:
        envelope["sequence_allocations"] = allocations
    return envelope


_MARIADB_TYPES = {"integer": "BIGINT", "real": "DECIMAL", "text": "VARCHAR",
                  "null": "NULL", "blob": "BLOB"}


def _mariadb_type(kind):
    return _MARIADB_TYPES.get(kind, "VARCHAR")


# ---------------------------------------------------------------------------
# EXPLAIN / ANALYZE
# ---------------------------------------------------------------------------

def explain(sql, analyze=False, user="forum_app"):
    """`EXPLAIN`, or MariaDB's `ANALYZE` which adds measured rows next to estimates."""
    denied = check_privileges(sql, user)
    if denied:
        return denied
    try:
        prepared, _ = _expand_sequences(sql)
        steps = _db.explain(prepared)
        measured = len(_db.query_all(rewrite(prepared))) if analyze else None
    except SequenceError as exc:
        return _sequence_error(exc)
    except SqlError as exc:
        return _sql_error(exc)
    rows = []
    for step in steps:
        detail = str(step.get("detail", ""))
        index = _index_name(detail)
        access = "ref" if index else ("ALL" if detail.startswith("SCAN") else "index")
        row = {"id": 1, "select_type": "SIMPLE", "table": _relation(detail),
               "type": access, "possible_keys": index, "key": index,
               "key_len": 4 if index else None, "ref": "const" if index else None,
               "rows": 1 if access == "ref" else 100, "Extra":
                   "Using where" if access == "ALL" else "Using index condition"}
        if analyze:
            row["r_rows"] = measured
            row["r_filtered"] = 100.0
            row["filtered"] = 100.0
        rows.append(row)
    return {"format": "analyze" if analyze else "explain", "rows": rows,
            **({"r_total_rows": measured} if analyze else {})}


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


def list_tables(user="forum_app"):
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


def describe_table(name, user="forum_app"):
    exists = _db.query_all(
        "SELECT name, type, sql FROM sqlite_master WHERE name = ? "
        "AND type IN ('table', 'view')", [name])
    if not exists:
        return _error(404, 1146, "42S02", "ER_NO_SUCH_TABLE",
                      f"Table '{_server_info()['database']}.{name}' doesn't exist",
                      table=name)
    columns = []
    for column in _db.query_all(f'PRAGMA table_info("{name}")'):
        columns.append({"Field": column["name"],
                        "Type": (column["type"] or "varchar(255)").lower(),
                        "Null": "NO" if column["notnull"] or column["pk"] else "YES",
                        "Key": "PRI" if column["pk"] else "",
                        "Default": column["dflt_value"], "Extra": ""})
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
            "columns": columns, "create_statement": exists[0]["sql"],
            "foreign_keys": [
                {"column": c["from"], "referenced_table": c["table"],
                 "referenced_column": c["to"], "on_delete": c["on_delete"]}
                for c in _db.query_all(f'PRAGMA foreign_key_list("{name}")')],
            "privileges": sorted(_privileges(user, name)), **meta}


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
                         "Column_name": column["name"], "Index_type": "BTREE"})
    return {"table": name, "indexes": rows, "count": len(rows)}


def list_sequences():
    rows = []
    for sequence in _sequences_rows():
        rows.append({**sequence, "cycle_option": bool(sequence["cycle_option"])})
    return {"sequences": rows, "count": len(rows)}


def sequence_next(name):
    try:
        value = next_value(name)
    except SequenceError as exc:
        return _sequence_error(exc)
    return {"sequence": name, "value": value,
            "next_not_cached_value": _sequence(name)["next_not_cached_value"]}


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


def show_engines():
    engines = _server_info()["engines"]
    return {"engines": engines, "count": len(engines),
            "non_transactional": sorted(e["Engine"] for e in engines
                                        if e["Transactions"] == "NO")}


def show_replication(user="forum_app"):
    account = _account(user)
    if not account or "REPLICATION CLIENT" not in account["privileges"]:
        return _error(403, 1227, "42000", "ER_SPECIFIC_ACCESS_DENIED_ERROR",
                      "Access denied; you need (at least one of) the SUPER, "
                      "REPLICATION CLIENT privilege(s) for this operation")
    replication = _server_info()["replication"]
    return {"gtid_binlog_pos": replication["gtid_binlog_pos"],
            "gtid_current_pos": replication["gtid_current_pos"],
            "binlog_file": replication["binlog_file"],
            "binlog_position": replication["binlog_position"],
            "replicas": replication["replicas"],
            "replica_count": len(replication["replicas"])}


def list_accounts(user="forum_app"):
    account = _account(user)
    rows = _accounts_rows() if account and "SUPER" in account["privileges"] \
        else [a for a in _accounts_rows() if a["user"] == user]
    return {"accounts": [{k: v for k, v in a.items() if k != "privileges"}
                         for a in rows], "count": len(rows),
            "source": "mysql.global_priv"}


def show_grants(target=None, user="forum_app"):
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
    grants = [f"GRANT {account['grants']} TO `{account['user']}`@`{account['host']}`"]
    for row in _grants_rows():
        if row["grantee"] == name:
            grants.append(
                f"GRANT {', '.join(row['privileges'])} ON "
                f"`{_server_info()['database']}`.`{row['table_name']}` TO "
                f"`{account['user']}`@`{account['host']}`")
    return {"user": f"`{account['user']}`@`{account['host']}`", "grants": grants,
            "count": len(grants)}


def server_status():
    info = _server_info()
    tables = [t for t in list_tables()["tables"] if t["TABLE_TYPE"] == "BASE TABLE"]
    return {"version": info["version"], "version_short": info["version_short"],
            "version_comment": info["version_comment"],
            "database": info["database"],
            "character_set_server": info["character_set_server"],
            "collation_server": info["collation_server"],
            "default_storage_engine": info["default_storage_engine"],
            "sql_mode": info["sql_mode"], "port": info["port"],
            "socket": info["socket"], "data_dir": info["data_dir"],
            "uptime_seconds": info["uptime_seconds"],
            "thread_handling": next(
                (v["Value"] for v in info["variables"]
                 if v["Variable_name"] == "thread_handling"), None),
            "table_count": len(tables),
            "total_rows": sum(t["live_rows"] for t in tables),
            "non_transactional_tables": sorted(ARIA_TABLES)}


def version():
    info = _server_info()
    return {"version": info["version"], "version_short": info["version_short"],
            "version_comment": info["version_comment"],
            "version_compile_os": info["version_compile_os"],
            "version_compile_machine": info["version_compile_machine"]}


def health():
    return {"status": "ok"}


def health_db():
    info = _server_info()
    started = time.perf_counter()
    _db.query_all("SELECT 1")
    behind = max((r["Seconds_Behind_Master"] for r in info["replication"]["replicas"]),
                 default=0)
    return {"status": "ok", "engine": "mariadb", "version": info["version_short"],
            "database": info["database"],
            "threads_connected": next(
                (int(s["Value"]) for s in info["status"]
                 if s["Variable_name"] == "Threads_connected"), 0),
            "gtid_current_pos": info["replication"]["gtid_current_pos"],
            "max_seconds_behind_master": behind,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3)}


_store.eager_load()
