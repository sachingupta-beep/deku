"""FastAPI server wrapping cockroachdb_data module as REST endpoints.

A CockroachDB 23.2 cluster served over HTTP. Statements are executed by a real
SQL engine, and the PostgreSQL SQLSTATE vocabulary is shared because CockroachDB
speaks the PostgreSQL wire protocol.

What is modelled beyond that is what makes it distributed: SERIALIZABLE
transactions with genuine 40001 retry errors, `AS OF SYSTEM TIME` historical
reads, ranges with lease holders and replica localities, nodes across regions
with one deliberately down, jobs, and cluster settings.

The `X-CRDB-User` header (or a bearer token) selects the SQL user.
"""

from fastapi import Body, FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Union

import cockroachdb_data
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

app = FastAPI(title="CockroachDB API (Mock)", version="23.2.5")
install_tracker(app)
install_admin_plane(app, store=cockroachdb_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    status = result.pop("status", 400)
    return JSONResponse(status_code=status, content=result)


def _user(crdb_user, authorization):
    return cockroachdb_data.resolve_user(crdb_user=crdb_user,
                                         authorization=authorization)


# --- Health / version ---

@app.get("/health/db")
def health_db():
    return cockroachdb_data.health_db()


@app.get("/api/v1/version")
def version():
    return cockroachdb_data.version()


# --- Statement execution ---

class StatementBody(BaseModel):
    sql: str
    params: Optional[Union[List[Any], Dict[str, Any]]] = None
    max_rows: Optional[int] = 1000
    as_of_system_time: Optional[str] = None


@app.post("/api/v1/query")
def query(body: StatementBody, x_crdb_user: Optional[str] = Header(None),
          authorization: Optional[str] = Header(None)):
    result = cockroachdb_data.query(
        body.sql, params=body.params, max_rows=body.max_rows or 1000,
        as_of_system_time=body.as_of_system_time,
        user=_user(x_crdb_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/execute")
def execute(body: StatementBody, x_crdb_user: Optional[str] = Header(None),
            authorization: Optional[str] = Header(None)):
    result = cockroachdb_data.execute(body.sql, params=body.params,
                                      max_rows=body.max_rows or 1000,
                                      user=_user(x_crdb_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class TransactionStatement(BaseModel):
    sql: str
    params: Optional[Union[List[Any], Dict[str, Any]]] = None


class TransactionBody(BaseModel):
    statements: List[TransactionStatement]
    priority: Optional[str] = "NORMAL"
    max_retries: Optional[int] = 0


@app.post("/api/v1/transaction")
def transaction(body: TransactionBody, x_crdb_user: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    result = cockroachdb_data.transaction(
        [s.model_dump() for s in body.statements], priority=body.priority,
        max_retries=body.max_retries or 0, user=_user(x_crdb_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class ExplainBody(BaseModel):
    sql: str
    analyze: Optional[bool] = False
    verbose: Optional[bool] = False


@app.post("/api/v1/explain")
def explain(body: ExplainBody, x_crdb_user: Optional[str] = Header(None),
            authorization: Optional[str] = Header(None)):
    result = cockroachdb_data.explain(body.sql, analyze=body.analyze,
                                      verbose=body.verbose,
                                      user=_user(x_crdb_user, authorization))
    if _is_error(result):
        return _fail(result)
    return result


# --- Schema ---

@app.get("/api/v1/databases")
def list_databases():
    return cockroachdb_data.list_databases()


@app.get("/api/v1/tables")
def list_tables():
    return cockroachdb_data.list_tables()


@app.get("/api/v1/tables/{name}")
def describe_table(name: str):
    result = cockroachdb_data.describe_table(name)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/tables/{name}/ranges")
def table_ranges(name: str):
    result = cockroachdb_data.show_ranges(table=name)
    if _is_error(result):
        return _fail(result)
    return result


# --- Cluster topology ---

@app.get("/api/v1/ranges")
def show_ranges():
    return cockroachdb_data.show_ranges()


@app.get("/api/v1/nodes")
def show_nodes():
    return cockroachdb_data.show_nodes()


@app.get("/api/v1/regions")
def show_regions():
    return cockroachdb_data.show_regions()


@app.get("/api/v1/jobs")
def show_jobs(status: Optional[str] = None, job_type: Optional[str] = None):
    return cockroachdb_data.show_jobs(status=status, job_type=job_type)


@app.get("/api/v1/cluster/settings")
def cluster_settings(name: Optional[str] = None):
    result = cockroachdb_data.cluster_settings(name=name)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/cluster/status")
def cluster_status():
    return cockroachdb_data.cluster_status()


@app.get("/api/v1/statements")
def statement_statistics(order_by: str = Query("count"),
                         limit: int = Query(10, ge=1, le=100)):
    result = cockroachdb_data.statement_statistics(order_by=order_by, limit=limit)
    if _is_error(result):
        return _fail(result)
    return result


# --- Users ---

@app.get("/api/v1/users")
def list_users():
    return cockroachdb_data.list_users()


@app.get("/api/v1/grants")
def show_grants(user: Optional[str] = Query(None)):
    result = cockroachdb_data.show_grants(user=user)
    if _is_error(result):
        return _fail(result)
    return result
