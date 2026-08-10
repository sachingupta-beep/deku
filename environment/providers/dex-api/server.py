"""FastAPI server wrapping dex_data module as REST endpoints.

Dex is a federator with no user database of its own, and the route layout shows
it. Two surfaces:

* `/dex/...` --- the OIDC provider: discovery, keys, the authorization and token
  endpoints, userinfo, introspection and the device authorization grant
  (RFC 8628). Errors follow RFC 6749 / RFC 8628.
* `/api/v2/...` --- Dex's gRPC API over HTTP. It keeps the distinctive
  success-with-flag envelopes: creating a client that already exists is 200 with
  `already_exists: true`, and deleting one that does not is 200 with
  `not_found: true`, rather than 409 and 404.

The only identities Dex stores are the `local` connector's static passwords,
which is why `/api/v2/passwords` is small and `/api/v2/refresh/{user_id}` is the
closest thing to a user list.
"""

from fastapi import Body, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict, List, Optional

import dex_data
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

app = FastAPI(title="Dex API (Mock)", version=dex_data.DEX_VERSION)
install_tracker(app)
install_admin_plane(app, store=dex_data._store)


@app.get("/health")
def health():
    return dex_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    if result.get("oauth"):
        body = {"error": result["error"]}
        if result.get("error_description"):
            body["error_description"] = result["error_description"]
        return JSONResponse(status_code=result["code"], content=body)
    return JSONResponse(status_code=result["code"],
                        content={"error": result["error"]})


def _ok(result, status_code=200):
    if _is_error(result):
        return _fail(result)
    return JSONResponse(status_code=status_code, content=result)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return dex_data.healthz()


@app.get("/dex/.well-known/openid-configuration")
def openid_configuration():
    return dex_data.openid_configuration()


@app.get("/dex/keys")
def keys():
    return dex_data.keys()


@app.get("/dex/connectors")
def list_connectors():
    """Not a Dex endpoint of its own — this is what the chooser page renders."""
    return _ok(dex_data.list_connectors())


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------

@app.get("/dex/auth")
def authorize(client_id: Optional[str] = None,
              redirect_uri: Optional[str] = None, response_type: str = "code",
              scope: Optional[str] = None, state: Optional[str] = None,
              nonce: Optional[str] = None,
              connector_id: Optional[str] = None,
              code_challenge: Optional[str] = None,
              code_challenge_method: Optional[str] = None):
    return _ok(dex_data.authorize(
        client_id=client_id, redirect_uri=redirect_uri,
        response_type=response_type, scope=scope, state=state, nonce=nonce,
        connector_id=connector_id, code_challenge=code_challenge,
        code_challenge_method=code_challenge_method))


@app.get("/dex/auth/{connector_id}")
def authorize_with_connector(connector_id: str,
                             client_id: Optional[str] = None,
                             redirect_uri: Optional[str] = None,
                             response_type: str = "code",
                             scope: Optional[str] = None,
                             state: Optional[str] = None,
                             nonce: Optional[str] = None,
                             code_challenge: Optional[str] = None,
                             code_challenge_method: Optional[str] = None):
    return _ok(dex_data.authorize(
        client_id=client_id, redirect_uri=redirect_uri,
        response_type=response_type, scope=scope, state=state, nonce=nonce,
        connector_id=connector_id, code_challenge=code_challenge,
        code_challenge_method=code_challenge_method))


@app.post("/dex/approval")
def approve(payload: Dict[str, Any] = Body(default={})):
    """Complete an authorization request against a connector.

    Real Dex runs the connector's own login page or OAuth callback; the mock
    takes the credentials directly so the exchange can be driven from a
    collection.
    """
    return _ok(dex_data.approve(
        auth_request_id=payload.get("req") or payload.get("auth_request_id"),
        connector_id=payload.get("connector_id"),
        username=payload.get("username"), password=payload.get("password")))


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

@app.post("/dex/token")
def token(payload: Dict[str, Any] = Body(default={})):
    """The token endpoint.

    Real clients post `application/x-www-form-urlencoded`; the mock accepts JSON
    with the same field names so the collection stays readable.
    """
    return _ok(dex_data.token(
        grant_type=payload.get("grant_type"),
        client_id=payload.get("client_id"),
        client_secret=payload.get("client_secret"),
        code=payload.get("code"), code_verifier=payload.get("code_verifier"),
        redirect_uri=payload.get("redirect_uri"),
        refresh_token=payload.get("refresh_token"),
        username=payload.get("username"), password=payload.get("password"),
        scope=payload.get("scope"), connector_id=payload.get("connector_id"),
        device_code=payload.get("device_code")))


@app.post("/dex/token/introspect")
def introspect(payload: Dict[str, Any] = Body(default={})):
    return _ok(dex_data.introspect(token_value=payload.get("token")))


@app.get("/dex/userinfo")
def userinfo(authorization: Optional[str] = Header(default=None)):
    return _ok(dex_data.userinfo(authorization=authorization))


# ---------------------------------------------------------------------------
# Device authorization grant
# ---------------------------------------------------------------------------

@app.post("/dex/device/code")
def device_code(payload: Dict[str, Any] = Body(default={})):
    return _ok(dex_data.device_code(client_id=payload.get("client_id"),
                                    scope=payload.get("scope")))


@app.get("/dex/device")
def device_lookup(user_code: Optional[str] = None):
    return _ok(dex_data.device_lookup(user_code=user_code))


@app.post("/dex/device/auth/verify")
def device_approve(payload: Dict[str, Any] = Body(default={})):
    """Approve or deny a device request.

    Dex renders this as a page the user visits; the mock takes the decision and
    the connector credentials directly.
    """
    return _ok(dex_data.device_approve(
        user_code=payload.get("user_code"),
        connector_id=payload.get("connector_id", "local"),
        username=payload.get("username"), password=payload.get("password"),
        approve_request=payload.get("approve", True)))


@app.post("/dex/device/token")
def device_token(payload: Dict[str, Any] = Body(default={})):
    """The device grant polls here; `/dex/token` accepts the same grant type."""
    return _ok(dex_data.token(grant_type=dex_data.DEVICE_GRANT,
                              client_id=payload.get("client_id"),
                              device_code=payload.get("device_code")))


# ---------------------------------------------------------------------------
# The gRPC-derived API
# ---------------------------------------------------------------------------

@app.get("/api/v2/version")
def api_version():
    return dex_data.api_version()


@app.get("/api/v2/clients")
def list_clients():
    return _ok(dex_data.list_clients())


@app.post("/api/v2/clients")
def create_client(payload: Dict[str, Any] = Body(default={})):
    return _ok(dex_data.create_client(payload))


@app.get("/api/v2/clients/{client_id}")
def get_client(client_id: str):
    return _ok(dex_data.get_client(client_id))


@app.put("/api/v2/clients/{client_id}")
def update_client(client_id: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(dex_data.update_client(client_id, payload))


@app.delete("/api/v2/clients/{client_id}")
def delete_client(client_id: str):
    return _ok(dex_data.delete_client(client_id))


@app.get("/api/v2/passwords")
def list_passwords():
    return _ok(dex_data.list_passwords())


@app.post("/api/v2/passwords")
def create_password(payload: Dict[str, Any] = Body(default={})):
    return _ok(dex_data.create_password(payload))


@app.put("/api/v2/passwords/{email}")
def update_password(email: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(dex_data.update_password(email, payload))


@app.delete("/api/v2/passwords/{email}")
def delete_password(email: str):
    return _ok(dex_data.delete_password(email))


@app.post("/api/v2/passwords/verify")
def verify_password(payload: Dict[str, Any] = Body(default={})):
    return _ok(dex_data.verify_password(email=payload.get("email"),
                                        password=payload.get("password")))


@app.get("/api/v2/refresh/{user_id:path}")
def list_refresh(user_id: str):
    """`user_id` is a path parameter because an LDAP identity is a full DN."""
    return _ok(dex_data.list_refresh(user_id))


@app.post("/api/v2/refresh/revoke")
def revoke_refresh(payload: Dict[str, Any] = Body(default={})):
    return _ok(dex_data.revoke_refresh(payload.get("user_id"),
                                       client_id=payload.get("client_id")))


@app.get("/api/v2/offline-sessions")
def list_offline_sessions():
    """Every identity Dex currently remembers — its nearest thing to a user list."""
    return _ok(dex_data.list_offline_sessions())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8120)
