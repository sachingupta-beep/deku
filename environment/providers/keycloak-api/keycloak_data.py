"""Data access module for the Keycloak mock service.

Keycloak's organising idea is the **realm**: every user, client, role, group and
session belongs to exactly one, and nothing crosses the boundary. The two URL
families reflect that --- `/realms/{realm}/protocol/openid-connect/...` for the
OIDC endpoints a client talks to, and `/admin/realms/{realm}/...` for the Admin
REST API.

Three things here are Keycloak-specific and are modelled properly rather than
flattened:

* **Direct grant.** `grant_type=password` against the token endpoint is the
  first-class way to authenticate, and it fails in four *different* ways ---
  wrong password, disabled account, pending required actions, and a
  brute-force-locked account --- each with the `error_description` Keycloak
  actually returns.
* **Composite roles.** A role may include other realm roles *and* client roles.
  The effective set is the transitive closure, so `platform-operator` drags in
  `incident-responder`, `status-viewer` and the client role
  `realm-management:view-users`.
* **Groups carry role mappings**, and a subgroup inherits its parent's. Being in
  `/platform/on-call` means holding everything `/platform` grants as well.

Passwords are verified as `sha256(credentialSalt + password)`; Keycloak itself
uses PBKDF2, and the credential representation says so. Mutations are held in
process memory and reset on restart.
"""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("keycloak-api")
_API = "keycloak-api"

MASTER_REALM = "master"
ADMIN_CLIENT = "admin-cli"
ADMIN_USERNAME = "kc-admin"
ADMIN_PASSWORD = "OrbitKeycloakAdmin2026!"
ADMIN_TOKEN = "kc-at-master-admin-cli-8f0c31d47a92"


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
    """Parse a `k=v;k=v` cell into a dict of single-valued lists.

    Keycloak's `attributes` are multi-valued maps; the seed keeps them flat so a
    CSV overlay can shadow the JSON.
    """
    out = {}
    for part in _semi_list(row, column):
        key, _, value = part.partition("=")
        if key:
            out.setdefault(key, []).append(value)
    return out


def _flag(row, column, default="0"):
    return opt_str(row, column, default=default) == "1"


_store.register("realms", primary_key="realm",
                initial_loader=lambda: _coerce_realms(_load("realms.json",
                                                            "realms")))
_store.register("clients", primary_key="id",
                initial_loader=lambda: _coerce_clients(_load("clients.json",
                                                             "clients")))
_store.register("realm_roles", primary_key="id",
                initial_loader=lambda: _coerce_realm_roles(
                    _load("realm_roles.json", "realm_roles")))
_store.register("client_roles", primary_key="id",
                initial_loader=lambda: _coerce_client_roles(
                    _load("client_roles.json", "client_roles")))
_store.register("groups", primary_key="id",
                initial_loader=lambda: _coerce_groups(_load("groups.json",
                                                            "groups")))
_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json",
                                                           "users")))
_store.register("group_memberships", primary_key="id",
                initial_loader=lambda: _coerce_ints(
                    _load("group_memberships.json", "group_memberships"),
                    ("id",)))
_store.register("role_mappings", primary_key="id",
                initial_loader=lambda: _coerce_ints(
                    _load("role_mappings.json", "role_mappings"), ("id",)))
_store.register("sessions", primary_key="id",
                initial_loader=lambda: _coerce_sessions(
                    _load("sessions.json", "sessions")))
_store.register("identity_providers", primary_key="alias",
                initial_loader=lambda: _coerce_identity_providers(
                    _load("identity_providers.json", "identity_providers")))
# A required action's alias is unique only within its realm, so the store needs
# a composite key.
_store.register("required_actions", primary_key="_pk",
                initial_loader=lambda: _coerce_required_actions(
                    _load("required_actions.json", "required_actions")))
_store.register("brute_force_status", primary_key="userId",
                initial_loader=lambda: _coerce_brute_force(
                    _load("brute_force_status.json", "brute_force_status")))
_store.register("events", primary_key="id",
                initial_loader=lambda: _coerce_ints(
                    _load("events.json", "events"), ("time",)))
_store.register("admin_events", primary_key="id",
                initial_loader=lambda: _coerce_ints(
                    _load("admin_events.json", "admin_events"), ("time",)))


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def _coerce_ints(rows, ints):
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in ints}}
            for r in rows]


_REALM_FLAGS = ("enabled", "registrationAllowed", "resetPasswordAllowed",
                "verifyEmail", "loginWithEmailAllowed", "duplicateEmailsAllowed",
                "bruteForceProtected", "permanentLockout")
_REALM_INTS = ("maxFailureWaitSeconds", "failureFactor", "accessTokenLifespan",
               "ssoSessionIdleTimeout", "ssoSessionMaxLifespan")


def _coerce_realms(rows):
    return [{**_strip_ctx(r),
             **{f: _flag(r, f) for f in _REALM_FLAGS},
             **{f: opt_int(r, f, default=0) for f in _REALM_INTS},
             "requiredCredentials": _semi_list(r, "requiredCredentials")}
            for r in rows]


_CLIENT_FLAGS = ("enabled", "publicClient", "standardFlowEnabled",
                 "directAccessGrantsEnabled", "serviceAccountsEnabled",
                 "bearerOnly")


def _coerce_clients(rows):
    return [{**_strip_ctx(r),
             **{f: _flag(r, f) for f in _CLIENT_FLAGS},
             "redirectUris": _semi_list(r, "redirectUris"),
             "webOrigins": _semi_list(r, "webOrigins"),
             "defaultClientScopes": _semi_list(r, "defaultClientScopes")}
            for r in rows]


def _coerce_realm_roles(rows):
    return [{**_strip_ctx(r), "composite": _flag(r, "composite"),
             "compositeRealmRoles": _semi_list(r, "compositeRealmRoles"),
             "compositeClientRoles": _semi_list(r, "compositeClientRoles")}
            for r in rows]


def _coerce_client_roles(rows):
    return [{**_strip_ctx(r), "composite": _flag(r, "composite"),
             "compositeClientRoles": _semi_list(r, "compositeClientRoles")}
            for r in rows]


def _coerce_groups(rows):
    return [{**_strip_ctx(r),
             "realmRoles": _semi_list(r, "realmRoles"),
             "clientRoles": _semi_list(r, "clientRoles"),
             "attributes": _semi_map(r, "attributes")} for r in rows]


def _coerce_users(rows):
    return [{**_strip_ctx(r),
             "enabled": _flag(r, "enabled"),
             "emailVerified": _flag(r, "emailVerified"),
             "totpConfigured": _flag(r, "totpConfigured"),
             "requiredActions": _semi_list(r, "requiredActions"),
             "attributes": _semi_map(r, "attributes"),
             "createdTimestamp": opt_int(r, "createdTimestamp", default=0)}
            for r in rows]


def _coerce_sessions(rows):
    return [{**_strip_ctx(r), "offline": _flag(r, "offline"),
             "started": opt_int(r, "started", default=0),
             "lastAccess": opt_int(r, "lastAccess", default=0),
             "expires": opt_int(r, "expires", default=0)} for r in rows]


def _coerce_identity_providers(rows):
    return [{**_strip_ctx(r), "enabled": _flag(r, "enabled"),
             "trustEmail": _flag(r, "trustEmail"),
             "storeToken": _flag(r, "storeToken"),
             "linkOnly": _flag(r, "linkOnly"),
             "config": _flat_map(r, "config")} for r in rows]


def _flat_map(row, column):
    """Like `_semi_map`, but single-valued -- config entries may contain `=`."""
    out = {}
    for part in _semi_list(row, column):
        key, _, value = part.partition("=")
        if key:
            out[key] = value
    return out


def _coerce_required_actions(rows):
    return [{**_strip_ctx(r), "_pk": f"{r['realm']}@{r['alias']}",
             "enabled": _flag(r, "enabled"),
             "defaultAction": _flag(r, "defaultAction"),
             "priority": opt_int(r, "priority", default=0)} for r in rows]


def _coerce_brute_force(rows):
    return [{**_strip_ctx(r), "disabled": _flag(r, "disabled"),
             "numFailures": opt_int(r, "numFailures", default=0),
             "lastFailure": opt_int(r, "lastFailure", default=0)} for r in rows]


# ---------------------------------------------------------------------------
# Table accessors
# ---------------------------------------------------------------------------

def _realms():
    return _store.table("realms").rows()


def _clients():
    return _store.table("clients").rows()


def _realm_roles():
    return _store.table("realm_roles").rows()


def _client_roles():
    return _store.table("client_roles").rows()


def _groups():
    return _store.table("groups").rows()


def _users():
    return _store.table("users").rows()


def _memberships():
    return _store.table("group_memberships").rows()


def _mappings():
    return _store.table("role_mappings").rows()


def _sessions():
    return _store.table("sessions").rows()


def _now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Errors
#
# The OIDC endpoints speak RFC 6749; the Admin REST API answers with
# `{"error": ..., "errorMessage": ...}` and a real HTTP status.
# ---------------------------------------------------------------------------

def _oauth_error(status, error, description=None):
    body = {"error": error, "code": status, "oauth": True}
    if description:
        body["error_description"] = description
    return body


def _admin_error(status, message, error=None):
    return {"error": error or message, "code": status, "errorMessage": message}


def _not_found(what="Resource not found"):
    return _admin_error(404, what)


# ---------------------------------------------------------------------------
# Realm and client resolution
# ---------------------------------------------------------------------------

def resolve_realm(realm_name):
    realm = _store.table("realms").get(realm_name)
    if not realm:
        # Keycloak answers 404 with this exact shape for an unknown realm.
        return None, _admin_error(404, f"Realm does not exist",
                                  error="Realm does not exist")
    return realm, None


def _find_client(realm_name, client_id):
    return _store.table("clients").find_one(
        lambda c: c["realm"] == realm_name and c["clientId"] == client_id)


def _client_by_uuid(realm_name, uuid_value):
    client = _store.table("clients").get(uuid_value)
    if client and client["realm"] == realm_name:
        return client
    return None


# ---------------------------------------------------------------------------
# Admin authentication
#
# The Admin REST API takes the bearer minted by the master realm's admin-cli
# client. Any live session's access token works for the realm it belongs to;
# the master token works everywhere.
# ---------------------------------------------------------------------------

def resolve_bearer(authorization=None):
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw:
        return None
    if raw == ADMIN_TOKEN:
        return {"realm": MASTER_REALM, "userId": "", "username": ADMIN_USERNAME,
                "clientId": ADMIN_CLIENT, "master": True}
    session = _store.table("sessions").find_one(
        lambda s: s["accessToken"] == raw)
    if not session or session["expires"] < _now_ms():
        return None
    return {"realm": session["realm"], "userId": session["userId"],
            "username": session["username"], "clientId": session["clientId"],
            "master": False, "sessionId": session["id"]}


def authorize_admin(authorization=None, realm_name=None, required_role=None):
    """Gate an Admin REST API call.

    Keycloak separates *who you are* from *what you may administer*: the bearer
    must be live (401), must belong to the realm it is administering (403), and
    must hold the right `realm-management` client role (403).
    """
    identity = resolve_bearer(authorization)
    if not identity:
        return None, _admin_error(401, "HTTP 401 Unauthorized",
                                  error="HTTP 401 Unauthorized")
    if identity["master"]:
        return identity, None
    if realm_name and identity["realm"] != realm_name:
        return None, _admin_error(
            403, f"Token issued for realm {identity['realm']} cannot "
                 f"administer realm {realm_name}", error="Forbidden")
    if required_role:
        held = effective_client_roles(identity["realm"], identity["userId"],
                                      "realm-management")
        if required_role not in held:
            return None, _admin_error(
                403, f"Missing realm-management role '{required_role}'",
                error="Forbidden")
    return identity, None


# ---------------------------------------------------------------------------
# Roles: direct, composite and effective
# ---------------------------------------------------------------------------

def _realm_role(realm_name, name):
    return _store.table("realm_roles").find_one(
        lambda r: r["realm"] == realm_name and r["name"] == name)


def _client_role(realm_name, client_id, name):
    return _store.table("client_roles").find_one(
        lambda r: r["realm"] == realm_name and r["clientId"] == client_id
        and r["name"] == name)


def _expand_realm_role(realm_name, name, seen_realm, seen_client):
    """Walk a composite realm role's closure, collecting realm and client roles."""
    if name in seen_realm:
        return
    role = _realm_role(realm_name, name)
    if not role:
        return
    seen_realm.add(name)
    for child in role["compositeRealmRoles"]:
        _expand_realm_role(realm_name, child, seen_realm, seen_client)
    for entry in role["compositeClientRoles"]:
        client_id, _, role_name = entry.partition(":")
        _expand_client_role(realm_name, client_id, role_name, seen_client)


def _expand_client_role(realm_name, client_id, name, seen_client):
    key = f"{client_id}:{name}"
    if key in seen_client:
        return
    role = _client_role(realm_name, client_id, name)
    if not role:
        return
    seen_client.add(key)
    for entry in role["compositeClientRoles"]:
        child_client, _, child_name = entry.partition(":")
        _expand_client_role(realm_name, child_client, child_name, seen_client)


def direct_role_mappings(realm_name, user_id):
    """Only the mappings written against the user -- no groups, no composites."""
    realm_names, client_pairs = [], []
    for mapping in _mappings():
        if mapping["realm"] != realm_name or mapping["userId"] != user_id:
            continue
        if mapping["roleType"] == "realm":
            realm_names.append(mapping["roleName"])
        else:
            client_pairs.append((mapping["clientId"], mapping["roleName"]))
    return realm_names, client_pairs


def _group_chain(realm_name, group_id):
    """A group plus every ancestor, because a subgroup inherits their mappings."""
    chain = []
    current = _store.table("groups").get(group_id)
    while current and current["realm"] == realm_name:
        chain.append(current)
        current = _store.table("groups").get(current["parentId"]) \
            if current["parentId"] else None
    return chain


def effective_roles(realm_name, user_id):
    """The transitive closure: direct + group-inherited + composite expansion."""
    seen_realm, seen_client = set(), set()
    realm_names, client_pairs = direct_role_mappings(realm_name, user_id)
    for membership in _memberships():
        if membership["realm"] != realm_name or membership["userId"] != user_id:
            continue
        for group in _group_chain(realm_name, membership["groupId"]):
            realm_names.extend(group["realmRoles"])
            for entry in group["clientRoles"]:
                client_id, _, role_name = entry.partition(":")
                client_pairs.append((client_id, role_name))
    for name in realm_names:
        _expand_realm_role(realm_name, name, seen_realm, seen_client)
    for client_id, role_name in client_pairs:
        _expand_client_role(realm_name, client_id, role_name, seen_client)
    return sorted(seen_realm), sorted(seen_client)


def effective_client_roles(realm_name, user_id, client_id):
    _, client_pairs = effective_roles(realm_name, user_id)
    prefix = f"{client_id}:"
    return sorted(p[len(prefix):] for p in client_pairs if p.startswith(prefix))


# ---------------------------------------------------------------------------
# Representations
# ---------------------------------------------------------------------------

_HIDDEN_USER_FIELDS = ("credentialSalt", "credentialHash", "realm")


def user_representation(user, brief=False):
    if not user:
        return None
    body = {k: v for k, v in user.items() if k not in _HIDDEN_USER_FIELDS}
    body["totp"] = user["totpConfigured"]
    body.pop("totpConfigured", None)
    if brief:
        for field in ("attributes", "federationLink", "serviceAccountClientId"):
            body.pop(field, None)
    return body


def realm_representation(realm):
    return {k: v for k, v in realm.items()}


def client_representation(client):
    # Keycloak masks the secret in list views; the dedicated endpoint returns it.
    return {k: v for k, v in client.items() if k not in ("secret", "realm")}


def realm_role_representation(role):
    return {"id": role["id"], "name": role["name"],
            "description": role["description"], "composite": role["composite"],
            "clientRole": False, "containerId": role["realm"]}


def client_role_representation(role):
    return {"id": role["id"], "name": role["name"],
            "description": role["description"], "composite": role["composite"],
            "clientRole": True, "containerId": role["clientUuid"]}


def group_representation(group, with_subgroups=True):
    body = {"id": group["id"], "name": group["name"], "path": group["path"],
            "realmRoles": group["realmRoles"],
            "clientRoles": _group_client_roles(group),
            "attributes": group["attributes"]}
    if with_subgroups:
        body["subGroups"] = [group_representation(g)
                             for g in _groups()
                             if g["parentId"] == group["id"]]
    return body


def _group_client_roles(group):
    out = {}
    for entry in group["clientRoles"]:
        client_id, _, role_name = entry.partition(":")
        out.setdefault(client_id, []).append(role_name)
    return out


# ---------------------------------------------------------------------------
# OIDC: discovery and realm info
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def server_info():
    return {"systemInfo": {"version": "26.0.5", "serverMode": "standalone"},
            "memoryInfo": {"total": 2147483648, "used": 734003200},
            "themes": {"login": ["keycloak"], "account": ["keycloak.v3"]},
            "realms": [r["realm"] for r in _realms()]}


def realm_public_info(realm):
    return {"realm": realm["realm"],
            "public_key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQ-orbit-labs-mock",
            "token-service": f"/realms/{realm['realm']}/protocol/openid-connect",
            "account-service": f"/realms/{realm['realm']}/account",
            "tokens-not-before": 0}


def openid_configuration(realm, base_url):
    issuer = f"{base_url}/realms/{realm['realm']}"
    protocol = f"{issuer}/protocol/openid-connect"
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{protocol}/auth",
        "token_endpoint": f"{protocol}/token",
        "introspection_endpoint": f"{protocol}/token/introspect",
        "userinfo_endpoint": f"{protocol}/userinfo",
        "end_session_endpoint": f"{protocol}/logout",
        "jwks_uri": f"{protocol}/certs",
        "grant_types_supported": ["authorization_code", "refresh_token",
                                  "password", "client_credentials"],
        "response_types_supported": ["code", "none"],
        "subject_types_supported": ["public", "pairwise"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "email", "roles",
                             "offline_access"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic",
                                                  "client_secret_post", "none"],
        "code_challenge_methods_supported": ["S256", "plain"],
    }


def certs():
    """Static JWKS. The mock signs nothing, so the key is a stable placeholder."""
    return {"keys": [{"kid": "kc-orbit-labs-2026", "kty": "RSA", "alg": "RS256",
                      "use": "sig",
                      "n": "a2V5Y2xvYWstb3JiaXQtbGFicy1tb2NrLW1vZHVsdXM",
                      "e": "AQAB"}]}


# ---------------------------------------------------------------------------
# OIDC: token endpoint
# ---------------------------------------------------------------------------

_GRANTS = ("password", "refresh_token", "client_credentials")


def token(realm, grant_type=None, client_id=None, client_secret=None,
          username=None, password=None, refresh_token=None, scope=None,
          ip="203.0.113.41"):
    if grant_type not in _GRANTS:
        return _oauth_error(400, "unsupported_grant_type",
                            f"Unsupported grant_type: {grant_type}")
    client = _find_client(realm["realm"], client_id) if client_id else None
    if not client or not client["enabled"]:
        return _oauth_error(401, "invalid_client", "Invalid client or "
                                                   "Invalid client credentials")
    if not client["publicClient"] and client["secret"]:
        if client_secret != client["secret"]:
            return _oauth_error(401, "invalid_client",
                                "Invalid client or Invalid client credentials")
    if grant_type == "client_credentials":
        return _client_credentials(realm, client)
    if grant_type == "refresh_token":
        return _refresh(realm, client, refresh_token)
    return _direct_grant(realm, client, username, password, ip)


def _direct_grant(realm, client, username, password, ip):
    if not client["directAccessGrantsEnabled"]:
        return _oauth_error(400, "unauthorized_client",
                            "Client not allowed for direct access grants")
    user = _store.table("users").find_one(
        lambda u: u["realm"] == realm["realm"]
        and (u["username"] == username
             or (realm["loginWithEmailAllowed"] and u["email"] == username)))
    if not user or not user["credentialHash"]:
        # No such user, or a federated account with no local credential.
        _record_event(realm["realm"], "LOGIN_ERROR", client_id=client["clientId"],
                      ip=ip, error="invalid_user_credentials",
                      details={"username": username or ""})
        return _oauth_error(401, "invalid_grant", "Invalid user credentials")
    lock = _store.table("brute_force_status").get(user["id"])
    if realm["bruteForceProtected"] and lock and lock["disabled"]:
        # Keycloak deliberately returns the same message as a bad password, so
        # the response cannot confirm that an account exists and is locked.
        _record_event(realm["realm"], "LOGIN_ERROR", user_id=user["id"],
                      client_id=client["clientId"], ip=ip,
                      error="user_temporarily_disabled",
                      details={"username": username or ""})
        return _oauth_error(401, "invalid_grant", "Invalid user credentials")
    if _hash_password(user["credentialSalt"], password or "") \
            != user["credentialHash"]:
        _register_failure(realm, user, ip)
        _record_event(realm["realm"], "LOGIN_ERROR", user_id=user["id"],
                      client_id=client["clientId"], ip=ip,
                      error="invalid_user_credentials",
                      details={"username": username or ""})
        return _oauth_error(401, "invalid_grant", "Invalid user credentials")
    if not user["enabled"]:
        return _oauth_error(400, "invalid_grant", "Account disabled")
    if user["requiredActions"]:
        # The password was right; the account still cannot complete a login.
        return _oauth_error(400, "invalid_grant", "Account is not fully set up")
    session = _open_session(realm, client, user, ip)
    _record_event(realm["realm"], "LOGIN", user_id=user["id"],
                  session_id=session["id"], client_id=client["clientId"], ip=ip,
                  details={"username": user["username"],
                           "auth_method": "openid-connect",
                           "grant_type": "password"})
    return _token_response(realm, client, user, session)


def _register_failure(realm, user, ip):
    if not realm["bruteForceProtected"]:
        return
    lock = _store.table("brute_force_status").get(user["id"])
    failures = (lock["numFailures"] if lock else 0) + 1
    _store.table("brute_force_status").upsert({
        "userId": user["id"], "realm": realm["realm"], "numFailures": failures,
        "disabled": failures >= realm["failureFactor"], "lastIPFailure": ip,
        "lastFailure": _now_ms()})


def _client_credentials(realm, client):
    if not client["serviceAccountsEnabled"]:
        return _oauth_error(400, "unauthorized_client",
                            "Client not enabled to retrieve service account")
    user = _store.table("users").find_one(
        lambda u: u["realm"] == realm["realm"]
        and u["serviceAccountClientId"] == client["clientId"])
    if not user:
        return _oauth_error(400, "invalid_request",
                            "Service account user not found")
    session = _open_session(realm, client, user, "198.51.100.77")
    _record_event(realm["realm"], "CLIENT_LOGIN", user_id=user["id"],
                  session_id=session["id"], client_id=client["clientId"],
                  ip="198.51.100.77",
                  details={"grant_type": "client_credentials"})
    body = _token_response(realm, client, user, session)
    # A service-account token has no refresh token in Keycloak's default setup.
    body.pop("refresh_token", None)
    body.pop("refresh_expires_in", None)
    return body


def _refresh(realm, client, refresh_token):
    session = _store.table("sessions").find_one(
        lambda s: s["refreshToken"] == refresh_token and s["realm"]
        == realm["realm"]) if refresh_token else None
    if not session:
        return _oauth_error(400, "invalid_grant",
                            "Invalid refresh token")
    if session["expires"] < _now_ms():
        return _oauth_error(400, "invalid_grant",
                            "Session not active")
    if session["clientId"] != client["clientId"]:
        return _oauth_error(400, "invalid_grant",
                            "Refresh token issued for another client")
    user = _store.table("users").get(session["userId"])
    if not user or not user["enabled"]:
        return _oauth_error(400, "invalid_grant", "Account disabled")
    updated = _store.table("sessions").patch(session["id"], {
        "accessToken": f"kc-at-{secrets.token_hex(10)}",
        "refreshToken": f"kc-rt-{secrets.token_hex(10)}",
        "lastAccess": _now_ms()})
    return _token_response(realm, client, user, updated)


def _open_session(realm, client, user, ip):
    now = _now_ms()
    session = {
        "id": str(uuid.uuid4()), "realm": realm["realm"], "userId": user["id"],
        "username": user["username"], "clientId": client["clientId"],
        "accessToken": f"kc-at-{secrets.token_hex(10)}",
        "refreshToken": f"kc-rt-{secrets.token_hex(10)}",
        "offline": False, "ipAddress": ip, "started": now, "lastAccess": now,
        "expires": now + realm["ssoSessionMaxLifespan"] * 1000,
    }
    _store_insert("sessions", session)
    return session


def _token_response(realm, client, user, session):
    realm_names, client_pairs = effective_roles(realm["realm"], user["id"])
    resource_access = {}
    for pair in client_pairs:
        client_id, _, role_name = pair.partition(":")
        resource_access.setdefault(client_id, {"roles": []})["roles"].append(
            role_name)
    return {
        "access_token": session["accessToken"],
        "expires_in": realm["accessTokenLifespan"],
        "refresh_expires_in": realm["ssoSessionIdleTimeout"],
        "refresh_token": session["refreshToken"],
        "token_type": "Bearer",
        "id_token": f"eyJhbGciOiJSUzI1NiJ9.{user['id']}.{client['clientId']}"
                    f".{realm['realm']}-mock-signature",
        "not-before-policy": 0,
        "session_state": session["id"],
        "scope": "openid profile email",
        "realm_access": {"roles": realm_names},
        "resource_access": resource_access,
    }


def introspect(realm, token_value=None):
    session = _store.table("sessions").find_one(
        lambda s: s["realm"] == realm["realm"]
        and s["accessToken"] == token_value) if token_value else None
    if not session or session["expires"] < _now_ms():
        # RFC 7662: an unknown or dead token is inactive, not an error.
        return {"active": False}
    user = _store.table("users").get(session["userId"])
    realm_names, client_pairs = effective_roles(realm["realm"], user["id"])
    resource_access = {}
    for pair in client_pairs:
        client_id, _, role_name = pair.partition(":")
        resource_access.setdefault(client_id, {"roles": []})["roles"].append(
            role_name)
    return {"active": True, "sub": user["id"], "username": user["username"],
            "email": user["email"], "client_id": session["clientId"],
            "session_state": session["id"], "typ": "Bearer",
            "realm_access": {"roles": realm_names},
            "resource_access": resource_access,
            "exp": session["expires"] // 1000,
            "iat": session["started"] // 1000,
            "iss": f"/realms/{realm['realm']}"}


def userinfo(realm, authorization=None):
    identity = resolve_bearer(authorization)
    if not identity or identity["master"] or identity["realm"] != realm["realm"]:
        return _oauth_error(401, "invalid_token",
                            "Token verification failed")
    user = _store.table("users").get(identity["userId"])
    if not user:
        return _oauth_error(401, "invalid_token", "User not found")
    realm_names, _ = effective_roles(realm["realm"], user["id"])
    return {"sub": user["id"], "preferred_username": user["username"],
            "email": user["email"], "email_verified": user["emailVerified"],
            "given_name": user["firstName"], "family_name": user["lastName"],
            "name": f"{user['firstName']} {user['lastName']}".strip(),
            "realm_access": {"roles": realm_names}}


def logout(realm, refresh_token=None):
    session = _store.table("sessions").find_one(
        lambda s: s["refreshToken"] == refresh_token
        and s["realm"] == realm["realm"]) if refresh_token else None
    if not session:
        return _oauth_error(400, "invalid_grant", "Invalid refresh token")
    _store.table("sessions").delete(session["id"])
    _record_event(realm["realm"], "LOGOUT", user_id=session["userId"],
                  session_id=session["id"], client_id=session["clientId"],
                  ip=session["ipAddress"])
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _record_event(realm_name, event_type, user_id="", session_id="",
                  client_id="", ip="203.0.113.41", error="", details=None):
    entry = {"id": f"ev{uuid.uuid4().hex[:13]}", "realm": realm_name,
             "type": event_type, "time": _now_ms(), "userId": user_id,
             "sessionId": session_id, "clientId": client_id, "ipAddress": ip,
             "error": error,
             "details": ";".join(f"{k}={v}" for k, v in (details or {}).items())}
    _store_insert("events", entry)
    return entry


def list_events(realm_name, event_type=None, user_id=None, client_id=None,
                first=0, max_results=20):
    rows = [e for e in _store.table("events").rows()
            if e["realm"] == realm_name]
    if event_type:
        rows = [e for e in rows if e["type"] == event_type]
    if user_id:
        rows = [e for e in rows if e["userId"] == user_id]
    if client_id:
        rows = [e for e in rows if e["clientId"] == client_id]
    rows.sort(key=lambda e: e["time"], reverse=True)
    return _slice(rows, first, max_results)


def list_admin_events(realm_name, operation_type=None, resource_type=None,
                      first=0, max_results=20):
    rows = [e for e in _store.table("admin_events").rows()
            if e["realm"] == realm_name]
    if operation_type:
        rows = [e for e in rows if e["operationType"] == operation_type]
    if resource_type:
        rows = [e for e in rows if e["resourceType"] == resource_type]
    rows.sort(key=lambda e: e["time"], reverse=True)
    return _slice(rows, first, max_results)


def _slice(rows, first, max_results):
    first = max(0, int(first or 0))
    max_results = max(1, min(int(max_results or 20), 500))
    return rows[first:first + max_results]


# ---------------------------------------------------------------------------
# Admin API: realms and clients
# ---------------------------------------------------------------------------

def list_realms():
    return [realm_representation(r) for r in _realms()]


def get_realm(realm):
    return realm_representation(realm)


def update_realm(realm, payload):
    patch = {}
    for field in ("displayName", "enabled", "registrationAllowed",
                  "resetPasswordAllowed", "verifyEmail", "bruteForceProtected",
                  "failureFactor", "accessTokenLifespan", "passwordPolicy"):
        if field in (payload or {}):
            patch[field] = payload[field]
    updated = _store.table("realms").patch(realm["realm"], patch)
    return realm_representation(updated)


def list_clients(realm_name, client_id=None):
    rows = [c for c in _clients() if c["realm"] == realm_name]
    if client_id:
        rows = [c for c in rows if c["clientId"] == client_id]
    return [client_representation(c) for c in rows]


def get_client(realm_name, uuid_value):
    client = _client_by_uuid(realm_name, uuid_value)
    if not client:
        return _not_found("Could not find client")
    body = client_representation(client)
    body["secret"] = client["secret"] or None
    return body


def get_client_secret(realm_name, uuid_value):
    client = _client_by_uuid(realm_name, uuid_value)
    if not client:
        return _not_found("Could not find client")
    if client["publicClient"] or not client["secret"]:
        return _admin_error(400, "Client is not a confidential client")
    return {"type": "secret", "value": client["secret"]}


def list_client_roles(realm_name, uuid_value):
    client = _client_by_uuid(realm_name, uuid_value)
    if not client:
        return _not_found("Could not find client")
    return [client_role_representation(r) for r in _client_roles()
            if r["clientUuid"] == uuid_value]


def client_user_sessions(realm_name, uuid_value):
    client = _client_by_uuid(realm_name, uuid_value)
    if not client:
        return _not_found("Could not find client")
    return [_session_representation(s) for s in _sessions()
            if s["realm"] == realm_name and s["clientId"] == client["clientId"]
            and not s["offline"]]


def _session_representation(session):
    return {"id": session["id"], "username": session["username"],
            "userId": session["userId"], "ipAddress": session["ipAddress"],
            "start": session["started"], "lastAccess": session["lastAccess"],
            "clients": {session["clientId"]: session["clientId"]}}


# ---------------------------------------------------------------------------
# Admin API: roles
# ---------------------------------------------------------------------------

def list_realm_roles(realm_name):
    return [realm_role_representation(r) for r in _realm_roles()
            if r["realm"] == realm_name]


def get_realm_role(realm_name, role_name):
    role = _realm_role(realm_name, role_name)
    if not role:
        return _not_found(f"Could not find role: {role_name}")
    return realm_role_representation(role)


def get_realm_role_composites(realm_name, role_name):
    role = _realm_role(realm_name, role_name)
    if not role:
        return _not_found(f"Could not find role: {role_name}")
    out = [realm_role_representation(_realm_role(realm_name, n))
           for n in role["compositeRealmRoles"] if _realm_role(realm_name, n)]
    for entry in role["compositeClientRoles"]:
        client_id, _, name = entry.partition(":")
        child = _client_role(realm_name, client_id, name)
        if child:
            out.append(client_role_representation(child))
    return out


def create_realm_role(realm_name, payload):
    payload = payload or {}
    name = payload.get("name")
    if not name:
        return _admin_error(400, "Role name is missing")
    if _realm_role(realm_name, name):
        return _admin_error(409, f"Role with name {name} already exists",
                            error="Conflict detected")
    role = {"id": f"r-{uuid.uuid4().hex[:16]}", "realm": realm_name,
            "name": name, "description": payload.get("description", ""),
            "composite": bool(payload.get("composite", False)),
            "compositeRealmRoles": payload.get("compositeRealmRoles") or [],
            "compositeClientRoles": payload.get("compositeClientRoles") or []}
    _store_insert("realm_roles", role)
    return {"__status__": 201, "id": role["id"], "name": role["name"]}


def delete_realm_role(realm_name, role_name):
    role = _realm_role(realm_name, role_name)
    if not role:
        return _not_found(f"Could not find role: {role_name}")
    _store.table("role_mappings").delete_where(
        lambda m: m["realm"] == realm_name and m["roleType"] == "realm"
        and m["roleName"] == role_name)
    _store.table("realm_roles").delete(role["id"])
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Admin API: users
# ---------------------------------------------------------------------------

def list_users(realm_name, search=None, username=None, email=None,
               enabled=None, first=0, max_results=20, brief=False):
    rows = [u for u in _users() if u["realm"] == realm_name]
    if search:
        needle = str(search).lower()
        rows = [u for u in rows
                if needle in u["username"].lower()
                or needle in (u["email"] or "").lower()
                or needle in (u["firstName"] or "").lower()
                or needle in (u["lastName"] or "").lower()]
    if username:
        rows = [u for u in rows if u["username"] == username]
    if email:
        rows = [u for u in rows if (u["email"] or "").lower() == str(email).lower()]
    if enabled is not None:
        rows = [u for u in rows if u["enabled"] == enabled]
    return [user_representation(u, brief=brief)
            for u in _slice(rows, first, max_results)]


def count_users(realm_name):
    return len([u for u in _users() if u["realm"] == realm_name])


def get_user(realm_name, user_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    return user_representation(user)


def create_user(realm, payload):
    payload = payload or {}
    username = payload.get("username")
    if not username:
        return _admin_error(400, "User name is missing")
    realm_name = realm["realm"]
    if _store.table("users").find_one(
            lambda u: u["realm"] == realm_name and u["username"] == username):
        return _admin_error(409, f"User exists with same username",
                            error="Conflict detected")
    email = payload.get("email")
    if email and not realm["duplicateEmailsAllowed"] and \
            _store.table("users").find_one(
                lambda u: u["realm"] == realm_name
                and (u["email"] or "").lower() == str(email).lower()):
        return _admin_error(409, "User exists with same email",
                            error="Conflict detected")
    credentials = payload.get("credentials") or []
    salt, digest = "", ""
    if credentials:
        raw = credentials[0].get("value")
        denied = _check_password_policy(realm, username, raw)
        if denied:
            return denied
        salt = uuid.uuid4().hex[:16]
        digest = _hash_password(salt, raw)
    user = {
        "id": str(uuid.uuid4()), "realm": realm_name, "username": username,
        "email": email or "", "firstName": payload.get("firstName", ""),
        "lastName": payload.get("lastName", ""),
        "enabled": bool(payload.get("enabled", True)),
        "emailVerified": bool(payload.get("emailVerified", False)),
        "credentialSalt": salt, "credentialHash": digest,
        "credentialType": "password" if digest else "",
        "requiredActions": payload.get("requiredActions") or [],
        "totpConfigured": False, "federationLink": "",
        "serviceAccountClientId": "",
        "attributes": payload.get("attributes") or {},
        "createdTimestamp": _now_ms(),
    }
    _store_insert("users", user)
    default_role = f"default-roles-{realm_name}"
    if _realm_role(realm_name, default_role):
        _add_mapping(realm_name, user["id"], "realm", default_role, "")
    _record_admin_event(realm_name, "CREATE", "USER", f"users/{user['id']}")
    return {"__status__": 201, "id": user["id"], "username": user["username"]}


def _check_password_policy(realm, username, password):
    """Enforce the realm's `passwordPolicy` string, as Keycloak parses it."""
    policy = realm.get("passwordPolicy") or ""
    if not password:
        return _admin_error(400, "Password is missing")
    for rule in [p.strip() for p in policy.split(" and ") if p.strip()]:
        name, _, argument = rule.partition("(")
        argument = argument.rstrip(")")
        if name == "length" and len(password) < int(argument or 8):
            return _admin_error(400,
                                f"Invalid password: minimum length "
                                f"{argument}.", error="invalidPasswordMinLength")
        if name == "upperCase" and sum(c.isupper() for c in password) \
                < int(argument or 1):
            return _admin_error(400, f"Invalid password: must contain at least "
                                     f"{argument} upper case characters.",
                                error="invalidPasswordMinUpperCaseChars")
        if name == "digits" and sum(c.isdigit() for c in password) \
                < int(argument or 1):
            return _admin_error(400, f"Invalid password: must contain at least "
                                     f"{argument} numerical digits.",
                                error="invalidPasswordMinDigits")
        if name == "notUsername" and username \
                and password.lower() == username.lower():
            return _admin_error(400, "Invalid password: must not be equal to "
                                     "the username.",
                                error="invalidPasswordNotUsername")
    return None


def update_user(realm_name, user_id, payload):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    payload = payload or {}
    patch = {}
    for field in ("firstName", "lastName", "email"):
        if field in payload:
            patch[field] = payload[field]
    for field in ("enabled", "emailVerified"):
        if field in payload:
            patch[field] = bool(payload[field])
    if "requiredActions" in payload:
        patch["requiredActions"] = list(payload["requiredActions"])
    if "attributes" in payload:
        patch["attributes"] = payload["attributes"]
    if "email" in payload and payload["email"]:
        clash = _store.table("users").find_one(
            lambda u: u["realm"] == realm_name and u["id"] != user_id
            and (u["email"] or "").lower() == str(payload["email"]).lower())
        if clash:
            return _admin_error(409, "User exists with same email",
                                error="Conflict detected")
    updated = _store.table("users").patch(user_id, patch)
    if patch.get("enabled") is False:
        _revoke_user_sessions(realm_name, user_id)
    _record_admin_event(realm_name, "UPDATE", "USER", f"users/{user_id}")
    return {"__status__": 204}


def delete_user(realm_name, user_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    _revoke_user_sessions(realm_name, user_id)
    _store.table("role_mappings").delete_where(lambda m: m["userId"] == user_id)
    _store.table("group_memberships").delete_where(
        lambda m: m["userId"] == user_id)
    _store.table("brute_force_status").delete(user_id)
    _store.table("users").delete(user_id)
    _record_admin_event(realm_name, "DELETE", "USER", f"users/{user_id}")
    return {"__status__": 204}


def reset_password(realm, user_id, payload):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm["realm"]:
        return _not_found("User not found")
    payload = payload or {}
    if payload.get("type", "password") != "password":
        return _admin_error(400, "Unsupported credential type")
    denied = _check_password_policy(realm, user["username"], payload.get("value"))
    if denied:
        return denied
    salt = uuid.uuid4().hex[:16]
    patch = {"credentialSalt": salt,
             "credentialHash": _hash_password(salt, payload["value"]),
             "credentialType": "password"}
    if payload.get("temporary"):
        # A temporary password forces UPDATE_PASSWORD on next login.
        patch["requiredActions"] = sorted(
            set(user["requiredActions"]) | {"UPDATE_PASSWORD"})
    _store.table("users").patch(user_id, patch)
    _revoke_user_sessions(realm["realm"], user_id)
    _record_event(realm["realm"], "UPDATE_PASSWORD", user_id=user_id,
                  details={"credential_type": "password"})
    return {"__status__": 204}


def execute_actions_email(realm_name, user_id, actions=None):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    known = {a["alias"] for a in _store.table("required_actions").rows()
             if a["realm"] == realm_name and a["enabled"]}
    unknown = [a for a in (actions or []) if a not in known]
    if unknown:
        return _admin_error(400, f"Provided required actions are not enabled on "
                                 f"this realm: {', '.join(unknown)}")
    merged = sorted(set(user["requiredActions"]) | set(actions or []))
    _store.table("users").patch(user_id, {"requiredActions": merged})
    return {"__status__": 204, "requiredActions": merged,
            "note": "no mail is delivered by the mock; the actions are recorded "
                    "on the user"}


def _revoke_user_sessions(realm_name, user_id):
    return _store.table("sessions").delete_where(
        lambda s: s["realm"] == realm_name and s["userId"] == user_id)


def user_sessions(realm_name, user_id, offline=False):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    return [_session_representation(s) for s in _sessions()
            if s["realm"] == realm_name and s["userId"] == user_id
            and s["offline"] == offline]


def logout_user(realm_name, user_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    _revoke_user_sessions(realm_name, user_id)
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Admin API: role mappings
# ---------------------------------------------------------------------------

def _add_mapping(realm_name, user_id, role_type, role_name, client_id):
    next_id = max((m["id"] for m in _mappings()), default=0) + 1
    return _store_insert("role_mappings", {
        "id": next_id, "realm": realm_name, "userId": user_id,
        "roleType": role_type, "roleName": role_name, "clientId": client_id})


def get_role_mappings(realm_name, user_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    realm_names, client_pairs = direct_role_mappings(realm_name, user_id)
    client_mappings = {}
    for client_id, role_name in client_pairs:
        role = _client_role(realm_name, client_id, role_name)
        if not role:
            continue
        entry = client_mappings.setdefault(
            client_id, {"id": role["clientUuid"], "client": client_id,
                        "mappings": []})
        entry["mappings"].append(client_role_representation(role))
    return {"realmMappings": [realm_role_representation(_realm_role(realm_name, n))
                              for n in realm_names
                              if _realm_role(realm_name, n)],
            "clientMappings": client_mappings}


def get_effective_role_mappings(realm_name, user_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    realm_names, client_pairs = effective_roles(realm_name, user_id)
    client_mappings = {}
    for pair in client_pairs:
        client_id, _, role_name = pair.partition(":")
        client_mappings.setdefault(client_id, []).append(role_name)
    return {"realmMappings": realm_names, "clientMappings": client_mappings,
            "note": "composite roles and group-inherited roles are expanded; "
                    "compare with /role-mappings for the direct set"}


def add_realm_role_mappings(realm_name, user_id, roles=None):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    for entry in (roles or []):
        name = entry.get("name") if isinstance(entry, dict) else entry
        if not _realm_role(realm_name, name):
            return _not_found(f"Could not find role: {name}")
        existing = _store.table("role_mappings").find_one(
            lambda m: m["realm"] == realm_name and m["userId"] == user_id
            and m["roleType"] == "realm" and m["roleName"] == name)
        if existing:
            continue
        _add_mapping(realm_name, user_id, "realm", name, "")
    _record_admin_event(realm_name, "UPDATE", "REALM_ROLE_MAPPING",
                        f"users/{user_id}/role-mappings/realm")
    return {"__status__": 204}


def remove_realm_role_mappings(realm_name, user_id, roles=None):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    for entry in (roles or []):
        name = entry.get("name") if isinstance(entry, dict) else entry
        _store.table("role_mappings").delete_where(
            lambda m: m["realm"] == realm_name and m["userId"] == user_id
            and m["roleType"] == "realm" and m["roleName"] == name)
    return {"__status__": 204}


def get_client_role_mappings(realm_name, user_id, uuid_value):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    client = _client_by_uuid(realm_name, uuid_value)
    if not client:
        return _not_found("Could not find client")
    _, client_pairs = direct_role_mappings(realm_name, user_id)
    out = []
    for client_id, role_name in client_pairs:
        if client_id != client["clientId"]:
            continue
        role = _client_role(realm_name, client_id, role_name)
        if role:
            out.append(client_role_representation(role))
    return out


def add_client_role_mappings(realm_name, user_id, uuid_value, roles=None):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    client = _client_by_uuid(realm_name, uuid_value)
    if not client:
        return _not_found("Could not find client")
    for entry in (roles or []):
        name = entry.get("name") if isinstance(entry, dict) else entry
        if not _client_role(realm_name, client["clientId"], name):
            return _not_found(f"Could not find role: {name}")
        existing = _store.table("role_mappings").find_one(
            lambda m: m["realm"] == realm_name and m["userId"] == user_id
            and m["roleType"] == "client" and m["roleName"] == name
            and m["clientId"] == client["clientId"])
        if existing:
            continue
        _add_mapping(realm_name, user_id, "client", name, client["clientId"])
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Admin API: groups
# ---------------------------------------------------------------------------

def list_groups(realm_name):
    return [group_representation(g) for g in _groups()
            if g["realm"] == realm_name and not g["parentId"]]


def get_group(realm_name, group_id):
    group = _store.table("groups").get(group_id)
    if not group or group["realm"] != realm_name:
        return _not_found("Could not find group by id")
    return group_representation(group)


def create_group(realm_name, payload, parent_id=""):
    payload = payload or {}
    name = payload.get("name")
    if not name:
        return _admin_error(400, "Group name is missing")
    parent = _store.table("groups").get(parent_id) if parent_id else None
    if parent_id and (not parent or parent["realm"] != realm_name):
        return _not_found("Could not find group by id")
    path = f"{parent['path']}/{name}" if parent else f"/{name}"
    if _store.table("groups").find_one(
            lambda g: g["realm"] == realm_name and g["path"] == path):
        return _admin_error(409, f"Top level group named '{name}' already exists.",
                            error="Conflict detected")
    group = {"id": f"g-{uuid.uuid4().hex[:16]}", "realm": realm_name,
             "name": name, "path": path, "parentId": parent_id,
             "realmRoles": payload.get("realmRoles") or [],
             "clientRoles": payload.get("clientRoles") or [],
             "attributes": payload.get("attributes") or {}}
    _store_insert("groups", group)
    _record_admin_event(realm_name, "CREATE", "GROUP", f"groups/{group['id']}")
    return {"__status__": 201, "id": group["id"], "path": group["path"]}


def delete_group(realm_name, group_id):
    group = _store.table("groups").get(group_id)
    if not group or group["realm"] != realm_name:
        return _not_found("Could not find group by id")
    children = [g for g in _groups() if g["parentId"] == group_id]
    if children:
        return _admin_error(400, "Group has subgroups; delete them first")
    _store.table("group_memberships").delete_where(
        lambda m: m["groupId"] == group_id)
    _store.table("groups").delete(group_id)
    return {"__status__": 204}


def group_members(realm_name, group_id):
    group = _store.table("groups").get(group_id)
    if not group or group["realm"] != realm_name:
        return _not_found("Could not find group by id")
    member_ids = [m["userId"] for m in _memberships()
                  if m["groupId"] == group_id]
    return [user_representation(_store.table("users").get(u), brief=True)
            for u in member_ids if _store.table("users").get(u)]


def group_role_mappings(realm_name, group_id):
    group = _store.table("groups").get(group_id)
    if not group or group["realm"] != realm_name:
        return _not_found("Could not find group by id")
    return {"realmMappings": [realm_role_representation(
        _realm_role(realm_name, n)) for n in group["realmRoles"]
        if _realm_role(realm_name, n)],
        "clientMappings": _group_client_roles(group)}


def user_groups(realm_name, user_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    group_ids = [m["groupId"] for m in _memberships()
                 if m["realm"] == realm_name and m["userId"] == user_id]
    return [group_representation(_store.table("groups").get(g),
                                 with_subgroups=False)
            for g in group_ids if _store.table("groups").get(g)]


def join_group(realm_name, user_id, group_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    group = _store.table("groups").get(group_id)
    if not group or group["realm"] != realm_name:
        return _not_found("Could not find group by id")
    existing = _store.table("group_memberships").find_one(
        lambda m: m["userId"] == user_id and m["groupId"] == group_id)
    if not existing:
        next_id = max((m["id"] for m in _memberships()), default=0) + 1
        _store_insert("group_memberships", {
            "id": next_id, "realm": realm_name, "userId": user_id,
            "groupId": group_id})
    return {"__status__": 204}


def leave_group(realm_name, user_id, group_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    removed = _store.table("group_memberships").delete_where(
        lambda m: m["userId"] == user_id and m["groupId"] == group_id)
    if not removed:
        return _not_found("Could not find group membership")
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Admin API: identity providers, required actions, brute force
# ---------------------------------------------------------------------------

def list_identity_providers(realm_name):
    return [p for p in _store.table("identity_providers").rows()
            if p["realm"] == realm_name]


def get_identity_provider(realm_name, alias):
    provider = _store.table("identity_providers").get(alias)
    if not provider or provider["realm"] != realm_name:
        return _not_found("Could not find identity provider")
    return provider


def list_required_actions(realm_name):
    rows = [a for a in _store.table("required_actions").rows()
            if a["realm"] == realm_name]
    rows.sort(key=lambda a: a["priority"])
    # `_pk` is the store's composite key, not part of the representation.
    return [{k: v for k, v in a.items() if k != "_pk"} for a in rows]


def brute_force_status(realm_name, user_id):
    user = _store.table("users").get(user_id)
    if not user or user["realm"] != realm_name:
        return _not_found("User not found")
    lock = _store.table("brute_force_status").get(user_id)
    if not lock:
        return {"numFailures": 0, "disabled": False, "lastIPFailure": "n/a",
                "lastFailure": 0}
    return {"numFailures": lock["numFailures"], "disabled": lock["disabled"],
            "lastIPFailure": lock["lastIPFailure"],
            "lastFailure": lock["lastFailure"]}


def clear_brute_force(realm_name, user_id=None):
    if user_id:
        user = _store.table("users").get(user_id)
        if not user or user["realm"] != realm_name:
            return _not_found("User not found")
        _store.table("brute_force_status").delete(user_id)
    else:
        _store.table("brute_force_status").delete_where(
            lambda b: b["realm"] == realm_name)
    return {"__status__": 204}


def _record_admin_event(realm_name, operation_type, resource_type,
                        resource_path):
    entry = {"id": f"ae{uuid.uuid4().hex[:12]}", "realm": realm_name,
             "time": _now_ms(), "operationType": operation_type,
             "resourceType": resource_type, "resourcePath": resource_path,
             "authRealm": realm_name, "authClient": ADMIN_CLIENT,
             "authUser": ADMIN_USERNAME, "ipAddress": "203.0.113.41"}
    _store_insert("admin_events", entry)
    return entry


_store.eager_load()
