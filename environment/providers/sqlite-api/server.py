"""FastAPI server wrapping sqlite_data module as REST endpoints.

A SQLite database served over HTTP. Statements are executed by a real SQLite
engine, so joins, aggregates, CTEs, constraints and query plans behave the way a
database behaves rather than being pattern-matched.

`/api/v1/query` is read-only, `/api/v1/execute` may write, and
`/api/v1/transaction` runs a batch atomically. The rest of the surface is
SQLite-specific: `EXPLAIN QUERY PLAN`, PRAGMAs, `sqlite_master` DDL and the
database-file statistics.

The `X-API-Key` header (or a bearer token) selects access: the read-only key
refuses writes, any other token is read/write.
"""

from fastapi import Body, FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Union

import sqlite_data
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

app = FastAPI(title="SQLite API (Mock)", version="3.45.3")
install_tracker(app)
install_admin_plane(app, store=sqlite_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    status = result.pop("status", 400)
    return JSONResponse(status_code=status, content=result)


def _access(api_key, authorization):
    return sqlite_data.resolve_access(api_key=api_key, authorization=authorization)


# --- Health ---

@app.get("/health/db")
def health_db():
    return sqlite_data.health_db()


# --- Statement execution ---

class StatementBody(BaseModel):
    sql: str
    params: Optional[Union[List[Any], Dict[str, Any]]] = None
    max_rows: Optional[int] = 1000


@app.post("/api/v1/query")
def query(body: StatementBody, x_api_key: Optional[str] = Header(None),
          authorization: Optional[str] = Header(None)):
    result = sqlite_data.query(body.sql, params=body.params,
                               max_rows=body.max_rows or 1000,
                               access=_access(x_api_key, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/execute")
def execute(body: StatementBody, x_api_key: Optional[str] = Header(None),
            authorization: Optional[str] = Header(None)):
    result = sqlite_data.execute(body.sql, params=body.params,
                                 max_rows=body.max_rows or 1000,
                                 access=_access(x_api_key, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class TransactionStatement(BaseModel):
    sql: str
    params: Optional[Union[List[Any], Dict[str, Any]]] = None


class TransactionBody(BaseModel):
    statements: List[TransactionStatement]
    atomic: Optional[bool] = True


@app.post("/api/v1/transaction")
def transaction(body: TransactionBody, x_api_key: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    result = sqlite_data.transaction(
        [s.model_dump() for s in body.statements], atomic=body.atomic,
        access=_access(x_api_key, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/explain")
def explain(body: StatementBody):
    result = sqlite_data.explain(body.sql, params=body.params)
    if _is_error(result):
        return _fail(result)
    return result


# --- Schema introspection ---

@app.get("/api/v1/tables")
def list_tables(include_views: bool = Query(True)):
    return sqlite_data.list_tables(include_views=include_views)


@app.get("/api/v1/tables/{name}")
def describe_table(name: str):
    result = sqlite_data.describe_table(name)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/indexes")
def list_indexes():
    return sqlite_data.list_indexes()


@app.get("/api/v1/schema")
def dump_schema():
    return sqlite_data.dump_schema()


# --- Database file ---

@app.get("/api/v1/database")
def database_info():
    return sqlite_data.database_info()


@app.get("/api/v1/pragma/{name}")
def pragma(name: str):
    result = sqlite_data.pragma(name)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/integrity-check")
def integrity_check():
    return sqlite_data.integrity_check()
