"""A real SQL execution core for the relational-database mock services.

Python ships with SQLite, so these mocks run genuine SQL rather than pattern
matching: joins, aggregates, subqueries, CTEs, constraints and query plans all
behave the way a database behaves. The engine keeps the shared store as the
source of truth so the admin plane can still drift a row mid-run:

1. every request materializes a fresh in-memory database from the store,
2. the statement executes against it,
3. a write syncs the resulting rows back into the store.

At mock scale (tens of rows) the round trip is immaterial, and it buys exact SQL
semantics plus drift support at the same time.

Dialect differences -- error codes, type names, metadata queries -- are the
caller's job; this module returns a neutral result and a neutral error kind that
each service maps onto its own vocabulary.
"""

import re
import sqlite3
import time

# Statements that could reach the filesystem or a second database file. The
# in-memory database is otherwise a closed world, so this is the whole guard.
_FORBIDDEN = re.compile(
    r"^\s*(ATTACH|DETACH|VACUUM\s+INTO|\.(read|shell|import|output))\b", re.IGNORECASE)

_WRITE_PREFIXES = ("insert", "update", "delete", "replace", "create", "drop",
                   "alter", "truncate")

# Neutral error kinds; each service maps these onto its dialect's SQLSTATE or
# vendor error number.
UNIQUE_VIOLATION = "unique_violation"
FOREIGN_KEY_VIOLATION = "foreign_key_violation"
NOT_NULL_VIOLATION = "not_null_violation"
CHECK_VIOLATION = "check_violation"
UNDEFINED_TABLE = "undefined_table"
UNDEFINED_COLUMN = "undefined_column"
SYNTAX_ERROR = "syntax_error"
DATATYPE_MISMATCH = "datatype_mismatch"
FEATURE_NOT_SUPPORTED = "feature_not_supported"
INTERNAL_ERROR = "internal_error"


class SqlError(Exception):
    """A statement failure, classified into a dialect-neutral `kind`."""

    def __init__(self, kind, message, statement=None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.statement = statement


class Database:
    """Materializes the store into SQLite and runs statements against it.

    ``ddl`` is the schema, ``tables`` maps each table name to a callable
    returning its rows as dicts, and ``store`` is the shared mutable store the
    rows come from and are written back to.
    """

    def __init__(self, name, ddl, tables, store, foreign_keys=True, rewriter=None,
                 functions=None):
        self.name = name
        self._ddl = list(ddl)
        self._tables = dict(tables)
        self._store = store
        self._foreign_keys = foreign_keys
        # Optional dialect translation applied to every incoming statement, so a
        # service can accept its own dialect's syntax on the shared engine.
        self._rewriter = rewriter
        # Scalar SQL functions a dialect provides but SQLite does not, registered
        # on every connection as {name: (arity, callable)}.
        self._functions = dict(functions or {})

    def rewrite(self, sql):
        return self._rewriter(sql) if self._rewriter else sql

    # -- materialization ---------------------------------------------------

    def connect(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        # Seed with foreign keys off so table registration order cannot matter:
        # a child table may legitimately be listed before its parent. Enforcement
        # is switched on once the data is in, so statements still see real FKs.
        connection.execute("PRAGMA foreign_keys=OFF")
        for name, (arity, implementation) in self._functions.items():
            connection.create_function(name, arity, implementation)
        for statement in self._ddl:
            connection.execute(statement)
        for table, loader in self._tables.items():
            rows = loader()
            if not rows:
                continue
            columns = list(rows[0].keys())
            placeholders = ",".join("?" * len(columns))
            connection.executemany(
                f'INSERT INTO "{table}" ({",".join(columns)}) VALUES ({placeholders})',
                [[row.get(column) for column in columns] for row in rows])
        connection.commit()
        if self._foreign_keys:
            connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _sync_back(self, connection):
        """Replace the store's rows with what the database now holds.

        Every table is re-read, not just the statement's target: a cascade or a
        trigger can touch tables the statement never named.
        """
        for table in self._tables:
            rows = [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]
            handle = self._store.table(table)
            handle.delete_where(lambda _row: True)
            for row in rows:
                handle.upsert(row)

    # -- execution ---------------------------------------------------------

    def execute(self, sql, params=None, readonly=False, max_rows=1000):
        """Run one statement. Returns a neutral result dict."""
        statement = (sql or "").strip()
        if not statement:
            raise SqlError(SYNTAX_ERROR, "empty statement")
        if _FORBIDDEN.match(statement):
            raise SqlError(FEATURE_NOT_SUPPORTED,
                           "statement is not permitted on this service",
                           statement)
        statement = self.rewrite(statement)
        writes = self.is_write(statement)
        if readonly and writes:
            raise SqlError(FEATURE_NOT_SUPPORTED,
                           "read-only endpoint received a write statement; "
                           "use the execute endpoint instead", statement)
        connection = self.connect()
        try:
            started = time.perf_counter()
            try:
                cursor = connection.execute(statement, _bind(params))
            except sqlite3.Error as exc:
                raise _classify(exc, statement)
            result = _harvest(cursor, max_rows, _statement_type(statement))
            result["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
            if writes:
                connection.commit()
                self._sync_back(connection)
            return result
        finally:
            connection.close()

    def execute_many(self, statements, atomic=True, max_rows=1000):
        """Run several statements on one connection.

        With ``atomic`` set, a failure rolls the whole batch back and nothing is
        synced to the store -- which is what makes the transaction endpoint
        behave like a transaction.
        """
        for entry in statements:
            candidate = (entry.get("sql") or "").strip()
            if _FORBIDDEN.match(candidate):
                raise SqlError(FEATURE_NOT_SUPPORTED,
                               "statement is not permitted on this service",
                               candidate)
        connection = self.connect()
        results, wrote = [], False
        try:
            for index, entry in enumerate(statements):
                statement = self.rewrite((entry.get("sql") or "").strip())
                started = time.perf_counter()
                try:
                    cursor = connection.execute(statement, _bind(entry.get("params")))
                except sqlite3.Error as exc:
                    error = _classify(exc, statement)
                    if atomic:
                        connection.rollback()
                        error.statement_index = index
                        raise error
                    results.append({"error": error.kind, "message": error.message,
                                    "statement_index": index})
                    continue
                harvested = _harvest(cursor, max_rows, _statement_type(statement))
                harvested["duration_ms"] = round(
                    (time.perf_counter() - started) * 1000, 3)
                harvested["statement_index"] = index
                results.append(harvested)
                wrote = wrote or self.is_write(statement)
            connection.commit()
            if wrote:
                self._sync_back(connection)
            return results
        finally:
            connection.close()

    def explain(self, sql, params=None):
        """`EXPLAIN QUERY PLAN` rows for a statement."""
        statement = (sql or "").strip()
        if _FORBIDDEN.match(statement):
            raise SqlError(FEATURE_NOT_SUPPORTED,
                           "statement is not permitted on this service", statement)
        connection = self.connect()
        try:
            try:
                cursor = connection.execute(
                    f"EXPLAIN QUERY PLAN {self.rewrite(statement)}", _bind(params))
            except sqlite3.Error as exc:
                raise _classify(exc, statement)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    def query_all(self, sql, params=None):
        """Convenience read used by the metadata endpoints."""
        connection = self.connect()
        try:
            try:
                cursor = connection.execute(sql, _bind(params))
            except sqlite3.Error as exc:
                raise _classify(exc, sql)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    @staticmethod
    def is_write(sql):
        head = re.sub(r"^\s*(with\b.*?\)\s*)?", "", (sql or "").strip(),
                      flags=re.IGNORECASE | re.DOTALL)
        return head.lower().startswith(_WRITE_PREFIXES)


def _bind(params):
    """Accept a positional list or a named dict, as every driver does."""
    if params is None:
        return []
    if isinstance(params, dict):
        return params
    return list(params)


def _statement_type(sql):
    match = re.match(r"\s*(\w+)", sql or "")
    return match.group(1).lower() if match else "unknown"


def _harvest(cursor, max_rows, statement_type):
    columns = [description[0] for description in (cursor.description or [])]
    rows, truncated = [], False
    if cursor.description:
        fetched = cursor.fetchmany(max_rows + 1)
        if len(fetched) > max_rows:
            fetched, truncated = fetched[:max_rows], True
        rows = [[_scalar(value) for value in row] for row in fetched]
    # `lastrowid` survives on the connection from seeding, so it is only
    # meaningful for a statement that actually inserted a row.
    inserted = statement_type in ("insert", "replace")
    return {
        "columns": columns,
        "types": _column_types(rows, columns),
        "rows": rows,
        "row_count": len(rows),
        "rows_affected": cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0,
        "last_insert_id": cursor.lastrowid if inserted and cursor.lastrowid else None,
        "statement_type": statement_type,
        "truncated": truncated,
    }


def _scalar(value):
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def _column_types(rows, columns):
    """Infer a type per column from the first non-null value in the result."""
    types = []
    for index in range(len(columns)):
        kind = "null"
        for row in rows:
            value = row[index]
            if value is None:
                continue
            kind = {bool: "integer", int: "integer", float: "real",
                    str: "text"}.get(type(value), "blob")
            break
        types.append(kind)
    return types


_UNIQUE_RE = re.compile(r"UNIQUE constraint failed: (.+)", re.IGNORECASE)
_NOT_NULL_RE = re.compile(r"NOT NULL constraint failed: (.+)", re.IGNORECASE)
_NO_TABLE_RE = re.compile(r"no such table: (\S+)", re.IGNORECASE)
_NO_COLUMN_RE = re.compile(r"no such column: (\S+)", re.IGNORECASE)


def _classify(exc, statement):
    """Turn a sqlite3 exception into a dialect-neutral SqlError."""
    message = str(exc)
    if isinstance(exc, sqlite3.IntegrityError):
        if _UNIQUE_RE.search(message):
            return SqlError(UNIQUE_VIOLATION, message, statement)
        if "FOREIGN KEY constraint failed" in message:
            return SqlError(FOREIGN_KEY_VIOLATION, message, statement)
        if _NOT_NULL_RE.search(message):
            return SqlError(NOT_NULL_VIOLATION, message, statement)
        if "CHECK constraint failed" in message:
            return SqlError(CHECK_VIOLATION, message, statement)
        return SqlError(CHECK_VIOLATION, message, statement)
    if isinstance(exc, sqlite3.OperationalError):
        if _NO_TABLE_RE.search(message):
            return SqlError(UNDEFINED_TABLE, message, statement)
        if _NO_COLUMN_RE.search(message):
            return SqlError(UNDEFINED_COLUMN, message, statement)
        if "syntax error" in message.lower() or "incomplete input" in message.lower():
            return SqlError(SYNTAX_ERROR, message, statement)
        return SqlError(SYNTAX_ERROR, message, statement)
    if isinstance(exc, sqlite3.ProgrammingError):
        if "supplied" in message and "bindings" in message:
            return SqlError(SYNTAX_ERROR, message, statement)
        return SqlError(SYNTAX_ERROR, message, statement)
    if isinstance(exc, sqlite3.InterfaceError):
        return SqlError(DATATYPE_MISMATCH, message, statement)
    return SqlError(INTERNAL_ERROR, message, statement)
