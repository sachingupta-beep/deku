"""HTTP surface for the simulated Supabase data plane.

Paths here are relative to the mount, so ``/rest/v1/{table}`` is served at
``/supabase/rest/v1/{table}``. Nothing in this file names the slug -- changing it
in ``service.toml`` moves the whole service and breaks nothing.

The routes are a thin translation layer and deliberately hold no logic: read
headers, call one :class:`~services.supabase.data.SupabaseData` method, map the
returned ``code`` onto an HTTP status. Everything a task can assert on lives in
the data layer, where it is testable without a client.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Body, Header, Query, Request
from fastapi.responses import JSONResponse

from .data import SupabaseData
from .models import BroadcastBody, BucketCreateBody, ObjectListBody, SignBody

#: Upstream error code -> HTTP status. One table, so a given SQLSTATE cannot mean
#: 404 on one endpoint and 401 on the next. Anything unlisted is a 400, which is
#: what PostgREST does with an unrecognised failure.
STATUS_BY_CODE: Dict[str, int] = {
    "42P01": 404,           # undefined_table
    "PGRST116": 404,        # no rows where one was required
    "PGRST202": 404,        # function not found in the schema cache
    "404": 404,
    "FunctionNotFound": 404,
    "42501": 401,           # insufficient_privilege / RLS denial
    "401": 401,
    "23503": 409,           # foreign_key_violation
    "Duplicate": 409,
    "409": 409,
    "429": 429,
}


def _is_error(result: Any) -> bool:
    return isinstance(result, dict) and "error" in result


def _fail(result: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=STATUS_BY_CODE.get(result.get("code"), 400), content=result)


def _unwrap(result: Any, status_code: int = 200) -> Any:
    """Turn the data layer's REST envelope into PostgREST's wire format.

    PostgREST answers with a **bare array** and puts the row count in
    ``Content-Range``; the envelope only exists so the data layer can return the
    count without a second call.
    """
    if _is_error(result):
        return _fail(result)
    return JSONResponse(status_code=status_code, content=result["data"],
                        headers={"Content-Range": result["content_range"]})


def _plain(result: Any) -> Any:
    return _fail(result) if _is_error(result) else result


def build_router(data: SupabaseData) -> APIRouter:
    """Build the Supabase router bound to one data-layer instance."""
    router = APIRouter()

    def role(apikey: Optional[str], authorization: Optional[str]) -> str:
        return data.resolve_role(apikey=apikey, authorization=authorization)

    # -- REST (PostgREST) --------------------------------------------------

    @router.get("/rest/v1/", tags=["rest"], summary="PostgREST schema root")
    def rest_root() -> Dict[str, Any]:
        return data.rest_root()

    # Declared before POST /rest/v1/{table}: registration order is match order,
    # and "rpc" is a valid table name as far as the path template is concerned.
    @router.post("/rest/v1/rpc/{fn_name}", tags=["rest"], summary="Call a Postgres function")
    def rest_rpc(
        fn_name: str,
        body: Dict[str, Any] = Body(default={}, examples=[{"project_id": 101}]),
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        """`project_stats`, `search_documents`, `publish_document`."""
        return _plain(data.call_rpc(fn_name, args=body, role=role(apikey, authorization)))

    @router.get("/rest/v1/{table}", tags=["rest"], summary="Select rows")
    def rest_select(
        table: str,
        request: Request,
        select: Optional[str] = Query(None, description="Columns and embeds, e.g. `id,title,profiles(username)`"),
        order: Optional[str] = Query(None, description="e.g. `star_count.desc`"),
        limit: Optional[int] = Query(None, ge=1, le=1000),
        offset: int = 0,
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        """Any unreserved query parameter is a filter: `?status=eq.published`.

        Supported operators: `eq neq gt gte lt lte like ilike in is cs`, each
        negatable with a `not.` prefix.
        """
        return _unwrap(
            data.select_rows(
                table,
                filters=dict(request.query_params),
                select=select,
                order=order,
                limit=limit,
                offset=offset,
                role=role(apikey, authorization),
            )
        )

    @router.post("/rest/v1/{table}", status_code=201, tags=["rest"], summary="Insert rows")
    def rest_insert(
        table: str,
        body: Union[Dict[str, Any], List[Dict[str, Any]]] = Body(...),
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
        prefer: Optional[str] = Header(None, description="`return=minimal` suppresses the body"),
    ) -> Any:
        return _unwrap(
            data.insert_rows(table, body, role=role(apikey, authorization),
                             prefer=prefer or "return=representation"),
            status_code=201,
        )

    @router.patch("/rest/v1/{table}", tags=["rest"], summary="Update rows matching the filters")
    def rest_update(
        table: str,
        request: Request,
        body: Dict[str, Any] = Body(...),
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
        prefer: Optional[str] = Header(None),
    ) -> Any:
        return _unwrap(
            data.update_rows(table, body, filters=dict(request.query_params),
                             role=role(apikey, authorization),
                             prefer=prefer or "return=representation")
        )

    @router.delete("/rest/v1/{table}", tags=["rest"], summary="Delete rows matching the filters")
    def rest_delete(
        table: str,
        request: Request,
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
        prefer: Optional[str] = Header(None),
    ) -> Any:
        """Requires the service key, and refuses an unfiltered delete."""
        return _unwrap(
            data.delete_rows(table, filters=dict(request.query_params),
                             role=role(apikey, authorization),
                             prefer=prefer or "return=representation")
        )

    # -- Storage: buckets --------------------------------------------------

    @router.get("/storage/v1/bucket", tags=["storage"], summary="List buckets")
    def list_buckets(
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> List[Dict[str, Any]]:
        return data.list_buckets(role=role(apikey, authorization))

    @router.get("/storage/v1/bucket/{bucket_id}", tags=["storage"], summary="Get a bucket")
    def get_bucket(
        bucket_id: str,
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _plain(data.get_bucket(bucket_id, role=role(apikey, authorization)))

    @router.post("/storage/v1/bucket", status_code=201, tags=["storage"], summary="Create a bucket")
    def create_bucket(
        body: BucketCreateBody,
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _plain(
            data.create_bucket(
                body.id, name=body.name, public=body.public,
                file_size_limit=body.file_size_limit,
                allowed_mime_types=body.allowed_mime_types,
                role=role(apikey, authorization),
            )
        )

    @router.delete("/storage/v1/bucket/{bucket_id}", tags=["storage"], summary="Delete a bucket")
    def delete_bucket(
        bucket_id: str,
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        """409 if the bucket still holds objects, as upstream does."""
        return _plain(data.delete_bucket(bucket_id, role=role(apikey, authorization)))

    # -- Storage: objects --------------------------------------------------

    @router.post("/storage/v1/object/list/{bucket_id}", tags=["storage"], summary="List objects")
    def list_objects(
        bucket_id: str,
        body: ObjectListBody = Body(default=ObjectListBody()),
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _plain(
            data.list_objects(bucket_id, prefix=body.prefix, limit=body.limit,
                              offset=body.offset, role=role(apikey, authorization))
        )

    @router.get("/storage/v1/object/info/{bucket_id}/{path:path}", tags=["storage"],
                summary="Object metadata")
    def get_object_info(
        bucket_id: str,
        path: str,
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _plain(data.get_object_info(bucket_id, path, role=role(apikey, authorization)))

    @router.post("/storage/v1/object/sign/{bucket_id}/{path:path}", tags=["storage"],
                 summary="Create a signed URL")
    def sign_object(
        bucket_id: str,
        path: str,
        body: SignBody = Body(default=SignBody()),
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _plain(
            data.sign_object(bucket_id, path, expires_in=body.expiresIn,
                             role=role(apikey, authorization))
        )

    @router.delete("/storage/v1/object/{bucket_id}/{path:path}", tags=["storage"],
                   summary="Delete an object")
    def delete_object(
        bucket_id: str,
        path: str,
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _plain(data.delete_object(bucket_id, path, role=role(apikey, authorization)))

    # -- Edge Functions ----------------------------------------------------

    @router.get("/functions/v1", tags=["functions"], summary="List edge functions")
    def list_functions() -> List[Dict[str, Any]]:
        return data.list_functions()

    @router.post("/functions/v1/{slug}", tags=["functions"], summary="Invoke an edge function")
    def invoke_function(
        slug: str,
        body: Dict[str, Any] = Body(default={}),
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        """401 when the function sets `verify_jwt` and the caller is anon;
        429 when it is THROTTLED."""
        return _plain(data.invoke_function(slug, payload=body, role=role(apikey, authorization)))

    # -- Realtime ----------------------------------------------------------

    @router.get("/realtime/v1/channels", tags=["realtime"], summary="List channels")
    def list_channels() -> List[Dict[str, Any]]:
        return data.list_channels()

    @router.post("/realtime/v1/api/broadcast", status_code=202, tags=["realtime"],
                 summary="Broadcast to channels")
    def broadcast(
        body: BroadcastBody,
        apikey: Optional[str] = Header(None),
        authorization: Optional[str] = Header(None),
    ) -> Any:
        return _plain(
            data.broadcast([m.model_dump() for m in body.messages],
                           role=role(apikey, authorization))
        )

    # -- Project read model ------------------------------------------------

    @router.get("/v1/projects", tags=["projects"], summary="List projects")
    def list_projects() -> List[Dict[str, Any]]:
        return data.list_projects()

    @router.get("/v1/projects/{ref}", tags=["projects"], summary="Project settings")
    def get_project(ref: str) -> Any:
        """The service key comes back masked, as the dashboard shows it."""
        settings = data.get_settings()
        if ref != settings["ref"]:
            return JSONResponse(status_code=404,
                                content={"error": f"Project not found: {ref}", "code": "404"})
        return settings

    return router
