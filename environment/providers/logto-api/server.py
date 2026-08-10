"""FastAPI server wrapping logto_data module as REST endpoints.

Two planes, and the boundary between them is the point of this service:

* `/oidc/*` is an OAuth 2.0 authorization server. `POST /oidc/token` takes a
  `grant_type`, a `resource` indicator and a `scope`, and mints an access token
  bound to that resource. Errors follow RFC 6749 (`error` /
  `error_description`).
* `/api/*` is the Management API, which is just another protected resource. A
  bearer works there only if it was issued **for** `https://default.logto.app/api`
  and carries a wide enough scope; otherwise the answer is 403, not 401.
  Errors use Logto's own `{"code", "message"}` shape.
"""

from fastapi import Body, FastAPI, Form, Header, Query, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict, List, Optional

import logto_data
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

app = FastAPI(title="Logto API (Mock)", version="1.23.0")
install_tracker(app)
install_admin_plane(app, store=logto_data._store)


@app.get("/health")
def health():
    return logto_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    """Render the right error body for whichever plane produced it."""
    status = result.get("code", 400)
    if result.get("oauth"):
        return JSONResponse(status_code=status,
                            content={"error": result["error"],
                                     "error_description":
                                         result["error_description"]})
    body = {"code": result.get("logto_code", "request.general"),
            "message": result["message"]}
    if result.get("data") is not None:
        body["data"] = result["data"]
    return JSONResponse(status_code=status, content=body)


def _ok(result, status_code=200):
    if _is_error(result):
        return _fail(result)
    if isinstance(result, dict) and "__status__" in result:
        body = {k: v for k, v in result.items() if k != "__status__"}
        if not body:
            return Response(status_code=result["__status__"])
        return JSONResponse(status_code=result["__status__"], content=body)
    return JSONResponse(status_code=status_code, content=result)


def _guard(authorization, required_scope=None):
    """Management API gate. Returns `(token, failure_response)`."""
    record, denied = logto_data.authorize_management(authorization,
                                                     required_scope)
    return record, (_fail(denied) if denied else None)


# --- Status ---

@app.get("/api/status")
def status():
    return logto_data.status()


# --- OIDC discovery ---

@app.get("/oidc/.well-known/openid-configuration")
def openid_configuration():
    return logto_data.openid_configuration()


@app.get("/oidc/jwks")
def jwks():
    return logto_data.jwks()


# --- OIDC authorize and token ---

@app.get("/oidc/auth")
def authorize(client_id: Optional[str] = None,
              redirect_uri: Optional[str] = None,
              response_type: str = "code", scope: Optional[str] = None,
              resource: Optional[str] = None,
              code_challenge: Optional[str] = None,
              code_challenge_method: Optional[str] = None,
              state: Optional[str] = None,
              organization_id: Optional[str] = None):
    return _ok(logto_data.authorize(
        client_id=client_id, redirect_uri=redirect_uri,
        response_type=response_type, scope=scope, resource=resource,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method, state=state,
        organization_id=organization_id))


@app.post("/oidc/token")
def token(payload: Dict[str, Any] = Body(default={})):
    """The token endpoint.

    Real clients post `application/x-www-form-urlencoded`; the mock accepts JSON
    with the same field names so the collection stays readable.
    """
    return _ok(logto_data.token(
        grant_type=payload.get("grant_type"),
        client_id=payload.get("client_id"),
        client_secret=payload.get("client_secret"),
        code=payload.get("code"), code_verifier=payload.get("code_verifier"),
        redirect_uri=payload.get("redirect_uri"),
        refresh_token=payload.get("refresh_token"),
        resource=payload.get("resource"), scope=payload.get("scope"),
        organization_id=payload.get("organization_id")))


@app.post("/oidc/token/introspection")
def introspect(payload: Dict[str, Any] = Body(default={})):
    return _ok(logto_data.introspect(token_value=payload.get("token")))


@app.post("/oidc/token/revocation")
def revoke(payload: Dict[str, Any] = Body(default={})):
    return _ok(logto_data.revoke(token_value=payload.get("token")))


@app.get("/oidc/me")
def userinfo(authorization: Optional[str] = Header(default=None)):
    return _ok(logto_data.userinfo(authorization=authorization))


# --- Management API: users ---

@app.get("/api/users")
def list_users(page: int = Query(1, ge=1),
               page_size: int = Query(20, ge=1, le=100, alias="page_size"),
               search: Optional[str] = None,
               isSuspended: Optional[bool] = None,
               authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "read:user")
    if denied:
        return denied
    return _ok(logto_data.list_users(page=page, page_size=page_size,
                                     search=search, is_suspended=isSuspended))


@app.post("/api/users")
def create_user(payload: Dict[str, Any] = Body(default={}),
                authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.create_user(payload), status_code=201)


@app.get("/api/users/{user_id}")
def get_user(user_id: str, authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "read:user")
    if denied:
        return denied
    return _ok(logto_data.get_user(user_id))


@app.patch("/api/users/{user_id}")
def update_user(user_id: str, payload: Dict[str, Any] = Body(default={}),
                authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.update_user(user_id, payload))


@app.delete("/api/users/{user_id}")
def delete_user(user_id: str,
                authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.delete_user(user_id))


@app.patch("/api/users/{user_id}/password")
def update_password(user_id: str, payload: Dict[str, Any] = Body(default={}),
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.update_password(user_id,
                                          password=payload.get("password")))


@app.post("/api/users/{user_id}/password/verify")
def verify_password(user_id: str, payload: Dict[str, Any] = Body(default={}),
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "read:user")
    if denied:
        return denied
    return _ok(logto_data.verify_password(user_id,
                                          password=payload.get("password")))


@app.patch("/api/users/{user_id}/is-suspended")
def set_suspended(user_id: str, payload: Dict[str, Any] = Body(default={}),
                  authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.set_suspended(user_id,
                                        is_suspended=payload.get("isSuspended")))


@app.get("/api/users/{user_id}/custom-data")
def get_custom_data(user_id: str,
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "read:user")
    if denied:
        return denied
    return _ok(logto_data.get_custom_data(user_id))


@app.patch("/api/users/{user_id}/custom-data")
def patch_custom_data(user_id: str, payload: Dict[str, Any] = Body(default={}),
                      authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.patch_custom_data(
        user_id, custom_data=payload.get("customData")))


@app.get("/api/users/{user_id}/identities")
def list_identities(user_id: str,
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "read:user")
    if denied:
        return denied
    return _ok(logto_data.list_identities(user_id))


@app.delete("/api/users/{user_id}/identities/{target}")
def delete_identity(user_id: str, target: str,
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.delete_identity(user_id, target))


@app.get("/api/users/{user_id}/roles")
def list_user_roles(user_id: str,
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "read:user")
    if denied:
        return denied
    return _ok(logto_data.list_user_roles(user_id))


@app.post("/api/users/{user_id}/roles")
def assign_user_roles(user_id: str, payload: Dict[str, Any] = Body(default={}),
                      authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.assign_user_roles(user_id,
                                            role_ids=payload.get("roleIds")))


@app.delete("/api/users/{user_id}/roles/{role_id}")
def remove_user_role(user_id: str, role_id: str,
                     authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "write:user")
    if denied:
        return denied
    return _ok(logto_data.remove_user_role(user_id, role_id))


@app.get("/api/users/{user_id}/organizations")
def list_user_organizations(user_id: str,
                            authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization, "read:user")
    if denied:
        return denied
    return _ok(logto_data.list_user_organizations(user_id))


# --- Management API: roles, applications, resources ---

@app.get("/api/roles")
def list_roles(type: Optional[str] = None,
               authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_roles(role_type=type))


@app.post("/api/roles")
def create_role(payload: Dict[str, Any] = Body(default={}),
                authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.create_role(payload), status_code=201)


@app.get("/api/roles/{role_id}")
def get_role(role_id: str, authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.get_role(role_id))


@app.delete("/api/roles/{role_id}")
def delete_role(role_id: str,
                authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.delete_role(role_id))


@app.get("/api/applications")
def list_applications(type: Optional[str] = None,
                      authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_applications(app_type=type))


@app.post("/api/applications")
def create_application(payload: Dict[str, Any] = Body(default={}),
                       authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.create_application(payload), status_code=201)


@app.get("/api/applications/{application_id}")
def get_application(application_id: str,
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.get_application(application_id))


@app.delete("/api/applications/{application_id}")
def delete_application(application_id: str,
                       authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.delete_application(application_id))


@app.get("/api/resources")
def list_resources(authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_resources())


@app.get("/api/resources/{resource_id}/scopes")
def resource_scopes(resource_id: str,
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.get_resource_scopes(resource_id))


# --- Management API: organizations ---

@app.get("/api/organizations")
def list_organizations(page: int = Query(1, ge=1),
                       page_size: int = Query(20, ge=1, le=100,
                                              alias="page_size"),
                       authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_organizations(page=page, page_size=page_size))


@app.post("/api/organizations")
def create_organization(payload: Dict[str, Any] = Body(default={}),
                        authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.create_organization(payload), status_code=201)


@app.get("/api/organizations/{organization_id}")
def get_organization(organization_id: str,
                     authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.get_organization(organization_id))


@app.delete("/api/organizations/{organization_id}")
def delete_organization(organization_id: str,
                        authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.delete_organization(organization_id))


@app.get("/api/organizations/{organization_id}/users")
def list_organization_users(organization_id: str,
                            authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_organization_users(organization_id))


@app.post("/api/organizations/{organization_id}/users")
def add_organization_users(organization_id: str,
                           payload: Dict[str, Any] = Body(default={}),
                           authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.add_organization_users(
        organization_id, user_ids=payload.get("userIds")))


@app.delete("/api/organizations/{organization_id}/users/{user_id}")
def remove_organization_user(organization_id: str, user_id: str,
                             authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.remove_organization_user(organization_id, user_id))


@app.post("/api/organizations/{organization_id}/users/{user_id}/roles")
def set_organization_user_roles(organization_id: str, user_id: str,
                                payload: Dict[str, Any] = Body(default={}),
                                authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.set_organization_user_roles(
        organization_id, user_id,
        organization_role_ids=payload.get("organizationRoleIds")))


@app.get("/api/organization-roles")
def list_organization_roles(authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_organization_roles())


@app.get("/api/organization-scopes")
def list_organization_scopes(authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_organization_scopes())


@app.get("/api/my-organization")
def my_organization(authorization: Optional[str] = Header(default=None)):
    """Read the organization an organization token is scoped to.

    This is the only endpoint that accepts an organization token rather than a
    Management API token, so it demonstrates the other audience.
    """
    record, denied = logto_data.authorize_organization(authorization,
                                                       required_scope="org:read")
    if denied:
        return _fail(denied)
    return _ok(logto_data.get_organization(record["organizationId"]))


# --- Management API: connectors, sign-in experience, logs, dashboard ---

@app.get("/api/connectors")
def list_connectors(type: Optional[str] = None,
                    authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_connectors(connector_type=type))


@app.get("/api/connectors/{connector_id}")
def get_connector(connector_id: str,
                  authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.get_connector(connector_id))


@app.get("/api/sign-in-exp")
def sign_in_experience(authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.sign_in_experience())


@app.patch("/api/sign-in-exp")
def update_sign_in_experience(payload: Dict[str, Any] = Body(default={}),
                              authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.update_sign_in_experience(payload))


@app.get("/api/logs")
def list_logs(page: int = Query(1, ge=1),
              page_size: int = Query(20, ge=1, le=100, alias="page_size"),
              logKey: Optional[str] = None, userId: Optional[str] = None,
              applicationId: Optional[str] = None,
              authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.list_logs(page=page, page_size=page_size,
                                    log_key=logKey, user_id=userId,
                                    application_id=applicationId))


@app.get("/api/logs/{log_id}")
def get_log(log_id: str, authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.get_log(log_id))


@app.get("/api/dashboard/users/total")
def dashboard_totals(authorization: Optional[str] = Header(default=None)):
    _, denied = _guard(authorization)
    if denied:
        return denied
    return _ok(logto_data.dashboard_totals())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8116)
