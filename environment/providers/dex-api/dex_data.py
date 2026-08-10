"""Data access module for the Dex mock service.

Dex is a **federator**, not an identity provider. It has no user database: real
identities live behind *connectors* (LDAP, GitHub, SAML), and the only thing Dex
stores locally is the set of "static passwords" belonging to the built-in `local`
connector. Everything else it knows about a person exists solely because a
refresh token remembers it, which is why `ListRefresh` is the closest thing this
API has to a user list.

Three consequences are modelled rather than flattened:

* **Connectors decide what is possible.** The password grant works only through
  a connector that supports it (`local`, `ldap`); asking for it via `github` is
  refused, and a disabled connector is refused outright.
* **The device authorization grant (RFC 8628) is first-class.** Polling a
  pending device code returns `authorization_pending`, polling faster than the
  interval returns `slow_down`, and denied/expired/redeemed codes each have
  their own error.
* **Cross-client audiences need a trusted peer.** A client may request
  `audience:server:client_id:<other>` only if it is listed on that other
  client's `trustedPeers`.

The gRPC API is exposed over HTTP under `/api/v2`, keeping Dex's distinctive
success-with-flag envelopes: creating a client that exists returns 200 with
`already_exists: true` rather than a 409, and deleting one that does not returns
`not_found: true` rather than a 404.

Passwords are verified as `sha256(salt + password)`; Dex stores bcrypt. Mutations
are held in process memory and reset on restart.
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("dex-api")
_API = "dex-api"

ISSUER = "https://dex.orbit-labs.com/dex"
DEX_VERSION = "v2.41.1"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
AUDIENCE_PREFIX = "audience:server:client_id:"
ID_TOKEN_LIFETIME = 86400
DEVICE_POLL_INTERVAL = 5


def _store_insert(_table, _row):
    """Persist a newly-created row into the shared store (drift/injection-safe).

    Synthesizes the table's registered primary key from the row's ``id`` field
    when the row doesn't already carry it, so creates work regardless of whether
    the table was registered with primary_key="id" or a domain-specific key.
    """
    _t = _store.table(_table)
    if _t.primary_key not in _row and "id" in _row:
        _row = {**_row, _t.primary_key: _row["id"]}
    return _t.upsert(_row)


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _semi_list(row, column):
    raw = opt_str(row, column, default="")
    return [part for part in raw.split(";") if part]


def _semi_map(row, column):
    """Parse a `k=v;k=v` cell into a dict.

    Connector `config` is free-form in Dex; the seed keeps it flat so a CSV
    overlay can shadow the JSON.
    """
    out = {}
    for part in _semi_list(row, column):
        key, _, value = part.partition("=")
        if key:
            out[key] = value
    return out


def _flag(row, column, default="0"):
    return opt_str(row, column, default=default) == "1"


_store.register("connectors", primary_key="id",
                initial_loader=lambda: _coerce_connectors(
                    _load("connectors.json", "connectors")))
_store.register("clients", primary_key="id",
                initial_loader=lambda: _coerce_clients(
                    _load("clients.json", "clients")))
_store.register("passwords", primary_key="email",
                initial_loader=lambda: _coerce_passwords(
                    _load("passwords.json", "passwords")))
_store.register("refresh_tokens", primary_key="id",
                initial_loader=lambda: _coerce_refresh(
                    _load("refresh_tokens.json", "refresh_tokens")))
_store.register("auth_codes", primary_key="code",
                initial_loader=lambda: _coerce_codes(
                    _load("auth_codes.json", "auth_codes")))
_store.register("auth_requests", primary_key="id",
                initial_loader=lambda: _coerce_auth_requests(
                    _load("auth_requests.json", "auth_requests")))
_store.register("device_requests", primary_key="deviceCode",
                initial_loader=lambda: _coerce_device(
                    _load("device_requests.json", "device_requests")))


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def _coerce_connectors(rows):
    return [{**_strip_ctx(r), "enabled": _flag(r, "enabled"),
             "supportsPasswordGrant": _flag(r, "supportsPasswordGrant"),
             "supportsRefresh": _flag(r, "supportsRefresh"),
             "config": _semi_map(r, "config")} for r in rows]


def _coerce_clients(rows):
    return [{**_strip_ctx(r), "public": _flag(r, "public"),
             "redirectURIs": _semi_list(r, "redirectURIs"),
             "trustedPeers": _semi_list(r, "trustedPeers"),
             "grantTypes": _semi_list(r, "grantTypes")} for r in rows]


def _coerce_passwords(rows):
    return [{**_strip_ctx(r), "groups": _semi_list(r, "groups")} for r in rows]


def _coerce_refresh(rows):
    return [{**_strip_ctx(r), "groups": _semi_list(r, "groups"),
             "scopes": _semi_list(r, "scopes")} for r in rows]


def _coerce_codes(rows):
    return [{**_strip_ctx(r), "used": _flag(r, "used"),
             "groups": _semi_list(r, "groups"),
             "scopes": _semi_list(r, "scopes")} for r in rows]


def _coerce_auth_requests(rows):
    return [{**_strip_ctx(r), "loggedIn": _flag(r, "loggedIn"),
             "scopes": _semi_list(r, "scopes"),
             "responseTypes": _semi_list(r, "responseTypes")} for r in rows]


def _coerce_device(rows):
    return [{**_strip_ctx(r), "groups": _semi_list(r, "groups"),
             "scopes": _semi_list(r, "scopes"),
             "pollCount": opt_int(r, "pollCount", default=0),
             "interval": opt_int(r, "interval", default=DEVICE_POLL_INTERVAL)}
            for r in rows]


# ---------------------------------------------------------------------------
# Table accessors
# ---------------------------------------------------------------------------

def _connectors():
    return _store.table("connectors").rows()


def _clients():
    return _store.table("clients").rows()


def _passwords():
    return _store.table("passwords").rows()


def _refresh_tokens():
    return _store.table("refresh_tokens").rows()


def _auth_requests():
    return _store.table("auth_requests").rows()


def _device_requests():
    return _store.table("device_requests").rows()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _in_seconds(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def _expired(stamp):
    return bool(stamp) and stamp < _now()


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def _user_code():
    """Dex's user codes are two four-character groups, e.g. BDWD-HQMK."""
    alphabet = "BCDFGHJKLMNPQRSTVWXZ"
    pick = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{pick[:4]}-{pick[4:]}"


# ---------------------------------------------------------------------------
# Errors
#
# The OAuth2 surface speaks RFC 6749 / RFC 8628; the gRPC-derived API answers
# 200 with a boolean flag instead of a status code, which is preserved below.
# ---------------------------------------------------------------------------

def _oauth_error(status, error, description=None):
    body = {"error": error, "code": status, "oauth": True}
    if description:
        body["error_description"] = description
    return body


def _api_error(status, message):
    return {"error": message, "code": status, "message": message}


# ---------------------------------------------------------------------------
# Clients and connectors
# ---------------------------------------------------------------------------

def _client(client_id):
    return _store.table("clients").get(client_id) if client_id else None


def _connector(connector_id):
    return _store.table("connectors").get(connector_id) if connector_id else None


def _authenticate_client(client_id, client_secret):
    """Confidential clients must present their secret; public ones must not."""
    client = _client(client_id)
    if not client:
        return None, _oauth_error(401, "invalid_client",
                                  "Invalid client credentials.")
    if not client["public"] and client["secret"] != (client_secret or ""):
        return None, _oauth_error(401, "invalid_client",
                                  "Invalid client credentials.")
    return client, None


def _requested_audiences(scopes):
    return [s[len(AUDIENCE_PREFIX):] for s in scopes
            if s.startswith(AUDIENCE_PREFIX)]


def _check_cross_client(client, scopes):
    """A client may only borrow another client's audience if trusted by it."""
    for peer_id in _requested_audiences(scopes):
        peer = _client(peer_id)
        if not peer:
            return _oauth_error(400, "invalid_scope",
                                f"Unknown audience client {peer_id}.")
        if peer_id == client["id"]:
            continue
        if client["id"] not in peer["trustedPeers"]:
            return _oauth_error(
                400, "invalid_scope",
                f"Client {client['id']} is not a trusted peer of {peer_id}; "
                f"add it to that client's trustedPeers to request its "
                f"audience.")
    return None


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def healthz():
    return {"status": "ok"}


def openid_configuration():
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/auth",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/keys",
        "userinfo_endpoint": f"{ISSUER}/userinfo",
        "device_authorization_endpoint": f"{ISSUER}/device/code",
        "introspection_endpoint": f"{ISSUER}/token/introspect",
        "grant_types_supported": ["authorization_code", "refresh_token",
                                  "password", DEVICE_GRANT],
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "code_challenge_methods_supported": ["S256", "plain"],
        "scopes_supported": ["openid", "email", "groups", "profile",
                             "offline_access"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic",
                                                  "client_secret_post"],
        "claims_supported": ["iss", "sub", "aud", "iat", "exp", "email",
                             "email_verified", "locale", "name",
                             "preferred_username", "groups"],
    }


def keys():
    """Static JWKS. The mock signs nothing, so the key is a stable placeholder."""
    return {"keys": [{"use": "sig", "kty": "RSA", "kid": "dex-orbit-labs-2026",
                      "alg": "RS256",
                      "n": "ZGV4LW9yYml0LWxhYnMtbW9jay1tb2R1bHVz",
                      "e": "AQAB"}]}


def list_connectors():
    """Not a real Dex endpoint, but the chooser page renders exactly this."""
    return {"connectors": [
        {"id": c["id"], "type": c["type"], "name": c["name"],
         "enabled": c["enabled"],
         "supportsPasswordGrant": c["supportsPasswordGrant"],
         "supportsRefresh": c["supportsRefresh"], "config": c["config"]}
        for c in _connectors()]}


# ---------------------------------------------------------------------------
# Authorization endpoint
# ---------------------------------------------------------------------------

def authorize(client_id=None, redirect_uri=None, response_type="code",
              scope=None, state=None, nonce=None, connector_id=None,
              code_challenge=None, code_challenge_method=None):
    """Start an authorization request.

    Dex either shows a connector chooser or, with `connector_id` set, hands off
    to that connector. The mock returns the decision rather than rendering HTML
    so the flow stays inspectable.
    """
    client = _client(client_id)
    if not client:
        return _oauth_error(400, "invalid_client",
                            f"Invalid client_id {client_id!r}.")
    if response_type != "code":
        return _oauth_error(400, "unsupported_response_type",
                            "Only the authorization code flow is supported.")
    if redirect_uri not in client["redirectURIs"]:
        return _oauth_error(400, "invalid_request",
                            f"Unregistered redirect_uri {redirect_uri!r}.")
    scopes = [s for s in (scope or "openid profile email").split(" ") if s]
    denied = _check_cross_client(client, scopes)
    if denied:
        return denied
    if connector_id:
        connector = _connector(connector_id)
        if not connector:
            return _oauth_error(400, "invalid_request",
                                f"Unknown connector {connector_id!r}.")
        if not connector["enabled"]:
            return _oauth_error(400, "invalid_request",
                                f"Connector {connector_id!r} is disabled.")
    request_id = f"arq-{uuid.uuid4().hex[:14]}"
    _store_insert("auth_requests", {
        "id": request_id, "clientId": client_id, "redirectUri": redirect_uri,
        "scopes": scopes, "responseTypes": [response_type], "state": state or "",
        "nonce": nonce or "", "connectorId": connector_id or "",
        "loggedIn": False, "codeChallenge": code_challenge or "",
        "codeChallengeMethod": code_challenge_method or "",
        "expiresAt": _in_seconds(1800), "createdAt": _now()})
    available = [{"id": c["id"], "name": c["name"], "type": c["type"],
                  "url": f"{ISSUER}/auth/{c['id']}?req={request_id}"}
                 for c in _connectors() if c["enabled"]]
    body = {"auth_request_id": request_id, "state": state or "",
            "scopes": scopes,
            "note": "the mock returns the authorization request rather than "
                    "rendering the login page, so the flow stays inspectable"}
    if connector_id:
        body["connector_id"] = connector_id
        body["login_url"] = f"{ISSUER}/auth/{connector_id}?req={request_id}"
    else:
        # With more than one connector enabled Dex shows a chooser first.
        body["connectors"] = available
    return body


def approve(auth_request_id=None, connector_id=None, username=None,
            password=None):
    """Complete an authorization request against a connector.

    Real Dex runs the connector's own login page or callback; the mock takes the
    credentials directly so the exchange can be driven from a collection.
    """
    request = _store.table("auth_requests").get(auth_request_id) \
        if auth_request_id else None
    if not request:
        return _oauth_error(400, "invalid_request",
                            "Unknown authorization request.")
    if _expired(request["expiresAt"]):
        return _oauth_error(400, "invalid_request",
                            "The authorization request has expired.")
    connector_id = connector_id or request["connectorId"] or "local"
    connector = _connector(connector_id)
    if not connector or not connector["enabled"]:
        return _oauth_error(400, "invalid_request",
                            f"Connector {connector_id!r} is not available.")
    identity, denied = _connector_login(connector, username, password)
    if denied:
        return denied
    code = f"dex-code-{secrets.token_hex(10)}"
    _store_insert("auth_codes", {
        "code": code, "clientId": request["clientId"],
        "connectorId": connector_id, "userId": identity["userId"],
        "username": identity["username"], "email": identity["email"],
        "groups": identity["groups"], "redirectUri": request["redirectUri"],
        "scopes": request["scopes"], "codeChallenge": request["codeChallenge"],
        "codeChallengeMethod": request["codeChallengeMethod"], "used": False,
        "expiresAt": _in_seconds(300)})
    _store.table("auth_requests").patch(auth_request_id, {"loggedIn": True,
                                                          "connectorId":
                                                              connector_id})
    return {"code": code, "state": request["state"],
            "redirect_uri": f"{request['redirectUri']}?code={code}"
                            f"&state={request['state']}"}


def _connector_login(connector, username, password):
    """Authenticate against a connector, returning `(identity, error)`.

    Only `local` has credentials Dex can check itself. `ldap` is modelled as
    the same password store behind a different connector id, which is what a
    directory-backed deployment looks like from the outside. `github` has no
    password at all.
    """
    if not connector["supportsPasswordGrant"]:
        return None, _oauth_error(
            400, "invalid_request",
            f"Connector {connector['id']!r} does not support password "
            f"authentication; use the browser flow.")
    record = _store.table("passwords").find_one(
        lambda p: p["email"].lower() == str(username or "").lower()
        or p["username"] == username)
    if not record or _hash_password(record["salt"], password or "") \
            != record["hash"]:
        return None, _oauth_error(401, "access_denied",
                                  "Invalid username or password.")
    if connector["id"] == "ldap":
        # A directory identity is keyed by its DN, not by the local user id.
        return {"userId": f"uid={record['username']},ou=people,"
                          f"dc=orbit-labs,dc=com",
                "username": record["username"], "email": record["email"],
                "groups": record["groups"]}, None
    return {"userId": record["userId"], "username": record["username"],
            "email": record["email"], "groups": record["groups"]}, None


# ---------------------------------------------------------------------------
# Token endpoint
# ---------------------------------------------------------------------------

_GRANTS = ("authorization_code", "refresh_token", "password", DEVICE_GRANT)


def token(grant_type=None, client_id=None, client_secret=None, code=None,
          code_verifier=None, redirect_uri=None, refresh_token=None,
          username=None, password=None, scope=None, connector_id=None,
          device_code=None):
    if grant_type not in _GRANTS:
        return _oauth_error(400, "unsupported_grant_type",
                            f"Unsupported grant_type {grant_type!r}.")
    if grant_type == DEVICE_GRANT:
        # The device grant identifies the client without a secret.
        return _device_token(client_id, device_code)
    client, denied = _authenticate_client(client_id, client_secret)
    if denied:
        return denied
    if grant_type not in client["grantTypes"]:
        return _oauth_error(400, "unauthorized_client",
                            f"Client {client['id']!r} is not allowed to use "
                            f"the {grant_type} grant.")
    if grant_type == "authorization_code":
        return _authorization_code(client, code, code_verifier, redirect_uri)
    if grant_type == "refresh_token":
        return _refresh(client, refresh_token, scope)
    return _password_grant(client, username, password, scope, connector_id)


def _id_token(identity, client_id, connector_id, scopes, nonce=""):
    payload = {"iss": ISSUER, "sub": _sub(identity["userId"], connector_id),
               "aud": client_id, "exp": ID_TOKEN_LIFETIME,
               "name": identity["username"]}
    if "email" in scopes:
        payload["email"] = identity["email"]
        payload["email_verified"] = True
    if "groups" in scopes:
        payload["groups"] = identity["groups"]
    if nonce:
        payload["nonce"] = nonce
    encoded = ".".join(["eyJhbGciOiJSUzI1NiJ9",
                        identity["userId"].replace("=", "_")[:32],
                        f"{connector_id}-{client_id}"])
    return encoded, payload


def _sub(user_id, connector_id):
    """Dex's `sub` encodes the connector, because ids are only unique per one."""
    return f"Ch{len(user_id):02d}{user_id}Egr{connector_id}"


def _token_response(client, identity, connector_id, scopes, nonce="",
                    issue_refresh=True):
    encoded, claims = _id_token(identity, client["id"], connector_id, scopes,
                                nonce)
    body = {"access_token": f"dex-at-{secrets.token_hex(12)}",
            "token_type": "bearer", "expires_in": ID_TOKEN_LIFETIME,
            "id_token": encoded, "id_token_claims": claims,
            "scope": " ".join(scopes)}
    audiences = _requested_audiences(scopes)
    if audiences:
        claims["aud"] = [client["id"]] + audiences
    if issue_refresh and "offline_access" in scopes:
        connector = _connector(connector_id)
        if connector and connector["supportsRefresh"]:
            value = f"dex-rt-{secrets.token_hex(12)}"
            _store_insert("refresh_tokens", {
                "id": f"rt-{uuid.uuid4().hex[:14]}", "token": value,
                "clientId": client["id"], "connectorId": connector_id,
                "userId": identity["userId"], "username": identity["username"],
                "email": identity["email"], "groups": identity["groups"],
                "scopes": scopes, "obsoleteToken": "", "createdAt": _now(),
                "lastUsed": _now()})
            body["refresh_token"] = value
    return body


def _authorization_code(client, code, code_verifier, redirect_uri):
    record = _store.table("auth_codes").get(code) if code else None
    if not record or record["clientId"] != client["id"]:
        return _oauth_error(400, "invalid_grant",
                            "Invalid or expired authorization code.")
    if record["used"]:
        return _oauth_error(400, "invalid_grant",
                            "Authorization code has already been redeemed.")
    if _expired(record["expiresAt"]):
        return _oauth_error(400, "invalid_grant",
                            "Invalid or expired authorization code.")
    if redirect_uri and redirect_uri != record["redirectUri"]:
        return _oauth_error(400, "invalid_grant",
                            "redirect_uri does not match the authorization "
                            "request.")
    if record["codeChallenge"]:
        if not code_verifier:
            return _oauth_error(400, "invalid_grant",
                                "code_verifier is required for this code.")
        if _pkce_challenge(code_verifier, record["codeChallengeMethod"]) \
                != record["codeChallenge"]:
            return _oauth_error(400, "invalid_grant",
                                "Invalid code_verifier.")
    _store.table("auth_codes").patch(code, {"used": True})
    identity = {"userId": record["userId"], "username": record["username"],
                "email": record["email"], "groups": record["groups"]}
    return _token_response(client, identity, record["connectorId"],
                           record["scopes"])


def _pkce_challenge(verifier, method):
    if (method or "S256") == "plain":
        return verifier
    import base64
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _refresh(client, refresh_token, scope):
    record = _store.table("refresh_tokens").find_one(
        lambda r: r["token"] == refresh_token) if refresh_token else None
    if not record:
        obsolete = _store.table("refresh_tokens").find_one(
            lambda r: r["obsoleteToken"] == refresh_token) \
            if refresh_token else None
        if obsolete:
            # Dex keeps one generation of the previous token so a client that
            # crashed mid-rotation can recover; anything older is gone.
            return _oauth_error(400, "invalid_grant",
                                "Refresh token is no longer valid; it has "
                                "already been rotated twice.")
        return _oauth_error(400, "invalid_grant", "Invalid refresh token.")
    if record["clientId"] != client["id"]:
        return _oauth_error(400, "invalid_grant",
                            "Refresh token was issued to another client.")
    scopes = record["scopes"]
    if scope:
        requested = [s for s in scope.split(" ") if s]
        widened = [s for s in requested if s not in scopes]
        if widened:
            # A refresh may narrow scopes but never widen them.
            return _oauth_error(400, "invalid_scope",
                                f"Requested scopes exceed the original grant: "
                                f"{', '.join(widened)}.")
        scopes = requested
    rotated = f"dex-rt-{secrets.token_hex(12)}"
    _store.table("refresh_tokens").patch(record["id"], {
        "token": rotated, "obsoleteToken": record["token"],
        "lastUsed": _now()})
    identity = {"userId": record["userId"], "username": record["username"],
                "email": record["email"], "groups": record["groups"]}
    body = _token_response(client, identity, record["connectorId"], scopes,
                           issue_refresh=False)
    body["refresh_token"] = rotated
    return body


def _password_grant(client, username, password, scope, connector_id):
    connector = _connector(connector_id or "local")
    if not connector:
        return _oauth_error(400, "invalid_request",
                            f"Unknown connector {connector_id!r}.")
    if not connector["enabled"]:
        return _oauth_error(400, "invalid_request",
                            f"Connector {connector['id']!r} is disabled.")
    scopes = [s for s in (scope or "openid profile email").split(" ") if s]
    denied = _check_cross_client(client, scopes)
    if denied:
        return denied
    identity, denied = _connector_login(connector, username, password)
    if denied:
        return denied
    return _token_response(client, identity, connector["id"], scopes)


# ---------------------------------------------------------------------------
# Device authorization grant (RFC 8628)
# ---------------------------------------------------------------------------

def device_code(client_id=None, scope=None):
    client = _client(client_id)
    if not client:
        return _oauth_error(400, "invalid_client",
                            f"Invalid client_id {client_id!r}.")
    if DEVICE_GRANT not in client["grantTypes"]:
        return _oauth_error(400, "unauthorized_client",
                            f"Client {client['id']!r} is not allowed to use "
                            f"the device grant.")
    scopes = [s for s in (scope or "openid profile email").split(" ") if s]
    value = f"dex-device-{secrets.token_hex(10)}"
    user = _user_code()
    _store_insert("device_requests", {
        "deviceCode": value, "userCode": user, "clientId": client["id"],
        "scopes": scopes, "state": "pending", "connectorId": "", "userId": "",
        "username": "", "email": "", "groups": [], "pollCount": 0,
        "interval": DEVICE_POLL_INTERVAL, "expiresAt": _in_seconds(600),
        "createdAt": _now()})
    return {"device_code": value, "user_code": user,
            "verification_uri": f"{ISSUER}/device",
            "verification_uri_complete": f"{ISSUER}/device?user_code={user}",
            "expires_in": 600, "interval": DEVICE_POLL_INTERVAL}


def device_lookup(user_code=None):
    request = _store.table("device_requests").find_one(
        lambda d: d["userCode"] == user_code) if user_code else None
    if not request:
        return _oauth_error(404, "invalid_request",
                            "Unknown or expired user code.")
    return {"user_code": request["userCode"], "client_id": request["clientId"],
            "scopes": request["scopes"], "state": request["state"],
            "expires_at": request["expiresAt"]}


def device_approve(user_code=None, connector_id="local", username=None,
                   password=None, approve_request=True):
    request = _store.table("device_requests").find_one(
        lambda d: d["userCode"] == user_code) if user_code else None
    if not request:
        return _oauth_error(404, "invalid_request",
                            "Unknown or expired user code.")
    if _expired(request["expiresAt"]):
        return _oauth_error(400, "expired_token",
                            "The device code has expired.")
    if request["state"] != "pending":
        return _oauth_error(400, "invalid_request",
                            f"The device request is already {request['state']}.")
    if not approve_request:
        _store.table("device_requests").patch(request["deviceCode"],
                                              {"state": "denied"})
        return {"user_code": user_code, "state": "denied"}
    connector = _connector(connector_id)
    if not connector or not connector["enabled"]:
        return _oauth_error(400, "invalid_request",
                            f"Connector {connector_id!r} is not available.")
    identity, denied = _connector_login(connector, username, password)
    if denied:
        return denied
    _store.table("device_requests").patch(request["deviceCode"], {
        "state": "approved", "connectorId": connector_id,
        "userId": identity["userId"], "username": identity["username"],
        "email": identity["email"], "groups": identity["groups"]})
    return {"user_code": user_code, "state": "approved",
            "username": identity["username"]}


def _device_token(client_id, device_code_value):
    request = _store.table("device_requests").get(device_code_value) \
        if device_code_value else None
    if not request or request["clientId"] != client_id:
        return _oauth_error(400, "invalid_grant",
                            "Invalid device code.")
    if request["state"] == "redeemed":
        return _oauth_error(400, "invalid_grant",
                            "The device code has already been redeemed.")
    if request["state"] == "denied":
        return _oauth_error(400, "access_denied",
                            "The user denied the authorization request.")
    if _expired(request["expiresAt"]):
        return _oauth_error(400, "expired_token",
                            "The device code has expired.")
    if request["state"] == "pending":
        polls = request["pollCount"] + 1
        _store.table("device_requests").patch(request["deviceCode"],
                                              {"pollCount": polls})
        if polls > 3:
            # RFC 8628: tell a client polling too eagerly to back off.
            return _oauth_error(400, "slow_down",
                                f"Polling too frequently; wait at least "
                                f"{request['interval'] + 5} seconds.")
        return _oauth_error(400, "authorization_pending",
                            "The user has not yet approved this request.")
    client = _client(client_id)
    _store.table("device_requests").patch(request["deviceCode"],
                                          {"state": "redeemed"})
    identity = {"userId": request["userId"], "username": request["username"],
                "email": request["email"], "groups": request["groups"]}
    return _token_response(client, identity, request["connectorId"],
                           request["scopes"])


# ---------------------------------------------------------------------------
# Userinfo and introspection
# ---------------------------------------------------------------------------

def _identity_for_refresh(token_value):
    return _store.table("refresh_tokens").find_one(
        lambda r: r["token"] == token_value) if token_value else None


def userinfo(authorization=None):
    """Dex derives userinfo from the token's claims, not from a user store.

    The mock keeps a refresh token as the anchor for that, which is the closest
    thing Dex has to a durable record of a person.
    """
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    record = _identity_for_refresh(raw)
    if not record:
        return _oauth_error(401, "invalid_token",
                            "The access token is missing or invalid.")
    return {"sub": _sub(record["userId"], record["connectorId"]),
            "name": record["username"],
            "preferred_username": record["username"],
            "email": record["email"], "email_verified": True,
            "groups": record["groups"]}


def introspect(token_value=None):
    record = _identity_for_refresh(token_value)
    if not record:
        # RFC 7662: an unknown token is inactive, not an error.
        return {"active": False}
    return {"active": True, "client_id": record["clientId"],
            "sub": _sub(record["userId"], record["connectorId"]),
            "username": record["username"], "email": record["email"],
            "groups": record["groups"], "scope": " ".join(record["scopes"]),
            "iss": ISSUER, "token_type": "bearer",
            "exp": ID_TOKEN_LIFETIME}


# ---------------------------------------------------------------------------
# The gRPC-derived API
#
# Dex's API answers 200 with a boolean flag where a REST API would use 409 or
# 404; that shape is preserved here.
# ---------------------------------------------------------------------------

def api_version():
    return {"server": DEX_VERSION, "api": 2}


def client_representation(client):
    return {"id": client["id"], "name": client["name"],
            "secret": client["secret"] or None,
            "redirectURIs": client["redirectURIs"],
            "trustedPeers": client["trustedPeers"], "public": client["public"],
            "logoURL": client["logoURL"], "grantTypes": client["grantTypes"]}


def list_clients():
    return {"clients": [client_representation(c) for c in _clients()]}


def get_client(client_id):
    client = _client(client_id)
    if not client:
        return _api_error(404, f"Client {client_id!r} not found.")
    return {"client": client_representation(client)}


def create_client(payload):
    payload = payload or {}
    client = payload.get("client") or payload
    client_id = client.get("id") or f"dex-{uuid.uuid4().hex[:12]}"
    if _client(client_id):
        # Dex reports this with a flag, not a 409.
        return {"already_exists": True,
                "client": client_representation(_client(client_id))}
    public = bool(client.get("public", False))
    record = {"id": client_id, "name": client.get("name", client_id),
              "secret": "" if public else (client.get("secret")
                                           or f"dex-secret-{secrets.token_hex(8)}"),
              "public": public,
              "redirectURIs": client.get("redirectURIs") or [],
              "trustedPeers": client.get("trustedPeers") or [],
              "logoURL": client.get("logoURL", ""),
              "grantTypes": client.get("grantTypes")
                            or ["authorization_code", "refresh_token"]}
    _store_insert("clients", record)
    return {"already_exists": False, "client": client_representation(record)}


def update_client(client_id, payload):
    client = _client(client_id)
    if not client:
        return {"not_found": True}
    payload = payload or {}
    patch = {}
    for field in ("name", "logoURL"):
        if field in payload:
            patch[field] = payload[field]
    for field in ("redirectURIs", "trustedPeers", "grantTypes"):
        if field in payload:
            patch[field] = list(payload[field])
    _store.table("clients").patch(client_id, patch)
    return {"not_found": False}


def delete_client(client_id):
    if not _client(client_id):
        return {"not_found": True}
    _store.table("refresh_tokens").delete_where(
        lambda r: r["clientId"] == client_id)
    _store.table("device_requests").delete_where(
        lambda d: d["clientId"] == client_id)
    _store.table("clients").delete(client_id)
    return {"not_found": False}


def password_representation(record):
    return {"email": record["email"], "username": record["username"],
            "userId": record["userId"], "groups": record["groups"],
            "createdAt": record["createdAt"]}


def list_passwords():
    return {"passwords": [password_representation(p) for p in _passwords()]}


def create_password(payload):
    payload = payload or {}
    record = payload.get("password") or payload
    email = record.get("email")
    if not email:
        return _api_error(400, "no email supplied")
    if _store.table("passwords").get(email):
        return {"already_exists": True}
    raw = record.get("hash") or record.get("password")
    if not raw:
        return _api_error(400, "no password supplied")
    salt = uuid.uuid4().hex[:16]
    _store_insert("passwords", {
        "email": email, "userId": record.get("userId") or str(uuid.uuid4()),
        "username": record.get("username", email.split("@")[0]),
        "salt": salt, "hash": _hash_password(salt, raw),
        "groups": record.get("groups") or [], "createdAt": _now()})
    return {"already_exists": False}


def update_password(email, payload):
    record = _store.table("passwords").get(email)
    if not record:
        return {"not_found": True}
    payload = payload or {}
    patch = {}
    if "username" in payload:
        patch["username"] = payload["username"]
    if "groups" in payload:
        patch["groups"] = list(payload["groups"])
    new_hash = payload.get("hash") or payload.get("newPassword")
    if new_hash:
        salt = uuid.uuid4().hex[:16]
        patch["salt"] = salt
        patch["hash"] = _hash_password(salt, new_hash)
        # Changing the password drops every offline session it anchored.
        _store.table("refresh_tokens").delete_where(
            lambda r: r["userId"] == record["userId"])
    _store.table("passwords").patch(email, patch)
    return {"not_found": False}


def delete_password(email):
    record = _store.table("passwords").get(email)
    if not record:
        return {"not_found": True}
    _store.table("refresh_tokens").delete_where(
        lambda r: r["userId"] == record["userId"])
    _store.table("passwords").delete(email)
    return {"not_found": False}


def verify_password(email=None, password=None):
    record = _store.table("passwords").get(email) if email else None
    if not record:
        return {"verified": False, "not_found": True}
    verified = _hash_password(record["salt"], password or "") == record["hash"]
    return {"verified": verified, "not_found": False}


def list_refresh(user_id):
    """The nearest thing Dex has to a user list: who still has a live session."""
    rows = [r for r in _refresh_tokens() if r["userId"] == user_id]
    return {"refresh_tokens": [
        {"id": r["id"], "clientId": r["clientId"],
         "connectorId": r["connectorId"], "scopes": r["scopes"],
         "createdAt": r["createdAt"], "lastUsed": r["lastUsed"]}
        for r in rows]}


def revoke_refresh(user_id, client_id=None):
    removed = _store.table("refresh_tokens").delete_where(
        lambda r: r["userId"] == user_id
        and (client_id is None or r["clientId"] == client_id))
    return {"not_found": removed == 0}


def list_offline_sessions():
    """Every identity Dex currently remembers, grouped by connector."""
    grouped = {}
    for record in _refresh_tokens():
        key = f"{record['connectorId']}:{record['userId']}"
        entry = grouped.setdefault(key, {
            "connectorId": record["connectorId"], "userId": record["userId"],
            "username": record["username"], "email": record["email"],
            "groups": record["groups"], "clients": []})
        entry["clients"].append(record["clientId"])
    return {"offline_sessions": sorted(grouped.values(),
                                       key=lambda e: (e["connectorId"],
                                                      e["username"]))}


_store.eager_load()
