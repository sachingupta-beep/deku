"""FastAPI server wrapping zitadel_data module as REST endpoints.

The organization is a **header**, not a path segment: `x-zitadel-orgid` selects
it for the whole request, and absent it the instance's default org is used. Every
handler resolves the org first, so a user in one org is simply not found from
another.

Three route families:

* `/v2/users/...` and `/v2/sessions/...` --- the v2 resource APIs. Sessions are
  built up factor by factor with `checks`, not with a single login call.
* `/v2/oidc/auth_requests/...` --- where a session is exchanged for an OIDC
  callback, and where the org's login policy (including `forceMfa`) is actually
  enforced.
* `/management/v1/...` and `/admin/v1/...` --- projects, roles, grants, members
  and instance-level org search.

Errors carry a gRPC status code in the body next to the HTTP status, and every
write returns Zitadel's `details` envelope with a monotonic `sequence`.
"""

from fastapi import Body, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict, List, Optional

import zitadel_data
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

app = FastAPI(title="Zitadel API (Mock)", version="2.65.1")
install_tracker(app)
install_admin_plane(app, store=zitadel_data._store)


@app.get("/health")
def health():
    return zitadel_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    body = {"code": result["grpc_code"], "message": result["message"]}
    if result.get("detail"):
        body["details"] = result["detail"]
    return JSONResponse(status_code=result.get("code", 400), content=body)


def _ok(result, status_code=200):
    if _is_error(result):
        return _fail(result)
    return JSONResponse(status_code=status_code, content=result)


def _context(authorization, org_header, write=False, instance=False):
    """Resolve the org and authorize the caller. Returns `(org_id, failure)`."""
    org, denied = zitadel_data.resolve_org(org_header)
    if denied:
        return None, _fail(denied)
    _, denied = zitadel_data.authorize(authorization, org["id"], write=write,
                                       instance=instance)
    if denied:
        return None, _fail(denied)
    return org["id"], None


def _public_org(org_header):
    """Resolve the org for an endpoint that takes no bearer (the session API)."""
    org, denied = zitadel_data.resolve_org(org_header)
    if denied:
        return None, _fail(denied)
    return org["id"], None


ORG_HEADER = Header(default=None, alias="x-zitadel-orgid")


# ---------------------------------------------------------------------------
# Instance
# ---------------------------------------------------------------------------

@app.get("/debug/healthz")
def healthz():
    return zitadel_data.healthz()


@app.get("/admin/v1/instance")
def instance_info(authorization: Optional[str] = Header(default=None)):
    _, denied = zitadel_data.authorize(authorization, instance=True)
    if denied:
        return _fail(denied)
    return zitadel_data.instance_info()


@app.post("/admin/v1/orgs/_search")
def search_orgs(payload: Dict[str, Any] = Body(default={}),
                authorization: Optional[str] = Header(default=None)):
    """Instance-level org search. Requires IAM_OWNER, not just an org role."""
    _, denied = zitadel_data.authorize(authorization, instance=True)
    if denied:
        return _fail(denied)
    return _ok(zitadel_data.search_orgs(query=payload.get("query"),
                                        state=payload.get("state"),
                                        limit=payload.get("limit", 20)))


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

@app.get("/management/v1/orgs/me")
def get_my_org(authorization: Optional[str] = Header(default=None),
               x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org, denied = zitadel_data.resolve_org(x_zitadel_orgid)
    if denied:
        return _fail(denied)
    _, denied = zitadel_data.authorize(authorization, org["id"])
    if denied:
        return _fail(denied)
    return _ok(zitadel_data.get_org(org))


@app.get("/management/v1/policies/login")
def get_login_policy(authorization: Optional[str] = Header(default=None),
                     x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.get_login_policy(org_id))


# ---------------------------------------------------------------------------
# Users (v2)
# ---------------------------------------------------------------------------

@app.post("/v2/users/human")
def create_human_user(payload: Dict[str, Any] = Body(default={}),
                      authorization: Optional[str] = Header(default=None),
                      x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.create_human_user(org_id, payload), status_code=201)


@app.post("/v2/users/_search")
def search_users(payload: Dict[str, Any] = Body(default={}),
                 authorization: Optional[str] = Header(default=None),
                 x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.search_users(
        org_id, query=payload.get("query"), state=payload.get("state"),
        user_type=payload.get("type"), limit=payload.get("limit", 20),
        offset=payload.get("offset", 0)))


@app.get("/v2/users/{user_id}")
def get_user(user_id: str, authorization: Optional[str] = Header(default=None),
             x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.get_user(org_id, user_id))


@app.put("/v2/users/human/{user_id}")
def update_human_user(user_id: str, payload: Dict[str, Any] = Body(default={}),
                      authorization: Optional[str] = Header(default=None),
                      x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.update_human_user(org_id, user_id, payload))


@app.delete("/v2/users/{user_id}")
def delete_user(user_id: str,
                authorization: Optional[str] = Header(default=None),
                x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.delete_user(org_id, user_id))


@app.post("/v2/users/{user_id}/email")
def set_email(user_id: str, payload: Dict[str, Any] = Body(default={}),
              authorization: Optional[str] = Header(default=None),
              x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    verification = payload.get("verification") or {}
    return _ok(zitadel_data.set_email(
        org_id, user_id, email=payload.get("email"),
        is_verified="isVerified" in verification,
        return_code="returnCode" in verification))


@app.post("/v2/users/{user_id}/email/_verify")
def verify_email(user_id: str, payload: Dict[str, Any] = Body(default={}),
                 authorization: Optional[str] = Header(default=None),
                 x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.verify_email(org_id, user_id,
                                         code=payload.get("verificationCode")))


@app.post("/v2/users/{user_id}/password")
def set_password(user_id: str, payload: Dict[str, Any] = Body(default={}),
                 authorization: Optional[str] = Header(default=None),
                 x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    new_password = (payload.get("newPassword") or {}).get("password") \
        if isinstance(payload.get("newPassword"), dict) \
        else payload.get("newPassword")
    change_required = (payload.get("newPassword") or {}).get("changeRequired",
                                                             False) \
        if isinstance(payload.get("newPassword"), dict) else False
    verification = payload.get("verification") or {}
    return _ok(zitadel_data.set_password(
        org_id, user_id, new_password=new_password,
        current_password=verification.get("currentPassword"),
        verification_code=verification.get("verificationCode"),
        change_required=change_required))


@app.post("/v2/users/{user_id}/password_reset")
def request_password_reset(user_id: str, payload: Dict[str, Any] = Body(default={}),
                           authorization: Optional[str] = Header(default=None),
                           x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.request_password_reset(
        org_id, user_id, return_code="returnCode" in (payload or {})))


def _state_route(action):
    """Build one of the four lifecycle handlers.

    They are separate routes rather than a `{action}` catch-all so they cannot
    shadow the sibling paths (`/totp`, `/email`, `/password`).
    """
    def handler(user_id: str,
                authorization: Optional[str] = Header(default=None),
                x_zitadel_orgid: Optional[str] = ORG_HEADER):
        org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
        if denied:
            return denied
        return _ok(zitadel_data.change_user_state(org_id, user_id, action))
    handler.__name__ = f"{action}_user"
    return handler


for _action in ("deactivate", "reactivate", "lock", "unlock"):
    app.post(f"/v2/users/{{user_id}}/{_action}")(_state_route(_action))


# ---------------------------------------------------------------------------
# Authentication factors
# ---------------------------------------------------------------------------

@app.get("/v2/users/{user_id}/authentication_factors")
def list_auth_factors(user_id: str,
                      authorization: Optional[str] = Header(default=None),
                      x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.list_auth_factors(org_id, user_id))


@app.post("/v2/users/{user_id}/totp")
def register_totp(user_id: str,
                  authorization: Optional[str] = Header(default=None),
                  x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.register_totp(org_id, user_id), status_code=201)


@app.post("/v2/users/{user_id}/totp/_verify")
def verify_totp(user_id: str, payload: Dict[str, Any] = Body(default={}),
                authorization: Optional[str] = Header(default=None),
                x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.verify_totp(org_id, user_id,
                                        code=payload.get("code")))


@app.delete("/v2/users/{user_id}/authentication_factors/{factor_id}")
def remove_auth_factor(user_id: str, factor_id: str,
                       authorization: Optional[str] = Header(default=None),
                       x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.remove_auth_factor(org_id, user_id, factor_id))


# ---------------------------------------------------------------------------
# Sessions (v2)
#
# These take no bearer: the session token *is* the credential, which is why
# creating a session is unauthenticated and everything after it quotes the
# token returned by the previous call.
# ---------------------------------------------------------------------------

@app.post("/v2/sessions")
def create_session(payload: Dict[str, Any] = Body(default={}),
                   x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _public_org(x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.create_session(
        org_id, checks=payload.get("checks"), metadata=payload.get("metadata"),
        lifetime_seconds=payload.get("lifetime"),
        user_agent=payload.get("userAgent")), status_code=201)


@app.post("/v2/sessions/_search")
def search_sessions(payload: Dict[str, Any] = Body(default={}),
                    authorization: Optional[str] = Header(default=None),
                    x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.search_sessions(org_id,
                                            user_id=payload.get("userId"),
                                            limit=payload.get("limit", 20)))


@app.get("/v2/sessions/{session_id}")
def get_session(session_id: str, sessionToken: Optional[str] = None,
                x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _public_org(x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.get_session(org_id, session_id,
                                        session_token=sessionToken))


@app.patch("/v2/sessions/{session_id}")
def update_session(session_id: str, payload: Dict[str, Any] = Body(default={}),
                   x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _public_org(x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.update_session(
        org_id, session_id, session_token=payload.get("sessionToken"),
        checks=payload.get("checks"), metadata=payload.get("metadata"),
        lifetime_seconds=payload.get("lifetime")))


@app.delete("/v2/sessions/{session_id}")
def delete_session(session_id: str, payload: Dict[str, Any] = Body(default={}),
                   x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _public_org(x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.delete_session(
        org_id, session_id, session_token=(payload or {}).get("sessionToken")))


# ---------------------------------------------------------------------------
# OIDC auth requests
# ---------------------------------------------------------------------------

@app.get("/v2/oidc/auth_requests/{auth_request_id}")
def get_auth_request(auth_request_id: str,
                     x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _public_org(x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.get_auth_request(org_id, auth_request_id))


@app.post("/v2/oidc/auth_requests/{auth_request_id}")
def finalize_auth_request(auth_request_id: str,
                          payload: Dict[str, Any] = Body(default={}),
                          x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _public_org(x_zitadel_orgid)
    if denied:
        return denied
    session = payload.get("session") or {}
    return _ok(zitadel_data.finalize_auth_request(
        org_id, auth_request_id, session_id=session.get("sessionId"),
        session_token=session.get("sessionToken"),
        deny=bool(payload.get("deny"))))


# ---------------------------------------------------------------------------
# Projects, roles and grants (management API)
# ---------------------------------------------------------------------------

@app.post("/management/v1/projects/_search")
def search_projects(payload: Dict[str, Any] = Body(default={}),
                    authorization: Optional[str] = Header(default=None),
                    x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.search_projects(org_id, query=payload.get("query"),
                                            limit=payload.get("limit", 20)))


@app.get("/management/v1/projects/{project_id}")
def get_project(project_id: str,
                authorization: Optional[str] = Header(default=None),
                x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.get_project(org_id, project_id))


@app.post("/management/v1/projects")
def create_project(payload: Dict[str, Any] = Body(default={}),
                   authorization: Optional[str] = Header(default=None),
                   x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.create_project(org_id, payload), status_code=201)


@app.post("/management/v1/projects/{project_id}/roles/_search")
def search_project_roles(project_id: str, payload: Dict[str, Any] = Body(default={}),
                         authorization: Optional[str] = Header(default=None),
                         x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.search_project_roles(org_id, project_id,
                                                 limit=payload.get("limit", 50)))


@app.post("/management/v1/projects/{project_id}/roles")
def add_project_role(project_id: str, payload: Dict[str, Any] = Body(default={}),
                     authorization: Optional[str] = Header(default=None),
                     x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.add_project_role(org_id, project_id, payload),
               status_code=201)


@app.post("/management/v1/users/grants/_search")
def search_user_grants(payload: Dict[str, Any] = Body(default={}),
                       authorization: Optional[str] = Header(default=None),
                       x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.search_user_grants(
        org_id, user_id=payload.get("userId"),
        project_id=payload.get("projectId"), state=payload.get("state"),
        limit=payload.get("limit", 50)))


@app.post("/management/v1/users/{user_id}/grants")
def create_user_grant(user_id: str, payload: Dict[str, Any] = Body(default={}),
                      authorization: Optional[str] = Header(default=None),
                      x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.create_user_grant(org_id, {**(payload or {}),
                                                       "userId": user_id}),
               status_code=201)


@app.put("/management/v1/users/{user_id}/grants/{grant_id}")
def update_user_grant(user_id: str, grant_id: str,
                      payload: Dict[str, Any] = Body(default={}),
                      authorization: Optional[str] = Header(default=None),
                      x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.update_user_grant(org_id, grant_id,
                                              role_keys=payload.get("roleKeys")))


@app.delete("/management/v1/users/{user_id}/grants/{grant_id}")
def delete_user_grant(user_id: str, grant_id: str,
                      authorization: Optional[str] = Header(default=None),
                      x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.delete_user_grant(org_id, grant_id))


# ---------------------------------------------------------------------------
# Org members and events
# ---------------------------------------------------------------------------

@app.post("/management/v1/orgs/me/members/_search")
def search_org_members(payload: Dict[str, Any] = Body(default={}),
                       authorization: Optional[str] = Header(default=None),
                       x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.search_org_members(org_id,
                                               limit=payload.get("limit", 50)))


@app.post("/management/v1/orgs/me/members")
def add_org_member(payload: Dict[str, Any] = Body(default={}),
                   authorization: Optional[str] = Header(default=None),
                   x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.add_org_member(org_id, payload), status_code=201)


@app.delete("/management/v1/orgs/me/members/{user_id}")
def remove_org_member(user_id: str,
                      authorization: Optional[str] = Header(default=None),
                      x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid, write=True)
    if denied:
        return denied
    return _ok(zitadel_data.remove_org_member(org_id, user_id))


@app.post("/admin/v1/events/_search")
def search_events(payload: Dict[str, Any] = Body(default={}),
                  authorization: Optional[str] = Header(default=None),
                  x_zitadel_orgid: Optional[str] = ORG_HEADER):
    org_id, denied = _context(authorization, x_zitadel_orgid)
    if denied:
        return denied
    return _ok(zitadel_data.list_events(
        org_id, aggregate_types=payload.get("aggregateTypes"),
        aggregate_id=payload.get("aggregateId"),
        event_types=payload.get("eventTypes"), limit=payload.get("limit", 20),
        asc=bool(payload.get("asc"))))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8118)
