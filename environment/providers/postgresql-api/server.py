"""FastAPI server wrapping postgresql_data module as REST endpoints.

A PostgreSQL database served over HTTP. Statements are executed by a real SQL
engine, so joins, aggregates, CTEs, window functions, constraints and query
plans behave the way a database behaves.

The surface is PostgreSQL throughout: SQLSTATE error reports,
`information_schema` and `pg_catalog` views, `EXPLAIN (ANALYZE, BUFFERS)` node
trees, role GRANTs, extensions, settings and replication state.

The `X-DB-Role` header (or a bearer token) selects the cluster role the
statement runs as, and table-level GRANTs are enforced against it.
"""

from fastapi import Body, FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Union

import postgresql_data
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

app = FastAPI(title="PostgreSQL API (Mock)", version="15.6")
install_tracker(app)
install_admin_plane(app, store=postgresql_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    status = result.pop("status", 400)
    return JSONResponse(status_code=status, content=result)


def _role(db_role, authorization):
    return postgresql_data.resolve_role(db_role=db_role, authorization=authorization)


# --- Health / version ---

@app.get("/health/db")
def health_db():
    return postgresql_data.health_db()


@app.get("/api/v1/version")
def version():
    return postgresql_data.version()


# --- Statement execution ---

class StatementBody(BaseModel):
    sql: str
    params: Optional[Union[List[Any], Dict[str, Any]]] = None
    max_rows: Optional[int] = 1000


@app.post("/api/v1/query")
def query(body: StatementBody, x_db_role: Optional[str] = Header(None),
          authorization: Optional[str] = Header(None)):
    result = postgresql_data.query(body.sql, params=body.params,
                                   max_rows=body.max_rows or 1000,
                                   role=_role(x_db_role, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/execute")
def execute(body: StatementBody, x_db_role: Optional[str] = Header(None),
            authorization: Optional[str] = Header(None)):
    result = postgresql_data.execute(body.sql, params=body.params,
                                     max_rows=body.max_rows or 1000,
                                     role=_role(x_db_role, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class TransactionStatement(BaseModel):
    sql: str
    params: Optional[Union[List[Any], Dict[str, Any]]] = None


class TransactionBody(BaseModel):
    statements: List[TransactionStatement]
    isolation_level: Optional[str] = "read committed"


@app.post("/api/v1/transaction")
def transaction(body: TransactionBody, x_db_role: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    result = postgresql_data.transaction(
        [s.model_dump() for s in body.statements],
        isolation_level=body.isolation_level,
        role=_role(x_db_role, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class ExplainBody(BaseModel):
    sql: str
    analyze: Optional[bool] = False
    buffers: Optional[bool] = False
    format: Optional[str] = "json"


@app.post("/api/v1/explain")
def explain(body: ExplainBody, x_db_role: Optional[str] = Header(None),
            authorization: Optional[str] = Header(None)):
    result = postgresql_data.explain(body.sql, analyze=body.analyze,
                                     buffers=body.buffers, fmt=body.format,
                                     role=_role(x_db_role, authorization))
    if _is_error(result):
        return _fail(result)
    return result


# --- information_schema ---

@app.get("/api/v1/schemas")
def list_schemas():
    return postgresql_data.list_schemas()


@app.get("/api/v1/tables")
def list_tables(x_db_role: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    return postgresql_data.list_tables(role=_role(x_db_role, authorization))


@app.get("/api/v1/tables/{name}")
def describe_table(name: str, x_db_role: Optional[str] = Header(None),
                   authorization: Optional[str] = Header(None)):
    result = postgresql_data.describe_table(name, role=_role(x_db_role, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/indexes")
def list_indexes():
    return postgresql_data.list_indexes()


# --- pg_catalog ---

@app.get("/api/v1/catalog/pg_stat_activity")
def stat_activity(x_db_role: Optional[str] = Header(None),
                  authorization: Optional[str] = Header(None)):
    return postgresql_data.stat_activity(role=_role(x_db_role, authorization))


@app.get("/api/v1/catalog/pg_stat_statements")
def stat_statements(order_by: str = Query("total_exec_time"),
                    limit: int = Query(10, ge=1, le=100),
                    x_db_role: Optional[str] = Header(None),
                    authorization: Optional[str] = Header(None)):
    result = postgresql_data.stat_statements(order_by=order_by, limit=limit,
                                             role=_role(x_db_role, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/catalog/pg_stat_user_tables")
def stat_user_tables():
    return postgresql_data.stat_user_tables()


@app.get("/api/v1/catalog/pg_stat_replication")
def stat_replication(x_db_role: Optional[str] = Header(None),
                     authorization: Optional[str] = Header(None)):
    return postgresql_data.stat_replication(role=_role(x_db_role, authorization))


@app.get("/api/v1/catalog/pg_settings")
def list_settings(name: Optional[str] = None):
    result = postgresql_data.list_settings(name=name)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/catalog/pg_extension")
def list_extensions():
    return postgresql_data.list_extensions()


@app.get("/api/v1/catalog/pg_roles")
def list_roles():
    return postgresql_data.list_roles()


@app.get("/api/v1/catalog/grants")
def list_grants(role: Optional[str] = None):
    return postgresql_data.list_grants(role=role)


# --- Database ---

@app.get("/api/v1/database")
def database_info():
    return postgresql_data.database_info()
