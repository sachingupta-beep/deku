"""FastAPI server wrapping supertokens_data module as REST endpoints.

Mirrors the SuperTokens **core** --- the service a backend SDK talks to, not the
SDK's own frontend routes. Two conventions run through everything:

* Domain outcomes ride in the body as a `status` string with HTTP 200. A wrong
  password is `{"status": "WRONG_CREDENTIALS_ERROR"}`, not a 401. Non-2xx is
  reserved for transport problems: a missing `api-key` (401), an unsupported
  `cdi-version` (400), an unknown tenant (404).
* Every recipe path is tenant-scoped. Both `/recipe/...` and the explicit
  `/appid-{app_id}/{tenant_id}/recipe/...` form are served; the short form
  resolves to the `public` tenant.
"""

from fastapi import Body, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Any, Dict, List, Optional

import supertokens_data
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

app = FastAPI(title="SuperTokens Core API (Mock)",
              version=supertokens_data.CORE_VERSION)
install_tracker(app)
install_admin_plane(app, store=supertokens_data._store)


@app.get("/health")
def health():
    return supertokens_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result.get("code", 400),
                        content={"message": result["message"]})


def _ok(result):
    if _is_error(result):
        return _fail(result)
    return JSONResponse(status_code=200, content=result)


def _gate(api_key, cdi_version, tenant_id=None):
    """Run the transport-level checks, then resolve the tenant.

    Returns `(tenant, failure_response)`; exactly one of the two is set.
    """
    denied = supertokens_data.check_api_key(api_key)
    if denied:
        return None, _fail(denied)
    denied = supertokens_data.check_cdi_version(cdi_version)
    if denied:
        return None, _fail(denied)
    tenant, denied = supertokens_data.resolve_tenant(tenant_id)
    if denied:
        return None, _fail(denied)
    return tenant, None


# --- Core metadata (no api-key required, as in SuperTokens) ---

@app.get("/hello", response_class=PlainTextResponse)
def hello():
    return supertokens_data.hello()


@app.get("/apiversion")
def api_version():
    return supertokens_data.api_version()


@app.get("/config")
def config(api_key: Optional[str] = Header(default=None, alias="api-key")):
    denied = supertokens_data.check_api_key(api_key)
    if denied:
        return _fail(denied)
    return supertokens_data.config()


@app.get("/recipe/jwt/jwks")
def jwks():
    return supertokens_data.jwks()


# --- emailpassword ---

@app.post("/appid-{app_id}/{tenant_id}/recipe/signup")
@app.post("/recipe/signup")
def signup(payload: Dict[str, Any] = Body(default={}),
           app_id: str = supertokens_data.DEFAULT_APP_ID,
           tenant_id: str = supertokens_data.DEFAULT_TENANT,
           api_key: Optional[str] = Header(default=None, alias="api-key"),
           cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.email_password_signup(
        tenant, email=payload.get("email"), password=payload.get("password")))


@app.post("/appid-{app_id}/{tenant_id}/recipe/signin")
@app.post("/recipe/signin")
def signin(payload: Dict[str, Any] = Body(default={}),
           app_id: str = supertokens_data.DEFAULT_APP_ID,
           tenant_id: str = supertokens_data.DEFAULT_TENANT,
           api_key: Optional[str] = Header(default=None, alias="api-key"),
           cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.email_password_signin(
        tenant, email=payload.get("email"), password=payload.get("password")))


@app.get("/appid-{app_id}/{tenant_id}/recipe/user")
@app.get("/recipe/user")
def get_recipe_user(app_id: str = supertokens_data.DEFAULT_APP_ID,
                    tenant_id: str = supertokens_data.DEFAULT_TENANT,
                    userId: Optional[str] = None, email: Optional[str] = None,
                    phoneNumber: Optional[str] = None,
                    thirdPartyId: Optional[str] = None,
                    thirdPartyUserId: Optional[str] = None,
                    recipeId: Optional[str] = None,
                    api_key: Optional[str] = Header(default=None, alias="api-key"),
                    cdi_version: Optional[str] = Header(default=None,
                                                        alias="cdi-version")):
    """One path, three recipes.

    A backend SDK reaches this through its own recipe's router, so the core
    knows which recipe is asking. Here the recipes share a path, so `recipeId`
    picks explicitly; without it the query parameters decide, and an email alone
    means emailpassword.
    """
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    if recipeId == "thirdparty" or thirdPartyId or thirdPartyUserId:
        return _ok(supertokens_data.third_party_get_user(
            tenant, third_party_id=thirdPartyId,
            third_party_user_id=thirdPartyUserId, user_id=userId))
    if recipeId == "passwordless" or phoneNumber:
        return _ok(supertokens_data.passwordless_get_user(
            tenant, email=email, phone_number=phoneNumber, user_id=userId))
    return _ok(supertokens_data.email_password_get_user(tenant, user_id=userId,
                                                        email=email))


@app.put("/appid-{app_id}/{tenant_id}/recipe/user")
@app.put("/recipe/user")
def put_recipe_user(payload: Dict[str, Any] = Body(default={}),
                    app_id: str = supertokens_data.DEFAULT_APP_ID,
                    tenant_id: str = supertokens_data.DEFAULT_TENANT,
                    api_key: Optional[str] = Header(default=None, alias="api-key"),
                    cdi_version: Optional[str] = Header(default=None,
                                                        alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.email_password_update_user(
        recipe_user_id=payload.get("recipeUserId") or payload.get("userId"),
        email=payload.get("email"), password=payload.get("password")))


@app.post("/appid-{app_id}/{tenant_id}/recipe/user/password/reset/token")
@app.post("/recipe/user/password/reset/token")
def create_password_reset_token(
        payload: Dict[str, Any] = Body(default={}),
        app_id: str = supertokens_data.DEFAULT_APP_ID,
        tenant_id: str = supertokens_data.DEFAULT_TENANT,
        api_key: Optional[str] = Header(default=None, alias="api-key"),
        cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.password_reset_token(
        tenant, user_id=payload.get("userId")))


@app.post("/appid-{app_id}/{tenant_id}/recipe/user/password/reset")
@app.post("/recipe/user/password/reset")
def consume_password_reset_token(
        payload: Dict[str, Any] = Body(default={}),
        app_id: str = supertokens_data.DEFAULT_APP_ID,
        tenant_id: str = supertokens_data.DEFAULT_TENANT,
        api_key: Optional[str] = Header(default=None, alias="api-key"),
        cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.password_reset(
        tenant, method=payload.get("method", "token"),
        token=payload.get("token"), new_password=payload.get("newPassword")))


# --- thirdparty ---

@app.post("/appid-{app_id}/{tenant_id}/recipe/signinup")
@app.post("/recipe/signinup")
def third_party_signinup(
        payload: Dict[str, Any] = Body(default={}),
        app_id: str = supertokens_data.DEFAULT_APP_ID,
        tenant_id: str = supertokens_data.DEFAULT_TENANT,
        api_key: Optional[str] = Header(default=None, alias="api-key"),
        cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    email = payload.get("email")
    if isinstance(email, dict):
        email = email.get("id")
    return _ok(supertokens_data.third_party_signinup(
        tenant, third_party_id=payload.get("thirdPartyId"),
        third_party_user_id=payload.get("thirdPartyUserId"), email=email))


# --- passwordless ---

@app.post("/appid-{app_id}/{tenant_id}/recipe/signinup/code")
@app.post("/recipe/signinup/code")
def create_passwordless_code(
        payload: Dict[str, Any] = Body(default={}),
        app_id: str = supertokens_data.DEFAULT_APP_ID,
        tenant_id: str = supertokens_data.DEFAULT_TENANT,
        api_key: Optional[str] = Header(default=None, alias="api-key"),
        cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.passwordless_create_code(
        tenant, email=payload.get("email"),
        phone_number=payload.get("phoneNumber"),
        user_input_code=payload.get("userInputCode")))


@app.post("/appid-{app_id}/{tenant_id}/recipe/signinup/code/consume")
@app.post("/recipe/signinup/code/consume")
def consume_passwordless_code(
        payload: Dict[str, Any] = Body(default={}),
        app_id: str = supertokens_data.DEFAULT_APP_ID,
        tenant_id: str = supertokens_data.DEFAULT_TENANT,
        api_key: Optional[str] = Header(default=None, alias="api-key"),
        cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.passwordless_consume_code(
        tenant, pre_auth_session_id=payload.get("preAuthSessionId"),
        link_code=payload.get("linkCode"), device_id=payload.get("deviceId"),
        user_input_code=payload.get("userInputCode")))


# --- session ---

@app.post("/appid-{app_id}/{tenant_id}/recipe/session")
@app.post("/recipe/session")
def create_session(payload: Dict[str, Any] = Body(default={}),
                   app_id: str = supertokens_data.DEFAULT_APP_ID,
                   tenant_id: str = supertokens_data.DEFAULT_TENANT,
                   api_key: Optional[str] = Header(default=None, alias="api-key"),
                   cdi_version: Optional[str] = Header(default=None,
                                                       alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.create_session(
        tenant, user_id=payload.get("userId"),
        recipe_user_id=payload.get("recipeUserId"),
        user_data_in_jwt=payload.get("userDataInJWT"),
        user_data_in_database=payload.get("userDataInDatabase"),
        enable_anti_csrf=payload.get("enableAntiCsrf", True)))


@app.post("/recipe/session/verify")
def verify_session(payload: Dict[str, Any] = Body(default={}),
                   api_key: Optional[str] = Header(default=None, alias="api-key"),
                   cdi_version: Optional[str] = Header(default=None,
                                                       alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.verify_session(
        access_token=payload.get("accessToken"),
        anti_csrf_token=payload.get("antiCsrfToken"),
        do_anti_csrf_check=payload.get("doAntiCsrfCheck", False)))


@app.post("/recipe/session/refresh")
def refresh_session(payload: Dict[str, Any] = Body(default={}),
                    api_key: Optional[str] = Header(default=None, alias="api-key"),
                    cdi_version: Optional[str] = Header(default=None,
                                                        alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.refresh_session(
        refresh_token=payload.get("refreshToken"),
        anti_csrf_token=payload.get("antiCsrfToken"),
        do_anti_csrf_check=payload.get("doAntiCsrfCheck", False)))


@app.post("/recipe/session/remove")
def remove_sessions(payload: Dict[str, Any] = Body(default={}),
                    api_key: Optional[str] = Header(default=None, alias="api-key"),
                    cdi_version: Optional[str] = Header(default=None,
                                                        alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.remove_sessions(
        session_handles=payload.get("sessionHandles"),
        user_id=payload.get("userId"), tenant_id=payload.get("tenantId")))


@app.get("/appid-{app_id}/{tenant_id}/recipe/session/user")
@app.get("/recipe/session/user")
def list_user_sessions(app_id: str = supertokens_data.DEFAULT_APP_ID,
                       tenant_id: str = supertokens_data.DEFAULT_TENANT,
                       userId: Optional[str] = None,
                       api_key: Optional[str] = Header(default=None,
                                                       alias="api-key"),
                       cdi_version: Optional[str] = Header(default=None,
                                                           alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.user_sessions(tenant, user_id=userId))


@app.get("/recipe/session/data")
def get_session_data(sessionHandle: Optional[str] = None,
                     api_key: Optional[str] = Header(default=None, alias="api-key"),
                     cdi_version: Optional[str] = Header(default=None,
                                                         alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.session_data(session_handle=sessionHandle))


@app.put("/recipe/session/data")
def put_session_data(payload: Dict[str, Any] = Body(default={}),
                     api_key: Optional[str] = Header(default=None, alias="api-key"),
                     cdi_version: Optional[str] = Header(default=None,
                                                         alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.update_session_data(
        session_handle=payload.get("sessionHandle"),
        user_data_in_database=payload.get("userDataInDatabase")))


# --- emailverification ---

@app.post("/appid-{app_id}/{tenant_id}/recipe/user/email/verify/token")
@app.post("/recipe/user/email/verify/token")
def create_email_verify_token(
        payload: Dict[str, Any] = Body(default={}),
        app_id: str = supertokens_data.DEFAULT_APP_ID,
        tenant_id: str = supertokens_data.DEFAULT_TENANT,
        api_key: Optional[str] = Header(default=None, alias="api-key"),
        cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.email_verify_token(
        tenant, user_id=payload.get("userId"), email=payload.get("email")))


@app.post("/appid-{app_id}/{tenant_id}/recipe/user/email/verify")
@app.post("/recipe/user/email/verify")
def consume_email_verify_token(
        payload: Dict[str, Any] = Body(default={}),
        app_id: str = supertokens_data.DEFAULT_APP_ID,
        tenant_id: str = supertokens_data.DEFAULT_TENANT,
        api_key: Optional[str] = Header(default=None, alias="api-key"),
        cdi_version: Optional[str] = Header(default=None, alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.email_verify(
        tenant, method=payload.get("method", "token"),
        token=payload.get("token")))


@app.get("/recipe/user/email/verify")
def is_email_verified(userId: Optional[str] = None, email: Optional[str] = None,
                      api_key: Optional[str] = Header(default=None,
                                                      alias="api-key"),
                      cdi_version: Optional[str] = Header(default=None,
                                                          alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.email_is_verified(user_id=userId, email=email))


# --- usermetadata ---

@app.get("/recipe/user/metadata")
def get_metadata(userId: Optional[str] = None,
                 api_key: Optional[str] = Header(default=None, alias="api-key"),
                 cdi_version: Optional[str] = Header(default=None,
                                                     alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.get_metadata(user_id=userId))


@app.put("/recipe/user/metadata")
def put_metadata(payload: Dict[str, Any] = Body(default={}),
                 api_key: Optional[str] = Header(default=None, alias="api-key"),
                 cdi_version: Optional[str] = Header(default=None,
                                                     alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.put_metadata(
        user_id=payload.get("userId"),
        metadata_update=payload.get("metadataUpdate")))


@app.post("/recipe/user/metadata/remove")
def remove_metadata(payload: Dict[str, Any] = Body(default={}),
                    api_key: Optional[str] = Header(default=None, alias="api-key"),
                    cdi_version: Optional[str] = Header(default=None,
                                                        alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.remove_metadata(user_id=payload.get("userId")))


# --- userroles ---

@app.put("/recipe/role")
def put_role(payload: Dict[str, Any] = Body(default={}),
             api_key: Optional[str] = Header(default=None, alias="api-key"),
             cdi_version: Optional[str] = Header(default=None,
                                                 alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.put_role(role=payload.get("role"),
                                         permissions=payload.get("permissions")))


@app.get("/recipe/roles")
def list_roles(api_key: Optional[str] = Header(default=None, alias="api-key"),
               cdi_version: Optional[str] = Header(default=None,
                                                   alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.list_roles())


@app.get("/recipe/role/permissions")
def role_permissions(role: Optional[str] = None,
                     api_key: Optional[str] = Header(default=None, alias="api-key"),
                     cdi_version: Optional[str] = Header(default=None,
                                                         alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.role_permissions(role=role))


@app.post("/recipe/role/remove")
def remove_role(payload: Dict[str, Any] = Body(default={}),
                api_key: Optional[str] = Header(default=None, alias="api-key"),
                cdi_version: Optional[str] = Header(default=None,
                                                    alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.remove_role(role=payload.get("role")))


@app.put("/appid-{app_id}/{tenant_id}/recipe/user/role")
@app.put("/recipe/user/role")
def add_user_role(payload: Dict[str, Any] = Body(default={}),
                  app_id: str = supertokens_data.DEFAULT_APP_ID,
                  tenant_id: str = supertokens_data.DEFAULT_TENANT,
                  api_key: Optional[str] = Header(default=None, alias="api-key"),
                  cdi_version: Optional[str] = Header(default=None,
                                                      alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.add_user_role(tenant,
                                              user_id=payload.get("userId"),
                                              role=payload.get("role")))


@app.get("/appid-{app_id}/{tenant_id}/recipe/user/roles")
@app.get("/recipe/user/roles")
def get_user_roles(app_id: str = supertokens_data.DEFAULT_APP_ID,
                   tenant_id: str = supertokens_data.DEFAULT_TENANT,
                   userId: Optional[str] = None,
                   api_key: Optional[str] = Header(default=None, alias="api-key"),
                   cdi_version: Optional[str] = Header(default=None,
                                                       alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.get_user_roles(tenant, user_id=userId))


@app.post("/appid-{app_id}/{tenant_id}/recipe/user/role/remove")
@app.post("/recipe/user/role/remove")
def remove_user_role(payload: Dict[str, Any] = Body(default={}),
                     app_id: str = supertokens_data.DEFAULT_APP_ID,
                     tenant_id: str = supertokens_data.DEFAULT_TENANT,
                     api_key: Optional[str] = Header(default=None, alias="api-key"),
                     cdi_version: Optional[str] = Header(default=None,
                                                         alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.remove_user_role(tenant,
                                                 user_id=payload.get("userId"),
                                                 role=payload.get("role")))


@app.get("/appid-{app_id}/{tenant_id}/recipe/role/users")
@app.get("/recipe/role/users")
def role_users(app_id: str = supertokens_data.DEFAULT_APP_ID,
               tenant_id: str = supertokens_data.DEFAULT_TENANT,
               role: Optional[str] = None,
               api_key: Optional[str] = Header(default=None, alias="api-key"),
               cdi_version: Optional[str] = Header(default=None,
                                                   alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.role_users(tenant, role=role))


# --- multitenancy ---

@app.get("/recipe/multitenancy/tenant/list")
def list_tenants(api_key: Optional[str] = Header(default=None, alias="api-key"),
                 cdi_version: Optional[str] = Header(default=None,
                                                     alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.list_tenants())


@app.get("/appid-{app_id}/{tenant_id}/recipe/multitenancy/tenant")
def get_tenant(app_id: str, tenant_id: str,
               api_key: Optional[str] = Header(default=None, alias="api-key"),
               cdi_version: Optional[str] = Header(default=None,
                                                   alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.get_tenant(tenant))


@app.put("/recipe/multitenancy/tenant")
def put_tenant(payload: Dict[str, Any] = Body(default={}),
               api_key: Optional[str] = Header(default=None, alias="api-key"),
               cdi_version: Optional[str] = Header(default=None,
                                                   alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.put_tenant(
        tenant_id=payload.get("tenantId"),
        email_password_enabled=(payload.get("emailPasswordEnabled")),
        third_party_enabled=(payload.get("thirdPartyEnabled")),
        passwordless_enabled=(payload.get("passwordlessEnabled")),
        first_factors=payload.get("firstFactors")))


@app.post("/recipe/multitenancy/tenant/remove")
def remove_tenant(payload: Dict[str, Any] = Body(default={}),
                  api_key: Optional[str] = Header(default=None, alias="api-key"),
                  cdi_version: Optional[str] = Header(default=None,
                                                      alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.remove_tenant(tenant_id=payload.get("tenantId")))


@app.post("/appid-{app_id}/{tenant_id}/recipe/multitenancy/tenant/user")
@app.post("/recipe/multitenancy/tenant/user")
def associate_user(payload: Dict[str, Any] = Body(default={}),
                   app_id: str = supertokens_data.DEFAULT_APP_ID,
                   tenant_id: str = supertokens_data.DEFAULT_TENANT,
                   api_key: Optional[str] = Header(default=None, alias="api-key"),
                   cdi_version: Optional[str] = Header(default=None,
                                                       alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.associate_user_to_tenant(
        tenant, recipe_user_id=payload.get("recipeUserId")))


# --- account linking ---

@app.post("/recipe/accountlinking/user/primary")
def make_primary(payload: Dict[str, Any] = Body(default={}),
                 api_key: Optional[str] = Header(default=None, alias="api-key"),
                 cdi_version: Optional[str] = Header(default=None,
                                                     alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.make_primary_user(
        recipe_user_id=payload.get("recipeUserId")))


@app.post("/recipe/accountlinking/user/link")
def link_accounts(payload: Dict[str, Any] = Body(default={}),
                  api_key: Optional[str] = Header(default=None, alias="api-key"),
                  cdi_version: Optional[str] = Header(default=None,
                                                      alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.link_accounts(
        recipe_user_id=payload.get("recipeUserId"),
        primary_user_id=payload.get("primaryUserId")))


@app.post("/recipe/accountlinking/user/unlink")
def unlink_account(payload: Dict[str, Any] = Body(default={}),
                   api_key: Optional[str] = Header(default=None, alias="api-key"),
                   cdi_version: Optional[str] = Header(default=None,
                                                       alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.unlink_account(
        recipe_user_id=payload.get("recipeUserId")))


# --- user listing ---

@app.get("/appid-{app_id}/{tenant_id}/users")
@app.get("/users")
def list_users(app_id: str = supertokens_data.DEFAULT_APP_ID,
               tenant_id: str = supertokens_data.DEFAULT_TENANT,
               limit: int = Query(100, ge=1, le=500),
               paginationToken: Optional[str] = None,
               includeRecipeIds: Optional[str] = None,
               email: Optional[str] = None,
               api_key: Optional[str] = Header(default=None, alias="api-key"),
               cdi_version: Optional[str] = Header(default=None,
                                                   alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    recipe_ids = [r for r in (includeRecipeIds or "").split(",") if r]
    return _ok(supertokens_data.list_users(
        tenant, limit=limit, pagination_token=paginationToken,
        include_recipe_ids=recipe_ids or None, email=email))


@app.get("/appid-{app_id}/{tenant_id}/users/count")
@app.get("/users/count")
def count_users(app_id: str = supertokens_data.DEFAULT_APP_ID,
                tenant_id: str = supertokens_data.DEFAULT_TENANT,
                includeAllTenants: bool = False,
                api_key: Optional[str] = Header(default=None, alias="api-key"),
                cdi_version: Optional[str] = Header(default=None,
                                                    alias="cdi-version")):
    tenant, denied = _gate(api_key, cdi_version, tenant_id)
    if denied:
        return denied
    return _ok(supertokens_data.count_users(tenant,
                                            include_all_tenants=includeAllTenants))


@app.get("/user/id")
def get_user_by_id(userId: Optional[str] = None,
                   api_key: Optional[str] = Header(default=None, alias="api-key"),
                   cdi_version: Optional[str] = Header(default=None,
                                                       alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.get_user_by_id(user_id=userId))


@app.post("/user/remove")
def remove_user(payload: Dict[str, Any] = Body(default={}),
                api_key: Optional[str] = Header(default=None, alias="api-key"),
                cdi_version: Optional[str] = Header(default=None,
                                                    alias="cdi-version")):
    _, denied = _gate(api_key, cdi_version)
    if denied:
        return denied
    return _ok(supertokens_data.delete_user(
        user_id=payload.get("userId"),
        remove_all_linked_accounts=payload.get("removeAllLinkedAccounts", True)))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8115)
