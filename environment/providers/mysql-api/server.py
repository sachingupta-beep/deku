"""FastAPI server wrapping mysql_data module as REST endpoints.

A MySQL 8 database served over HTTP. Statements are executed by a real SQL
engine, so joins, aggregates, subqueries, constraints and query plans behave the
way a database behaves.

The surface is MySQL throughout: vendor error numbers alongside SQLSTATE,
`SHOW`-style metadata, `information_schema.TABLES` columns, `EXPLAIN` in the
traditional column format or as JSON, and `'user'@'host'` accounts with
per-table grants.

The `X-MySQL-User` header (or a bearer token) selects the account the statement
runs as; grants and the PROCESS privilege are enforced against it.
"""

from fastapi import Body, FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Union

import mysql_data
try:
    from tracking_middleware import install_tracker
    from admin_plane import install_admin_plane
except ModuleNotFoundError as _shared_plane_err:  # standalone run without the shared module on sys.path
    import logging as _logging
    _logging.error("SHARED PLANE MISSING - audit + admin disabled: %s", _shared_plane_err)
    def install_tracker(app):  # no-op fallback: audit endpoints disabled
        return None

    def install_admin_plane(app, store=None, one_shot_registry=None):
        return None

app = FastAPI(title="MySQL API (Mock)", version="8.0.36")
install_tracker(app)
install_admin_plane(app, store=mysql_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    status = result.pop("status", 400)
    return JSONResponse(status_code=status, content=result)


def _user(mysql_user, authorization):
    return mysql_data.resolve_user(mysql_user=mysql_user, authorization=authorization)


# --- Health / version ---

@app.get("/health/db")
def health_db():
    return mysql_data.health_db()


@app.get("/api/v1/version")
def version():
    return mysql_data.version()


@app.get("/api/v1/status")
def server_status():
    return mysql_data.server_status()


# --- Statement execution ---

class StatementBody(BaseModel):
    sql: str
    params: Optional[Union[List[Any], Dict[str, Any]]] = None
    max_rows: Optional[int] = 1000


@app.post("/api/v1/query")
def query(body: StatementBody, x_mysql_user: Optional[str] = Header(None),
          authorization: Optional[str] = Header(None)):
    result = mysql_data.query(body.sql, params=body.params,
                              max_rows=body.max_rows or 1000,
                              user=_user(x_mysql_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/execute")
def execute(body: StatementBody, x_mysql_user: Optional[str] = Header(None),
            authorization: Optional[str] = Header(None)):
    result = mysql_data.execute(body.sql, params=body.params,
                                max_rows=body.max_rows or 1000,
                                user=_user(x_mysql_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class TransactionStatement(BaseModel):
    sql: str
    params: Optional[Union[List[Any], Dict[str, Any]]] = None


class TransactionBody(BaseModel):
    statements: List[TransactionStatement]
    isolation_level: Optional[str] = "REPEATABLE READ"


@app.post("/api/v1/transaction")
def transaction(body: TransactionBody, x_mysql_user: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    result = mysql_data.transaction(
        [s.model_dump() for s in body.statements],
        isolation_level=body.isolation_level,
        user=_user(x_mysql_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class ExplainBody(BaseModel):
    sql: str
    format: Optional[str] = "traditional"


@app.post("/api/v1/explain")
def explain(body: ExplainBody, x_mysql_user: Optional[str] = Header(None),
            authorization: Optional[str] = Header(None)):
    result = mysql_data.explain(body.sql, fmt=body.format,
                                user=_user(x_mysql_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


# --- SHOW / information_schema ---

@app.get("/api/v1/databases")
def list_databases():
    return mysql_data.list_databases()


@app.get("/api/v1/tables")
def list_tables(x_mysql_user: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    return mysql_data.list_tables(user=_user(x_mysql_user, authorization))


@app.get("/api/v1/tables/{name}")
def describe_table(name: str, x_mysql_user: Optional[str] = Header(None),
                   authorization: Optional[str] = Header(None)):
    result = mysql_data.describe_table(name, user=_user(x_mysql_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/tables/{name}/indexes")
def table_indexes(name: str):
    result = mysql_data.table_indexes(name)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/variables")
def show_variables(like: Optional[str] = None):
    return mysql_data.show_variables(like=like)


@app.get("/api/v1/status/counters")
def show_status(like: Optional[str] = None):
    return mysql_data.show_status(like=like)


@app.get("/api/v1/processlist")
def show_processlist(x_mysql_user: Optional[str] = Header(None),
                     authorization: Optional[str] = Header(None)):
    return mysql_data.show_processlist(user=_user(x_mysql_user, authorization))


@app.get("/api/v1/engines")
def show_engines():
    return mysql_data.show_engines()


@app.get("/api/v1/replication")
def show_replication(x_mysql_user: Optional[str] = Header(None),
                     authorization: Optional[str] = Header(None)):
    result = mysql_data.show_replication(user=_user(x_mysql_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


# --- Accounts ---

@app.get("/api/v1/users")
def list_users(x_mysql_user: Optional[str] = Header(None),
               authorization: Optional[str] = Header(None)):
    return mysql_data.list_users(user=_user(x_mysql_user, authorization))


@app.get("/api/v1/grants")
def show_grants(user: Optional[str] = Query(None),
                x_mysql_user: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    result = mysql_data.show_grants(target=user,
                                    user=_user(x_mysql_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result
