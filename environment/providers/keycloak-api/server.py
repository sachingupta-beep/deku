"""FastAPI server wrapping keycloak_data module as REST endpoints.

Two URL families, both scoped to a realm:

* `/realms/{realm}/protocol/openid-connect/...` --- what a client talks to.
  `POST .../token` supports `password` (Keycloak's direct grant),
  `refresh_token` and `client_credentials`. Errors are RFC 6749.
* `/admin/realms/{realm}/...` --- the Admin REST API. It takes the bearer minted
  by the master realm's `admin-cli`, or any live session token *for that realm*,
  and checks the caller's `realm-management` client roles. Errors are Keycloak's
  `{"error", "errorMessage"}`.

Nothing crosses a realm boundary: a token issued for `orbit-labs` administering
`orbit-partners` is 403, and a user only exists inside their own realm.
"""

from fastapi import Body, FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict, List, Optional

import keycloak_data
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

app = FastAPI(title="Keycloak API (Mock)", version="26.0.5")
install_tracker(app)
install_admin_plane(app, store=keycloak_data._store)


@app.get("/health")
def health():
    return keycloak_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    status = result.get("code", 400)
    if result.get("oauth"):
        body = {"error": result["error"]}
        if result.get("error_description"):
            body["error_description"] = result["error_description"]
        return JSONResponse(status_code=status, content=body)
    return JSONResponse(status_code=status,
                        content={"error": result["error"],
                                 "errorMessage": result["errorMessage"]})


def _ok(result, status_code=200):
    if _is_error(result):
        return _fail(result)
    if isinstance(result, dict) and "__status__" in result:
        body = {k: v for k, v in result.items() if k != "__status__"}
        if not body:
            return Response(status_code=result["__status__"])
        return JSONResponse(status_code=result["__status__"], content=body)
    return JSONResponse(status_code=status_code, content=result)


def _realm_or_fail(realm_name):
    """Resolve a realm. Returns `(realm, failure_response)`."""
    realm, denied = keycloak_data.resolve_realm(realm_name)
    return realm, (_fail(denied) if denied else None)


def _admin_gate(authorization, realm_name, required_role=None):
    """Resolve the realm and authorize the admin caller in one step."""
    realm, denied = _realm_or_fail(realm_name)
    if denied:
        return None, denied
    _, denied = keycloak_data.authorize_admin(authorization, realm_name,
                                              required_role)
    if denied:
        return None, _fail(denied)
    return realm, None


def _client_ip(request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "203.0.113.41"


def _base_url(request):
    return str(request.base_url).rstrip("/")


# ---------------------------------------------------------------------------
# OIDC endpoints
# ---------------------------------------------------------------------------

@app.get("/realms/{realm_name}")
def realm_info(realm_name: str):
    realm, denied = _realm_or_fail(realm_name)
    if denied:
        return denied
    return keycloak_data.realm_public_info(realm)


@app.get("/realms/{realm_name}/.well-known/openid-configuration")
def openid_configuration(realm_name: str, request: Request):
    realm, denied = _realm_or_fail(realm_name)
    if denied:
        return denied
    return keycloak_data.openid_configuration(realm, _base_url(request))


@app.get("/realms/{realm_name}/protocol/openid-connect/certs")
def certs(realm_name: str):
    _, denied = _realm_or_fail(realm_name)
    if denied:
        return denied
    return keycloak_data.certs()


@app.post("/realms/{realm_name}/protocol/openid-connect/token")
def token(realm_name: str, request: Request,
          payload: Dict[str, Any] = Body(default={})):
    """The token endpoint.

    Real clients post `application/x-www-form-urlencoded`; the mock accepts JSON
    with the same field names so the collection stays readable.
    """
    realm, denied = _realm_or_fail(realm_name)
    if denied:
        return denied
    return _ok(keycloak_data.token(
        realm, grant_type=payload.get("grant_type"),
        client_id=payload.get("client_id"),
        client_secret=payload.get("client_secret"),
        username=payload.get("username"), password=payload.get("password"),
        refresh_token=payload.get("refresh_token"), scope=payload.get("scope"),
        ip=_client_ip(request)))


@app.post("/realms/{realm_name}/protocol/openid-connect/token/introspect")
def introspect(realm_name: str, payload: Dict[str, Any] = Body(default={})):
    realm, denied = _realm_or_fail(realm_name)
    if denied:
        return denied
    return _ok(keycloak_data.introspect(realm, token_value=payload.get("token")))


@app.get("/realms/{realm_name}/protocol/openid-connect/userinfo")
def userinfo(realm_name: str, authorization: Optional[str] = Header(default=None)):
    realm, denied = _realm_or_fail(realm_name)
    if denied:
        return denied
    return _ok(keycloak_data.userinfo(realm, authorization=authorization))


@app.post("/realms/{realm_name}/protocol/openid-connect/logout")
def logout(realm_name: str, payload: Dict[str, Any] = Body(default={})):
    realm, denied = _realm_or_fail(realm_name)
    if denied:
        return denied
    return _ok(keycloak_data.logout(realm,
                                    refresh_token=payload.get("refresh_token")))


# ---------------------------------------------------------------------------
# Admin API: server info and realms
# ---------------------------------------------------------------------------

@app.get("/admin/serverinfo")
def server_info(authorization: Optional[str] = Header(default=None)):
    _, denied = keycloak_data.authorize_admin(authorization)
    if denied:
        return _fail(denied)
    return keycloak_data.server_info()


@app.get("/admin/realms")
def list_realms(authorization: Optional[str] = Header(default=None)):
    _, denied = keycloak_data.authorize_admin(authorization)
    if denied:
        return _fail(denied)
    return _ok(keycloak_data.list_realms())


@app.get("/admin/realms/{realm_name}")
def get_realm(realm_name: str,
              authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_realm(realm))


@app.put("/admin/realms/{realm_name}")
def update_realm(realm_name: str, payload: Dict[str, Any] = Body(default={}),
                 authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-realm")
    if denied:
        return denied
    return _ok(keycloak_data.update_realm(realm, payload))


# ---------------------------------------------------------------------------
# Admin API: clients
# ---------------------------------------------------------------------------

@app.get("/admin/realms/{realm_name}/clients")
def list_clients(realm_name: str, clientId: Optional[str] = None,
                 authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_clients(realm_name, client_id=clientId))


@app.get("/admin/realms/{realm_name}/clients/{client_uuid}")
def get_client(realm_name: str, client_uuid: str,
               authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_client(realm_name, client_uuid))


@app.get("/admin/realms/{realm_name}/clients/{client_uuid}/client-secret")
def get_client_secret(realm_name: str, client_uuid: str,
                      authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-realm")
    if denied:
        return denied
    return _ok(keycloak_data.get_client_secret(realm_name, client_uuid))


@app.get("/admin/realms/{realm_name}/clients/{client_uuid}/roles")
def list_client_roles(realm_name: str, client_uuid: str,
                      authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_client_roles(realm_name, client_uuid))


@app.get("/admin/realms/{realm_name}/clients/{client_uuid}/user-sessions")
def client_user_sessions(realm_name: str, client_uuid: str,
                         authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.client_user_sessions(realm_name, client_uuid))


# ---------------------------------------------------------------------------
# Admin API: realm roles
# ---------------------------------------------------------------------------

@app.get("/admin/realms/{realm_name}/roles")
def list_realm_roles(realm_name: str,
                     authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_realm_roles(realm_name))


@app.post("/admin/realms/{realm_name}/roles")
def create_realm_role(realm_name: str, payload: Dict[str, Any] = Body(default={}),
                      authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-realm")
    if denied:
        return denied
    return _ok(keycloak_data.create_realm_role(realm_name, payload))


@app.get("/admin/realms/{realm_name}/roles/{role_name}")
def get_realm_role(realm_name: str, role_name: str,
                   authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_realm_role(realm_name, role_name))


@app.get("/admin/realms/{realm_name}/roles/{role_name}/composites")
def get_realm_role_composites(realm_name: str, role_name: str,
                              authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_realm_role_composites(realm_name, role_name))


@app.delete("/admin/realms/{realm_name}/roles/{role_name}")
def delete_realm_role(realm_name: str, role_name: str,
                      authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-realm")
    if denied:
        return denied
    return _ok(keycloak_data.delete_realm_role(realm_name, role_name))


# ---------------------------------------------------------------------------
# Admin API: users
# ---------------------------------------------------------------------------

@app.get("/admin/realms/{realm_name}/users")
def list_users(realm_name: str, search: Optional[str] = None,
               username: Optional[str] = None, email: Optional[str] = None,
               enabled: Optional[bool] = None, first: int = Query(0, ge=0),
               max: int = Query(20, ge=1, le=500), briefRepresentation: bool = False,
               authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_users(realm_name, search=search,
                                        username=username, email=email,
                                        enabled=enabled, first=first,
                                        max_results=max,
                                        brief=briefRepresentation))


@app.get("/admin/realms/{realm_name}/users/count")
def count_users(realm_name: str,
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.count_users(realm_name))


@app.post("/admin/realms/{realm_name}/users")
def create_user(realm_name: str, payload: Dict[str, Any] = Body(default={}),
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.create_user(realm, payload))


@app.get("/admin/realms/{realm_name}/users/{user_id}")
def get_user(realm_name: str, user_id: str,
             authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_user(realm_name, user_id))


@app.put("/admin/realms/{realm_name}/users/{user_id}")
def update_user(realm_name: str, user_id: str,
                payload: Dict[str, Any] = Body(default={}),
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.update_user(realm_name, user_id, payload))


@app.delete("/admin/realms/{realm_name}/users/{user_id}")
def delete_user(realm_name: str, user_id: str,
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.delete_user(realm_name, user_id))


@app.put("/admin/realms/{realm_name}/users/{user_id}/reset-password")
def reset_password(realm_name: str, user_id: str,
                   payload: Dict[str, Any] = Body(default={}),
                   authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.reset_password(realm, user_id, payload))


@app.put("/admin/realms/{realm_name}/users/{user_id}/execute-actions-email")
def execute_actions_email(realm_name: str, user_id: str,
                          payload: List[str] = Body(default=[]),
                          authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.execute_actions_email(realm_name, user_id,
                                                   actions=payload))


@app.get("/admin/realms/{realm_name}/users/{user_id}/sessions")
def user_sessions(realm_name: str, user_id: str,
                  authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.user_sessions(realm_name, user_id))


@app.get("/admin/realms/{realm_name}/users/{user_id}/offline-sessions")
def user_offline_sessions(realm_name: str, user_id: str,
                          authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.user_sessions(realm_name, user_id, offline=True))


@app.post("/admin/realms/{realm_name}/users/{user_id}/logout")
def logout_user(realm_name: str, user_id: str,
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.logout_user(realm_name, user_id))


# ---------------------------------------------------------------------------
# Admin API: role mappings
# ---------------------------------------------------------------------------

@app.get("/admin/realms/{realm_name}/users/{user_id}/role-mappings")
def get_role_mappings(realm_name: str, user_id: str,
                      authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_role_mappings(realm_name, user_id))


@app.get("/admin/realms/{realm_name}/users/{user_id}/role-mappings/effective")
def get_effective_role_mappings(realm_name: str, user_id: str,
                                authorization: Optional[str] = Header(default=None)):
    """Direct mappings plus group inheritance plus composite expansion.

    Not a Keycloak path verbatim --- the real API exposes the same information
    through `composite=true` query parameters on several endpoints. Collapsing it
    into one place keeps the difference from `/role-mappings` visible.
    """
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_effective_role_mappings(realm_name, user_id))


@app.post("/admin/realms/{realm_name}/users/{user_id}/role-mappings/realm")
def add_realm_role_mappings(realm_name: str, user_id: str,
                            payload: List[Dict[str, Any]] = Body(default=[]),
                            authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.add_realm_role_mappings(realm_name, user_id,
                                                     roles=payload))


@app.delete("/admin/realms/{realm_name}/users/{user_id}/role-mappings/realm")
def remove_realm_role_mappings(realm_name: str, user_id: str,
                               payload: List[Dict[str, Any]] = Body(default=[]),
                               authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.remove_realm_role_mappings(realm_name, user_id,
                                                        roles=payload))


@app.get("/admin/realms/{realm_name}/users/{user_id}/role-mappings/clients/{client_uuid}")
def get_client_role_mappings(realm_name: str, user_id: str, client_uuid: str,
                             authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_client_role_mappings(realm_name, user_id,
                                                      client_uuid))


@app.post("/admin/realms/{realm_name}/users/{user_id}/role-mappings/clients/{client_uuid}")
def add_client_role_mappings(realm_name: str, user_id: str, client_uuid: str,
                             payload: List[Dict[str, Any]] = Body(default=[]),
                             authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.add_client_role_mappings(realm_name, user_id,
                                                      client_uuid, roles=payload))


# ---------------------------------------------------------------------------
# Admin API: groups
# ---------------------------------------------------------------------------

@app.get("/admin/realms/{realm_name}/groups")
def list_groups(realm_name: str,
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_groups(realm_name))


@app.post("/admin/realms/{realm_name}/groups")
def create_group(realm_name: str, payload: Dict[str, Any] = Body(default={}),
                 authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.create_group(realm_name, payload))


@app.get("/admin/realms/{realm_name}/groups/{group_id}")
def get_group(realm_name: str, group_id: str,
              authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_group(realm_name, group_id))


@app.post("/admin/realms/{realm_name}/groups/{group_id}/children")
def create_subgroup(realm_name: str, group_id: str,
                    payload: Dict[str, Any] = Body(default={}),
                    authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.create_group(realm_name, payload,
                                          parent_id=group_id))


@app.delete("/admin/realms/{realm_name}/groups/{group_id}")
def delete_group(realm_name: str, group_id: str,
                 authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.delete_group(realm_name, group_id))


@app.get("/admin/realms/{realm_name}/groups/{group_id}/members")
def group_members(realm_name: str, group_id: str,
                  authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.group_members(realm_name, group_id))


@app.get("/admin/realms/{realm_name}/groups/{group_id}/role-mappings")
def group_role_mappings(realm_name: str, group_id: str,
                        authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.group_role_mappings(realm_name, group_id))


@app.get("/admin/realms/{realm_name}/users/{user_id}/groups")
def user_groups(realm_name: str, user_id: str,
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.user_groups(realm_name, user_id))


@app.put("/admin/realms/{realm_name}/users/{user_id}/groups/{group_id}")
def join_group(realm_name: str, user_id: str, group_id: str,
               authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.join_group(realm_name, user_id, group_id))


@app.delete("/admin/realms/{realm_name}/users/{user_id}/groups/{group_id}")
def leave_group(realm_name: str, user_id: str, group_id: str,
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.leave_group(realm_name, user_id, group_id))


# ---------------------------------------------------------------------------
# Admin API: identity providers, required actions, brute force, events
# ---------------------------------------------------------------------------

@app.get("/admin/realms/{realm_name}/identity-provider/instances")
def list_identity_providers(realm_name: str,
                            authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_identity_providers(realm_name))


@app.get("/admin/realms/{realm_name}/identity-provider/instances/{alias}")
def get_identity_provider(realm_name: str, alias: str,
                          authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.get_identity_provider(realm_name, alias))


@app.get("/admin/realms/{realm_name}/authentication/required-actions")
def list_required_actions(realm_name: str,
                          authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_required_actions(realm_name))


@app.get("/admin/realms/{realm_name}/attack-detection/brute-force/users/{user_id}")
def brute_force_status(realm_name: str, user_id: str,
                       authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.brute_force_status(realm_name, user_id))


@app.delete("/admin/realms/{realm_name}/attack-detection/brute-force/users/{user_id}")
def clear_brute_force_user(realm_name: str, user_id: str,
                           authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.clear_brute_force(realm_name, user_id))


@app.delete("/admin/realms/{realm_name}/attack-detection/brute-force/users")
def clear_brute_force_all(realm_name: str,
                          authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "manage-users")
    if denied:
        return denied
    return _ok(keycloak_data.clear_brute_force(realm_name))


@app.get("/admin/realms/{realm_name}/events")
def list_events(realm_name: str, type: Optional[str] = None,
                user: Optional[str] = None, client: Optional[str] = None,
                first: int = Query(0, ge=0), max: int = Query(20, ge=1, le=500),
                authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_events(realm_name, event_type=type,
                                         user_id=user, client_id=client,
                                         first=first, max_results=max))


@app.get("/admin/realms/{realm_name}/admin-events")
def list_admin_events(realm_name: str, operationTypes: Optional[str] = None,
                      resourceTypes: Optional[str] = None,
                      first: int = Query(0, ge=0),
                      max: int = Query(20, ge=1, le=500),
                      authorization: Optional[str] = Header(default=None)):
    realm, denied = _admin_gate(authorization, realm_name, "view-users")
    if denied:
        return denied
    return _ok(keycloak_data.list_admin_events(realm_name,
                                               operation_type=operationTypes,
                                               resource_type=resourceTypes,
                                               first=first, max_results=max))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8117)
