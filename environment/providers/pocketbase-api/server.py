"""FastAPI server wrapping pocketbase_data module as REST endpoints.

Mirrors a subset of the PocketBase API. Base path: /api
Records live under /api/collections/{collection}/records; the auth endpoints
(auth-with-password, auth-refresh, OAuth2) are served by `pocketbase-auth-api`.

The `Authorization` header carries a PocketBase token (with or without the
`Bearer` prefix): the superuser token bypasses collection rules, any other
token authenticates as the seeded user record, and no token is a guest.
"""

from fastapi import Body, FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

import pocketbase_data
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

app = FastAPI(title="PocketBase API (Mock)", version="v0.24.4")
install_tracker(app)
install_admin_plane(app, store=pocketbase_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result.get("code", 400), content=result)


def _identity(authorization):
    return pocketbase_data.resolve_identity(authorization)


# --- Health (PocketBase native) ---

@app.get("/api/health")
def api_health():
    return pocketbase_data.health()


# --- Collections ---

@app.get("/api/collections")
def list_collections(page: int = Query(1, ge=1), perPage: int = Query(30, ge=1, le=500),
                     authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.list_collections(page=page, per_page=perPage,
                                              kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/collections/{collection}")
def get_collection(collection: str, authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.get_collection(collection, kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Records ---

@app.get("/api/collections/{collection}/records")
def list_records(collection: str, page: int = Query(1, ge=1),
                 perPage: int = Query(30, ge=1, le=500),
                 sort: Optional[str] = None, filter: Optional[str] = None,
                 expand: Optional[str] = None, fields: Optional[str] = None,
                 skipTotal: bool = False,
                 authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.list_records(
        collection, page=page, per_page=perPage, sort=sort, filter_expr=filter,
        expand=expand, fields=fields, skip_total=skipTotal, kind=kind, auth_id=auth_id,
    )
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/collections/{collection}/records/{record_id}")
def get_record(collection: str, record_id: str, expand: Optional[str] = None,
               fields: Optional[str] = None,
               authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.get_record(collection, record_id, expand=expand,
                                        fields=fields, kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/collections/{collection}/records")
def create_record(collection: str, body: Dict[str, Any] = Body(...),
                  authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.create_record(collection, body, kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.patch("/api/collections/{collection}/records/{record_id}")
def update_record(collection: str, record_id: str, body: Dict[str, Any] = Body(...),
                  authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.update_record(collection, record_id, body,
                                           kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/api/collections/{collection}/records/{record_id}")
def delete_record(collection: str, record_id: str,
                  authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.delete_record(collection, record_id,
                                           kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Files ---

@app.get("/api/files/{collection}/{record_id}/{filename}")
def get_file(collection: str, record_id: str, filename: str,
             thumb: Optional[str] = None):
    result = pocketbase_data.get_file(collection, record_id, filename, thumb=thumb)
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/files/token")
def create_file_token(authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.create_file_token(kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Logs ---

@app.get("/api/logs")
def list_logs(page: int = Query(1, ge=1), perPage: int = Query(30, ge=1, le=500),
              filter: Optional[str] = None, sort: str = "-created",
              authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.list_logs(page=page, per_page=perPage, filter_expr=filter,
                                       sort=sort, kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/logs/stats")
def log_stats(filter: Optional[str] = None,
              authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.log_stats(filter_expr=filter, kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Backups ---

@app.get("/api/backups")
def list_backups(authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.list_backups(kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


class BackupCreateBody(BaseModel):
    name: Optional[str] = None


@app.post("/api/backups")
def create_backup(body: BackupCreateBody = Body(default=BackupCreateBody()),
                  authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.create_backup(name=body.name, kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/api/backups/{key}")
def delete_backup(key: str, authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.delete_backup(key, kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Crons / settings ---

@app.get("/api/crons")
def list_crons(authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.list_crons(kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/settings")
def get_settings(authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.get_settings(kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Realtime ---

class SubscribeBody(BaseModel):
    clientId: Optional[str] = None
    subscriptions: Optional[List[str]] = None


@app.post("/api/realtime")
def subscribe(body: SubscribeBody = Body(default=SubscribeBody()),
              authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.subscribe(client_id=body.clientId,
                                       subscriptions=body.subscriptions,
                                       kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/realtime")
def list_subscriptions(authorization: Optional[str] = Header(None)):
    kind, auth_id = _identity(authorization)
    result = pocketbase_data.list_subscriptions(kind=kind, auth_id=auth_id)
    if _is_error(result):
        return _fail(result)
    return result
