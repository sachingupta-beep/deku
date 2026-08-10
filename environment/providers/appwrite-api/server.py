"""FastAPI server wrapping appwrite_data module as REST endpoints.

Mirrors a subset of the Appwrite API. Base path: /v1
Covers Databases, Storage, Functions, Teams, Users, Account, Locale and Health.

Auth headers follow Appwrite: `X-Appwrite-Project` selects the project,
`X-Appwrite-Key` is a server key that bypasses permissions, and
`X-Appwrite-Session` / `X-Appwrite-JWT` authenticate as the project's session
user. Without any of them the caller is a guest and sees only `read("any")` rows.
"""

from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional

import appwrite_data
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

app = FastAPI(title="Appwrite API (Mock)", version="1.6.0")
install_tracker(app)
install_admin_plane(app, store=appwrite_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result.get("code", 400), content=result)


def _ctx(request, project, key, session, jwt):
    """Resolve (project_error, scope, user_id) and the effective query list."""
    error = appwrite_data.check_project(project)
    scope, user_id = appwrite_data.resolve_scope(api_key=key, session=session, jwt=jwt)
    queries = request.query_params.getlist("queries[]") + \
        request.query_params.getlist("queries")
    return error, scope, user_id, queries


# --- Health / locale / project ---

@app.get("/v1/health")
def api_health():
    return appwrite_data.health()


@app.get("/v1/health/db")
def api_health_db():
    return appwrite_data.health_db()


@app.get("/v1/health/storage")
def api_health_storage():
    return appwrite_data.health_storage()


@app.get("/v1/locale")
def get_locale(x_appwrite_project: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    return appwrite_data.get_locale()


@app.get("/v1/project")
def get_project(x_appwrite_project: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    return appwrite_data.get_project()


# --- Databases ---

@app.get("/v1/databases")
def list_databases(request: Request,
                   queries: Optional[List[str]] = Query(None, alias="queries[]"),
                   x_appwrite_project: Optional[str] = Header(None),
                   x_appwrite_key: Optional[str] = Header(None),
                   x_appwrite_session: Optional[str] = Header(None),
                   x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_databases(queries=qs, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/databases/{database_id}")
def get_database(database_id: str,
                 x_appwrite_project: Optional[str] = Header(None),
                 x_appwrite_key: Optional[str] = Header(None),
                 x_appwrite_session: Optional[str] = Header(None),
                 x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_database(database_id, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/databases/{database_id}/collections")
def list_collections(database_id: str, request: Request,
                     queries: Optional[List[str]] = Query(None, alias="queries[]"),
                     x_appwrite_project: Optional[str] = Header(None),
                     x_appwrite_key: Optional[str] = Header(None),
                     x_appwrite_session: Optional[str] = Header(None),
                     x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_collections(database_id, queries=qs, scope=scope,
                                            user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/databases/{database_id}/collections/{collection_id}")
def get_collection(database_id: str, collection_id: str,
                   x_appwrite_project: Optional[str] = Header(None),
                   x_appwrite_key: Optional[str] = Header(None),
                   x_appwrite_session: Optional[str] = Header(None),
                   x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_collection(database_id, collection_id, scope=scope,
                                          user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Documents ---

@app.get("/v1/databases/{database_id}/collections/{collection_id}/documents")
def list_documents(database_id: str, collection_id: str, request: Request,
                   queries: Optional[List[str]] = Query(None, alias="queries[]"),
                   x_appwrite_project: Optional[str] = Header(None),
                   x_appwrite_key: Optional[str] = Header(None),
                   x_appwrite_session: Optional[str] = Header(None),
                   x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_documents(database_id, collection_id, queries=qs,
                                          scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


class DocumentCreateBody(BaseModel):
    documentId: Optional[str] = "unique()"
    data: Dict[str, Any]
    permissions: Optional[List[str]] = None


@app.post("/v1/databases/{database_id}/collections/{collection_id}/documents",
          status_code=201)
def create_document(database_id: str, collection_id: str, body: DocumentCreateBody,
                    x_appwrite_project: Optional[str] = Header(None),
                    x_appwrite_key: Optional[str] = Header(None),
                    x_appwrite_session: Optional[str] = Header(None),
                    x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.create_document(
        database_id, collection_id, document_id=body.documentId, data=body.data,
        permissions=body.permissions, scope=scope, user_id=user_id,
    )
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/databases/{database_id}/collections/{collection_id}/documents/{document_id}")
def get_document(database_id: str, collection_id: str, document_id: str,
                 x_appwrite_project: Optional[str] = Header(None),
                 x_appwrite_key: Optional[str] = Header(None),
                 x_appwrite_session: Optional[str] = Header(None),
                 x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_document(database_id, collection_id, document_id,
                                        scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


class DocumentUpdateBody(BaseModel):
    data: Optional[Dict[str, Any]] = None
    permissions: Optional[List[str]] = None


@app.patch("/v1/databases/{database_id}/collections/{collection_id}/documents/{document_id}")
def update_document(database_id: str, collection_id: str, document_id: str,
                    body: DocumentUpdateBody,
                    x_appwrite_project: Optional[str] = Header(None),
                    x_appwrite_key: Optional[str] = Header(None),
                    x_appwrite_session: Optional[str] = Header(None),
                    x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.update_document(
        database_id, collection_id, document_id, data=body.data,
        permissions=body.permissions, scope=scope, user_id=user_id,
    )
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/v1/databases/{database_id}/collections/{collection_id}/documents/{document_id}")
def delete_document(database_id: str, collection_id: str, document_id: str,
                    x_appwrite_project: Optional[str] = Header(None),
                    x_appwrite_key: Optional[str] = Header(None),
                    x_appwrite_session: Optional[str] = Header(None),
                    x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.delete_document(database_id, collection_id, document_id,
                                           scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Storage ---

@app.get("/v1/storage/buckets")
def list_buckets(request: Request,
                 queries: Optional[List[str]] = Query(None, alias="queries[]"),
                 x_appwrite_project: Optional[str] = Header(None),
                 x_appwrite_key: Optional[str] = Header(None),
                 x_appwrite_session: Optional[str] = Header(None),
                 x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_buckets(queries=qs, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/storage/buckets/{bucket_id}")
def get_bucket(bucket_id: str,
               x_appwrite_project: Optional[str] = Header(None),
               x_appwrite_key: Optional[str] = Header(None),
               x_appwrite_session: Optional[str] = Header(None),
               x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_bucket(bucket_id, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/storage/buckets/{bucket_id}/files")
def list_files(bucket_id: str, request: Request,
               queries: Optional[List[str]] = Query(None, alias="queries[]"),
               x_appwrite_project: Optional[str] = Header(None),
               x_appwrite_key: Optional[str] = Header(None),
               x_appwrite_session: Optional[str] = Header(None),
               x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_files(bucket_id, queries=qs, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/storage/buckets/{bucket_id}/files/{file_id}")
def get_file(bucket_id: str, file_id: str,
             x_appwrite_project: Optional[str] = Header(None),
             x_appwrite_key: Optional[str] = Header(None),
             x_appwrite_session: Optional[str] = Header(None),
             x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_file(bucket_id, file_id, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/v1/storage/buckets/{bucket_id}/files/{file_id}")
def delete_file(bucket_id: str, file_id: str,
                x_appwrite_project: Optional[str] = Header(None),
                x_appwrite_key: Optional[str] = Header(None),
                x_appwrite_session: Optional[str] = Header(None),
                x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.delete_file(bucket_id, file_id, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Functions ---

@app.get("/v1/functions")
def list_functions(request: Request,
                   queries: Optional[List[str]] = Query(None, alias="queries[]"),
                   x_appwrite_project: Optional[str] = Header(None),
                   x_appwrite_key: Optional[str] = Header(None),
                   x_appwrite_session: Optional[str] = Header(None),
                   x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_functions(queries=qs, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/functions/{function_id}")
def get_function(function_id: str,
                 x_appwrite_project: Optional[str] = Header(None),
                 x_appwrite_key: Optional[str] = Header(None),
                 x_appwrite_session: Optional[str] = Header(None),
                 x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_function(function_id, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/functions/{function_id}/executions")
def list_executions(function_id: str, request: Request,
                    queries: Optional[List[str]] = Query(None, alias="queries[]"),
                    x_appwrite_project: Optional[str] = Header(None),
                    x_appwrite_key: Optional[str] = Header(None),
                    x_appwrite_session: Optional[str] = Header(None),
                    x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_executions(function_id, queries=qs, scope=scope,
                                           user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


class ExecutionCreateBody(BaseModel):
    body: Optional[Dict[str, Any]] = None
    path: Optional[str] = "/"
    method: Optional[str] = "POST"
    # `async` is a Python keyword, so the wire name is carried by an alias.
    async_: Optional[bool] = Field(default=False, alias="async")

    model_config = ConfigDict(populate_by_name=True)


@app.post("/v1/functions/{function_id}/executions", status_code=201)
def create_execution(function_id: str,
                     body: ExecutionCreateBody = Body(default=ExecutionCreateBody()),
                     x_appwrite_project: Optional[str] = Header(None),
                     x_appwrite_key: Optional[str] = Header(None),
                     x_appwrite_session: Optional[str] = Header(None),
                     x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.create_execution(
        function_id, body=body.body, path=body.path, method=body.method,
        async_=body.async_, scope=scope, user_id=user_id,
    )
    if _is_error(result):
        return _fail(result)
    return result


# --- Teams ---

@app.get("/v1/teams")
def list_teams(request: Request,
               queries: Optional[List[str]] = Query(None, alias="queries[]"),
               x_appwrite_project: Optional[str] = Header(None),
               x_appwrite_key: Optional[str] = Header(None),
               x_appwrite_session: Optional[str] = Header(None),
               x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_teams(queries=qs, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/teams/{team_id}")
def get_team(team_id: str,
             x_appwrite_project: Optional[str] = Header(None),
             x_appwrite_key: Optional[str] = Header(None),
             x_appwrite_session: Optional[str] = Header(None),
             x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_team(team_id, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/teams/{team_id}/memberships")
def list_memberships(team_id: str, request: Request,
                     queries: Optional[List[str]] = Query(None, alias="queries[]"),
                     x_appwrite_project: Optional[str] = Header(None),
                     x_appwrite_key: Optional[str] = Header(None),
                     x_appwrite_session: Optional[str] = Header(None),
                     x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_memberships(team_id, queries=qs, scope=scope,
                                            user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Users / account ---

@app.get("/v1/users")
def list_users(request: Request,
               queries: Optional[List[str]] = Query(None, alias="queries[]"),
               x_appwrite_project: Optional[str] = Header(None),
               x_appwrite_key: Optional[str] = Header(None),
               x_appwrite_session: Optional[str] = Header(None),
               x_appwrite_jwt: Optional[str] = Header(None)):
    err, scope, user_id, qs = _ctx(request, x_appwrite_project, x_appwrite_key,
                                   x_appwrite_session, x_appwrite_jwt)
    if err:
        return _fail(err)
    result = appwrite_data.list_users(queries=qs, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/users/{target_id}")
def get_user(target_id: str,
             x_appwrite_project: Optional[str] = Header(None),
             x_appwrite_key: Optional[str] = Header(None),
             x_appwrite_session: Optional[str] = Header(None),
             x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_user(target_id, scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/account")
def get_account(x_appwrite_project: Optional[str] = Header(None),
                x_appwrite_key: Optional[str] = Header(None),
                x_appwrite_session: Optional[str] = Header(None),
                x_appwrite_jwt: Optional[str] = Header(None)):
    err = appwrite_data.check_project(x_appwrite_project)
    if err:
        return _fail(err)
    scope, user_id = appwrite_data.resolve_scope(x_appwrite_key, x_appwrite_session,
                                                 x_appwrite_jwt)
    result = appwrite_data.get_account(scope=scope, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result
