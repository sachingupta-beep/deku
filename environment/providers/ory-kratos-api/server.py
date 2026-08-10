"""FastAPI server wrapping ory_kratos_data module as REST endpoints.

Ory Kratos has no login endpoint. It has **self-service flows**, and they are
first-class resources: you create one, receive a flow object carrying a
renderable `ui`, and then submit against that flow's id. A failed submission is
not a bare error --- it is the whole flow re-rendered with messages attached to
the offending `ui.nodes`, which is what a client draws.

Three route families:

* `/self-service/...` --- create and submit login, registration, recovery,
  verification, settings and logout flows.
* `/sessions/...` and `/schemas/...` --- the public read surface.
* `/admin/...` --- the administrative API Kratos serves on its second port,
  including JSON Patch on identities.

Kratos separates its ports; the mock serves both on one and keeps the `/admin`
prefix so the boundary stays visible.
"""

from fastapi import Body, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict, List, Optional

import ory_kratos_data
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

app = FastAPI(title="Ory Kratos API (Mock)", version="v1.3.1")
install_tracker(app)
install_admin_plane(app, store=ory_kratos_data._store)


@app.get("/health")
def health():
    return ory_kratos_data.health()


def _is_error(result):
    return isinstance(result, dict) and "kratos_error" in result


def _fail(result):
    return JSONResponse(status_code=result["code"],
                        content={"error": result["error"]})


def _ok(result, status_code=200):
    """Render a data-module result.

    A failed flow submission comes back as the flow itself with `__status__`
    set, because that is what Kratos returns --- the client re-renders the form
    rather than reading an error body.
    """
    if _is_error(result):
        return _fail(result)
    if isinstance(result, dict) and "__status__" in result:
        status = result["__status__"]
        body = {k: v for k, v in result.items() if k != "__status__"}
        if not body:
            return Response(status_code=status)
        return JSONResponse(status_code=status, content=body)
    return JSONResponse(status_code=status_code, content=result)


SESSION_HEADER = Header(default=None, alias="x-session-token")


# ---------------------------------------------------------------------------
# Health and metadata
# ---------------------------------------------------------------------------

@app.get("/health/alive")
def health_alive():
    return ory_kratos_data.health_alive()


@app.get("/health/ready")
def health_ready():
    return ory_kratos_data.health_ready()


@app.get("/version")
def version():
    return ory_kratos_data.version()


@app.get("/schemas")
def list_schemas():
    return _ok(ory_kratos_data.list_schemas())


@app.get("/schemas/{schema_id}")
def get_schema(schema_id: str):
    return _ok(ory_kratos_data.get_schema(schema_id))


# ---------------------------------------------------------------------------
# Self-service: flow retrieval
#
# Declared before the `{client_type}` creation routes below, because FastAPI
# matches in declaration order and `flows` would otherwise be read as a client
# type.
# ---------------------------------------------------------------------------

def _flow_getter(flow_type):
    def handler(id: Optional[str] = None):
        return _ok(ory_kratos_data.get_flow(flow_type, id))
    handler.__name__ = f"get_{flow_type}_flow"
    return handler


for _flow_type in ("login", "registration", "recovery", "verification",
                   "settings"):
    app.get(f"/self-service/{_flow_type}/flows")(_flow_getter(_flow_type))


# ---------------------------------------------------------------------------
# Self-service: flow creation
# ---------------------------------------------------------------------------

@app.get("/self-service/login/{client_type}")
def create_login_flow(client_type: str, refresh: bool = False,
                      aal: str = "aal1", return_to: Optional[str] = None,
                      x_session_token: Optional[str] = SESSION_HEADER):
    if client_type not in ("api", "browser"):
        return _fail(ory_kratos_data._not_found(
            "Unable to locate the flow you are looking for."))
    return _ok(ory_kratos_data.create_login_flow(
        client_type, refresh=refresh, aal=aal, return_to=return_to or "",
        session_token=x_session_token))


@app.get("/self-service/registration/{client_type}")
def create_registration_flow(client_type: str,
                             return_to: Optional[str] = None):
    if client_type not in ("api", "browser"):
        return _fail(ory_kratos_data._not_found(
            "Unable to locate the flow you are looking for."))
    return _ok(ory_kratos_data.create_registration_flow(client_type,
                                                    return_to=return_to or ""))


@app.get("/self-service/recovery/{client_type}")
def create_recovery_flow(client_type: str, return_to: Optional[str] = None):
    if client_type not in ("api", "browser"):
        return _fail(ory_kratos_data._not_found(
            "Unable to locate the flow you are looking for."))
    return _ok(ory_kratos_data.create_recovery_flow(client_type,
                                                return_to=return_to or ""))


@app.get("/self-service/verification/{client_type}")
def create_verification_flow(client_type: str,
                             return_to: Optional[str] = None):
    if client_type not in ("api", "browser"):
        return _fail(ory_kratos_data._not_found(
            "Unable to locate the flow you are looking for."))
    return _ok(ory_kratos_data.create_verification_flow(client_type,
                                                    return_to=return_to or ""))


@app.get("/self-service/settings/{client_type}")
def create_settings_flow(client_type: str, return_to: Optional[str] = None,
                         x_session_token: Optional[str] = SESSION_HEADER):
    if client_type not in ("api", "browser"):
        return _fail(ory_kratos_data._not_found(
            "Unable to locate the flow you are looking for."))
    return _ok(ory_kratos_data.create_settings_flow(
        client_type, session_token=x_session_token, return_to=return_to or ""))


# ---------------------------------------------------------------------------
# Self-service: submissions
# ---------------------------------------------------------------------------

@app.post("/self-service/login")
def submit_login(flow: Optional[str] = None,
                 payload: Dict[str, Any] = Body(default={})):
    return _ok(ory_kratos_data.submit_login(flow, payload))


@app.post("/self-service/registration")
def submit_registration(flow: Optional[str] = None,
                        payload: Dict[str, Any] = Body(default={})):
    return _ok(ory_kratos_data.submit_registration(flow, payload))


@app.post("/self-service/recovery")
def submit_recovery(flow: Optional[str] = None,
                    payload: Dict[str, Any] = Body(default={})):
    return _ok(ory_kratos_data.submit_recovery(flow, payload))


@app.post("/self-service/verification")
def submit_verification(flow: Optional[str] = None,
                        payload: Dict[str, Any] = Body(default={})):
    return _ok(ory_kratos_data.submit_verification(flow, payload))


@app.post("/self-service/settings")
def submit_settings(flow: Optional[str] = None,
                    payload: Dict[str, Any] = Body(default={}),
                    x_session_token: Optional[str] = SESSION_HEADER):
    return _ok(ory_kratos_data.submit_settings(flow, payload,
                                           session_token=x_session_token))


@app.delete("/self-service/logout/api")
def submit_logout(payload: Dict[str, Any] = Body(default={}),
                  x_session_token: Optional[str] = SESSION_HEADER):
    token = (payload or {}).get("session_token") or x_session_token
    return _ok(ory_kratos_data.submit_logout(session_token=token))


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@app.get("/sessions/whoami")
def whoami(x_session_token: Optional[str] = SESSION_HEADER):
    return _ok(ory_kratos_data.whoami(session_token=x_session_token))


@app.get("/sessions")
def list_my_sessions(x_session_token: Optional[str] = SESSION_HEADER):
    return _ok(ory_kratos_data.list_my_sessions(session_token=x_session_token))


@app.delete("/sessions")
def revoke_my_sessions(x_session_token: Optional[str] = SESSION_HEADER):
    return _ok(ory_kratos_data.revoke_my_sessions(session_token=x_session_token))


@app.delete("/sessions/{session_id}")
def revoke_my_session(session_id: str,
                      x_session_token: Optional[str] = SESSION_HEADER):
    return _ok(ory_kratos_data.revoke_my_session(session_id,
                                             session_token=x_session_token))


# ---------------------------------------------------------------------------
# Admin: identities
# ---------------------------------------------------------------------------

@app.get("/admin/identities")
def admin_list_identities(page_size: int = Query(20, ge=1, le=500),
                          page_token: Optional[str] = None,
                          credentials_identifier: Optional[str] = None,
                          include_credential: Optional[str] = None):
    include = include_credential.split(",") if include_credential else None
    return _ok(ory_kratos_data.admin_list_identities(
        page_size=page_size, page_token=page_token,
        credentials_identifier=credentials_identifier,
        include_credential=include))


@app.post("/admin/identities")
def admin_create_identity(payload: Dict[str, Any] = Body(default={})):
    return _ok(ory_kratos_data.admin_create_identity(payload))


@app.get("/admin/identities/{identity_id}")
def admin_get_identity(identity_id: str,
                       include_credential: Optional[str] = None):
    include = include_credential.split(",") if include_credential else None
    return _ok(ory_kratos_data.admin_get_identity(identity_id,
                                              include_credential=include))


@app.put("/admin/identities/{identity_id}")
def admin_update_identity(identity_id: str,
                          payload: Dict[str, Any] = Body(default={})):
    return _ok(ory_kratos_data.admin_update_identity(identity_id, payload))


@app.patch("/admin/identities/{identity_id}")
def admin_patch_identity(identity_id: str,
                         payload: List[Dict[str, Any]] = Body(default=[])):
    """JSON Patch (RFC 6902), which Kratos exposes alongside the whole-document PUT."""
    return _ok(ory_kratos_data.admin_patch_identity(identity_id, payload))


@app.delete("/admin/identities/{identity_id}")
def admin_delete_identity(identity_id: str):
    return _ok(ory_kratos_data.admin_delete_identity(identity_id))


@app.get("/admin/identities/{identity_id}/sessions")
def admin_identity_sessions(identity_id: str, active: Optional[bool] = None):
    return _ok(ory_kratos_data.admin_identity_sessions(identity_id, active=active))


@app.delete("/admin/identities/{identity_id}/sessions")
def admin_delete_identity_sessions(identity_id: str):
    return _ok(ory_kratos_data.admin_delete_identity_sessions(identity_id))


@app.delete("/admin/identities/{identity_id}/credentials/{credential_type}")
def admin_delete_credential(identity_id: str, credential_type: str):
    return _ok(ory_kratos_data.admin_delete_credential(identity_id,
                                                   credential_type))


# ---------------------------------------------------------------------------
# Admin: recovery, sessions
# ---------------------------------------------------------------------------

@app.post("/admin/recovery/code")
def admin_create_recovery_code(payload: Dict[str, Any] = Body(default={})):
    return _ok(ory_kratos_data.admin_create_recovery_code(payload))


@app.post("/admin/recovery/link")
def admin_create_recovery_link(payload: Dict[str, Any] = Body(default={})):
    return _ok(ory_kratos_data.admin_create_recovery_link(payload))


@app.get("/admin/sessions")
def admin_list_sessions(active: Optional[bool] = None,
                        page_size: int = Query(20, ge=1, le=500)):
    return _ok(ory_kratos_data.admin_list_sessions(active=active,
                                               page_size=page_size))


@app.get("/admin/sessions/{session_id}")
def admin_get_session(session_id: str):
    return _ok(ory_kratos_data.admin_get_session(session_id))


@app.patch("/admin/sessions/{session_id}/extend")
def admin_extend_session(session_id: str):
    return _ok(ory_kratos_data.admin_extend_session(session_id))


@app.delete("/admin/sessions/{session_id}")
def admin_disable_session(session_id: str):
    return _ok(ory_kratos_data.admin_disable_session(session_id))


# ---------------------------------------------------------------------------
# Admin: courier
# ---------------------------------------------------------------------------

@app.get("/admin/courier/messages")
def admin_list_courier_messages(status: Optional[str] = None,
                                recipient: Optional[str] = None,
                                page_size: int = Query(20, ge=1, le=500)):
    return _ok(ory_kratos_data.list_courier_messages(status=status,
                                                 recipient=recipient,
                                                 page_size=page_size))


@app.get("/admin/courier/messages/{message_id}")
def admin_get_courier_message(message_id: str):
    return _ok(ory_kratos_data.get_courier_message(message_id))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8119)
