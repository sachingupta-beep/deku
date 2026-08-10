"""FastAPI server wrapping pocketbase_auth_data module as REST endpoints.

Serves the auth half of the same PocketBase instance `pocketbase-api` backs.
Base path: /api. Auth is per collection --- every endpoint below is scoped to
`/api/collections/{collection}`, with `users` and the system `_superusers`
collection carrying their own rules.

The `Authorization` header carries a PocketBase token, with or without the
`Bearer` prefix. Tokens are `<header>.<recordId>.<tokenKey>` and resolve only
while the record still carries that tokenKey, so changing a password or an email
invalidates every token already issued for it.
"""

from fastapi import Body, FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional

import pocketbase_auth_data
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

app = FastAPI(title="PocketBase Auth API (Mock)", version="v0.24.4")
install_tracker(app)
install_admin_plane(app, store=pocketbase_auth_data._store)


@app.get("/health")
def health():
    return pocketbase_auth_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result.get("code", 400), content=result)


def _ok(result, status_code=200):
    """Render a data-module result.

    PocketBase answers 204 with an empty body for the mail flows and deletes;
    the module marks those with `__status__` so the note it attaches (the token
    it would have emailed) is still visible in the harness report.
    """
    if _is_error(result):
        return _fail(result)
    if isinstance(result, dict) and "__status__" in result:
        body = {k: v for k, v in result.items() if k != "__status__"}
        if not body:
            return Response(status_code=result["__status__"])
        return JSONResponse(status_code=200, content=body)
    return JSONResponse(status_code=status_code, content=result)


def _identity(authorization):
    return pocketbase_auth_data.resolve_identity(authorization)


def _client_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "203.0.113.41"


# --- Health (PocketBase native) ---

@app.get("/api/health")
def api_health():
    return pocketbase_auth_data.api_health()


# --- Auth collections ---

@app.get("/api/collections")
def list_auth_collections(authorization: Optional[str] = Header(None)):
    kind, _ = _identity(authorization)
    return _ok(pocketbase_auth_data.list_auth_collections(kind=kind))


@app.get("/api/collections/{collection}/auth-methods")
def auth_methods(collection: str):
    return _ok(pocketbase_auth_data.auth_methods(collection))


# --- Password, OTP and OAuth2 grants ---

@app.post("/api/collections/{collection}/auth-with-password")
def auth_with_password(collection: str, request: Request,
                       payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.auth_with_password(
        collection, identity=payload.get("identity"),
        password=payload.get("password"), mfa_id=payload.get("mfaId"),
        ip=_client_ip(request)))


@app.post("/api/collections/{collection}/request-otp")
def request_otp(collection: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.request_otp(collection,
                                                email=payload.get("email")))


@app.post("/api/collections/{collection}/auth-with-otp")
def auth_with_otp(collection: str, request: Request,
                  payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.auth_with_otp(
        collection, otp_id=payload.get("otpId"),
        password=payload.get("password"), mfa_id=payload.get("mfaId"),
        ip=_client_ip(request)))


@app.post("/api/collections/{collection}/auth-with-oauth2")
def auth_with_oauth2(collection: str, request: Request,
                     payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.auth_with_oauth2(
        collection, provider=payload.get("provider"), code=payload.get("code"),
        code_verifier=payload.get("codeVerifier"),
        redirect_url=payload.get("redirectURL"), ip=_client_ip(request)))


@app.post("/api/collections/{collection}/auth-refresh")
def auth_refresh(collection: str, authorization: Optional[str] = Header(None)):
    kind, viewer = _identity(authorization)
    return _ok(pocketbase_auth_data.auth_refresh(collection, kind=kind,
                                                 viewer=viewer))


@app.post("/api/collections/{collection}/impersonate/{record_id}")
def impersonate(collection: str, record_id: str,
                payload: Dict[str, Any] = Body(default={}),
                authorization: Optional[str] = Header(None)):
    kind, _ = _identity(authorization)
    return _ok(pocketbase_auth_data.impersonate(
        collection, record_id, duration=payload.get("duration"), kind=kind))


# --- Verification, password reset, email change ---

@app.post("/api/collections/{collection}/request-verification")
def request_verification(collection: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.request_verification(
        collection, email=payload.get("email")))


@app.post("/api/collections/{collection}/confirm-verification")
def confirm_verification(collection: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.confirm_verification(
        collection, token=payload.get("token")))


@app.post("/api/collections/{collection}/request-password-reset")
def request_password_reset(collection: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.request_password_reset(
        collection, email=payload.get("email")))


@app.post("/api/collections/{collection}/confirm-password-reset")
def confirm_password_reset(collection: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.confirm_password_reset(
        collection, token=payload.get("token"), password=payload.get("password"),
        password_confirm=payload.get("passwordConfirm")))


@app.post("/api/collections/{collection}/request-email-change")
def request_email_change(collection: str, payload: Dict[str, Any] = Body(default={}),
                         authorization: Optional[str] = Header(None)):
    kind, viewer = _identity(authorization)
    return _ok(pocketbase_auth_data.request_email_change(
        collection, new_email=payload.get("newEmail"), kind=kind, viewer=viewer))


@app.post("/api/collections/{collection}/confirm-email-change")
def confirm_email_change(collection: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(pocketbase_auth_data.confirm_email_change(
        collection, token=payload.get("token"), password=payload.get("password")))


# --- Auth records ---

@app.get("/api/collections/{collection}/records")
def list_records(collection: str, page: int = Query(1, ge=1),
                 perPage: int = Query(30, ge=1, le=500),
                 role: Optional[str] = None, verified: Optional[bool] = None,
                 authorization: Optional[str] = Header(None)):
    kind, viewer = _identity(authorization)
    return _ok(pocketbase_auth_data.list_records(
        collection, page=page, per_page=perPage, filter_role=role,
        verified=verified, kind=kind, viewer=viewer))


@app.get("/api/collections/{collection}/records/{record_id}")
def get_record(collection: str, record_id: str,
               authorization: Optional[str] = Header(None)):
    kind, viewer = _identity(authorization)
    return _ok(pocketbase_auth_data.get_record(collection, record_id, kind=kind,
                                               viewer=viewer))


@app.post("/api/collections/{collection}/records")
def create_record(collection: str, payload: Dict[str, Any] = Body(default={}),
                  authorization: Optional[str] = Header(None)):
    kind, _ = _identity(authorization)
    result = pocketbase_auth_data.create_record(collection, payload, kind=kind)
    return _ok(result, status_code=200)


@app.patch("/api/collections/{collection}/records/{record_id}")
def update_record(collection: str, record_id: str,
                  payload: Dict[str, Any] = Body(default={}),
                  authorization: Optional[str] = Header(None)):
    kind, viewer = _identity(authorization)
    return _ok(pocketbase_auth_data.update_record(collection, record_id, payload,
                                                  kind=kind, viewer=viewer))


@app.delete("/api/collections/{collection}/records/{record_id}")
def delete_record(collection: str, record_id: str,
                  authorization: Optional[str] = Header(None)):
    kind, viewer = _identity(authorization)
    return _ok(pocketbase_auth_data.delete_record(collection, record_id,
                                                  kind=kind, viewer=viewer))


# --- External auth providers ---

@app.get("/api/collections/{collection}/records/{record_id}/external-auths")
def list_external_auths(collection: str, record_id: str,
                        authorization: Optional[str] = Header(None)):
    kind, viewer = _identity(authorization)
    return _ok(pocketbase_auth_data.list_external_auths(collection, record_id,
                                                        kind=kind, viewer=viewer))


@app.delete("/api/collections/{collection}/records/{record_id}/external-auths/{provider}")
def unlink_external_auth(collection: str, record_id: str, provider: str,
                         authorization: Optional[str] = Header(None)):
    kind, viewer = _identity(authorization)
    return _ok(pocketbase_auth_data.unlink_external_auth(
        collection, record_id, provider, kind=kind, viewer=viewer))


# --- Logs ---

@app.get("/api/logs")
def list_logs(page: int = Query(1, ge=1), perPage: int = Query(30, ge=1, le=500),
              authId: Optional[str] = None, status: Optional[int] = None,
              authorization: Optional[str] = Header(None)):
    kind, _ = _identity(authorization)
    return _ok(pocketbase_auth_data.list_logs(page=page, per_page=perPage,
                                              auth_id=authId, status=status,
                                              kind=kind))


@app.get("/api/logs/stats")
def logs_stats(authorization: Optional[str] = Header(None)):
    kind, _ = _identity(authorization)
    return _ok(pocketbase_auth_data.logs_stats(kind=kind))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8114)
