"""FastAPI server wrapping supabase_auth_data module as REST endpoints.

Implements the GoTrue surface of the same self-hosted Supabase project that
`supabase-api` serves, mounted at /auth/v1: sign-up, the password and
refresh_token grants, the current-user endpoints, one-time tokens (recovery,
magic link, OTP, verify, resend), OAuth authorize, MFA enrolment/challenge/verify
and the service_role-only admin surface.

The `apikey` header (or `Authorization: Bearer`) selects the project role exactly
as it does in `supabase-api`: absent or the anon key -> `anon`, the service key
-> `service_role`. End-user endpoints instead read the bearer access token minted
by /auth/v1/token and resolve it to a live session.
"""

from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional

import supabase_auth_data
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

app = FastAPI(title="Supabase Auth API (Mock)", version="v1")
install_tracker(app)
install_admin_plane(app, store=supabase_auth_data._store)


@app.get("/health")
def health():
    return supabase_auth_data.health()


# --- Error mapping ---

def _is_error(result):
    return isinstance(result, dict) and "error_code" in result


def _fail(result):
    return JSONResponse(status_code=result.get("status", 400),
                        content={"code": result["code"],
                                 "error_code": result["error_code"],
                                 "msg": result["msg"]})


def _ok(result, status_code=200):
    if _is_error(result):
        return _fail(result)
    return JSONResponse(status_code=status_code, content=result)


def _key(apikey, authorization):
    return supabase_auth_data.resolve_key(apikey=apikey,
                                          authorization=authorization)


def _client_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "203.0.113.41"


# --- Service metadata ---

@app.get("/auth/v1/health")
def gotrue_health():
    return supabase_auth_data.gotrue_health()


@app.get("/auth/v1/settings")
def settings():
    return supabase_auth_data.get_settings()


# --- Sign-up and sign-in ---

@app.post("/auth/v1/signup")
def signup(request: Request, payload: Dict[str, Any] = Body(default={})):
    result = supabase_auth_data.sign_up(
        email=payload.get("email"), phone=payload.get("phone"),
        password=payload.get("password"), data=payload.get("data"),
        ip=_client_ip(request))
    return _ok(result)


@app.post("/auth/v1/token")
def token(request: Request, grant_type: str = Query(default="password"),
          payload: Dict[str, Any] = Body(default={})):
    ip = _client_ip(request)
    if grant_type == "password":
        result = supabase_auth_data.sign_in_password(
            email=payload.get("email"), phone=payload.get("phone"),
            password=payload.get("password"), ip=ip)
    elif grant_type == "refresh_token":
        result = supabase_auth_data.refresh(
            refresh_token=payload.get("refresh_token"), ip=ip)
    else:
        return JSONResponse(status_code=400,
                            content={"code": 400,
                                     "error_code": "validation_failed",
                                     "msg": f"unsupported_grant_type: "
                                            f"{grant_type}"})
    return _ok(result)


@app.post("/auth/v1/signup/anonymous")
def signup_anonymous(request: Request):
    """Anonymous sign-in.

    The real client calls POST /auth/v1/signup with an empty body; the mock
    gives it a distinct path so the two flows stay separable in a collection.
    """
    return _ok(supabase_auth_data.sign_in_anonymous(ip=_client_ip(request)))


@app.post("/auth/v1/logout")
def logout(scope: str = Query(default="global"),
           authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.sign_out(authorization=authorization,
                                           scope=scope))


# --- Current user ---

@app.get("/auth/v1/user")
def read_user(authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.get_user(authorization=authorization))


@app.put("/auth/v1/user")
def write_user(payload: Dict[str, Any] = Body(default={}),
               authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.update_user(
        authorization=authorization, email=payload.get("email"),
        phone=payload.get("phone"), password=payload.get("password"),
        data=payload.get("data")))


# --- One-time tokens ---

@app.post("/auth/v1/recover")
def recover(request: Request, payload: Dict[str, Any] = Body(default={})):
    return _ok(supabase_auth_data.recover(email=payload.get("email"),
                                          ip=_client_ip(request)))


@app.post("/auth/v1/magiclink")
def magiclink(request: Request, payload: Dict[str, Any] = Body(default={})):
    return _ok(supabase_auth_data.magic_link(email=payload.get("email"),
                                             ip=_client_ip(request)))


@app.post("/auth/v1/otp")
def otp(request: Request, payload: Dict[str, Any] = Body(default={})):
    return _ok(supabase_auth_data.send_otp(email=payload.get("email"),
                                           phone=payload.get("phone"),
                                           ip=_client_ip(request)))


@app.post("/auth/v1/verify")
def verify(request: Request, payload: Dict[str, Any] = Body(default={})):
    return _ok(supabase_auth_data.verify(
        token_type=payload.get("type"), token=payload.get("token"),
        otp=payload.get("otp"), email=payload.get("email"),
        ip=_client_ip(request)))


@app.post("/auth/v1/resend")
def resend(payload: Dict[str, Any] = Body(default={})):
    return _ok(supabase_auth_data.resend(token_type=payload.get("type"),
                                         email=payload.get("email"),
                                         phone=payload.get("phone")))


@app.get("/auth/v1/authorize")
def authorize(provider: Optional[str] = None,
              redirect_to: Optional[str] = None):
    return _ok(supabase_auth_data.authorize(provider=provider,
                                            redirect_to=redirect_to))


# --- MFA ---

@app.post("/auth/v1/factors")
def enroll_factor(payload: Dict[str, Any] = Body(default={}),
                  authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.enroll_factor(
        authorization=authorization,
        factor_type=payload.get("factor_type", "totp"),
        friendly_name=payload.get("friendly_name")))


@app.post("/auth/v1/factors/{factor_id}/challenge")
def challenge_factor(factor_id: str,
                     authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.challenge_factor(factor_id,
                                                   authorization=authorization))


@app.post("/auth/v1/factors/{factor_id}/verify")
def verify_factor(factor_id: str, request: Request,
                  payload: Dict[str, Any] = Body(default={}),
                  authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.verify_factor(
        factor_id, challenge_id=payload.get("challenge_id"),
        code=payload.get("code"), authorization=authorization,
        ip=_client_ip(request)))


@app.delete("/auth/v1/factors/{factor_id}")
def unenroll_factor(factor_id: str,
                    authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.unenroll_factor(factor_id,
                                                  authorization=authorization))


# --- Admin (service_role) ---

@app.get("/auth/v1/admin/users")
def admin_list_users(page: int = 1, per_page: int = 50,
                     apikey: Optional[str] = Header(default=None),
                     authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.admin_list_users(
        page=page, per_page=per_page, key=_key(apikey, authorization)))


@app.post("/auth/v1/admin/users")
def admin_create_user(request: Request, payload: Dict[str, Any] = Body(default={}),
                      apikey: Optional[str] = Header(default=None),
                      authorization: Optional[str] = Header(default=None)):
    result = supabase_auth_data.admin_create_user(
        payload, key=_key(apikey, authorization), ip=_client_ip(request))
    return _ok(result, status_code=201 if not _is_error(result) else 200)


@app.get("/auth/v1/admin/users/{user_id}")
def admin_get_user(user_id: str, apikey: Optional[str] = Header(default=None),
                   authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.admin_get_user(
        user_id, key=_key(apikey, authorization)))


@app.put("/auth/v1/admin/users/{user_id}")
def admin_update_user(user_id: str, request: Request,
                      payload: Dict[str, Any] = Body(default={}),
                      apikey: Optional[str] = Header(default=None),
                      authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.admin_update_user(
        user_id, payload, key=_key(apikey, authorization),
        ip=_client_ip(request)))


@app.delete("/auth/v1/admin/users/{user_id}")
def admin_delete_user(user_id: str, request: Request,
                      payload: Dict[str, Any] = Body(default={}),
                      apikey: Optional[str] = Header(default=None),
                      authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.admin_delete_user(
        user_id, should_soft_delete=bool(payload.get("should_soft_delete")),
        key=_key(apikey, authorization), ip=_client_ip(request)))


@app.post("/auth/v1/admin/generate_link")
def admin_generate_link(payload: Dict[str, Any] = Body(default={}),
                        apikey: Optional[str] = Header(default=None),
                        authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.admin_generate_link(
        link_type=payload.get("type"), email=payload.get("email"),
        password=payload.get("password"),
        redirect_to=(payload.get("options") or {}).get("redirect_to"),
        key=_key(apikey, authorization)))


@app.get("/auth/v1/admin/audit")
def admin_audit(page: int = 1, per_page: int = 25,
                action: Optional[str] = None,
                apikey: Optional[str] = Header(default=None),
                authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.admin_audit(
        page=page, per_page=per_page, action=action,
        key=_key(apikey, authorization)))


@app.get("/auth/v1/admin/sessions")
def admin_sessions(user_id: Optional[str] = None,
                   apikey: Optional[str] = Header(default=None),
                   authorization: Optional[str] = Header(default=None)):
    return _ok(supabase_auth_data.admin_list_sessions(
        user_id=user_id, key=_key(apikey, authorization)))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8113)
