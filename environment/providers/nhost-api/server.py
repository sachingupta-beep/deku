"""FastAPI server wrapping nhost_data module as REST endpoints.

Mirrors a subset of the Nhost surface: Hasura GraphQL at /v1/graphql, Hasura
Auth at /v1/auth, Hasura Storage at /v1/storage and serverless functions at
/v1/functions, plus /v1/metadata, /v1/version and /healthz.

`x-hasura-admin-secret` grants the `admin` role and bypasses every permission;
`Authorization: Bearer <token>` authenticates as the project's session user with
the `user` role; without either the caller is the `public` role. An admin
request may narrow itself with `x-hasura-role`, as Hasura allows.
"""

from fastapi import Body, FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional

import nhost_data
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

app = FastAPI(title="Nhost API (Mock)", version="v2.42.0")
install_tracker(app)
install_admin_plane(app, store=nhost_data._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result.get("status", 400),
                        content={"message": result["message"],
                                 "error": result["error"],
                                 "extensions": result.get("extensions", {})})


def _role(admin_secret, authorization, hasura_role):
    return nhost_data.resolve_role(admin_secret=admin_secret,
                                   authorization=authorization,
                                   requested_role=hasura_role)


# --- Health / version / metadata ---

@app.get("/healthz")
def healthz():
    return nhost_data.healthz()


@app.get("/v1/version")
def version():
    return nhost_data.get_version()


@app.get("/v1/metadata")
def metadata(x_hasura_admin_secret: Optional[str] = Header(None),
             authorization: Optional[str] = Header(None),
             x_hasura_role: Optional[str] = Header(None)):
    role, _user_id = _role(x_hasura_admin_secret, authorization, x_hasura_role)
    result = nhost_data.get_metadata(role=role)
    if _is_error(result):
        return _fail(result)
    return result


# --- GraphQL ---

class GraphQLBody(BaseModel):
    query: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    operationName: Optional[str] = None


@app.post("/v1/graphql")
def graphql(body: GraphQLBody,
            x_hasura_admin_secret: Optional[str] = Header(None),
            authorization: Optional[str] = Header(None),
            x_hasura_role: Optional[str] = Header(None)):
    role, user_id = _role(x_hasura_admin_secret, authorization, x_hasura_role)
    return nhost_data.run_graphql(query=body.query, variables=body.variables,
                                  operation_name=body.operationName,
                                  role=role, user_id=user_id)


# --- Auth ---

class SignInBody(BaseModel):
    email: str
    password: str


@app.post("/v1/auth/signin/email-password")
def sign_in(body: SignInBody):
    result = nhost_data.sign_in(email=body.email, password=body.password)
    if _is_error(result):
        return _fail(result)
    return result


class RefreshBody(BaseModel):
    refreshToken: str


@app.post("/v1/auth/token")
def refresh_token(body: RefreshBody):
    result = nhost_data.refresh_session(refresh_token=body.refreshToken)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/auth/user")
def auth_user(x_hasura_admin_secret: Optional[str] = Header(None),
              authorization: Optional[str] = Header(None),
              x_hasura_role: Optional[str] = Header(None)):
    role, user_id = _role(x_hasura_admin_secret, authorization, x_hasura_role)
    result = nhost_data.get_session_user(role=role, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


class SignOutBody(BaseModel):
    refreshToken: Optional[str] = None
    all: Optional[bool] = False


@app.post("/v1/auth/signout")
def sign_out(body: SignOutBody = Body(default=SignOutBody())):
    return nhost_data.sign_out(refresh_token=body.refreshToken, all_sessions=body.all)


# --- Storage ---

@app.get("/v1/storage/buckets")
def list_buckets(x_hasura_admin_secret: Optional[str] = Header(None),
                 authorization: Optional[str] = Header(None),
                 x_hasura_role: Optional[str] = Header(None)):
    role, user_id = _role(x_hasura_admin_secret, authorization, x_hasura_role)
    result = nhost_data.list_buckets(role=role, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/storage/files")
def list_files(bucketId: Optional[str] = Query(None),
               x_hasura_admin_secret: Optional[str] = Header(None),
               authorization: Optional[str] = Header(None),
               x_hasura_role: Optional[str] = Header(None)):
    role, user_id = _role(x_hasura_admin_secret, authorization, x_hasura_role)
    result = nhost_data.list_files(bucket_id=bucketId, role=role, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/v1/storage/files/{file_id}")
def get_file(file_id: str, x_hasura_admin_secret: Optional[str] = Header(None),
             authorization: Optional[str] = Header(None),
             x_hasura_role: Optional[str] = Header(None)):
    role, user_id = _role(x_hasura_admin_secret, authorization, x_hasura_role)
    result = nhost_data.get_file(file_id, role=role, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/v1/storage/files/{file_id}")
def delete_file(file_id: str, x_hasura_admin_secret: Optional[str] = Header(None),
                authorization: Optional[str] = Header(None),
                x_hasura_role: Optional[str] = Header(None)):
    role, user_id = _role(x_hasura_admin_secret, authorization, x_hasura_role)
    result = nhost_data.delete_file(file_id, role=role, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result


# --- Functions ---

@app.get("/v1/functions")
def list_functions():
    return nhost_data.list_functions()


@app.post("/v1/functions/{name}")
def invoke_function(name: str, body: Dict[str, Any] = Body(default={}),
                    x_hasura_admin_secret: Optional[str] = Header(None),
                    authorization: Optional[str] = Header(None),
                    x_hasura_role: Optional[str] = Header(None)):
    role, user_id = _role(x_hasura_admin_secret, authorization, x_hasura_role)
    result = nhost_data.invoke_function(name, payload=body, role=role, user_id=user_id)
    if _is_error(result):
        return _fail(result)
    return result
