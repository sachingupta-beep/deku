"""Data access module for the Zitadel mock service.

Two things make Zitadel's API shape distinctive, and both are modelled here
rather than flattened into a conventional login endpoint.

**Sessions are built up factor by factor.** There is no "log in" call. You
`POST /v2/sessions` with whichever `checks` you can satisfy, and the session
records a *factor* for each one that passed --- `user`, `password`, `webAuthN`,
`totp`, `intent` --- each with its own `verifiedAt`. You then `PATCH` the session
with more checks as the user completes them. An OIDC auth request can only be
finalized once the session's accumulated factors satisfy the org's login policy,
so `forceMfa` is enforced at the *end* of the flow, not at the password prompt.

**The organization is a request header, not a path segment.** `x-zitadel-orgid`
selects the org for the whole request; absent, the default org is used. A user in
one org is simply not found from another, and a token minted for one org cannot
administer another.

Every write returns a `details` envelope carrying a monotonically increasing
`sequence`, which is what Zitadel's eventstore actually exposes. Errors carry a
gRPC status code in the body alongside the HTTP status.

Passwords are verified as `sha256(passwordSalt + password)`; Zitadel uses
bcrypt. Mutations are held in process memory and reset on restart.
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

_store = get_store("zitadel-api")
_API = "zitadel-api"

DEFAULT_ORG = "280310551611113987"
INSTANCE_ID = "280310551611113986"

# gRPC status codes, which Zitadel reports in the body next to the HTTP status.
GRPC_INVALID_ARGUMENT = 3
GRPC_NOT_FOUND = 5
GRPC_ALREADY_EXISTS = 6
GRPC_PERMISSION_DENIED = 7
GRPC_FAILED_PRECONDITION = 9
GRPC_UNAUTHENTICATED = 16

_HTTP_FOR_GRPC = {
    GRPC_INVALID_ARGUMENT: 400,
    GRPC_NOT_FOUND: 404,
    GRPC_ALREADY_EXISTS: 409,
    GRPC_PERMISSION_DENIED: 403,
    GRPC_FAILED_PRECONDITION: 400,
    GRPC_UNAUTHENTICATED: 401,
}


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

    Zitadel's session `metadata` and event `payload` are free-form; the seed
    keeps them flat so a CSV overlay can shadow the JSON.
    """
    out = {}
    for part in _semi_list(row, column):
        key, _, value = part.partition("=")
        if key:
            out[key] = value
    return out


def _flag(row, column, default="0"):
    return opt_str(row, column, default=default) == "1"


_store.register("organizations", primary_key="id",
                initial_loader=lambda: _coerce_orgs(
                    _load("organizations.json", "organizations")))
_store.register("login_policies", primary_key="orgId",
                initial_loader=lambda: _coerce_policies(
                    _load("login_policies.json", "login_policies")))
_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json", "users")))
_store.register("auth_factors", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("auth_factors.json", "auth_factors")])
_store.register("sessions", primary_key="id",
                initial_loader=lambda: _coerce_sessions(
                    _load("sessions.json", "sessions")))
_store.register("projects", primary_key="id",
                initial_loader=lambda: _coerce_projects(
                    _load("projects.json", "projects")))
# A role key is unique only within its project, so the store needs a composite key.
_store.register("project_roles", primary_key="_pk",
                initial_loader=lambda: _coerce_project_roles(
                    _load("project_roles.json", "project_roles")))
_store.register("user_grants", primary_key="id",
                initial_loader=lambda: _coerce_grants(
                    _load("user_grants.json", "user_grants")))
_store.register("org_members", primary_key="id",
                initial_loader=lambda: _coerce_members(
                    _load("org_members.json", "org_members")))
_store.register("access_tokens", primary_key="token",
                initial_loader=lambda: _coerce_tokens(
                    _load("access_tokens.json", "access_tokens")))
_store.register("auth_requests", primary_key="id",
                initial_loader=lambda: _coerce_auth_requests(
                    _load("auth_requests.json", "auth_requests")))
_store.register("events", primary_key="sequence",
                initial_loader=lambda: _coerce_events(_load("events.json",
                                                            "events")))


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def _coerce_orgs(rows):
    return [{**_strip_ctx(r), "isDefault": _flag(r, "isDefault"),
             "sequence": opt_int(r, "sequence", default=0)} for r in rows]


_POLICY_FLAGS = ("allowUsernamePassword", "allowRegister", "allowExternalIdp",
                 "forceMfa", "forceMfaLocalOnly", "hidePasswordReset",
                 "isDefault")
_POLICY_INTS = ("passwordCheckLifetime", "mfaInitSkipLifetime",
                "maxPasswordAttempts")


def _coerce_policies(rows):
    return [{**_strip_ctx(r),
             **{f: _flag(r, f) for f in _POLICY_FLAGS},
             **{f: opt_int(r, f, default=0) for f in _POLICY_INTS},
             "multiFactors": _semi_list(r, "multiFactors"),
             "secondFactors": _semi_list(r, "secondFactors")} for r in rows]


def _coerce_users(rows):
    return [{**_strip_ctx(r),
             "isEmailVerified": _flag(r, "isEmailVerified"),
             "isPhoneVerified": _flag(r, "isPhoneVerified"),
             "passwordChangeRequired": _flag(r, "passwordChangeRequired"),
             "loginNames": _semi_list(r, "loginNames"),
             "sequence": opt_int(r, "sequence", default=0)} for r in rows]


def _coerce_sessions(rows):
    out = []
    for r in rows:
        factors = {}
        for entry in _semi_list(r, "factors"):
            name, _, verified_at = entry.partition(":")
            if name:
                factors[name] = verified_at
        out.append({**_strip_ctx(r), "factors": factors,
                    "metadata": _semi_map(r, "metadata"),
                    "sequence": opt_int(r, "sequence", default=0)})
    return out


def _coerce_projects(rows):
    return [{**_strip_ctx(r),
             "projectRoleAssertion": _flag(r, "projectRoleAssertion"),
             "projectRoleCheck": _flag(r, "projectRoleCheck"),
             "hasProjectCheck": _flag(r, "hasProjectCheck"),
             "sequence": opt_int(r, "sequence", default=0)} for r in rows]


def _coerce_project_roles(rows):
    return [{**_strip_ctx(r), "_pk": f"{r['projectId']}@{r['key']}"}
            for r in rows]


def _coerce_grants(rows):
    return [{**_strip_ctx(r), "roleKeys": _semi_list(r, "roleKeys"),
             "sequence": opt_int(r, "sequence", default=0)} for r in rows]


def _coerce_members(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "roles": _semi_list(r, "roles")} for r in rows]


def _coerce_tokens(rows):
    return [{**_strip_ctx(r), "revoked": _flag(r, "revoked"),
             "scopes": _semi_list(r, "scopes"),
             "instanceRoles": _semi_list(r, "instanceRoles"),
             "orgRoles": _semi_list(r, "orgRoles")} for r in rows]


def _coerce_auth_requests(rows):
    return [{**_strip_ctx(r), "scopes": _semi_list(r, "scopes")} for r in rows]


def _coerce_events(rows):
    return [{**_strip_ctx(r), "sequence": opt_int(r, "sequence", default=0),
             "payload": _semi_map(r, "payload")} for r in rows]


# ---------------------------------------------------------------------------
# Table accessors
# ---------------------------------------------------------------------------

def _orgs():
    return _store.table("organizations").rows()


def _users():
    return _store.table("users").rows()


def _factors():
    return _store.table("auth_factors").rows()


def _sessions():
    return _store.table("sessions").rows()


def _projects():
    return _store.table("projects").rows()


def _project_roles():
    return _store.table("project_roles").rows()


def _grants():
    return _store.table("user_grants").rows()


def _members():
    return _store.table("org_members").rows()


def _auth_requests():
    return _store.table("auth_requests").rows()


def _events():
    return _store.table("events").rows()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


_SNOWFLAKE = {"value": 281940113077380000}


def _snowflake():
    """Zitadel ids are snowflake-style numeric strings, allocated in order."""
    _SNOWFLAKE["value"] += 1
    return str(_SNOWFLAKE["value"])


def _next_sequence():
    """The eventstore sequence is global and monotonic."""
    return max((e["sequence"] for e in _events()), default=0) + 1


# ---------------------------------------------------------------------------
# Envelopes
# ---------------------------------------------------------------------------

def _details(org_id, sequence=None):
    return {"sequence": str(sequence if sequence is not None
                            else _next_sequence()),
            "changeDate": _now(), "resourceOwner": org_id}


def _error(grpc_code, message, detail=None):
    return {"error": message, "code": _HTTP_FOR_GRPC.get(grpc_code, 400),
            "grpc_code": grpc_code, "message": message, "detail": detail}


def _not_found(what):
    return _error(GRPC_NOT_FOUND, what)


# ---------------------------------------------------------------------------
# Org selection and authorization
# ---------------------------------------------------------------------------

def resolve_org(org_id=None):
    """`x-zitadel-orgid` selects the org; absent, the default org is used."""
    org = _store.table("organizations").get(org_id or DEFAULT_ORG)
    if not org:
        return None, _error(GRPC_NOT_FOUND,
                            f"Organisation {org_id} not found (ORG-Nc8it)")
    if org["state"] != "ORG_STATE_ACTIVE":
        return None, _error(GRPC_FAILED_PRECONDITION,
                            f"Organisation {org['name']} is not active "
                            f"(ORG-Aq49k)")
    return org, None


def resolve_token(authorization=None):
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw:
        return None
    record = _store.table("access_tokens").get(raw)
    if not record or record["revoked"]:
        return None
    return record


_ORG_WRITE_ROLES = {"ORG_OWNER", "ORG_USER_MANAGER"}


def authorize(authorization=None, org_id=None, write=False, instance=False):
    """Gate an API call.

    Three distinct refusals, all of which a real Zitadel deployment produces:
      * no usable token at all -> UNAUTHENTICATED
      * a token minted for a different org -> PERMISSION_DENIED
      * a read-only token attempting a write -> PERMISSION_DENIED
    """
    record = resolve_token(authorization)
    if not record:
        return None, _error(GRPC_UNAUTHENTICATED,
                            "authentication failed (AUTH-7fs3d)")
    if instance:
        if "IAM_OWNER" not in record["instanceRoles"]:
            return None, _error(GRPC_PERMISSION_DENIED,
                                "No matching permissions found "
                                "(AUTH-boeQa): IAM_OWNER required")
        return record, None
    target = org_id or DEFAULT_ORG
    if record["orgId"] != target and "IAM_OWNER" not in record["instanceRoles"]:
        return None, _error(
            GRPC_PERMISSION_DENIED,
            f"No matching permissions found (AUTH-boeQa): token belongs to "
            f"organisation {record['orgId']}, not {target}")
    if write and not (_ORG_WRITE_ROLES & set(record["orgRoles"])) \
            and "IAM_OWNER" not in record["instanceRoles"]:
        return None, _error(
            GRPC_PERMISSION_DENIED,
            f"No matching permissions found (AUTH-boeQa): "
            f"{', '.join(record['orgRoles']) or 'no role'} may not write")
    return record, None


# ---------------------------------------------------------------------------
# Representations
# ---------------------------------------------------------------------------

_HIDDEN_USER_FIELDS = ("passwordSalt", "passwordHash")


def user_representation(user):
    if not user:
        return None
    body = {"userId": user["id"], "details": {
        "sequence": str(user["sequence"]), "changeDate": user["changeDate"],
        "resourceOwner": user["resourceOwner"]},
        "state": user["state"], "username": user["userName"],
        "loginNames": user["loginNames"],
        "preferredLoginName": user["preferredLoginName"]}
    if user["type"] == "human":
        body["human"] = {
            "profile": {"givenName": user["givenName"],
                        "familyName": user["familyName"],
                        "nickName": user["nickName"],
                        "displayName": user["displayName"]},
            "email": {"email": user["email"],
                      "isVerified": user["isEmailVerified"]},
            "phone": {"phone": user["phone"],
                      "isVerified": user["isPhoneVerified"]},
            "passwordChangeRequired": user["passwordChangeRequired"],
            "passwordChanged": user["changeDate"],
        }
    else:
        body["machine"] = {"name": user["machineName"],
                           "description": user["machineDescription"],
                           "hasSecret": False}
    return body


def session_representation(session, with_token=False):
    body = {
        "id": session["id"],
        "creationDate": session["creationDate"],
        "changeDate": session["changeDate"],
        "sequence": str(session["sequence"]),
        "factors": _factor_representation(session),
        "metadata": session["metadata"],
        "userAgent": {"fingerprintId": session["userAgentFingerprint"]},
        "expirationDate": session["expirationDate"],
    }
    if with_token:
        body["sessionToken"] = session["token"]
    return body


def _factor_representation(session):
    out = {}
    for name, verified_at in session["factors"].items():
        if name == "user":
            user = _store.table("users").get(session["userId"])
            out["user"] = {"verifiedAt": verified_at,
                           "id": session["userId"],
                           "loginName": user["preferredLoginName"] if user
                           else "",
                           "displayName": user["displayName"] if user else "",
                           "organizationId": session["orgId"]}
        else:
            out[name] = {"verifiedAt": verified_at}
    return out


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _record_event(org_id, event_type, aggregate_type, aggregate_id,
                  editor_user_id="", editor_display_name="", payload=None):
    sequence = _next_sequence()
    entry = {"sequence": sequence, "orgId": org_id, "type": event_type,
             "aggregateType": aggregate_type, "aggregateId": aggregate_id,
             "editorUserId": editor_user_id,
             "editorDisplayName": editor_display_name,
             "creationDate": _now(), "payload": payload or {}}
    _store.table("events").upsert(entry)
    return sequence


def list_events(org_id, aggregate_types=None, aggregate_id=None,
                event_types=None, limit=20, asc=False):
    rows = [e for e in _events() if e["orgId"] == org_id]
    if aggregate_types:
        rows = [e for e in rows if e["aggregateType"] in aggregate_types]
    if aggregate_id:
        rows = [e for e in rows if e["aggregateId"] == aggregate_id]
    if event_types:
        rows = [e for e in rows if e["type"] in event_types]
    rows.sort(key=lambda e: e["sequence"], reverse=not asc)
    limit = max(1, min(int(limit or 20), 500))
    return {"events": [{**e, "sequence": str(e["sequence"])}
                       for e in rows[:limit]]}


# ---------------------------------------------------------------------------
# Health and instance info
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def healthz():
    return {}


def instance_info():
    return {"instance": {"id": INSTANCE_ID, "name": "orbit-labs",
                         "version": "2.65.1",
                         "domains": [{"domain": "orbit-labs.zitadel.cloud",
                                      "primary": True, "generated": True}],
                         "defaultOrgId": DEFAULT_ORG,
                         "state": "STATE_RUNNING"}}


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------

def org_representation(org):
    return {"id": org["id"], "name": org["name"],
            "primaryDomain": org["primaryDomain"], "state": org["state"],
            "details": {"sequence": str(org["sequence"]),
                        "changeDate": org["changeDate"],
                        "resourceOwner": org["id"]}}


def get_org(org):
    return {"org": org_representation(org)}


def search_orgs(query=None, state=None, limit=20):
    rows = _orgs()
    if query:
        needle = str(query).lower()
        rows = [o for o in rows if needle in o["name"].lower()
                or needle in o["primaryDomain"].lower()]
    if state:
        rows = [o for o in rows if o["state"] == state]
    limit = max(1, min(int(limit or 20), 500))
    return {"details": {"totalResult": str(len(rows)), "processedSequence":
                        str(_next_sequence() - 1), "timestamp": _now()},
            "result": [org_representation(o) for o in rows[:limit]]}


def get_login_policy(org_id):
    policy = _store.table("login_policies").get(org_id)
    if not policy:
        return _not_found(f"Login policy for organisation {org_id} not found "
                          f"(POLICY-4Md9s)")
    return {"policy": {k: v for k, v in policy.items() if k != "orgId"}}


# ---------------------------------------------------------------------------
# Users (v2)
# ---------------------------------------------------------------------------

def _user_in_org(user_id, org_id):
    user = _store.table("users").get(user_id)
    if not user or user["resourceOwner"] != org_id:
        return None
    return user


def get_user(org_id, user_id):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (QUERY-Dfbg2)")
    return {"user": user_representation(user)}


def search_users(org_id, query=None, state=None, user_type=None, limit=20,
                 offset=0):
    rows = [u for u in _users() if u["resourceOwner"] == org_id]
    if query:
        needle = str(query).lower()
        rows = [u for u in rows
                if needle in u["userName"].lower()
                or needle in (u["email"] or "").lower()
                or needle in (u["displayName"] or "").lower()]
    if state:
        rows = [u for u in rows if u["state"] == state]
    if user_type:
        rows = [u for u in rows if u["type"] == user_type]
    limit = max(1, min(int(limit or 20), 500))
    offset = max(0, int(offset or 0))
    page = rows[offset:offset + limit]
    return {"details": {"totalResult": str(len(rows)),
                        "processedSequence": str(_next_sequence() - 1),
                        "timestamp": _now()},
            "result": [user_representation(u) for u in page]}


def create_human_user(org_id, payload, editor=None):
    payload = payload or {}
    profile = payload.get("profile") or {}
    email = (payload.get("email") or {}).get("email")
    username = payload.get("username") or email
    if not username:
        return _error(GRPC_INVALID_ARGUMENT,
                      "username or email is required (COMMAND-9dk1s)")
    if not profile.get("givenName") or not profile.get("familyName"):
        return _error(GRPC_INVALID_ARGUMENT,
                      "givenName and familyName are required (COMMAND-3jd9a)")
    if _store.table("users").find_one(
            lambda u: u["resourceOwner"] == org_id and u["userName"] == username):
        return _error(GRPC_ALREADY_EXISTS,
                      f"User {username} already exists (COMMAND-9opd2)")
    password = (payload.get("password") or {}).get("password")
    salt, digest = "", ""
    if password:
        denied = check_password_complexity(org_id, password)
        if denied:
            return denied
        salt = uuid.uuid4().hex[:16]
        digest = _hash_password(salt, password)
    now = _now()
    sequence = _next_sequence()
    user = {
        "id": _snowflake(), "resourceOwner": org_id, "type": "human",
        # Without a password the account is INITIAL and cannot authenticate.
        "state": "USER_STATE_ACTIVE" if digest else "USER_STATE_INITIAL",
        "userName": username,
        "loginNames": [username] + ([email] if email and email != username
                                    else []),
        "preferredLoginName": username,
        "givenName": profile.get("givenName", ""),
        "familyName": profile.get("familyName", ""),
        "displayName": profile.get("displayName")
                       or f"{profile.get('givenName', '')} "
                          f"{profile.get('familyName', '')}".strip(),
        "nickName": profile.get("nickName", ""),
        "email": email or "",
        "isEmailVerified": bool((payload.get("email") or {}).get("isVerified")),
        "phone": (payload.get("phone") or {}).get("phone", ""),
        "isPhoneVerified": bool((payload.get("phone") or {}).get("isVerified")),
        "passwordSalt": salt, "passwordHash": digest,
        "passwordChangeRequired": bool(
            (payload.get("password") or {}).get("changeRequired", False)),
        "machineName": "", "machineDescription": "",
        "sequence": sequence, "creationDate": now, "changeDate": now,
    }
    _store_insert("users", user)
    _record_event(org_id, "user.human.added", "user", user["id"],
                  editor_user_id=(editor or {}).get("userId", ""))
    return {"userId": user["id"], "details": _details(org_id, sequence)}


def update_human_user(org_id, user_id, payload, editor=None):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    payload = payload or {}
    patch = {}
    profile = payload.get("profile") or {}
    for source, target in (("givenName", "givenName"),
                           ("familyName", "familyName"),
                           ("nickName", "nickName"),
                           ("displayName", "displayName")):
        if source in profile:
            patch[target] = profile[source]
    if "username" in payload and payload["username"]:
        clash = _store.table("users").find_one(
            lambda u: u["resourceOwner"] == org_id and u["id"] != user_id
            and u["userName"] == payload["username"])
        if clash:
            return _error(GRPC_ALREADY_EXISTS,
                          f"User {payload['username']} already exists "
                          f"(COMMAND-9opd2)")
        patch["userName"] = payload["username"]
        patch["preferredLoginName"] = payload["username"]
    sequence = _next_sequence()
    patch["sequence"] = sequence
    patch["changeDate"] = _now()
    _store.table("users").patch(user_id, patch)
    _record_event(org_id, "user.human.profile.changed", "user", user_id,
                  editor_user_id=(editor or {}).get("userId", ""))
    return {"details": _details(org_id, sequence)}


def set_email(org_id, user_id, email=None, is_verified=False,
              return_code=False):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    if not email or "@" not in email:
        return _error(GRPC_INVALID_ARGUMENT,
                      "email is not a valid address (COMMAND-1kd9a)")
    clash = _store.table("users").find_one(
        lambda u: u["resourceOwner"] == org_id and u["id"] != user_id
        and (u["email"] or "").lower() == email.lower())
    if clash:
        return _error(GRPC_ALREADY_EXISTS,
                      f"Email {email} is already in use (COMMAND-6b7dk)")
    sequence = _next_sequence()
    _store.table("users").patch(user_id, {
        "email": email, "isEmailVerified": bool(is_verified),
        "sequence": sequence, "changeDate": _now()})
    body = {"details": _details(org_id, sequence)}
    if not is_verified:
        # Zitadel returns the code only when the caller asks to send it itself.
        code = _digits(f"{user_id}:{email}", 6)
        _store.table("users").patch(user_id, {"emailVerificationCode": code})
        if return_code:
            body["verificationCode"] = code
        else:
            body["note"] = ("no mail is delivered by the mock; pass "
                            "returnCode to receive the verification code")
    return body


def verify_email(org_id, user_id, code=None):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    expected = user.get("emailVerificationCode")
    if not expected or code != expected:
        return _error(GRPC_INVALID_ARGUMENT,
                      "Code is invalid or has expired (COMMAND-2M9fs)")
    sequence = _next_sequence()
    _store.table("users").patch(user_id, {
        "isEmailVerified": True, "emailVerificationCode": "",
        "sequence": sequence, "changeDate": _now()})
    _record_event(org_id, "user.human.email.verified", "user", user_id)
    return {"details": _details(org_id, sequence)}


def _digits(seed, length):
    """Derive a stable numeric code from a seed string.

    `hash()` is salted per process, so codes derived from it would differ across
    restarts.
    """
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    return str(int(digest[:12], 16)).zfill(length)[-length:]


def check_password_complexity(org_id, password):
    """Zitadel's password complexity policy, expressed per organisation."""
    if len(password) < 8:
        return _error(GRPC_INVALID_ARGUMENT,
                      "Password does not fulfil the complexity policy: minimum "
                      "length 8 (COMMAND-HuJf6)")
    if not any(c.isupper() for c in password):
        return _error(GRPC_INVALID_ARGUMENT,
                      "Password does not fulfil the complexity policy: needs an "
                      "upper-case letter (COMMAND-Kd8s2)")
    if not any(c.isdigit() for c in password):
        return _error(GRPC_INVALID_ARGUMENT,
                      "Password does not fulfil the complexity policy: needs a "
                      "digit (COMMAND-9dK2s)")
    if not any(not c.isalnum() for c in password):
        return _error(GRPC_INVALID_ARGUMENT,
                      "Password does not fulfil the complexity policy: needs a "
                      "symbol (COMMAND-2Md9a)")
    return None


def set_password(org_id, user_id, new_password=None, current_password=None,
                 verification_code=None, change_required=False):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    if not new_password:
        return _error(GRPC_INVALID_ARGUMENT,
                      "newPassword is required (COMMAND-3kd8s)")
    denied = check_password_complexity(org_id, new_password)
    if denied:
        return denied
    if current_password is not None:
        if not user["passwordHash"] or _hash_password(
                user["passwordSalt"], current_password) != user["passwordHash"]:
            return _error(GRPC_INVALID_ARGUMENT,
                          "Current password is invalid (COMMAND-3M0fs)")
    elif verification_code is not None:
        if verification_code != user.get("passwordResetCode"):
            return _error(GRPC_INVALID_ARGUMENT,
                          "Code is invalid or has expired (COMMAND-2M9fs)")
    salt = uuid.uuid4().hex[:16]
    sequence = _next_sequence()
    patch = {"passwordSalt": salt,
             "passwordHash": _hash_password(salt, new_password),
             "passwordChangeRequired": bool(change_required),
             "passwordResetCode": "", "sequence": sequence,
             "changeDate": _now()}
    if user["state"] == "USER_STATE_INITIAL":
        # Setting the first password is what activates an INITIAL account.
        patch["state"] = "USER_STATE_ACTIVE"
    _store.table("users").patch(user_id, patch)
    # Every session that authenticated with the old password is dropped.
    _store.table("sessions").delete_where(
        lambda s: s["userId"] == user_id and "password" in s["factors"])
    _record_event(org_id, "user.human.password.changed", "user", user_id)
    return {"details": _details(org_id, sequence)}


def request_password_reset(org_id, user_id, return_code=False):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    code = _digits(f"reset:{user_id}", 8)
    sequence = _next_sequence()
    _store.table("users").patch(user_id, {"passwordResetCode": code,
                                          "sequence": sequence})
    body = {"details": _details(org_id, sequence)}
    if return_code:
        body["verificationCode"] = code
    else:
        body["note"] = ("no mail is delivered by the mock; pass returnCode to "
                        "receive the reset code")
    return body


_STATE_TRANSITIONS = {
    "deactivate": ("USER_STATE_ACTIVE", "USER_STATE_INACTIVE",
                   "user.deactivated"),
    "reactivate": ("USER_STATE_INACTIVE", "USER_STATE_ACTIVE",
                   "user.reactivated"),
    "lock": ("USER_STATE_ACTIVE", "USER_STATE_LOCKED", "user.locked"),
    "unlock": ("USER_STATE_LOCKED", "USER_STATE_ACTIVE", "user.unlocked"),
}


def change_user_state(org_id, user_id, action):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    required, target, event = _STATE_TRANSITIONS[action]
    if user["state"] != required:
        return _error(GRPC_FAILED_PRECONDITION,
                      f"User is {user['state']}, cannot {action} "
                      f"(COMMAND-3M9sf)")
    sequence = _next_sequence()
    _store.table("users").patch(user_id, {"state": target,
                                          "sequence": sequence,
                                          "changeDate": _now()})
    if target in ("USER_STATE_INACTIVE", "USER_STATE_LOCKED"):
        _store.table("sessions").delete_where(lambda s: s["userId"] == user_id)
    _record_event(org_id, event, "user", user_id)
    return {"details": _details(org_id, sequence)}


def delete_user(org_id, user_id):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    _store.table("sessions").delete_where(lambda s: s["userId"] == user_id)
    _store.table("auth_factors").delete_where(lambda f: f["userId"] == user_id)
    _store.table("user_grants").delete_where(lambda g: g["userId"] == user_id)
    _store.table("org_members").delete_where(lambda m: m["userId"] == user_id)
    _store.table("users").delete(user_id)
    sequence = _record_event(org_id, "user.removed", "user", user_id)
    return {"details": _details(org_id, sequence)}


# ---------------------------------------------------------------------------
# Authentication factors
# ---------------------------------------------------------------------------

def list_auth_factors(org_id, user_id):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (QUERY-Dfbg2)")
    return {"result": [{"id": f["id"], "type": f["type"], "state": f["state"],
                        "name": f["name"], "createdAt": f["createdAt"]}
                       for f in _factors() if f["userId"] == user_id]}


def register_totp(org_id, user_id):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    existing = _store.table("auth_factors").find_one(
        lambda f: f["userId"] == user_id and f["type"] == "totp"
        and f["state"] == "AUTH_FACTOR_STATE_READY")
    if existing:
        return _error(GRPC_ALREADY_EXISTS,
                      "TOTP is already set up for this user (COMMAND-8Md9s)")
    factor_id = f"af-{uuid.uuid4().hex[:16]}"
    code = _digits(factor_id, 6)
    _store_insert("auth_factors", {
        "id": factor_id, "userId": user_id, "type": "totp",
        "state": "AUTH_FACTOR_STATE_NOT_READY", "name": "Authenticator app",
        "secret": "JBSWY3DPEHPK3PXP", "code": code, "createdAt": _now()})
    sequence = _record_event(org_id, "user.human.mfa.otp.added", "user", user_id)
    return {"details": _details(org_id, sequence), "uri":
            f"otpauth://totp/ZITADEL:{user['preferredLoginName']}"
            f"?algorithm=SHA1&digits=6&issuer=ZITADEL&period=30"
            f"&secret=JBSWY3DPEHPK3PXP",
            "secret": "JBSWY3DPEHPK3PXP", "expectedCode": code,
            "note": "the expected code is returned because no authenticator app "
                    "is actually enrolled"}


def verify_totp(org_id, user_id, code=None):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    factor = _store.table("auth_factors").find_one(
        lambda f: f["userId"] == user_id and f["type"] == "totp")
    if not factor:
        return _not_found("TOTP is not set up for this user (COMMAND-3M9df)")
    if code != factor["code"]:
        return _error(GRPC_INVALID_ARGUMENT,
                      "Invalid code (COMMAND-8Nd9s)")
    _store.table("auth_factors").patch(factor["id"],
                                       {"state": "AUTH_FACTOR_STATE_READY"})
    sequence = _record_event(org_id, "user.human.mfa.otp.verified", "user",
                             user_id)
    return {"details": _details(org_id, sequence)}


def remove_auth_factor(org_id, user_id, factor_id):
    user = _user_in_org(user_id, org_id)
    if not user:
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    factor = _store.table("auth_factors").get(factor_id)
    if not factor or factor["userId"] != user_id:
        return _not_found(f"Factor {factor_id} not found (COMMAND-2Md8s)")
    _store.table("auth_factors").delete(factor_id)
    sequence = _record_event(org_id, "user.human.mfa.otp.removed", "user",
                             user_id)
    return {"details": _details(org_id, sequence)}


# ---------------------------------------------------------------------------
# Sessions (v2) --- the incremental factor model
# ---------------------------------------------------------------------------

_CHECK_ORDER = ("user", "password", "webAuthN", "totp", "otpSms", "idpIntent")


def _apply_checks(org_id, session, checks, existing_user_id=None):
    """Apply a `checks` block, returning `(factors, user_id, error)`.

    Each check that passes contributes one factor. A failing check aborts the
    whole call --- Zitadel does not partially apply a checks block.
    """
    factors = dict(session["factors"]) if session else {}
    user_id = existing_user_id
    checks = checks or {}
    now = _now()

    if "user" in checks:
        identifier = (checks["user"].get("loginName")
                      or checks["user"].get("userId"))
        if not identifier:
            return None, None, _error(GRPC_INVALID_ARGUMENT,
                                      "loginName or userId is required "
                                      "(COMMAND-2Md9f)")
        user = _store.table("users").find_one(
            lambda u: u["resourceOwner"] == org_id
            and (u["id"] == identifier or identifier in u["loginNames"]
                 or u["userName"] == identifier))
        if not user:
            return None, None, _not_found(
                f"User {identifier} not found in organisation {org_id} "
                f"(COMMAND-Dfbg2)")
        if user["state"] == "USER_STATE_INACTIVE":
            return None, None, _error(GRPC_FAILED_PRECONDITION,
                                      "User is deactivated (COMMAND-4M0fs)")
        if user["state"] == "USER_STATE_LOCKED":
            return None, None, _error(GRPC_FAILED_PRECONDITION,
                                      "User is locked (COMMAND-5M0fs)")
        user_id = user["id"]
        factors["user"] = now

    if not user_id:
        return None, None, _error(GRPC_FAILED_PRECONDITION,
                                  "The session has no user; send a user check "
                                  "first (COMMAND-1M9fs)")
    user = _store.table("users").get(user_id)

    if "password" in checks:
        password = checks["password"].get("password")
        if not user["passwordHash"]:
            return None, None, _error(
                GRPC_FAILED_PRECONDITION,
                "User has no password set (COMMAND-6M0fs)")
        if _hash_password(user["passwordSalt"], password or "") \
                != user["passwordHash"]:
            _record_event(org_id, "user.human.password.check.failed", "user",
                          user_id)
            return None, None, _error(GRPC_INVALID_ARGUMENT,
                                      "Invalid password (COMMAND-SAF3t)")
        _record_event(org_id, "user.human.password.check.succeeded", "user",
                      user_id)
        factors["password"] = now

    if "totp" in checks:
        code = checks["totp"].get("code")
        factor = _store.table("auth_factors").find_one(
            lambda f: f["userId"] == user_id and f["type"] == "totp"
            and f["state"] == "AUTH_FACTOR_STATE_READY")
        if not factor:
            return None, None, _error(
                GRPC_FAILED_PRECONDITION,
                "TOTP is not set up for this user (COMMAND-3M9df)")
        if code != factor["code"]:
            return None, None, _error(GRPC_INVALID_ARGUMENT,
                                      "Invalid code (COMMAND-8Nd9s)")
        _record_event(org_id, "user.human.mfa.otp.check.succeeded", "user",
                      user_id)
        factors["totp"] = now

    if "webAuthN" in checks:
        factor = _store.table("auth_factors").find_one(
            lambda f: f["userId"] == user_id and f["type"] in ("passkey", "u2f")
            and f["state"] == "AUTH_FACTOR_STATE_READY")
        if not factor:
            return None, None, _error(
                GRPC_FAILED_PRECONDITION,
                "No WebAuthN credential is registered (COMMAND-4Md9a)")
        # The mock cannot run a real assertion, so any credential id is taken
        # as proof once one is registered.
        _record_event(org_id, "user.human.webauthn.check.succeeded", "user",
                      user_id)
        factors["webAuthN"] = now

    if "idpIntent" in checks:
        factors["intent"] = now

    return factors, user_id, None


def create_session(org_id, checks=None, metadata=None, lifetime_seconds=None,
                   user_agent=None):
    factors, user_id, denied = _apply_checks(org_id, None, checks)
    if denied:
        return denied
    now = _now()
    sequence = _next_sequence()
    lifetime = int(lifetime_seconds or 86400)
    session = {
        "id": _snowflake(), "orgId": org_id, "userId": user_id,
        "token": f"zt-session-{secrets.token_hex(10)}", "factors": factors,
        "userAgentFingerprint": (user_agent or {}).get("fingerprintId", ""),
        "metadata": metadata or {}, "sequence": sequence,
        "creationDate": now, "changeDate": now,
        "expirationDate": (datetime.now(timezone.utc)
                           + timedelta(seconds=lifetime)).strftime(
                               "%Y-%m-%dT%H:%M:%SZ"),
    }
    _store_insert("sessions", session)
    return {"sessionId": session["id"], "sessionToken": session["token"],
            "details": _details(org_id, sequence),
            "factors": _factor_representation(session)}


def _session_for_token(session_id, session_token):
    session = _store.table("sessions").get(session_id) if session_id else None
    if not session:
        return None, _not_found(f"Session {session_id} not found (QUERY-2M9fs)")
    if session_token and session["token"] != session_token:
        return None, _error(GRPC_PERMISSION_DENIED,
                            "Invalid session token (COMMAND-sGr42)")
    if session["expirationDate"] < _now():
        return None, _error(GRPC_FAILED_PRECONDITION,
                            "Session has expired (COMMAND-6M9fs)")
    return session, None


def get_session(org_id, session_id, session_token=None):
    session, denied = _session_for_token(session_id, session_token)
    if denied:
        return denied
    if session["orgId"] != org_id:
        return _not_found(f"Session {session_id} not found (QUERY-2M9fs)")
    return {"session": session_representation(session)}


def update_session(org_id, session_id, session_token=None, checks=None,
                   metadata=None, lifetime_seconds=None):
    session, denied = _session_for_token(session_id, session_token)
    if denied:
        return denied
    if session["orgId"] != org_id:
        return _not_found(f"Session {session_id} not found (COMMAND-2M9fs)")
    factors, user_id, denied = _apply_checks(org_id, session, checks,
                                             existing_user_id=session["userId"])
    if denied:
        return denied
    sequence = _next_sequence()
    patch = {"factors": factors, "userId": user_id, "sequence": sequence,
             "changeDate": _now()}
    if metadata:
        patch["metadata"] = {**session["metadata"], **metadata}
    if lifetime_seconds:
        patch["expirationDate"] = (datetime.now(timezone.utc) + timedelta(
            seconds=int(lifetime_seconds))).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Every update rotates the session token, as Zitadel does.
    rotated = f"zt-session-{secrets.token_hex(10)}"
    patch["token"] = rotated
    updated = _store.table("sessions").patch(session_id, patch)
    return {"sessionToken": rotated, "details": _details(org_id, sequence),
            "factors": _factor_representation(updated)}


def delete_session(org_id, session_id, session_token=None):
    session, denied = _session_for_token(session_id, session_token)
    if denied:
        return denied
    if session["orgId"] != org_id:
        return _not_found(f"Session {session_id} not found (COMMAND-2M9fs)")
    _store.table("sessions").delete(session_id)
    sequence = _record_event(org_id, "session.terminated", "session",
                             session_id)
    return {"details": _details(org_id, sequence)}


def search_sessions(org_id, user_id=None, limit=20):
    rows = [s for s in _sessions() if s["orgId"] == org_id]
    if user_id:
        rows = [s for s in rows if s["userId"] == user_id]
    limit = max(1, min(int(limit or 20), 500))
    return {"details": {"totalResult": str(len(rows)),
                        "processedSequence": str(_next_sequence() - 1),
                        "timestamp": _now()},
            "sessions": [session_representation(s) for s in rows[:limit]]}


# ---------------------------------------------------------------------------
# OIDC auth requests --- where the login policy is actually enforced
# ---------------------------------------------------------------------------

def get_auth_request(org_id, auth_request_id):
    request = _store.table("auth_requests").get(auth_request_id)
    if not request or request["orgId"] != org_id:
        return _not_found(f"Auth request {auth_request_id} not found "
                          f"(QUERY-3M9fs)")
    return {"authRequest": {
        "id": request["id"], "creationDate": request["creationDate"],
        "clientId": request["clientId"], "scope": request["scopes"],
        "redirectUri": request["redirectUri"], "prompt": [request["prompt"]],
        "loginHint": request["loginHint"], "state": request["state"],
        "requestState": request["state_name"], "sessionId": request["sessionId"]}}


def _required_factors(org_id):
    """What the org's login policy demands before an auth request may finish."""
    policy = _store.table("login_policies").get(org_id)
    if not policy:
        return {"user"}
    required = {"user"}
    if policy["forceMfa"]:
        required.add("mfa")
    return required


def finalize_auth_request(org_id, auth_request_id, session_id=None,
                          session_token=None, deny=False):
    request = _store.table("auth_requests").get(auth_request_id)
    if not request or request["orgId"] != org_id:
        return _not_found(f"Auth request {auth_request_id} not found "
                          f"(COMMAND-3M9fs)")
    if request["state_name"] != "AUTH_REQUEST_STATE_CREATED":
        return _error(GRPC_FAILED_PRECONDITION,
                      f"Auth request is {request['state_name']} and cannot be "
                      f"completed again (COMMAND-7M9fs)")
    if deny:
        _store.table("auth_requests").patch(
            auth_request_id, {"state_name": "AUTH_REQUEST_STATE_FAILED"})
        sequence = _record_event(org_id, "oidc.session.failed", "auth_request",
                                 auth_request_id)
        return {"details": _details(org_id, sequence),
                "callbackUrl": f"{request['redirectUri']}?error=access_denied"
                               f"&state={request['state']}"}
    session, denied = _session_for_token(session_id, session_token)
    if denied:
        return denied
    if session["orgId"] != org_id:
        return _not_found(f"Session {session_id} not found (COMMAND-2M9fs)")
    required = _required_factors(org_id)
    present = set(session["factors"])
    mfa_present = bool(present & {"totp", "webAuthN", "otpSms"})
    missing = []
    if "user" not in present:
        missing.append("user")
    if "password" not in present and not mfa_present:
        missing.append("password or a passwordless factor")
    if "mfa" in required and not mfa_present:
        missing.append("a second factor (the organisation forces MFA)")
    if missing:
        return _error(GRPC_FAILED_PRECONDITION,
                      f"Session does not satisfy the login policy; missing: "
                      f"{', '.join(missing)} (COMMAND-Sfefs)")
    code = f"zt-code-{secrets.token_hex(8)}"
    sequence = _next_sequence()
    _store.table("auth_requests").patch(auth_request_id, {
        "sessionId": session_id, "state_name": "AUTH_REQUEST_STATE_SUCCEEDED"})
    _record_event(org_id, "oidc.session.added", "auth_request",
                  auth_request_id, payload={"sessionId": session_id})
    return {"details": _details(org_id, sequence),
            "callbackUrl": f"{request['redirectUri']}?code={code}"
                           f"&state={request['state']}",
            "sessionId": session_id,
            "factors": sorted(present)}


# ---------------------------------------------------------------------------
# Projects, roles and grants (management API)
# ---------------------------------------------------------------------------

def project_representation(project):
    return {"id": project["id"], "name": project["name"],
            "state": project["state"],
            "projectRoleAssertion": project["projectRoleAssertion"],
            "projectRoleCheck": project["projectRoleCheck"],
            "hasProjectCheck": project["hasProjectCheck"],
            "privateLabelingSetting": project["privateLabelingSetting"],
            "details": {"sequence": str(project["sequence"]),
                        "changeDate": project["changeDate"],
                        "resourceOwner": project["resourceOwner"]}}


def search_projects(org_id, query=None, limit=20):
    rows = [p for p in _projects() if p["resourceOwner"] == org_id]
    if query:
        needle = str(query).lower()
        rows = [p for p in rows if needle in p["name"].lower()]
    limit = max(1, min(int(limit or 20), 500))
    return {"details": {"totalResult": str(len(rows)),
                        "processedSequence": str(_next_sequence() - 1),
                        "timestamp": _now()},
            "result": [project_representation(p) for p in rows[:limit]]}


def get_project(org_id, project_id):
    project = _store.table("projects").get(project_id)
    if not project or project["resourceOwner"] != org_id:
        return _not_found(f"Project {project_id} not found (QUERY-4M9fs)")
    return {"project": project_representation(project)}


def create_project(org_id, payload):
    payload = payload or {}
    name = payload.get("name")
    if not name:
        return _error(GRPC_INVALID_ARGUMENT, "name is required (COMMAND-2M9fa)")
    if _store.table("projects").find_one(
            lambda p: p["resourceOwner"] == org_id and p["name"] == name):
        return _error(GRPC_ALREADY_EXISTS,
                      f"Project {name} already exists (COMMAND-3M9fa)")
    now = _now()
    sequence = _next_sequence()
    project = {"id": _snowflake(), "resourceOwner": org_id, "name": name,
               "state": "PROJECT_STATE_ACTIVE",
               "projectRoleAssertion": bool(payload.get("projectRoleAssertion",
                                                        True)),
               "projectRoleCheck": bool(payload.get("projectRoleCheck", False)),
               "hasProjectCheck": bool(payload.get("hasProjectCheck", False)),
               "privateLabelingSetting":
                   "PRIVATE_LABELING_SETTING_UNSPECIFIED",
               "sequence": sequence, "creationDate": now, "changeDate": now}
    _store_insert("projects", project)
    _record_event(org_id, "project.added", "project", project["id"])
    return {"id": project["id"], "details": _details(org_id, sequence)}


def search_project_roles(org_id, project_id, limit=50):
    project = _store.table("projects").get(project_id)
    if not project or project["resourceOwner"] != org_id:
        return _not_found(f"Project {project_id} not found (QUERY-4M9fs)")
    rows = [r for r in _project_roles() if r["projectId"] == project_id]
    return {"details": {"totalResult": str(len(rows)),
                        "processedSequence": str(_next_sequence() - 1),
                        "timestamp": _now()},
            "result": [{k: v for k, v in r.items() if k != "_pk"}
                       for r in rows[:max(1, min(int(limit or 50), 500))]]}


def add_project_role(org_id, project_id, payload):
    project = _store.table("projects").get(project_id)
    if not project or project["resourceOwner"] != org_id:
        return _not_found(f"Project {project_id} not found (COMMAND-4M9fs)")
    payload = payload or {}
    key = payload.get("roleKey")
    if not key:
        return _error(GRPC_INVALID_ARGUMENT,
                      "roleKey is required (COMMAND-5M9fa)")
    if _store.table("project_roles").get(f"{project_id}@{key}"):
        return _error(GRPC_ALREADY_EXISTS,
                      f"Role {key} already exists on this project "
                      f"(COMMAND-6M9fa)")
    _store.table("project_roles").upsert({
        "_pk": f"{project_id}@{key}", "projectId": project_id, "key": key,
        "displayName": payload.get("displayName", key),
        "group": payload.get("group", ""), "creationDate": _now()})
    sequence = _record_event(org_id, "project.role.added", "project",
                             project_id)
    return {"details": _details(org_id, sequence)}


def grant_representation(grant):
    user = _store.table("users").get(grant["userId"])
    project = _store.table("projects").get(grant["projectId"])
    return {"id": grant["id"], "userId": grant["userId"],
            "projectId": grant["projectId"], "roleKeys": grant["roleKeys"],
            "state": grant["state"],
            "displayName": user["displayName"] if user else "",
            "projectName": project["name"] if project else "",
            "details": {"sequence": str(grant["sequence"]),
                        "changeDate": grant["changeDate"],
                        "resourceOwner": grant["resourceOwner"]}}


def search_user_grants(org_id, user_id=None, project_id=None, state=None,
                       limit=50):
    rows = [g for g in _grants() if g["resourceOwner"] == org_id]
    if user_id:
        rows = [g for g in rows if g["userId"] == user_id]
    if project_id:
        rows = [g for g in rows if g["projectId"] == project_id]
    if state:
        rows = [g for g in rows if g["state"] == state]
    limit = max(1, min(int(limit or 50), 500))
    return {"details": {"totalResult": str(len(rows)),
                        "processedSequence": str(_next_sequence() - 1),
                        "timestamp": _now()},
            "result": [grant_representation(g) for g in rows[:limit]]}


def create_user_grant(org_id, payload):
    payload = payload or {}
    user_id = payload.get("userId")
    project_id = payload.get("projectId")
    role_keys = payload.get("roleKeys") or []
    if not _user_in_org(user_id, org_id):
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    project = _store.table("projects").get(project_id)
    if not project or project["resourceOwner"] != org_id:
        return _not_found(f"Project {project_id} not found (COMMAND-4M9fs)")
    known = {r["key"] for r in _project_roles() if r["projectId"] == project_id}
    unknown = [k for k in role_keys if k not in known]
    if unknown:
        return _error(GRPC_INVALID_ARGUMENT,
                      f"Roles not defined on this project: "
                      f"{', '.join(unknown)} (COMMAND-8M9fa)")
    existing = _store.table("user_grants").find_one(
        lambda g: g["userId"] == user_id and g["projectId"] == project_id)
    if existing:
        return _error(GRPC_ALREADY_EXISTS,
                      "The user already has a grant on this project "
                      "(COMMAND-9M9fa)")
    now = _now()
    sequence = _next_sequence()
    grant = {"id": _snowflake(), "userId": user_id, "projectId": project_id,
             "resourceOwner": org_id, "roleKeys": list(role_keys),
             "state": "USER_GRANT_STATE_ACTIVE", "sequence": sequence,
             "creationDate": now, "changeDate": now}
    _store_insert("user_grants", grant)
    _record_event(org_id, "user.grant.added", "usergrant", grant["id"])
    return {"userGrantId": grant["id"], "details": _details(org_id, sequence)}


def update_user_grant(org_id, grant_id, role_keys=None):
    grant = _store.table("user_grants").get(grant_id)
    if not grant or grant["resourceOwner"] != org_id:
        return _not_found(f"Grant {grant_id} not found (COMMAND-1M9fa)")
    known = {r["key"] for r in _project_roles()
             if r["projectId"] == grant["projectId"]}
    unknown = [k for k in (role_keys or []) if k not in known]
    if unknown:
        return _error(GRPC_INVALID_ARGUMENT,
                      f"Roles not defined on this project: "
                      f"{', '.join(unknown)} (COMMAND-8M9fa)")
    sequence = _next_sequence()
    _store.table("user_grants").patch(grant_id, {"roleKeys": list(role_keys or []),
                                                 "sequence": sequence,
                                                 "changeDate": _now()})
    return {"details": _details(org_id, sequence)}


def delete_user_grant(org_id, grant_id):
    grant = _store.table("user_grants").get(grant_id)
    if not grant or grant["resourceOwner"] != org_id:
        return _not_found(f"Grant {grant_id} not found (COMMAND-1M9fa)")
    _store.table("user_grants").delete(grant_id)
    sequence = _record_event(org_id, "user.grant.removed", "usergrant",
                             grant_id)
    return {"details": _details(org_id, sequence)}


# ---------------------------------------------------------------------------
# Org members
# ---------------------------------------------------------------------------

_ORG_ROLES = ("ORG_OWNER", "ORG_USER_MANAGER", "ORG_PROJECT_CREATOR",
              "ORG_OWNER_VIEWER")


def search_org_members(org_id, limit=50):
    rows = [m for m in _members() if m["orgId"] == org_id]
    out = []
    for member in rows[:max(1, min(int(limit or 50), 500))]:
        user = _store.table("users").get(member["userId"])
        out.append({"userId": member["userId"], "roles": member["roles"],
                    "displayName": user["displayName"] if user else "",
                    "preferredLoginName": user["preferredLoginName"] if user
                    else "", "creationDate": member["creationDate"]})
    return {"details": {"totalResult": str(len(rows)),
                        "processedSequence": str(_next_sequence() - 1),
                        "timestamp": _now()},
            "result": out}


def add_org_member(org_id, payload):
    payload = payload or {}
    user_id = payload.get("userId")
    roles = payload.get("roles") or []
    if not _user_in_org(user_id, org_id):
        return _not_found(f"User {user_id} not found (COMMAND-Dfbg2)")
    unknown = [r for r in roles if r not in _ORG_ROLES]
    if unknown:
        return _error(GRPC_INVALID_ARGUMENT,
                      f"Unknown organisation roles: {', '.join(unknown)} "
                      f"(COMMAND-2M9fb)")
    if _store.table("org_members").find_one(
            lambda m: m["orgId"] == org_id and m["userId"] == user_id):
        return _error(GRPC_ALREADY_EXISTS,
                      "The user is already a member of this organisation "
                      "(COMMAND-3M9fb)")
    next_id = max((m["id"] for m in _members()), default=0) + 1
    _store_insert("org_members", {"id": next_id, "orgId": org_id,
                                  "userId": user_id, "roles": list(roles),
                                  "creationDate": _now()})
    sequence = _record_event(org_id, "org.member.added", "org", org_id)
    return {"details": _details(org_id, sequence)}


def remove_org_member(org_id, user_id):
    member = _store.table("org_members").find_one(
        lambda m: m["orgId"] == org_id and m["userId"] == user_id)
    if not member:
        return _not_found(f"Member {user_id} not found (COMMAND-4M9fb)")
    owners = [m for m in _members()
              if m["orgId"] == org_id and "ORG_OWNER" in m["roles"]]
    if "ORG_OWNER" in member["roles"] and len(owners) == 1:
        # An org must keep at least one owner.
        return _error(GRPC_FAILED_PRECONDITION,
                      "Cannot remove the last organisation owner "
                      "(COMMAND-5M9fb)")
    _store.table("org_members").delete(member["id"])
    sequence = _record_event(org_id, "org.member.removed", "org", org_id)
    return {"details": _details(org_id, sequence)}


_store.eager_load()
