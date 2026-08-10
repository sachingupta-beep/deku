"""FastAPI server wrapping directus_data module as REST endpoints.

Mirrors a subset of the Directus API: /items, /collections, /fields, /users,
/roles, /permissions, /files, /activity, /flows, /settings, /auth and /server.

Static tokens select the role: the admin token bypasses the permission table,
the editor token (or any other token) authenticates as the Editor role, and no
token resolves to the Public role. Directus accepts the token either as
`Authorization: Bearer <token>` or as an `access_token` query parameter.
"""

from fastapi import Body, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional

import directus_data
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

app = FastAPI(title="Directus API (Mock)", version="11.1.1")
install_tracker(app)
install_admin_plane(app, store=directus_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result.get("status", 400),
                        content={"errors": result["errors"]})


def _identity(authorization, access_token):
    return directus_data.resolve_identity(authorization=authorization,
                                          access_token=access_token)


# --- Server ---

@app.get("/server/ping")
def server_ping():
    return Response(content="pong", media_type="text/plain")


@app.get("/server/health")
def server_health():
    return directus_data.server_health()


@app.get("/server/info")
def server_info():
    return directus_data.server_info()


# --- Auth ---

class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/auth/login")
def login(body: LoginBody):
    result = directus_data.login(email=body.email, password=body.password)
    if _is_error(result):
        return _fail(result)
    return result


# --- Items ---

@app.get("/items/{collection}")
def list_items(collection: str, filter: Optional[str] = None,
               fields: Optional[str] = None, sort: Optional[str] = None,
               search: Optional[str] = None, limit: int = 100, offset: int = 0,
               page: Optional[int] = None, meta: Optional[str] = None,
               aggregate: Optional[str] = None, groupBy: Optional[str] = None,
               access_token: Optional[str] = Query(None),
               authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_items(
        collection, filter_json=filter, fields=fields, sort=sort, search=search,
        limit=limit, offset=offset, page=page, meta=meta, aggregate_json=aggregate,
        group_by=groupBy, role_id=role_id, kind=kind,
    )
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/items/{collection}")
def create_item(collection: str, body: Dict[str, Any] = Body(...),
                access_token: Optional[str] = Query(None),
                authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.create_item(collection, body, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/items/{collection}/{item_id}")
def get_item(collection: str, item_id: str, fields: Optional[str] = None,
             access_token: Optional[str] = Query(None),
             authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.get_item(collection, item_id, fields=fields,
                                    role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.patch("/items/{collection}/{item_id}")
def update_item(collection: str, item_id: str, body: Dict[str, Any] = Body(...),
                access_token: Optional[str] = Query(None),
                authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.update_item(collection, item_id, body,
                                       role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/items/{collection}/{item_id}", status_code=204)
def delete_item(collection: str, item_id: str,
                access_token: Optional[str] = Query(None),
                authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.delete_item(collection, item_id, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return Response(status_code=204)


# --- Schema ---

@app.get("/collections")
def list_collections(access_token: Optional[str] = Query(None),
                     authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_collections(role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/collections/{collection}")
def get_collection(collection: str, access_token: Optional[str] = Query(None),
                   authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.get_collection(collection, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/fields")
def list_fields(access_token: Optional[str] = Query(None),
                authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_fields(role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/fields/{collection}")
def list_collection_fields(collection: str, access_token: Optional[str] = Query(None),
                           authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_fields(collection=collection, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


# --- Users / roles / permissions ---

@app.get("/users/me")
def get_me(access_token: Optional[str] = Query(None),
           authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.get_me(user_id, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/users")
def list_users(filter: Optional[str] = None, fields: Optional[str] = None,
               sort: Optional[str] = None, limit: int = 100, offset: int = 0,
               access_token: Optional[str] = Query(None),
               authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_users(filter_json=filter, fields=fields, sort=sort,
                                      limit=limit, offset=offset, role_id=role_id,
                                      kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/users/{target_id}")
def get_user(target_id: str, access_token: Optional[str] = Query(None),
             authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.get_user(target_id, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/roles")
def list_roles(access_token: Optional[str] = Query(None),
               authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_roles(role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/roles/{target_id}")
def get_role(target_id: str, access_token: Optional[str] = Query(None),
             authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.get_role(target_id, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/permissions")
def list_permissions(access_token: Optional[str] = Query(None),
                     authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_permissions(role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


# --- Files / activity / flows / settings ---

@app.get("/files")
def list_files(filter: Optional[str] = None, sort: Optional[str] = None,
               limit: int = 100, offset: int = 0,
               access_token: Optional[str] = Query(None),
               authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_files(filter_json=filter, sort=sort, limit=limit,
                                      offset=offset, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/files/{file_id}")
def get_file(file_id: str, access_token: Optional[str] = Query(None),
             authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.get_file(file_id, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/activity")
def list_activity(filter: Optional[str] = None, sort: str = "-timestamp",
                  limit: int = 100, offset: int = 0,
                  access_token: Optional[str] = Query(None),
                  authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_activity(filter_json=filter, sort=sort, limit=limit,
                                         offset=offset, role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/flows")
def list_flows(access_token: Optional[str] = Query(None),
               authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.list_flows(role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/settings")
def get_settings(access_token: Optional[str] = Query(None),
                 authorization: Optional[str] = Header(None)):
    kind, user_id, role_id = _identity(authorization, access_token)
    result = directus_data.get_settings(role_id=role_id, kind=kind)
    if _is_error(result):
        return _fail(result)
    return result
