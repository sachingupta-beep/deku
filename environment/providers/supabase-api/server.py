"""FastAPI server wrapping supabase_data module as REST endpoints.

Implements a subset of the self-hosted Supabase surface: PostgREST at
/rest/v1, Storage at /storage/v1, Edge Functions at /functions/v1, Realtime at
/realtime/v1 and the project management read model at /v1/projects.
GoTrue (sign-up / sign-in / admin users) is served by `supabase-auth-api`.

The `apikey` header (or `Authorization: Bearer`) selects the Postgres role that
row-level security is evaluated against: absent or the anon key -> `anon`, the
service key -> `service_role`, any other token -> `authenticated`.
"""

from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Union

import supabase_data
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

app = FastAPI(title="Supabase API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=supabase_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


# --- Error mapping ---

_STATUS_BY_CODE = {
    "42P01": 404, "PGRST116": 404, "PGRST202": 404, "404": 404,
    "FunctionNotFound": 404,
    "42501": 401, "401": 401,
    "23503": 409, "Duplicate": 409, "409": 409,
    "429": 429,
}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=_STATUS_BY_CODE.get(result.get("code"), 400),
                        content=result)


def _role(apikey, authorization):
    return supabase_data.resolve_role(apikey=apikey, authorization=authorization)


def _rest_response(result, status_code=200):
    """Unwrap the PostgREST envelope into a bare array plus Content-Range."""
    if _is_error(result):
        return _fail(result)
    return JSONResponse(status_code=status_code, content=result["data"],
                        headers={"Content-Range": result["content_range"]})


# --- REST (PostgREST) ---

@app.get("/rest/v1/")
def rest_root():
    return supabase_data.rest_root()


@app.get("/rest/v1/{table}")
def rest_select(table: str, request: Request,
                select: Optional[str] = None, order: Optional[str] = None,
                limit: Optional[int] = Query(None, ge=1, le=1000), offset: int = 0,
                apikey: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    result = supabase_data.select_rows(
        table, filters=dict(request.query_params), select=select, order=order,
        limit=limit, offset=offset, role=_role(apikey, authorization),
    )
    return _rest_response(result)


@app.post("/rest/v1/rpc/{fn_name}")
def rest_rpc(fn_name: str, body: Dict[str, Any] = Body(default={}),
             apikey: Optional[str] = Header(None),
             authorization: Optional[str] = Header(None)):
    result = supabase_data.call_rpc(fn_name, args=body, role=_role(apikey, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/rest/v1/{table}", status_code=201)
def rest_insert(table: str,
                body: Union[Dict[str, Any], List[Dict[str, Any]]] = Body(...),
                apikey: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None),
                prefer: Optional[str] = Header(None)):
    result = supabase_data.insert_rows(
        table, body, role=_role(apikey, authorization),
        prefer=prefer or "return=representation",
    )
    return _rest_response(result, status_code=201)


@app.patch("/rest/v1/{table}")
def rest_update(table: str, request: Request, body: Dict[str, Any] = Body(...),
                apikey: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None),
                prefer: Optional[str] = Header(None)):
    result = supabase_data.update_rows(
        table, body, filters=dict(request.query_params),
        role=_role(apikey, authorization), prefer=prefer or "return=representation",
    )
    return _rest_response(result)


@app.delete("/rest/v1/{table}")
def rest_delete(table: str, request: Request,
                apikey: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None),
                prefer: Optional[str] = Header(None)):
    result = supabase_data.delete_rows(
        table, filters=dict(request.query_params),
        role=_role(apikey, authorization), prefer=prefer or "return=representation",
    )
    return _rest_response(result)


# --- Storage: buckets ---

@app.get("/storage/v1/bucket")
def list_buckets(apikey: Optional[str] = Header(None),
                 authorization: Optional[str] = Header(None)):
    return supabase_data.list_buckets(role=_role(apikey, authorization))


@app.get("/storage/v1/bucket/{bucket_id}")
def get_bucket(bucket_id: str, apikey: Optional[str] = Header(None),
               authorization: Optional[str] = Header(None)):
    result = supabase_data.get_bucket(bucket_id, role=_role(apikey, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class BucketCreateBody(BaseModel):
    id: str
    name: Optional[str] = None
    public: Optional[bool] = False
    file_size_limit: Optional[int] = None
    allowed_mime_types: Optional[List[str]] = None


@app.post("/storage/v1/bucket", status_code=201)
def create_bucket(body: BucketCreateBody, apikey: Optional[str] = Header(None),
                  authorization: Optional[str] = Header(None)):
    result = supabase_data.create_bucket(
        body.id, name=body.name, public=body.public,
        file_size_limit=body.file_size_limit,
        allowed_mime_types=body.allowed_mime_types,
        role=_role(apikey, authorization),
    )
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/storage/v1/bucket/{bucket_id}")
def delete_bucket(bucket_id: str, apikey: Optional[str] = Header(None),
                  authorization: Optional[str] = Header(None)):
    result = supabase_data.delete_bucket(bucket_id, role=_role(apikey, authorization))
    if _is_error(result):
        return _fail(result)
    return result


# --- Storage: objects ---

class ObjectListBody(BaseModel):
    prefix: Optional[str] = ""
    limit: Optional[int] = 100
    offset: Optional[int] = 0


@app.post("/storage/v1/object/list/{bucket_id}")
def list_objects(bucket_id: str, body: ObjectListBody = Body(default=ObjectListBody()),
                 apikey: Optional[str] = Header(None),
                 authorization: Optional[str] = Header(None)):
    result = supabase_data.list_objects(
        bucket_id, prefix=body.prefix, limit=body.limit, offset=body.offset,
        role=_role(apikey, authorization),
    )
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/storage/v1/object/info/{bucket_id}/{path:path}")
def get_object_info(bucket_id: str, path: str, apikey: Optional[str] = Header(None),
                    authorization: Optional[str] = Header(None)):
    result = supabase_data.get_object_info(bucket_id, path, role=_role(apikey, authorization))
    if _is_error(result):
        return _fail(result)
    return result


class SignBody(BaseModel):
    expiresIn: Optional[int] = 3600


@app.post("/storage/v1/object/sign/{bucket_id}/{path:path}")
def sign_object(bucket_id: str, path: str, body: SignBody = Body(default=SignBody()),
                apikey: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None)):
    result = supabase_data.sign_object(bucket_id, path, expires_in=body.expiresIn,
                                       role=_role(apikey, authorization))
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/storage/v1/object/{bucket_id}/{path:path}")
def delete_object(bucket_id: str, path: str, apikey: Optional[str] = Header(None),
                  authorization: Optional[str] = Header(None)):
    result = supabase_data.delete_object(bucket_id, path, role=_role(apikey, authorization))
    if _is_error(result):
        return _fail(result)
    return result


# --- Edge Functions ---

@app.get("/functions/v1")
def list_functions():
    return supabase_data.list_functions()


@app.post("/functions/v1/{slug}")
def invoke_function(slug: str, body: Dict[str, Any] = Body(default={}),
                    apikey: Optional[str] = Header(None),
                    authorization: Optional[str] = Header(None)):
    result = supabase_data.invoke_function(slug, payload=body,
                                           role=_role(apikey, authorization))
    if _is_error(result):
        return _fail(result)
    return result


# --- Realtime ---

@app.get("/realtime/v1/channels")
def list_channels():
    return supabase_data.list_channels()


class BroadcastMessage(BaseModel):
    topic: str
    event: Optional[str] = "broadcast"
    payload: Optional[Dict[str, Any]] = None


class BroadcastBody(BaseModel):
    messages: List[BroadcastMessage]


@app.post("/realtime/v1/api/broadcast", status_code=202)
def broadcast(body: BroadcastBody, apikey: Optional[str] = Header(None),
              authorization: Optional[str] = Header(None)):
    result = supabase_data.broadcast([m.model_dump() for m in body.messages],
                                     role=_role(apikey, authorization))
    if _is_error(result):
        return _fail(result)
    return result


# --- Project settings ---

@app.get("/v1/projects")
def list_projects():
    settings = supabase_data.get_settings()
    return [{"id": settings["ref"], "name": settings["name"],
             "organization": settings["organization"], "region": settings["region"],
             "status": settings["status"], "created_at": settings["created_at"]}]


@app.get("/v1/projects/{ref}")
def get_project(ref: str):
    settings = supabase_data.get_settings()
    if ref != settings["ref"]:
        return JSONResponse(status_code=404,
                            content={"error": f"Project not found: {ref}", "code": "404"})
    return settings
