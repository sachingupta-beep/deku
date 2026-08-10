"""Data access module for the Logto mock service.

Logto is OIDC-first, and that shapes the whole surface. There are two planes:

* `/oidc/*` --- a real OAuth 2.0 authorization server. `POST /oidc/token` takes
  `grant_type` (`authorization_code`, `refresh_token`, `client_credentials`), a
  `resource` indicator and a `scope`, and issues an access token *scoped to that
  resource*. Errors follow RFC 6749 (`{"error": "invalid_grant", ...}`).
* `/api/*` --- the Management API, which is itself just another protected
  resource. A bearer only works there if it was issued **for** the indicator
  `https://default.logto.app/api` and carries a scope wide enough for the
  endpoint. A token minted for the Orbit Status API is a perfectly valid token
  and still gets 403 here.

Organizations are the third axis: a token can be issued for an organization
instead of a resource, in which case its audience is
`urn:logto:organization:<id>` and its scopes are organization scopes.

Passwords are verified as `sha256(passwordSalt + password)` --- real Logto uses
Argon2i, and the seed records `passwordEncryptionMethod` accordingly. Mutations
are held in process memory and reset on restart.
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

_store = get_store("logto-api")
_API = "logto-api"

MANAGEMENT_API = "https://default.logto.app/api"
ALL_SCOPE = "all"


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

    Logto's `customData` and connector `config` are free-form JSON; the seed
    keeps them flat so a CSV overlay can shadow the JSON.
    """
    out = {}
    for part in _semi_list(row, column):
        key, _, value = part.partition("=")
        if key:
            out[key] = value
    return out


def _load_json(filename):
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json", "users")))
_store.register("applications", primary_key="id",
                initial_loader=lambda: _coerce_applications(
                    _load("applications.json", "applications")))
_store.register("resources", primary_key="id",
                initial_loader=lambda: _coerce_resources(
                    _load("resources.json", "resources")))
_store.register("scopes", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("scopes.json", "scopes")])
_store.register("roles", primary_key="id",
                initial_loader=lambda: [
                    {**_strip_ctx(r), "scopeIds": _semi_list(r, "scopeIds")}
                    for r in _load("roles.json", "roles")])
_store.register("user_roles", primary_key="id",
                initial_loader=lambda: _coerce_ints(
                    _load("user_roles.json", "user_roles"), ("id",)))
_store.register("application_roles", primary_key="id",
                initial_loader=lambda: _coerce_ints(
                    _load("application_roles.json", "application_roles"), ("id",)))
_store.register("organizations", primary_key="id",
                initial_loader=lambda: _coerce_organizations(
                    _load("organizations.json", "organizations")))
_store.register("organization_scopes", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("organization_scopes.json",
                                              "organization_scopes")])
_store.register("organization_roles", primary_key="id",
                initial_loader=lambda: [
                    {**_strip_ctx(r), "scopeIds": _semi_list(r, "scopeIds")}
                    for r in _load("organization_roles.json", "organization_roles")])
_store.register("organization_memberships", primary_key="id",
                initial_loader=lambda: _coerce_memberships(
                    _load("organization_memberships.json",
                          "organization_memberships")))
_store.register("access_tokens", primary_key="token",
                initial_loader=lambda: _coerce_tokens(
                    _load("access_tokens.json", "access_tokens")))
_store.register("refresh_tokens", primary_key="token",
                initial_loader=lambda: _coerce_flags(
                    _load("refresh_tokens.json", "refresh_tokens"), ("revoked",),
                    ints=("issuedAt",)))
_store.register("authorization_codes", primary_key="code",
                initial_loader=lambda: _coerce_flags(
                    _load("authorization_codes.json", "authorization_codes"),
                    ("used",), ints=("expiresAt",)))
_store.register("connectors", primary_key="id",
                initial_loader=lambda: _coerce_connectors(
                    _load("connectors.json", "connectors")))
_store.register("verification_codes", primary_key="id",
                initial_loader=lambda: _coerce_flags(
                    _load("verification_codes.json", "verification_codes"),
                    ("consumed",), ints=("expiresAt", "createdAt")))
_store.register("logs", primary_key="id",
                initial_loader=lambda: _coerce_ints(
                    _load("logs.json", "logs"), ("createdAt",)))
_store.register_document("sign_in_experience",
                         initial_loader=lambda: _load_json("sign_in_experience.json"))
_store.register_document("oidc_config",
                         initial_loader=lambda: _load_json("oidc_config.json"))


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def _coerce_ints(rows, ints):
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in ints}}
            for r in rows]


def _coerce_flags(rows, flags, ints=()):
    return [{**_strip_ctx(r),
             **{f: bool(opt_int(r, f, default=0)) for f in flags},
             **{f: opt_int(r, f, default=0) for f in ints}} for r in rows]


def _coerce_users(rows):
    out = []
    for r in rows:
        identities = {}
        for entry in _semi_list(r, "identities"):
            target, _, user_id = entry.partition(":")
            if target:
                identities[target] = {"userId": user_id,
                                      "details": {"id": user_id}}
        out.append({**_strip_ctx(r),
                    "isSuspended": opt_str(r, "isSuspended", default="0") == "1",
                    "lastSignInAt": opt_int(r, "lastSignInAt", default=0),
                    "createdAt": opt_int(r, "createdAt", default=0),
                    "customData": _semi_map(r, "customData"),
                    "identities": identities})
    return out


def _coerce_applications(rows):
    return [{**_strip_ctx(r),
             "redirectUris": _semi_list(r, "redirectUris"),
             "postLogoutRedirectUris": _semi_list(r, "postLogoutRedirectUris"),
             "corsAllowedOrigins": _semi_list(r, "corsAllowedOrigins"),
             "grantTypes": _semi_list(r, "grantTypes"),
             "isThirdParty": opt_str(r, "isThirdParty", default="0") == "1",
             "createdAt": opt_int(r, "createdAt", default=0)} for r in rows]


def _coerce_resources(rows):
    return [{**_strip_ctx(r),
             "accessTokenTtl": opt_int(r, "accessTokenTtl", default=3600),
             "isDefault": opt_str(r, "isDefault", default="0") == "1"}
            for r in rows]


def _coerce_organizations(rows):
    return [{**_strip_ctx(r),
             "isMfaRequired": opt_str(r, "isMfaRequired", default="0") == "1",
             "customData": _semi_map(r, "customData"),
             "createdAt": opt_int(r, "createdAt", default=0)} for r in rows]


def _coerce_memberships(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "roleIds": _semi_list(r, "roleIds"),
             "joinedAt": opt_int(r, "joinedAt", default=0)} for r in rows]


def _coerce_tokens(rows):
    return [{**_strip_ctx(r),
             "scope": [s for s in opt_str(r, "scope", default="").split(" ") if s],
             "revoked": opt_str(r, "revoked", default="0") == "1",
             "expiresAt": opt_int(r, "expiresAt", default=0),
             "issuedAt": opt_int(r, "issuedAt", default=0)} for r in rows]


def _coerce_connectors(rows):
    return [{**_strip_ctx(r),
             "enabled": opt_str(r, "enabled", default="0") == "1",
             "config": _semi_map(r, "config")} for r in rows]


# ---------------------------------------------------------------------------
# Table accessors
# ---------------------------------------------------------------------------

def _users():
    return _store.table("users").rows()


def _applications():
    return _store.table("applications").rows()


def _resources():
    return _store.table("resources").rows()


def _scopes():
    return _store.table("scopes").rows()


def _roles():
    return _store.table("roles").rows()


def _user_roles():
    return _store.table("user_roles").rows()


def _application_roles():
    return _store.table("application_roles").rows()


def _organizations():
    return _store.table("organizations").rows()


def _organization_roles():
    return _store.table("organization_roles").rows()


def _organization_scopes():
    return _store.table("organization_scopes").rows()


def _memberships():
    return _store.table("organization_memberships").rows()


def _connectors():
    return _store.table("connectors").rows()


def _logs():
    return _store.table("logs").rows()


def _oidc():
    return _store.document("oidc_config").get()


def _now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def _logto_id(prefix=""):
    """Logto ids are short lowercase alphanumerics."""
    return (prefix + uuid.uuid4().hex)[:12]


# ---------------------------------------------------------------------------
# Errors
#
# Logto uses real HTTP statuses. The OIDC plane speaks RFC 6749
# (`{"error", "error_description"}`); the Management API speaks Logto's own
# `{"code", "message"}`.
# ---------------------------------------------------------------------------

def _oauth_error(status, error, description):
    return {"error": error, "code": status, "oauth": True,
            "error_description": description}


def _api_error(status, code, message, data=None):
    return {"error": message, "code": status, "logto_code": code,
            "message": message, "data": data}


def _not_found(entity, id_value):
    return _api_error(404, "entity.not_found",
                      f"The {entity} with id {id_value} was not found.",
                      {"entity": entity, "id": id_value})


# ---------------------------------------------------------------------------
# Bearer resolution and authorization
# ---------------------------------------------------------------------------

def resolve_token(authorization=None):
    """Resolve a bearer to its access-token record, or None."""
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw:
        return None
    record = _store.table("access_tokens").get(raw)
    if not record or record["revoked"] or record["expiresAt"] < _now_ms():
        return None
    return record


def authorize_management(authorization=None, required_scope=None):
    """Gate a Management API call.

    Three distinct refusals, all of which a real Logto deployment produces:
      * no usable bearer at all -> 401
      * a valid token minted for a *different* resource -> 403, wrong audience
      * the right resource but too narrow a scope -> 403, insufficient scope
    """
    record = resolve_token(authorization)
    if not record:
        return None, _api_error(401, "auth.authorization_header_missing",
                                "Authorization header is missing or the token "
                                "is invalid, revoked or expired.")
    if record["resource"] != MANAGEMENT_API:
        return None, _api_error(
            403, "auth.forbidden",
            f"The access token was issued for {record['resource'] or 'an '
                                               'organization'}, not for the "
            f"Management API ({MANAGEMENT_API}).",
            {"audience": record["resource"] or
             f"urn:logto:organization:{record['organizationId']}",
             "expected": MANAGEMENT_API})
    scopes = set(record["scope"])
    if required_scope and ALL_SCOPE not in scopes and required_scope not in scopes:
        return None, _api_error(
            403, "auth.insufficient_scope",
            f"The access token does not carry the required scope "
            f"'{required_scope}'.",
            {"scope": sorted(scopes), "required": required_scope})
    return record, None


def authorize_organization(authorization=None, organization_id=None,
                           required_scope=None):
    """Gate an organization-token call."""
    record = resolve_token(authorization)
    if not record:
        return None, _api_error(401, "auth.authorization_header_missing",
                                "Authorization header is missing or the token "
                                "is invalid, revoked or expired.")
    if not record["organizationId"]:
        return None, _api_error(403, "auth.forbidden",
                                "The access token is not an organization token.")
    if organization_id and record["organizationId"] != organization_id:
        return None, _api_error(
            403, "auth.forbidden",
            f"The organization token is scoped to "
            f"{record['organizationId']}, not {organization_id}.")
    if required_scope and required_scope not in set(record["scope"]):
        return None, _api_error(
            403, "auth.insufficient_scope",
            f"The organization token does not carry the required scope "
            f"'{required_scope}'.",
            {"scope": record["scope"], "required": required_scope})
    return record, None


# ---------------------------------------------------------------------------
# Service metadata
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def status():
    oidc = _oidc()
    return {"status": "ok", "version": oidc["logtoVersion"],
            "tenantId": oidc["tenantId"]}


def openid_configuration():
    oidc = _oidc()
    issuer = oidc["issuer"]
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/auth",
        "token_endpoint": f"{issuer}/token",
        "userinfo_endpoint": f"{issuer}/me",
        "jwks_uri": f"{issuer}/jwks",
        "end_session_endpoint": f"{issuer}/session/end",
        "revocation_endpoint": f"{issuer}/token/revocation",
        "introspection_endpoint": f"{issuer}/token/introspection",
        "response_types_supported": oidc["responseTypesSupported"],
        "grant_types_supported": oidc["grantTypesSupported"],
        "subject_types_supported": oidc["subjectTypesSupported"],
        "id_token_signing_alg_values_supported":
            oidc["idTokenSigningAlgValuesSupported"],
        "scopes_supported": oidc["scopesSupported"],
        "claims_supported": oidc["claimsSupported"],
        "code_challenge_methods_supported": oidc["codeChallengeMethodsSupported"],
        "token_endpoint_auth_methods_supported":
            oidc["tokenEndpointAuthMethodsSupported"],
    }


def jwks():
    """Static JWKS. The mock signs nothing, so the key is a stable placeholder."""
    return {"keys": [{"kty": "EC", "crv": "P-384", "kid": "logto-orbit-labs-2026",
                      "x": "bG9ndG8tb3JiaXQtbGFicy1tb2NrLXgtY29vcmRpbmF0ZQ",
                      "y": "bG9ndG8tb3JiaXQtbGFicy1tb2NrLXktY29vcmRpbmF0ZQ",
                      "alg": "ES384", "use": "sig"}]}


# ---------------------------------------------------------------------------
# OIDC: authorize and token
# ---------------------------------------------------------------------------

def authorize(client_id=None, redirect_uri=None, response_type="code",
              scope=None, resource=None, code_challenge=None,
              code_challenge_method=None, state=None, organization_id=None):
    """The authorization endpoint.

    A real deployment redirects to the sign-in experience; the mock returns the
    parameters it would carry so the flow stays inspectable, plus a usable
    authorization code for the seeded user of that application.
    """
    application = _store.table("applications").get(client_id) if client_id else None
    if not application:
        return _oauth_error(400, "invalid_client", "Unknown client_id.")
    if response_type != "code":
        return _oauth_error(400, "unsupported_response_type",
                            "Only the authorization code flow is supported.")
    if "authorization_code" not in application["grantTypes"]:
        return _oauth_error(400, "unauthorized_client",
                            f"The application {application['name']} is a "
                            f"{application['type']} app and may not use the "
                            f"authorization code grant.")
    if redirect_uri not in application["redirectUris"]:
        return _oauth_error(400, "invalid_request",
                            "redirect_uri is not registered for this client.")
    if application["type"] in ("SPA", "Native") and not code_challenge:
        # Public clients must use PKCE.
        return _oauth_error(400, "invalid_request",
                            f"PKCE is required for {application['type']} "
                            f"applications.")
    user = _store.table("users").find_one(
        lambda u: u["applicationId"] == client_id and not u["isSuspended"])
    if not user:
        return _oauth_error(400, "access_denied",
                            "No active seeded user is bound to this client.")
    code = f"logto_code_{uuid.uuid4().hex[:16]}"
    _store.table("authorization_codes").upsert({
        "code": code, "clientId": client_id, "userId": user["id"],
        "redirectUri": redirect_uri,
        "scope": scope or "openid profile email offline_access",
        "resource": resource or "", "codeChallenge": code_challenge or "",
        "codeVerifier": "", "organizationId": organization_id or "",
        "used": False, "expiresAt": _now_ms() + 600000})
    _record_log("ExperienceApi.SignIn.Submit", "SignIn", "Success",
                user_id=user["id"], application_id=client_id)
    return {"redirect_to": f"{redirect_uri}?code={code}&state={state or ''}",
            "code": code, "state": state,
            "sub": user["id"], "client_id": client_id,
            "note": "the mock returns the authorization code rather than "
                    "redirecting, so the flow stays inspectable"}


_GRANTS = ("authorization_code", "refresh_token", "client_credentials")


def token(grant_type=None, client_id=None, client_secret=None, code=None,
          code_verifier=None, redirect_uri=None, refresh_token=None,
          resource=None, scope=None, organization_id=None):
    if grant_type not in _GRANTS:
        return _oauth_error(400, "unsupported_grant_type",
                            f"grant_type must be one of {', '.join(_GRANTS)}.")
    application = _store.table("applications").get(client_id) if client_id else None
    if not application:
        return _oauth_error(401, "invalid_client", "Unknown client_id.")
    if grant_type not in application["grantTypes"]:
        return _oauth_error(400, "unauthorized_client",
                            f"The application {application['name']} is not "
                            f"allowed to use the {grant_type} grant.")
    # Confidential clients must authenticate; public ones must not send a secret.
    if application["clientSecret"]:
        if client_secret != application["clientSecret"]:
            return _oauth_error(401, "invalid_client",
                                "Client authentication failed.")
    if grant_type == "client_credentials":
        return _client_credentials(application, resource, scope, organization_id)
    if grant_type == "authorization_code":
        return _authorization_code(application, code, code_verifier, redirect_uri)
    return _refresh(application, refresh_token, resource, scope, organization_id)


def _granted_scopes(subject_id, subject_type, resource, requested):
    """Intersect what was asked for with what the subject's roles actually grant."""
    if subject_type == "application":
        role_ids = [r["roleId"] for r in _application_roles()
                    if r["applicationId"] == subject_id]
    else:
        role_ids = [r["roleId"] for r in _user_roles() if r["userId"] == subject_id]
    scope_ids = {s for role in _roles() if role["id"] in role_ids
                 for s in role["scopeIds"]}
    by_id = {s["id"]: s for s in _scopes()}
    available = {by_id[s]["name"] for s in scope_ids
                 if s in by_id and by_id[s]["resourceId"] == _resource_id(resource)}
    if not requested:
        return sorted(available)
    asked = {s for s in requested.split(" ") if s}
    return sorted(available & asked)


def _resource_id(indicator):
    resource = _store.table("resources").find_one(
        lambda r: r["indicator"] == indicator)
    return resource["id"] if resource else ""


def _org_scopes_for(user_id, organization_id, requested):
    membership = _store.table("organization_memberships").find_one(
        lambda m: m["userId"] == user_id
        and m["organizationId"] == organization_id)
    if not membership:
        return None
    by_id = {r["id"]: r for r in _organization_roles()}
    scope_ids = {s for role_id in membership["roleIds"] if role_id in by_id
                 for s in by_id[role_id]["scopeIds"]}
    names = {s["name"] for s in _organization_scopes() if s["id"] in scope_ids}
    if not requested:
        return sorted(names)
    asked = {s for s in requested.split(" ") if s}
    return sorted(names & asked)


def _issue_access_token(client_id, subject, subject_type, resource, scopes,
                        organization_id=""):
    oidc = _oidc()
    ttl = 3600
    if resource:
        record = _store.table("resources").find_one(
            lambda r: r["indicator"] == resource)
        if record:
            ttl = record["accessTokenTtl"]
    value = f"logto_at_{secrets.token_hex(12)}"
    _store.table("access_tokens").upsert({
        "token": value, "clientId": client_id, "subject": subject,
        "subjectType": subject_type, "resource": resource or "",
        "scope": list(scopes), "organizationId": organization_id or "",
        "revoked": False, "expiresAt": _now_ms() + ttl * 1000,
        "issuedAt": _now_ms()})
    audience = resource or (f"{oidc['organizationTokenAudiencePrefix']}"
                            f"{organization_id}" if organization_id else client_id)
    return value, ttl, audience


def _client_credentials(application, resource, scope, organization_id):
    if organization_id:
        return _oauth_error(400, "invalid_request",
                            "Organization tokens require a user subject.")
    resource = resource or MANAGEMENT_API
    granted = _granted_scopes(application["id"], "application", resource, scope)
    if not granted:
        return _oauth_error(400, "invalid_scope",
                            f"The application has no scopes on {resource}.")
    value, ttl, audience = _issue_access_token(
        application["id"], application["id"], "application", resource, granted)
    _record_log("ExchangeTokenBy.ClientCredentials", "ExchangeTokenBy", "Success",
                application_id=application["id"])
    return {"access_token": value, "token_type": "Bearer", "expires_in": ttl,
            "scope": " ".join(granted), "aud": audience}


def _authorization_code(application, code, code_verifier, redirect_uri):
    record = _store.table("authorization_codes").get(code) if code else None
    if not record or record["clientId"] != application["id"]:
        return _oauth_error(400, "invalid_grant",
                            "The authorization code is invalid.")
    if record["used"]:
        # Replaying a code is an attack signal; the spec says reject it.
        return _oauth_error(400, "invalid_grant",
                            "The authorization code has already been used.")
    if record["expiresAt"] < _now_ms():
        return _oauth_error(400, "invalid_grant",
                            "The authorization code has expired.")
    if redirect_uri and redirect_uri != record["redirectUri"]:
        return _oauth_error(400, "invalid_grant",
                            "redirect_uri does not match the authorization "
                            "request.")
    if record["codeChallenge"]:
        if not code_verifier:
            return _oauth_error(400, "invalid_grant",
                                "code_verifier is required for this code.")
        challenge = _pkce_challenge(code_verifier)
        if challenge != record["codeChallenge"]:
            return _oauth_error(400, "invalid_grant",
                                "code_verifier does not match code_challenge.")
    _store.table("authorization_codes").patch(code, {"used": True})
    user = _store.table("users").get(record["userId"])
    resource = record["resource"]
    granted = _granted_scopes(user["id"], "user", resource, record["scope"]) \
        if resource else []
    value, ttl, audience = _issue_access_token(
        application["id"], user["id"], "user", resource, granted)
    body = {"access_token": value, "token_type": "Bearer", "expires_in": ttl,
            "scope": " ".join(granted), "aud": audience,
            "id_token": _id_token(user, application["id"])}
    if "offline_access" in record["scope"].split(" "):
        rt = f"logto_rt_{secrets.token_hex(12)}"
        _store.table("refresh_tokens").upsert({
            "token": rt, "clientId": application["id"], "userId": user["id"],
            "scope": record["scope"], "resource": resource, "revoked": False,
            "issuedAt": _now_ms()})
        body["refresh_token"] = rt
    return body


def _pkce_challenge(verifier):
    import base64
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _refresh(application, refresh_token, resource, scope, organization_id):
    record = _store.table("refresh_tokens").get(refresh_token) \
        if refresh_token else None
    if not record or record["clientId"] != application["id"]:
        return _oauth_error(400, "invalid_grant", "The refresh token is invalid.")
    if record["revoked"]:
        return _oauth_error(400, "invalid_grant",
                            "The refresh token has been revoked.")
    user = _store.table("users").get(record["userId"])
    if not user:
        return _oauth_error(400, "invalid_grant", "The user no longer exists.")
    if user["isSuspended"]:
        return _oauth_error(400, "invalid_grant", "The user is suspended.")
    if organization_id:
        granted = _org_scopes_for(user["id"], organization_id, scope)
        if granted is None:
            return _oauth_error(403, "access_denied",
                                f"{user['username']} is not a member of "
                                f"{organization_id}.")
        value, ttl, audience = _issue_access_token(
            application["id"], user["id"], "user", "", granted,
            organization_id=organization_id)
    else:
        resource = resource or record["resource"]
        granted = _granted_scopes(user["id"], "user", resource,
                                  scope or record["scope"])
        value, ttl, audience = _issue_access_token(
            application["id"], user["id"], "user", resource, granted)
    # Rotation: the presented token is revoked and a descendant issued.
    rotated = f"logto_rt_{secrets.token_hex(12)}"
    _store.table("refresh_tokens").patch(refresh_token, {"revoked": True})
    _store.table("refresh_tokens").upsert({
        "token": rotated, "clientId": application["id"], "userId": user["id"],
        "scope": record["scope"], "resource": record["resource"],
        "revoked": False, "issuedAt": _now_ms()})
    _record_log("ExchangeTokenBy.RefreshToken", "ExchangeTokenBy", "Success",
                user_id=user["id"], application_id=application["id"])
    return {"access_token": value, "token_type": "Bearer", "expires_in": ttl,
            "scope": " ".join(granted), "aud": audience,
            "refresh_token": rotated, "id_token": _id_token(user,
                                                            application["id"])}


def _id_token(user, client_id):
    oidc = _oidc()
    return (f"eyJhbGciOiJFUzM4NCJ9.{user['id']}.{client_id}"
            f".{oidc['tenantId']}-mock-signature")


def introspect(token_value=None):
    record = _store.table("access_tokens").get(token_value) if token_value else None
    if not record or record["revoked"] or record["expiresAt"] < _now_ms():
        # RFC 7662: an unknown or dead token is simply inactive, not an error.
        return {"active": False}
    oidc = _oidc()
    audience = record["resource"] or (
        f"{oidc['organizationTokenAudiencePrefix']}{record['organizationId']}"
        if record["organizationId"] else record["clientId"])
    return {"active": True, "sub": record["subject"],
            "client_id": record["clientId"], "aud": audience,
            "scope": " ".join(record["scope"]), "iss": oidc["issuer"],
            "token_type": "Bearer",
            "exp": record["expiresAt"] // 1000, "iat": record["issuedAt"] // 1000}


def revoke(token_value=None):
    """RFC 7009: revocation always answers 200, even for an unknown token."""
    if _store.table("access_tokens").get(token_value):
        _store.table("access_tokens").patch(token_value, {"revoked": True})
    elif _store.table("refresh_tokens").get(token_value):
        _store.table("refresh_tokens").patch(token_value, {"revoked": True})
    return {}


def userinfo(authorization=None):
    record = resolve_token(authorization)
    if not record:
        return _oauth_error(401, "invalid_token",
                            "The access token is missing, invalid or expired.")
    if record["subjectType"] != "user":
        return _oauth_error(403, "insufficient_scope",
                            "A machine-to-machine token has no user profile.")
    user = _store.table("users").get(record["subject"])
    body = {"sub": user["id"], "name": user["name"],
            "username": user["username"], "picture": user["avatar"],
            "email": user["primaryEmail"], "email_verified": True,
            "custom_data": user["customData"], "identities": user["identities"]}
    body["roles"] = _role_names_for_user(user["id"])
    body["organizations"] = [m["organizationId"] for m in _memberships()
                             if m["userId"] == user["id"]]
    return body


def _role_names_for_user(user_id):
    role_ids = {r["roleId"] for r in _user_roles() if r["userId"] == user_id}
    return sorted(r["name"] for r in _roles() if r["id"] in role_ids)


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def _record_log(key, log_type, result, user_id="", application_id="",
                ip="203.0.113.41", user_agent="orbit-status/2.1"):
    entry = {"id": _logto_id("log"), "key": key, "type": log_type,
             "result": result, "userId": user_id,
             "applicationId": application_id, "ip": ip,
             "userAgent": user_agent, "createdAt": _now_ms()}
    _store_insert("logs", entry)
    return entry


def list_logs(page=1, page_size=20, log_key=None, user_id=None,
              application_id=None):
    rows = _logs()
    if log_key:
        rows = [r for r in rows if r["key"] == log_key]
    if user_id:
        rows = [r for r in rows if r["userId"] == user_id]
    if application_id:
        rows = [r for r in rows if r["applicationId"] == application_id]
    rows.sort(key=lambda r: r["createdAt"], reverse=True)
    return _paginate(rows, page, page_size)


def get_log(log_id):
    row = _store.table("logs").get(log_id)
    if not row:
        return _not_found("log", log_id)
    return row


def _paginate(rows, page, page_size):
    page_size = max(1, min(int(page_size or 20), 100))
    page = max(1, int(page or 1))
    start = (page - 1) * page_size
    return {"items": rows[start:start + page_size], "totalCount": len(rows),
            "page": page, "pageSize": page_size}


# ---------------------------------------------------------------------------
# Management API: users
# ---------------------------------------------------------------------------

_HIDDEN_USER_FIELDS = ("passwordEncrypted", "passwordSalt")


def public_user(user):
    if not user:
        return None
    body = {k: v for k, v in user.items() if k not in _HIDDEN_USER_FIELDS}
    body["hasPassword"] = bool(user["passwordEncrypted"])
    return body


def list_users(page=1, page_size=20, search=None, is_suspended=None):
    rows = _users()
    if search:
        needle = str(search).lower()
        rows = [u for u in rows
                if needle in (u["username"] or "").lower()
                or needle in (u["primaryEmail"] or "").lower()
                or needle in (u["name"] or "").lower()]
    if is_suspended is not None:
        rows = [u for u in rows if u["isSuspended"] == is_suspended]
    body = _paginate(rows, page, page_size)
    body["items"] = [public_user(u) for u in body["items"]]
    return body


def get_user(user_id):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    return public_user(user)


def create_user(payload):
    payload = payload or {}
    email = payload.get("primaryEmail")
    username = payload.get("username")
    if not email and not username and not payload.get("primaryPhone"):
        return _api_error(422, "guard.invalid_input",
                          "A user needs at least a username, an email or a "
                          "phone number.")
    if email and _store.table("users").find_one(
            lambda u: (u["primaryEmail"] or "").lower() == str(email).lower()):
        return _api_error(422, "user.email_already_in_use",
                          "This email is associated with an existing account.")
    if username and _store.table("users").find_one(
            lambda u: u["username"] == username):
        return _api_error(422, "user.username_already_in_use",
                          "This username is associated with an existing account.")
    password = payload.get("password")
    denied = _check_password_policy(password) if password else None
    if denied:
        return denied
    salt = uuid.uuid4().hex[:16] if password else ""
    now = _now_ms()
    user = {
        "id": _logto_id(), "username": username or "",
        "primaryEmail": email or "",
        "primaryPhone": payload.get("primaryPhone", ""),
        "name": payload.get("name", ""), "avatar": payload.get("avatar", ""),
        "passwordSalt": salt,
        "passwordEncrypted": _hash_password(salt, password) if password else "",
        "passwordEncryptionMethod": "SHA256" if password else "",
        "isSuspended": False, "applicationId": payload.get("applicationId", ""),
        "lastSignInAt": 0, "createdAt": now,
        "customData": payload.get("customData") or {}, "identities": {},
    }
    _store_insert("users", user)
    _record_log("ExperienceApi.Register.Submit", "Register", "Success",
                user_id=user["id"])
    return public_user(user)


def _check_password_policy(password):
    """Enforce the seeded sign-in experience's password policy."""
    policy = _store.document("sign_in_experience").get()["passwordPolicy"]
    if len(password) < policy["length"]["min"]:
        return _api_error(422, "password.rejected",
                          f"The password must be at least "
                          f"{policy['length']['min']} characters.",
                          {"minLength": policy["length"]["min"]})
    kinds = sum(bool(check(password)) for check in (
        lambda p: any(c.islower() for c in p),
        lambda p: any(c.isupper() for c in p),
        lambda p: any(c.isdigit() for c in p),
        lambda p: any(not c.isalnum() for c in p)))
    if kinds < policy["characterTypes"]["min"]:
        return _api_error(422, "password.rejected",
                          f"The password must mix at least "
                          f"{policy['characterTypes']['min']} character types.",
                          {"characterTypes": kinds})
    lowered = password.lower()
    for word in policy["rejects"]["words"]:
        if word in lowered:
            return _api_error(422, "password.rejected",
                              f"The password must not contain '{word}'.",
                              {"word": word})
    return None


def update_user(user_id, payload):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    payload = payload or {}
    patch = {}
    for field in ("name", "avatar", "primaryPhone", "username", "primaryEmail"):
        if field in payload:
            patch[field] = payload[field]
    if "primaryEmail" in payload and payload["primaryEmail"]:
        clash = _store.table("users").find_one(
            lambda u: u["id"] != user_id
            and (u["primaryEmail"] or "").lower()
            == str(payload["primaryEmail"]).lower())
        if clash:
            return _api_error(422, "user.email_already_in_use",
                              "This email is associated with an existing "
                              "account.")
    if "customData" in payload:
        patch["customData"] = payload["customData"]
    updated = _store.table("users").patch(user_id, patch)
    return public_user(updated)


def delete_user(user_id):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    _store.table("user_roles").delete_where(lambda r: r["userId"] == user_id)
    _store.table("organization_memberships").delete_where(
        lambda m: m["userId"] == user_id)
    _store.table("access_tokens").delete_where(
        lambda t: t["subjectType"] == "user" and t["subject"] == user_id)
    _store.table("refresh_tokens").delete_where(lambda t: t["userId"] == user_id)
    _store.table("users").delete(user_id)
    return {"__status__": 204}


def update_password(user_id, password=None):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    if not password:
        return _api_error(422, "guard.invalid_input", "password is required.")
    denied = _check_password_policy(password)
    if denied:
        return denied
    salt = uuid.uuid4().hex[:16]
    _store.table("users").patch(user_id, {
        "passwordSalt": salt, "passwordEncrypted": _hash_password(salt, password),
        "passwordEncryptionMethod": "SHA256"})
    # Changing a password invalidates the user's live tokens.
    _store.table("access_tokens").delete_where(
        lambda t: t["subjectType"] == "user" and t["subject"] == user_id)
    _store.table("refresh_tokens").delete_where(lambda t: t["userId"] == user_id)
    return public_user(_store.table("users").get(user_id))


def verify_password(user_id, password=None):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    if not user["passwordEncrypted"]:
        return _api_error(422, "user.password_not_set",
                          "This account has no password; it signs in with a "
                          "social identity.")
    if _hash_password(user["passwordSalt"], password or "") \
            != user["passwordEncrypted"]:
        return _api_error(422, "session.invalid_credentials",
                          "Invalid credentials.")
    return {"__status__": 204}


def set_suspended(user_id, is_suspended=None):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    if is_suspended is None:
        return _api_error(422, "guard.invalid_input", "isSuspended is required.")
    updated = _store.table("users").patch(user_id,
                                          {"isSuspended": bool(is_suspended)})
    if is_suspended:
        # Suspending kills every live token the user holds.
        _store.table("access_tokens").delete_where(
            lambda t: t["subjectType"] == "user" and t["subject"] == user_id)
        _store.table("refresh_tokens").delete_where(
            lambda t: t["userId"] == user_id)
    return public_user(updated)


def get_custom_data(user_id):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    return user["customData"]


def patch_custom_data(user_id, custom_data=None):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    merged = {**user["customData"], **(custom_data or {})}
    _store.table("users").patch(user_id, {"customData": merged})
    return merged


def list_identities(user_id):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    return user["identities"]


def delete_identity(user_id, target):
    user = _store.table("users").get(user_id)
    if not user:
        return _not_found("user", user_id)
    if target not in user["identities"]:
        return _api_error(404, "user.identity_not_exist",
                          f"The user has no {target} identity.")
    if len(user["identities"]) == 1 and not user["passwordEncrypted"]:
        # Removing the only sign-in method would lock the account out.
        return _api_error(422, "user.cannot_delete_only_identity",
                          "Cannot remove the only identity from a user without "
                          "a password.")
    identities = {k: v for k, v in user["identities"].items() if k != target}
    _store.table("users").patch(user_id, {"identities": identities})
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Management API: roles
# ---------------------------------------------------------------------------

def list_roles(role_type=None):
    rows = _roles()
    if role_type:
        rows = [r for r in rows if r["type"] == role_type]
    return [_public_role(r) for r in rows]


def _public_role(role):
    by_id = {s["id"]: s for s in _scopes()}
    return {**role, "scopes": [by_id[s]["name"] for s in role["scopeIds"]
                               if s in by_id]}


def get_role(role_id):
    role = _store.table("roles").get(role_id)
    if not role:
        return _not_found("role", role_id)
    return _public_role(role)


def create_role(payload):
    payload = payload or {}
    name = payload.get("name")
    if not name:
        return _api_error(422, "guard.invalid_input", "name is required.")
    if _store.table("roles").find_one(lambda r: r["name"] == name):
        return _api_error(422, "role.name_in_use",
                          f"The role name {name} is already in use.")
    scope_names = set(payload.get("scopeNames") or [])
    scope_ids = [s["id"] for s in _scopes() if s["name"] in scope_names]
    role = {"id": _logto_id("rol"), "name": name,
            "description": payload.get("description", ""),
            "type": payload.get("type", "User"), "scopeIds": scope_ids}
    _store_insert("roles", role)
    return _public_role(role)


def delete_role(role_id):
    role = _store.table("roles").get(role_id)
    if not role:
        return _not_found("role", role_id)
    _store.table("user_roles").delete_where(lambda r: r["roleId"] == role_id)
    _store.table("application_roles").delete_where(
        lambda r: r["roleId"] == role_id)
    _store.table("roles").delete(role_id)
    return {"__status__": 204}


def list_user_roles(user_id):
    if not _store.table("users").get(user_id):
        return _not_found("user", user_id)
    role_ids = {r["roleId"] for r in _user_roles() if r["userId"] == user_id}
    return [_public_role(r) for r in _roles() if r["id"] in role_ids]


def assign_user_roles(user_id, role_ids=None):
    if not _store.table("users").get(user_id):
        return _not_found("user", user_id)
    for role_id in (role_ids or []):
        if not _store.table("roles").get(role_id):
            return _not_found("role", role_id)
        if _store.table("user_roles").find_one(
                lambda r: r["userId"] == user_id and r["roleId"] == role_id):
            return _api_error(422, "user.role_exists",
                              f"The user already has the role {role_id}.")
        next_id = max((r["id"] for r in _user_roles()), default=0) + 1
        _store_insert("user_roles", {"id": next_id, "userId": user_id,
                                     "roleId": role_id})
    return {"__status__": 201}


def remove_user_role(user_id, role_id):
    if not _store.table("users").get(user_id):
        return _not_found("user", user_id)
    removed = _store.table("user_roles").delete_where(
        lambda r: r["userId"] == user_id and r["roleId"] == role_id)
    if not removed:
        return _not_found("user role", role_id)
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Management API: applications, resources
# ---------------------------------------------------------------------------

def _public_application(application):
    # The client secret is only meaningful to the owner of the app.
    return {**application, "clientSecret": application["clientSecret"] or None}


def list_applications(app_type=None):
    rows = _applications()
    if app_type:
        rows = [a for a in rows if a["type"] == app_type]
    return [_public_application(a) for a in rows]


def get_application(application_id):
    application = _store.table("applications").get(application_id)
    if not application:
        return _not_found("application", application_id)
    return _public_application(application)


def create_application(payload):
    payload = payload or {}
    name = payload.get("name")
    app_type = payload.get("type")
    if not name or app_type not in ("SPA", "Native", "Traditional",
                                    "MachineToMachine"):
        return _api_error(422, "guard.invalid_input",
                          "name and a valid type are required.")
    confidential = app_type in ("Traditional", "MachineToMachine")
    application = {
        "id": _logto_id("app"), "name": name, "type": app_type,
        "description": payload.get("description", ""),
        "clientSecret": f"logto_secret_{secrets.token_hex(8)}"
                        if confidential else "",
        "redirectUris": payload.get("redirectUris") or [],
        "postLogoutRedirectUris": payload.get("postLogoutRedirectUris") or [],
        "corsAllowedOrigins": payload.get("corsAllowedOrigins") or [],
        "grantTypes": ["client_credentials"] if app_type == "MachineToMachine"
                      else ["authorization_code", "refresh_token"],
        "isThirdParty": bool(payload.get("isThirdParty", False)),
        "createdAt": _now_ms(),
    }
    _store_insert("applications", application)
    return _public_application(application)


def delete_application(application_id):
    application = _store.table("applications").get(application_id)
    if not application:
        return _not_found("application", application_id)
    if _store.table("users").find_one(
            lambda u: u["applicationId"] == application_id):
        return _api_error(422, "application.in_use",
                          "Users are still bound to this application.")
    _store.table("application_roles").delete_where(
        lambda r: r["applicationId"] == application_id)
    _store.table("applications").delete(application_id)
    return {"__status__": 204}


def list_resources():
    return _resources()


def get_resource_scopes(resource_id):
    if not _store.table("resources").get(resource_id):
        return _not_found("resource", resource_id)
    return [s for s in _scopes() if s["resourceId"] == resource_id]


# ---------------------------------------------------------------------------
# Management API: organizations
# ---------------------------------------------------------------------------

def list_organizations(page=1, page_size=20):
    return _paginate(_organizations(), page, page_size)


def get_organization(organization_id):
    organization = _store.table("organizations").get(organization_id)
    if not organization:
        return _not_found("organization", organization_id)
    return organization


def create_organization(payload):
    payload = payload or {}
    if not payload.get("name"):
        return _api_error(422, "guard.invalid_input", "name is required.")
    organization = {
        "id": _logto_id("org"), "name": payload["name"],
        "description": payload.get("description", ""),
        "isMfaRequired": bool(payload.get("isMfaRequired", False)),
        "customData": payload.get("customData") or {}, "createdAt": _now_ms(),
    }
    _store_insert("organizations", organization)
    return organization


def delete_organization(organization_id):
    if not _store.table("organizations").get(organization_id):
        return _not_found("organization", organization_id)
    _store.table("organization_memberships").delete_where(
        lambda m: m["organizationId"] == organization_id)
    _store.table("organizations").delete(organization_id)
    return {"__status__": 204}


def list_organization_users(organization_id):
    if not _store.table("organizations").get(organization_id):
        return _not_found("organization", organization_id)
    by_id = {r["id"]: r for r in _organization_roles()}
    members = []
    for membership in _memberships():
        if membership["organizationId"] != organization_id:
            continue
        user = _store.table("users").get(membership["userId"])
        if not user:
            continue
        members.append({
            **public_user(user),
            "organizationRoles": [{"id": r, "name": by_id[r]["name"]}
                                  for r in membership["roleIds"] if r in by_id],
        })
    return members


def add_organization_users(organization_id, user_ids=None):
    if not _store.table("organizations").get(organization_id):
        return _not_found("organization", organization_id)
    for user_id in (user_ids or []):
        if not _store.table("users").get(user_id):
            return _not_found("user", user_id)
        if _store.table("organization_memberships").find_one(
                lambda m: m["organizationId"] == organization_id
                and m["userId"] == user_id):
            continue
        next_id = max((m["id"] for m in _memberships()), default=0) + 1
        _store_insert("organization_memberships", {
            "id": next_id, "organizationId": organization_id,
            "userId": user_id, "roleIds": [], "joinedAt": _now_ms()})
    return {"__status__": 201}


def remove_organization_user(organization_id, user_id):
    if not _store.table("organizations").get(organization_id):
        return _not_found("organization", organization_id)
    removed = _store.table("organization_memberships").delete_where(
        lambda m: m["organizationId"] == organization_id
        and m["userId"] == user_id)
    if not removed:
        return _not_found("organization membership", user_id)
    return {"__status__": 204}


def set_organization_user_roles(organization_id, user_id,
                                organization_role_ids=None):
    membership = _store.table("organization_memberships").find_one(
        lambda m: m["organizationId"] == organization_id
        and m["userId"] == user_id)
    if not membership:
        return _not_found("organization membership", user_id)
    for role_id in (organization_role_ids or []):
        if not _store.table("organization_roles").get(role_id):
            return _not_found("organization role", role_id)
    _store.table("organization_memberships").patch(
        membership["id"], {"roleIds": list(organization_role_ids or [])})
    return {"__status__": 201}


def list_organization_roles():
    by_id = {s["id"]: s for s in _organization_scopes()}
    return [{**r, "scopes": [by_id[s]["name"] for s in r["scopeIds"]
                             if s in by_id]} for r in _organization_roles()]


def list_organization_scopes():
    return _organization_scopes()


def list_user_organizations(user_id):
    if not _store.table("users").get(user_id):
        return _not_found("user", user_id)
    by_role = {r["id"]: r for r in _organization_roles()}
    out = []
    for membership in _memberships():
        if membership["userId"] != user_id:
            continue
        organization = _store.table("organizations").get(
            membership["organizationId"])
        if not organization:
            continue
        out.append({**organization,
                    "organizationRoles": [{"id": r, "name": by_role[r]["name"]}
                                          for r in membership["roleIds"]
                                          if r in by_role]})
    return out


# ---------------------------------------------------------------------------
# Management API: connectors, sign-in experience, dashboard
# ---------------------------------------------------------------------------

def list_connectors(connector_type=None):
    rows = _connectors()
    if connector_type:
        rows = [c for c in rows if c["type"] == connector_type]
    return rows


def get_connector(connector_id):
    connector = _store.table("connectors").get(connector_id)
    if not connector:
        return _not_found("connector", connector_id)
    return connector


def sign_in_experience():
    return _store.document("sign_in_experience").get()


def update_sign_in_experience(payload):
    document = _store.document("sign_in_experience")
    merged = {**document.get(), **(payload or {})}
    document.set(merged)
    return merged


def dashboard_totals():
    users = _users()
    return {"totalUserCount": len(users),
            "suspendedUserCount": len([u for u in users if u["isSuspended"]]),
            "applicationCount": len(_applications()),
            "organizationCount": len(_organizations()),
            "roleCount": len(_roles()),
            "activeTokenCount": len([t for t in
                                     _store.table("access_tokens").rows()
                                     if not t["revoked"]])}


_store.eager_load()
