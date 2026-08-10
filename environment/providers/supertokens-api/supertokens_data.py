"""Data access module for the SuperTokens Core mock service.

Models the SuperTokens **core**, not an SDK: the thing a backend SDK talks to
over HTTP with an `api-key` header. Two properties shape everything here.

First, the core reports domain outcomes in the *body*, not the status line. A
wrong password is `200 {"status": "WRONG_CREDENTIALS_ERROR"}`, not a 401. HTTP
statuses are reserved for transport-level problems: a missing API key (401), an
unsupported CDI version (400) and an unknown tenant path (404).

Second, everything is scoped to a tenant: `/appid-<appId>/<tenantId>/recipe/...`.
The two seeded tenants deliberately enable different recipes, so the same
request succeeds on one and returns `TENANT_NOT_FOUND_ERROR` or a recipe-disabled
status on the other.

Recipes covered: emailpassword, thirdparty, passwordless, session, emailverification,
usermetadata, userroles, multitenancy and account linking. Passwords are verified
as `sha256(passwordSalt + password)`; the hash is never returned. Mutations are
held in process memory and reset on restart.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("supertokens-api")
_API = "supertokens-api"

CDI_VERSIONS = ["3.0", "4.0", "5.0", "5.1", "5.2"]
CORE_VERSION = "9.2.2"
API_KEY = "orbit-labs-supertokens-core-key"
DEFAULT_APP_ID = "public"
DEFAULT_TENANT = "public"


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

    SuperTokens carries free-form JSON in `userDataInJWT`, `metadata` and the
    per-tenant `coreConfig`; the seed keeps them flat so a CSV overlay can
    shadow the JSON.
    """
    out = {}
    for part in _semi_list(row, column):
        key, _, value = part.partition("=")
        if not key:
            continue
        out[key] = _maybe_number(value)
    return out


def _maybe_number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


_store.register("tenants", primary_key="tenantId",
                initial_loader=lambda: _coerce_tenants(_load("tenants.json", "tenants")))
_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json", "users")))
_store.register("login_methods", primary_key="recipeUserId",
                initial_loader=lambda: _coerce_login_methods(
                    _load("login_methods.json", "login_methods")))
_store.register("sessions", primary_key="sessionHandle",
                initial_loader=lambda: _coerce_sessions(
                    _load("sessions.json", "sessions")))
_store.register("refresh_tokens", primary_key="token",
                initial_loader=lambda: _coerce_flags(
                    _load("refresh_tokens.json", "refresh_tokens"), ("used",),
                    ints=("createdTime",)))
_store.register("password_reset_tokens", primary_key="token",
                initial_loader=lambda: _coerce_flags(
                    _load("password_reset_tokens.json", "password_reset_tokens"),
                    ("used",), ints=("tokenExpiry",)))
_store.register("email_verification_tokens", primary_key="token",
                initial_loader=lambda: _coerce_flags(
                    _load("email_verification_tokens.json",
                          "email_verification_tokens"),
                    ("used",), ints=("tokenExpiry",)))
_store.register("passwordless_devices", primary_key="deviceId",
                initial_loader=lambda: _coerce_ints(
                    _load("passwordless_devices.json", "passwordless_devices"),
                    ("failedAttempts", "createdAt")))
_store.register("passwordless_codes", primary_key="codeId",
                initial_loader=lambda: _coerce_ints(
                    _load("passwordless_codes.json", "passwordless_codes"),
                    ("createdAt", "expiresAt")))
_store.register("roles", primary_key="role",
                initial_loader=lambda: [
                    {**_strip_ctx(r), "permissions": _semi_list(r, "permissions")}
                    for r in _load("roles.json", "roles")])
_store.register("user_roles", primary_key="id",
                initial_loader=lambda: _coerce_ints(
                    _load("user_roles.json", "user_roles"), ("id",)))
_store.register("user_metadata", primary_key="userId",
                initial_loader=lambda: [
                    {"userId": r["userId"], "metadata": _semi_map(r, "metadata")}
                    for r in _load("user_metadata.json", "user_metadata")])


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def _coerce_tenants(rows):
    return [{
        "tenantId": r["tenantId"], "appId": r["appId"],
        "emailPassword": {"enabled": opt_str(r, "emailPasswordEnabled",
                                             default="0") == "1"},
        "thirdParty": {"enabled": opt_str(r, "thirdPartyEnabled",
                                          default="0") == "1",
                       "providers": _semi_list(r, "providers")},
        "passwordless": {"enabled": opt_str(r, "passwordlessEnabled",
                                            default="0") == "1",
                         "flowType": opt_str(r, "passwordlessFlowType", default=""),
                         "contactMethod": opt_str(r, "passwordlessContactMethod",
                                                  default="")},
        "firstFactors": _semi_list(r, "firstFactors"),
        "requiredSecondaryFactors": _semi_list(r, "requiredSecondaryFactors"),
        "coreConfig": _semi_map(r, "coreConfig"),
        "created": r["created"],
    } for r in rows]


def _coerce_users(rows):
    return [{"id": r["id"],
             "isPrimaryUser": opt_str(r, "isPrimaryUser", default="0") == "1",
             "timeJoined": opt_int(r, "timeJoined", default=0),
             "primaryTenant": r["primaryTenant"],
             "note": opt_str(r, "note", default="")} for r in rows]


def _coerce_login_methods(rows):
    return [{**_strip_ctx(r),
             "tenantIds": _semi_list(r, "tenantIds"),
             "verified": opt_str(r, "verified", default="0") == "1",
             "timeJoined": opt_int(r, "timeJoined", default=0)} for r in rows]


def _coerce_sessions(rows):
    return [{**_strip_ctx(r),
             "userDataInJWT": _semi_map(r, "userDataInJWT"),
             "userDataInDatabase": _semi_map(r, "userDataInDatabase"),
             "revoked": opt_str(r, "revoked", default="0") == "1",
             "createdTime": opt_int(r, "createdTime", default=0),
             "expiry": opt_int(r, "expiry", default=0)} for r in rows]


def _coerce_flags(rows, flags, ints=()):
    return [{**_strip_ctx(r),
             **{f: bool(opt_int(r, f, default=0)) for f in flags},
             **{f: opt_int(r, f, default=0) for f in ints}} for r in rows]


def _coerce_ints(rows, ints):
    return [{**_strip_ctx(r), **{f: opt_int(r, f, default=0) for f in ints}}
            for r in rows]


# ---------------------------------------------------------------------------
# Table accessors
# ---------------------------------------------------------------------------

def _tenants():
    return _store.table("tenants").rows()


def _users():
    return _store.table("users").rows()


def _login_methods():
    return _store.table("login_methods").rows()


def _sessions():
    return _store.table("sessions").rows()


def _roles():
    return _store.table("roles").rows()


def _user_roles():
    return _store.table("user_roles").rows()


def _now_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def _new_id():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Transport-level errors
#
# These are the only cases the core answers with a non-2xx status; every domain
# outcome rides in the body as a `status` string.
# ---------------------------------------------------------------------------

def _http_error(code, message):
    return {"error": message, "code": code, "message": message}


def check_api_key(api_key):
    """The core rejects a missing or wrong `api-key` header with 401."""
    if not api_key:
        return _http_error(401, "Invalid API key")
    if api_key != API_KEY:
        return _http_error(401, "Invalid API key")
    return None


def check_cdi_version(cdi_version):
    if cdi_version and cdi_version not in CDI_VERSIONS:
        return _http_error(400, f"cdi-version {cdi_version} not supported")
    return None


def resolve_tenant(tenant_id=None):
    tenant = _store.table("tenants").get(tenant_id or DEFAULT_TENANT)
    if not tenant:
        return None, _http_error(404, f"Tenant with id {tenant_id} does not exist")
    return tenant, None


# ---------------------------------------------------------------------------
# Service metadata
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def hello():
    """The core's own liveness probe; it answers with the literal text Hello."""
    return "Hello"


def api_version():
    return {"versions": CDI_VERSIONS}


def config():
    return {"status": "OK", "path": "/usr/lib/supertokens/config.yaml"}


# ---------------------------------------------------------------------------
# User projection
# ---------------------------------------------------------------------------

def _public_login_method(method):
    body = {
        "recipeId": method["recipeId"],
        "recipeUserId": method["recipeUserId"],
        "tenantIds": method["tenantIds"],
        "timeJoined": method["timeJoined"],
        "verified": method["verified"],
    }
    if method["email"]:
        body["email"] = method["email"]
    if method["phoneNumber"]:
        body["phoneNumber"] = method["phoneNumber"]
    if method["thirdPartyId"]:
        body["thirdParty"] = {"id": method["thirdPartyId"],
                              "userId": method["thirdPartyUserId"]}
    return body


def public_user(user):
    """The account-linking-era user object: a primary user plus its login methods."""
    if not user:
        return None
    methods = [m for m in _login_methods() if m["userId"] == user["id"]]
    emails = sorted({m["email"] for m in methods if m["email"]})
    phones = sorted({m["phoneNumber"] for m in methods if m["phoneNumber"]})
    tenants = sorted({t for m in methods for t in m["tenantIds"]})
    return {
        "id": user["id"],
        "isPrimaryUser": user["isPrimaryUser"],
        "timeJoined": user["timeJoined"],
        "tenantIds": tenants,
        "emails": emails,
        "phoneNumbers": phones,
        "thirdParty": [{"id": m["thirdPartyId"], "userId": m["thirdPartyUserId"]}
                       for m in methods if m["thirdPartyId"]],
        "loginMethods": [_public_login_method(m) for m in methods],
    }


def _user_of_method(method):
    return _store.table("users").get(method["userId"])


def _find_method(tenant_id, recipe_id, email=None, phone=None,
                 third_party_id=None, third_party_user_id=None):
    for method in _login_methods():
        if method["recipeId"] != recipe_id or tenant_id not in method["tenantIds"]:
            continue
        if email is not None and method["email"].lower() != str(email).lower():
            continue
        if phone is not None and method["phoneNumber"] != phone:
            continue
        if third_party_id is not None and method["thirdPartyId"] != third_party_id:
            continue
        if (third_party_user_id is not None
                and method["thirdPartyUserId"] != str(third_party_user_id)):
            continue
        return method
    return None


# ---------------------------------------------------------------------------
# emailpassword
# ---------------------------------------------------------------------------

def email_password_signup(tenant, email=None, password=None):
    if not tenant["emailPassword"]["enabled"]:
        return {"status": "EMAIL_PASSWORD_NOT_ENABLED_ERROR"}
    if not email or not password:
        return _http_error(400, "Field name 'email' and 'password' are invalid "
                                "in JSON input")
    if _find_method(tenant["tenantId"], "emailpassword", email=email):
        return {"status": "EMAIL_ALREADY_EXISTS_ERROR"}
    now = _now_ms()
    user_id = _new_id()
    salt = uuid.uuid4().hex[:16]
    _store_insert("users", {"id": user_id, "isPrimaryUser": False,
                            "timeJoined": now,
                            "primaryTenant": tenant["tenantId"], "note": ""})
    _store.table("login_methods").upsert({
        "recipeUserId": user_id, "userId": user_id, "recipeId": "emailpassword",
        "tenantIds": [tenant["tenantId"]], "email": email, "phoneNumber": "",
        "thirdPartyId": "", "thirdPartyUserId": "", "passwordSalt": salt,
        "passwordHash": _hash_password(salt, password), "verified": False,
        "timeJoined": now})
    return {"status": "OK", "user": public_user(_store.table("users").get(user_id)),
            "recipeUserId": user_id}


def email_password_signin(tenant, email=None, password=None):
    if not tenant["emailPassword"]["enabled"]:
        return {"status": "EMAIL_PASSWORD_NOT_ENABLED_ERROR"}
    method = _find_method(tenant["tenantId"], "emailpassword", email=email)
    # An unknown email and a wrong password are the same status, so the response
    # cannot be used to enumerate accounts.
    if not method or _hash_password(method["passwordSalt"], password or "") \
            != method["passwordHash"]:
        return {"status": "WRONG_CREDENTIALS_ERROR"}
    return {"status": "OK", "user": public_user(_user_of_method(method)),
            "recipeUserId": method["recipeUserId"]}


def email_password_get_user(tenant, user_id=None, email=None):
    if user_id:
        method = _store.table("login_methods").get(user_id)
        if not method or method["recipeId"] != "emailpassword":
            return {"status": "UNKNOWN_USER_ID_ERROR"}
    else:
        method = _find_method(tenant["tenantId"], "emailpassword", email=email)
        if not method:
            return {"status": "UNKNOWN_EMAIL_ERROR"}
    return {"status": "OK", "user": public_user(_user_of_method(method)),
            "recipeUserId": method["recipeUserId"]}


def email_password_update_user(recipe_user_id=None, email=None, password=None):
    method = _store.table("login_methods").get(recipe_user_id) \
        if recipe_user_id else None
    if not method or method["recipeId"] != "emailpassword":
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    patch = {}
    if email and email.lower() != method["email"].lower():
        for tenant_id in method["tenantIds"]:
            if _find_method(tenant_id, "emailpassword", email=email):
                return {"status": "EMAIL_ALREADY_EXISTS_ERROR"}
        patch["email"] = email
        # A new address starts unverified, exactly as the core does.
        patch["verified"] = False
    if password:
        salt = uuid.uuid4().hex[:16]
        patch["passwordSalt"] = salt
        patch["passwordHash"] = _hash_password(salt, password)
    if not patch:
        return {"status": "OK"}
    _store.table("login_methods").patch(recipe_user_id, patch)
    if password:
        # Changing a password revokes every session the recipe user holds.
        _revoke_sessions(lambda s: s["recipeUserId"] == recipe_user_id)
    return {"status": "OK"}


def password_reset_token(tenant, user_id=None):
    method = _store.table("login_methods").get(user_id) if user_id else None
    if not method or method["recipeId"] != "emailpassword":
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    token = f"st-pwreset-{uuid.uuid4().hex[:16]}"
    _store.table("password_reset_tokens").upsert({
        "token": token, "userId": method["recipeUserId"],
        "email": method["email"], "tenantId": tenant["tenantId"], "used": False,
        "tokenExpiry": _now_ms()
        + tenant["coreConfig"].get("password_reset_token_lifetime", 3600000)})
    return {"status": "OK", "token": token}


def password_reset(tenant, method="token", token=None, new_password=None):
    if method != "token":
        return _http_error(400, "Field name 'method' is invalid in JSON input")
    record = _store.table("password_reset_tokens").get(token) if token else None
    if (not record or record["used"] or record["tenantId"] != tenant["tenantId"]
            or record["tokenExpiry"] < _now_ms()):
        return {"status": "RESET_PASSWORD_INVALID_TOKEN_ERROR"}
    if not new_password:
        return _http_error(400, "Field name 'newPassword' is invalid in JSON input")
    _store.table("password_reset_tokens").patch(token, {"used": True})
    salt = uuid.uuid4().hex[:16]
    _store.table("login_methods").patch(record["userId"], {
        "passwordSalt": salt, "passwordHash": _hash_password(salt, new_password)})
    _revoke_sessions(lambda s: s["recipeUserId"] == record["userId"])
    return {"status": "OK", "userId": record["userId"], "email": record["email"]}


# ---------------------------------------------------------------------------
# thirdparty
# ---------------------------------------------------------------------------

def third_party_signinup(tenant, third_party_id=None, third_party_user_id=None,
                         email=None):
    if not tenant["thirdParty"]["enabled"]:
        return {"status": "THIRD_PARTY_NOT_ENABLED_ERROR"}
    if not third_party_id or not third_party_user_id:
        return _http_error(400, "Field name 'thirdPartyId' and "
                                "'thirdPartyUserId' are invalid in JSON input")
    if third_party_id not in tenant["thirdParty"]["providers"]:
        return {"status": "UNKNOWN_PROVIDER_ERROR"}
    method = _find_method(tenant["tenantId"], "thirdparty",
                          third_party_id=third_party_id,
                          third_party_user_id=third_party_user_id)
    if method:
        if email and email.lower() != method["email"].lower():
            _store.table("login_methods").patch(method["recipeUserId"],
                                                {"email": email})
            method = _store.table("login_methods").get(method["recipeUserId"])
        return {"status": "OK", "createdNewUser": False,
                "user": public_user(_user_of_method(method)),
                "recipeUserId": method["recipeUserId"]}
    now = _now_ms()
    user_id = _new_id()
    _store_insert("users", {"id": user_id, "isPrimaryUser": False,
                            "timeJoined": now,
                            "primaryTenant": tenant["tenantId"], "note": ""})
    _store.table("login_methods").upsert({
        "recipeUserId": user_id, "userId": user_id, "recipeId": "thirdparty",
        "tenantIds": [tenant["tenantId"]], "email": email or "",
        "phoneNumber": "", "thirdPartyId": third_party_id,
        "thirdPartyUserId": str(third_party_user_id), "passwordSalt": "",
        "passwordHash": "", "verified": True, "timeJoined": now})
    return {"status": "OK", "createdNewUser": True,
            "user": public_user(_store.table("users").get(user_id)),
            "recipeUserId": user_id}


def third_party_get_user(tenant, third_party_id=None, third_party_user_id=None,
                         user_id=None):
    if user_id:
        method = _store.table("login_methods").get(user_id)
        if not method or method["recipeId"] != "thirdparty":
            return {"status": "UNKNOWN_USER_ID_ERROR"}
    else:
        method = _find_method(tenant["tenantId"], "thirdparty",
                              third_party_id=third_party_id,
                              third_party_user_id=third_party_user_id)
        if not method:
            return {"status": "UNKNOWN_USER_ID_ERROR"}
    return {"status": "OK", "user": public_user(_user_of_method(method)),
            "recipeUserId": method["recipeUserId"]}


# ---------------------------------------------------------------------------
# passwordless
# ---------------------------------------------------------------------------

MAX_CODE_ATTEMPTS = 5


def passwordless_create_code(tenant, email=None, phone_number=None,
                             user_input_code=None):
    if not tenant["passwordless"]["enabled"]:
        return {"status": "PASSWORDLESS_NOT_ENABLED_ERROR"}
    if not email and not phone_number:
        return _http_error(400, "Please provide exactly one of email or "
                                "phoneNumber")
    now = _now_ms()
    device_id = f"st-device-{uuid.uuid4().hex[:12]}"
    pre_auth = f"st-preauth-{uuid.uuid4().hex[:12]}"
    code_id = f"st-code-{uuid.uuid4().hex[:10]}"
    code = user_input_code or _digits(code_id, 6)
    lifetime = 900000
    _store_insert("passwordless_devices", {
        "deviceId": device_id, "preAuthSessionId": pre_auth,
        "tenantId": tenant["tenantId"], "email": email or "",
        "phoneNumber": phone_number or "", "failedAttempts": 0,
        "createdAt": now})
    _store_insert("passwordless_codes", {
        "codeId": code_id, "deviceId": device_id, "preAuthSessionId": pre_auth,
        "linkCode": f"st-link-{uuid.uuid4().hex[:16]}", "userInputCode": code,
        "createdAt": now, "expiresAt": now + lifetime})
    record = _store.table("passwordless_codes").get(code_id)
    return {"status": "OK", "preAuthSessionId": pre_auth, "codeId": code_id,
            "deviceId": device_id, "userInputCode": record["userInputCode"],
            "linkCode": record["linkCode"], "timeCreated": now,
            "codeLifetime": lifetime}


def _digits(seed, length):
    """Derive a stable numeric code from a seed string.

    `hash()` is salted per process, so codes derived from it would differ across
    restarts.
    """
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    return str(int(digest[:12], 16)).zfill(length)[-length:]


def passwordless_consume_code(tenant, pre_auth_session_id=None, link_code=None,
                              device_id=None, user_input_code=None):
    if not tenant["passwordless"]["enabled"]:
        return {"status": "PASSWORDLESS_NOT_ENABLED_ERROR"}
    device = _store.table("passwordless_devices").find_one(
        lambda d: d["preAuthSessionId"] == pre_auth_session_id
        and d["tenantId"] == tenant["tenantId"]) if pre_auth_session_id else None
    if not device:
        return {"status": "RESTART_FLOW_ERROR"}
    code = _store.table("passwordless_codes").find_one(
        lambda c: c["preAuthSessionId"] == pre_auth_session_id)
    if not code:
        return {"status": "RESTART_FLOW_ERROR"}
    if code["expiresAt"] < _now_ms():
        return {"status": "EXPIRED_USER_INPUT_CODE_ERROR",
                "failedCodeInputAttemptCount": device["failedAttempts"],
                "maximumCodeInputAttempts": MAX_CODE_ATTEMPTS}
    if link_code is not None:
        if link_code != code["linkCode"]:
            return {"status": "RESTART_FLOW_ERROR"}
    else:
        if device_id and device_id != device["deviceId"]:
            return {"status": "RESTART_FLOW_ERROR"}
        if user_input_code != code["userInputCode"]:
            attempts = device["failedAttempts"] + 1
            if attempts >= MAX_CODE_ATTEMPTS:
                # Too many wrong guesses burns the device, as the core does.
                _store.table("passwordless_codes").delete_where(
                    lambda c: c["deviceId"] == device["deviceId"])
                _store.table("passwordless_devices").delete(device["deviceId"])
                return {"status": "RESTART_FLOW_ERROR"}
            _store.table("passwordless_devices").patch(
                device["deviceId"], {"failedAttempts": attempts})
            return {"status": "INCORRECT_USER_INPUT_CODE_ERROR",
                    "failedCodeInputAttemptCount": attempts,
                    "maximumCodeInputAttempts": MAX_CODE_ATTEMPTS}
    method = _find_method(tenant["tenantId"], "passwordless",
                          email=device["email"] or None,
                          phone=device["phoneNumber"] or None)
    created = False
    if not method:
        now = _now_ms()
        user_id = _new_id()
        created = True
        _store_insert("users", {"id": user_id, "isPrimaryUser": False,
                                "timeJoined": now,
                                "primaryTenant": tenant["tenantId"], "note": ""})
        _store.table("login_methods").upsert({
            "recipeUserId": user_id, "userId": user_id,
            "recipeId": "passwordless", "tenantIds": [tenant["tenantId"]],
            "email": device["email"], "phoneNumber": device["phoneNumber"],
            "thirdPartyId": "", "thirdPartyUserId": "", "passwordSalt": "",
            "passwordHash": "", "verified": True, "timeJoined": now})
        method = _store.table("login_methods").get(user_id)
    _store.table("passwordless_codes").delete_where(
        lambda c: c["deviceId"] == device["deviceId"])
    _store.table("passwordless_devices").delete(device["deviceId"])
    return {"status": "OK", "createdNewUser": created,
            "user": public_user(_user_of_method(method)),
            "recipeUserId": method["recipeUserId"]}


def passwordless_get_user(tenant, email=None, phone_number=None, user_id=None):
    if user_id:
        method = _store.table("login_methods").get(user_id)
        if not method or method["recipeId"] != "passwordless":
            return {"status": "UNKNOWN_USER_ID_ERROR"}
    else:
        method = _find_method(tenant["tenantId"], "passwordless", email=email,
                              phone=phone_number)
        if not method:
            return {"status": "UNKNOWN_USER_ID_ERROR"}
    return {"status": "OK", "user": public_user(_user_of_method(method)),
            "recipeUserId": method["recipeUserId"]}


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------

def _revoke_sessions(predicate):
    handles = [s["sessionHandle"] for s in _sessions() if predicate(s)]
    for handle in handles:
        _store.table("sessions").patch(handle, {"revoked": True})
        _store.table("refresh_tokens").delete_where(
            lambda t, h=handle: t["sessionHandle"] == h)
    return handles


def _session_response(session):
    return {
        "status": "OK",
        "session": {"handle": session["sessionHandle"],
                    "userId": session["userId"],
                    "recipeUserId": session["recipeUserId"],
                    "userDataInJWT": session["userDataInJWT"],
                    "tenantId": session["tenantId"]},
        "accessToken": {"token": session["accessToken"],
                        "expiry": session["expiry"],
                        "createdTime": session["createdTime"]},
        "refreshToken": {"token": session["refreshToken"],
                         "expiry": session["expiry"],
                         "createdTime": session["createdTime"]},
        "antiCsrfToken": session["antiCsrfToken"],
    }


def create_session(tenant, user_id=None, recipe_user_id=None,
                   user_data_in_jwt=None, user_data_in_database=None,
                   enable_anti_csrf=True):
    if not user_id:
        return _http_error(400, "Field name 'userId' is invalid in JSON input")
    user = _store.table("users").get(user_id)
    if not user:
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    now = _now_ms()
    handle = _new_id()
    session = {
        "sessionHandle": handle, "userId": user_id,
        "recipeUserId": recipe_user_id or user_id,
        "tenantId": tenant["tenantId"],
        "accessToken": f"st-at-{uuid.uuid4().hex[:16]}",
        "refreshToken": f"st-rt-{uuid.uuid4().hex[:16]}",
        "antiCsrfToken": f"st-csrf-{uuid.uuid4().hex[:8]}"
                         if enable_anti_csrf else "",
        "userDataInJWT": user_data_in_jwt or {},
        "userDataInDatabase": user_data_in_database or {},
        "revoked": False, "createdTime": now, "expiry": now + 100 * 24 * 3600 * 1000,
    }
    _store.table("sessions").upsert(session)
    _store.table("refresh_tokens").upsert({
        "token": session["refreshToken"], "sessionHandle": handle,
        "userId": user_id, "parent": "", "used": False, "createdTime": now})
    return _session_response(session)


def verify_session(access_token=None, anti_csrf_token=None,
                   do_anti_csrf_check=False):
    session = _store.table("sessions").find_one(
        lambda s: s["accessToken"] == access_token) if access_token else None
    if not session:
        return {"status": "UNAUTHORISED", "message": "Session does not exist."}
    if session["revoked"]:
        return {"status": "UNAUTHORISED", "message": "Session does not exist."}
    if session["expiry"] < _now_ms():
        # The core distinguishes "expired, go refresh" from "gone".
        return {"status": "TRY_REFRESH_TOKEN",
                "message": "Access token has expired. Please call the refresh "
                           "API."}
    if do_anti_csrf_check and session["antiCsrfToken"] \
            and anti_csrf_token != session["antiCsrfToken"]:
        return {"status": "TRY_REFRESH_TOKEN",
                "message": "anti-csrf check failed"}
    return {"status": "OK",
            "session": {"handle": session["sessionHandle"],
                        "userId": session["userId"],
                        "recipeUserId": session["recipeUserId"],
                        "userDataInJWT": session["userDataInJWT"],
                        "tenantId": session["tenantId"],
                        "expiryTime": session["expiry"]}}


def refresh_session(refresh_token=None, anti_csrf_token=None,
                    do_anti_csrf_check=False):
    record = _store.table("refresh_tokens").get(refresh_token) \
        if refresh_token else None
    if not record:
        return {"status": "UNAUTHORISED", "message": "Refresh token not found."}
    session = _store.table("sessions").get(record["sessionHandle"])
    if not session or session["revoked"]:
        return {"status": "UNAUTHORISED", "message": "Session does not exist."}
    if record["used"]:
        # A token that has already been rotated is being replayed: SuperTokens
        # treats that as theft, kills the session and names the victim.
        _revoke_sessions(lambda s: s["sessionHandle"] == record["sessionHandle"])
        return {"status": "TOKEN_THEFT_DETECTED",
                "session": {"handle": session["sessionHandle"],
                            "userId": session["userId"],
                            "recipeUserId": session["recipeUserId"]}}
    if do_anti_csrf_check and session["antiCsrfToken"] \
            and anti_csrf_token != session["antiCsrfToken"]:
        return {"status": "UNAUTHORISED", "message": "anti-csrf check failed"}
    now = _now_ms()
    rotated = f"st-rt-{uuid.uuid4().hex[:16]}"
    _store.table("refresh_tokens").patch(refresh_token, {"used": True})
    _store.table("refresh_tokens").upsert({
        "token": rotated, "sessionHandle": session["sessionHandle"],
        "userId": session["userId"], "parent": refresh_token, "used": False,
        "createdTime": now})
    updated = _store.table("sessions").patch(session["sessionHandle"], {
        "accessToken": f"st-at-{uuid.uuid4().hex[:16]}",
        "refreshToken": rotated, "createdTime": now})
    return _session_response(updated)


def remove_sessions(session_handles=None, user_id=None, tenant_id=None):
    if session_handles:
        wanted = set(session_handles)
        revoked = _revoke_sessions(lambda s: s["sessionHandle"] in wanted
                                   and not s["revoked"])
    elif user_id:
        revoked = _revoke_sessions(
            lambda s: s["userId"] == user_id and not s["revoked"]
            and (tenant_id is None or s["tenantId"] == tenant_id))
    else:
        return _http_error(400, "Field name 'sessionHandles' or 'userId' is "
                                "invalid in JSON input")
    return {"status": "OK", "sessionHandlesRevoked": revoked}


def user_sessions(tenant, user_id=None):
    handles = [s["sessionHandle"] for s in _sessions()
               if s["userId"] == user_id and not s["revoked"]
               and s["tenantId"] == tenant["tenantId"]]
    return {"status": "OK", "sessionHandles": handles}


def session_data(session_handle=None):
    session = _store.table("sessions").get(session_handle) \
        if session_handle else None
    if not session or session["revoked"]:
        return {"status": "UNAUTHORISED", "message": "Session does not exist."}
    return {"status": "OK", "userDataInDatabase": session["userDataInDatabase"]}


def update_session_data(session_handle=None, user_data_in_database=None):
    session = _store.table("sessions").get(session_handle) \
        if session_handle else None
    if not session or session["revoked"]:
        return {"status": "UNAUTHORISED", "message": "Session does not exist."}
    _store.table("sessions").patch(
        session_handle, {"userDataInDatabase": user_data_in_database or {}})
    return {"status": "OK"}


def jwks():
    """Static JWKS. The mock signs nothing, so the key is a stable placeholder."""
    return {"keys": [{"kty": "RSA", "kid": "s-orbit-labs-2026", "n":
                      "sT0rb1tL4bsMockPublicModulus_Ax9Qk3vZ", "e": "AQAB",
                      "alg": "RS256", "use": "sig"}]}


# ---------------------------------------------------------------------------
# emailverification
# ---------------------------------------------------------------------------

def email_verify_token(tenant, user_id=None, email=None):
    method = _store.table("login_methods").get(user_id) if user_id else None
    if not method:
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    if method["verified"]:
        return {"status": "EMAIL_ALREADY_VERIFIED_ERROR"}
    token = f"st-emailverify-{uuid.uuid4().hex[:16]}"
    _store.table("email_verification_tokens").upsert({
        "token": token, "userId": method["recipeUserId"],
        "email": email or method["email"], "tenantId": tenant["tenantId"],
        "used": False,
        "tokenExpiry": _now_ms()
        + tenant["coreConfig"].get("email_verification_token_lifetime", 86400000)})
    return {"status": "OK", "token": token}


def email_verify(tenant, method="token", token=None):
    if method != "token":
        return _http_error(400, "Field name 'method' is invalid in JSON input")
    record = _store.table("email_verification_tokens").get(token) if token else None
    if (not record or record["used"] or record["tenantId"] != tenant["tenantId"]
            or record["tokenExpiry"] < _now_ms()):
        return {"status": "EMAIL_VERIFICATION_INVALID_TOKEN_ERROR"}
    _store.table("email_verification_tokens").patch(token, {"used": True})
    _store.table("login_methods").patch(record["userId"], {"verified": True})
    return {"status": "OK", "userId": record["userId"], "email": record["email"]}


def email_is_verified(user_id=None, email=None):
    method = _store.table("login_methods").get(user_id) if user_id else None
    if not method:
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    return {"status": "OK", "isVerified": method["verified"]}


# ---------------------------------------------------------------------------
# usermetadata
# ---------------------------------------------------------------------------

def get_metadata(user_id=None):
    record = _store.table("user_metadata").get(user_id) if user_id else None
    return {"status": "OK", "metadata": record["metadata"] if record else {}}


def put_metadata(user_id=None, metadata_update=None):
    if not user_id:
        return _http_error(400, "Field name 'userId' is invalid in JSON input")
    record = _store.table("user_metadata").get(user_id)
    merged = dict(record["metadata"]) if record else {}
    for key, value in (metadata_update or {}).items():
        # A null clears the key -- the core's shallow-merge semantics.
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    _store.table("user_metadata").upsert({"userId": user_id, "metadata": merged})
    return {"status": "OK", "metadata": merged}


def remove_metadata(user_id=None):
    _store.table("user_metadata").delete(user_id)
    return {"status": "OK"}


# ---------------------------------------------------------------------------
# userroles
# ---------------------------------------------------------------------------

def put_role(role=None, permissions=None):
    if not role:
        return _http_error(400, "Field name 'role' is invalid in JSON input")
    existing = _store.table("roles").get(role)
    merged = sorted(set(existing["permissions"] if existing else [])
                    | set(permissions or []))
    _store.table("roles").upsert({"role": role, "permissions": merged})
    return {"status": "OK", "createdNewRole": existing is None}


def list_roles():
    return {"status": "OK", "roles": [r["role"] for r in _roles()]}


def role_permissions(role=None):
    record = _store.table("roles").get(role) if role else None
    if not record:
        return {"status": "UNKNOWN_ROLE_ERROR"}
    return {"status": "OK", "permissions": record["permissions"]}


def remove_role(role=None):
    record = _store.table("roles").get(role) if role else None
    if not record:
        return {"status": "OK", "didRoleExist": False}
    _store.table("user_roles").delete_where(lambda r: r["role"] == role)
    _store.table("roles").delete(role)
    return {"status": "OK", "didRoleExist": True}


def add_user_role(tenant, user_id=None, role=None):
    if not _store.table("roles").get(role):
        return {"status": "UNKNOWN_ROLE_ERROR"}
    existing = _store.table("user_roles").find_one(
        lambda r: r["userId"] == user_id and r["role"] == role
        and r["tenantId"] == tenant["tenantId"])
    if existing:
        return {"status": "OK", "didUserAlreadyHaveRole": True}
    next_id = max((r["id"] for r in _user_roles()), default=0) + 1
    _store_insert("user_roles", {"id": next_id, "userId": user_id,
                                 "tenantId": tenant["tenantId"], "role": role})
    return {"status": "OK", "didUserAlreadyHaveRole": False}


def get_user_roles(tenant, user_id=None):
    return {"status": "OK",
            "roles": sorted(r["role"] for r in _user_roles()
                            if r["userId"] == user_id
                            and r["tenantId"] == tenant["tenantId"])}


def remove_user_role(tenant, user_id=None, role=None):
    if not _store.table("roles").get(role):
        return {"status": "UNKNOWN_ROLE_ERROR"}
    removed = _store.table("user_roles").delete_where(
        lambda r: r["userId"] == user_id and r["role"] == role
        and r["tenantId"] == tenant["tenantId"])
    return {"status": "OK", "didUserHaveRole": bool(removed)}


def role_users(tenant, role=None):
    if not _store.table("roles").get(role):
        return {"status": "UNKNOWN_ROLE_ERROR"}
    return {"status": "OK",
            "users": [r["userId"] for r in _user_roles()
                      if r["role"] == role and r["tenantId"] == tenant["tenantId"]]}


# ---------------------------------------------------------------------------
# multitenancy
# ---------------------------------------------------------------------------

def _tenant_config(tenant):
    return {
        "tenantId": tenant["tenantId"],
        "emailPassword": tenant["emailPassword"],
        "thirdParty": tenant["thirdParty"],
        "passwordless": tenant["passwordless"],
        "firstFactors": tenant["firstFactors"],
        "requiredSecondaryFactors": tenant["requiredSecondaryFactors"],
        "coreConfig": tenant["coreConfig"],
    }


def list_tenants():
    return {"status": "OK", "tenants": [_tenant_config(t) for t in _tenants()]}


def get_tenant(tenant):
    return {"status": "OK", **_tenant_config(tenant)}


def put_tenant(tenant_id=None, email_password_enabled=None,
               third_party_enabled=None, passwordless_enabled=None,
               first_factors=None):
    if not tenant_id:
        return _http_error(400, "Field name 'tenantId' is invalid in JSON input")
    existing = _store.table("tenants").get(tenant_id)
    created = existing is None
    tenant = existing or {
        "tenantId": tenant_id, "appId": DEFAULT_APP_ID,
        "emailPassword": {"enabled": False},
        "thirdParty": {"enabled": False, "providers": []},
        "passwordless": {"enabled": False, "flowType": "", "contactMethod": ""},
        "firstFactors": [], "requiredSecondaryFactors": [], "coreConfig": {},
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tenant = dict(tenant)
    if email_password_enabled is not None:
        tenant["emailPassword"] = {"enabled": bool(email_password_enabled)}
    if third_party_enabled is not None:
        tenant["thirdParty"] = {**tenant["thirdParty"],
                                "enabled": bool(third_party_enabled)}
    if passwordless_enabled is not None:
        tenant["passwordless"] = {**tenant["passwordless"],
                                  "enabled": bool(passwordless_enabled)}
    if first_factors is not None:
        tenant["firstFactors"] = list(first_factors)
    _store.table("tenants").upsert(tenant)
    return {"status": "OK", "createdNew": created}


def remove_tenant(tenant_id=None):
    if tenant_id == DEFAULT_TENANT:
        # The core refuses to delete the public tenant.
        return _http_error(403, "Cannot delete public tenant")
    if not _store.table("tenants").get(tenant_id):
        return {"status": "OK", "didExist": False}
    _store.table("tenants").delete(tenant_id)
    return {"status": "OK", "didExist": True}


def associate_user_to_tenant(tenant, recipe_user_id=None):
    method = _store.table("login_methods").get(recipe_user_id) \
        if recipe_user_id else None
    if not method:
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    if tenant["tenantId"] in method["tenantIds"]:
        return {"status": "OK", "wasAlreadyAssociated": True}
    if method["recipeId"] == "emailpassword" and _find_method(
            tenant["tenantId"], "emailpassword", email=method["email"]):
        return {"status": "EMAIL_ALREADY_EXISTS_ERROR"}
    _store.table("login_methods").patch(
        recipe_user_id, {"tenantIds": method["tenantIds"] + [tenant["tenantId"]]})
    return {"status": "OK", "wasAlreadyAssociated": False}


# ---------------------------------------------------------------------------
# account linking
# ---------------------------------------------------------------------------

def make_primary_user(recipe_user_id=None):
    method = _store.table("login_methods").get(recipe_user_id) \
        if recipe_user_id else None
    if not method:
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    user = _store.table("users").get(method["userId"])
    if user and user["isPrimaryUser"]:
        return {"status": "OK", "wasAlreadyAPrimaryUser": True,
                "user": public_user(user)}
    if method["userId"] != recipe_user_id:
        return {"status": "RECIPE_USER_ID_ALREADY_LINKED_WITH_PRIMARY_USER_ID_ERROR",
                "primaryUserId": method["userId"]}
    updated = _store.table("users").patch(recipe_user_id, {"isPrimaryUser": True})
    return {"status": "OK", "wasAlreadyAPrimaryUser": False,
            "user": public_user(updated)}


def link_accounts(recipe_user_id=None, primary_user_id=None):
    method = _store.table("login_methods").get(recipe_user_id) \
        if recipe_user_id else None
    primary = _store.table("users").get(primary_user_id) if primary_user_id else None
    if not method or not primary:
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    if not primary["isPrimaryUser"]:
        return {"status": "INPUT_USER_IS_NOT_A_PRIMARY_USER"}
    if method["userId"] == primary_user_id:
        return {"status": "OK", "accountsAlreadyLinked": True,
                "user": public_user(primary)}
    if method["userId"] != recipe_user_id:
        return {"status": "RECIPE_USER_ID_ALREADY_LINKED_WITH_PRIMARY_USER_ID_ERROR",
                "primaryUserId": method["userId"]}
    _store.table("login_methods").patch(recipe_user_id,
                                        {"userId": primary_user_id})
    # The absorbed recipe user is no longer a user in its own right.
    _store.table("users").delete(recipe_user_id)
    return {"status": "OK", "accountsAlreadyLinked": False,
            "user": public_user(_store.table("users").get(primary_user_id))}


def unlink_account(recipe_user_id=None):
    method = _store.table("login_methods").get(recipe_user_id) \
        if recipe_user_id else None
    if not method:
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    if method["userId"] == recipe_user_id:
        return {"status": "OK", "wasRecipeUserDeleted": False,
                "wasLinked": False}
    _store.table("login_methods").patch(recipe_user_id,
                                        {"userId": recipe_user_id})
    _store_insert("users", {"id": recipe_user_id, "isPrimaryUser": False,
                            "timeJoined": method["timeJoined"],
                            "primaryTenant": method["tenantIds"][0]
                            if method["tenantIds"] else DEFAULT_TENANT,
                            "note": ""})
    return {"status": "OK", "wasRecipeUserDeleted": False, "wasLinked": True}


# ---------------------------------------------------------------------------
# user listing
# ---------------------------------------------------------------------------

def list_users(tenant, limit=100, pagination_token=None, include_recipe_ids=None,
               email=None):
    rows = [u for u in _users()
            if any(tenant["tenantId"] in m["tenantIds"]
                   for m in _login_methods() if m["userId"] == u["id"])]
    if include_recipe_ids:
        wanted = set(include_recipe_ids)
        rows = [u for u in rows
                if any(m["recipeId"] in wanted for m in _login_methods()
                       if m["userId"] == u["id"])]
    if email:
        needle = str(email).lower()
        rows = [u for u in rows
                if any(needle in m["email"].lower() for m in _login_methods()
                       if m["userId"] == u["id"] and m["email"])]
    rows.sort(key=lambda u: u["timeJoined"])
    start = 0
    if pagination_token:
        ids = [u["id"] for u in rows]
        start = ids.index(pagination_token) if pagination_token in ids else 0
    limit = max(1, min(int(limit or 100), 500))
    page = rows[start:start + limit]
    next_token = rows[start + limit]["id"] if start + limit < len(rows) else None
    body = {"status": "OK", "users": [public_user(u) for u in page]}
    if next_token:
        body["nextPaginationToken"] = next_token
    return body


def count_users(tenant, include_all_tenants=False):
    if include_all_tenants:
        return {"status": "OK", "count": len(_users())}
    return {"status": "OK",
            "count": len([u for u in _users()
                          if any(tenant["tenantId"] in m["tenantIds"]
                                 for m in _login_methods()
                                 if m["userId"] == u["id"])])}


def get_user_by_id(user_id=None):
    user = _store.table("users").get(user_id) if user_id else None
    if not user:
        return {"status": "UNKNOWN_USER_ID_ERROR"}
    return {"status": "OK", "user": public_user(user)}


def delete_user(user_id=None, remove_all_linked_accounts=True):
    user = _store.table("users").get(user_id) if user_id else None
    if not user:
        # The core is idempotent here: deleting an unknown user is still OK.
        return {"status": "OK"}
    _revoke_sessions(lambda s: s["userId"] == user_id)
    if remove_all_linked_accounts:
        _store.table("login_methods").delete_where(
            lambda m: m["userId"] == user_id)
    else:
        _store.table("login_methods").delete(user_id)
    _store.table("user_roles").delete_where(lambda r: r["userId"] == user_id)
    _store.table("user_metadata").delete(user_id)
    _store.table("users").delete(user_id)
    return {"status": "OK"}


_store.eager_load()
