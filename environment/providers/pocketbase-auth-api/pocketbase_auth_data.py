"""Data access module for the PocketBase Auth mock service.

Serves the auth half of the same self-hosted PocketBase instance `pocketbase-api`
backs -- the Orbit Labs Status page. Record ids and collection ids are the ones
used there, so the two services describe one `pb_data/data.db`.

PocketBase authenticates *per collection*, not globally: `users` and the system
`_superusers` collection each carry their own identity fields, password rules,
OTP/MFA switches and OAuth2 providers. Tokens are stateless -- the mock encodes
them as `<header>.<recordId>.<tokenKey>` and resolves them by looking the record
up, which reproduces PocketBase's real invalidation rule: changing a password or
an email rotates `tokenKey`, and every token already issued for that record stops
working.

Passwords are verified as `sha256(passwordSalt + password)`; neither the hash nor
the salt is ever returned. Mutations are held in process memory and reset on
restart.
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("pocketbase-auth-api")
_API = "pocketbase-auth-api"

TOKEN_HEADER = "eyJhbGciOiJIUzI1NiJ9"

GUEST = "guest"
USER = "user"
SUPERUSER = "superuser"

SUPERUSER_COLLECTION = "_superusers"


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


def _load_settings():
    with open(DATA_DIR / "settings.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("auth_records", primary_key="id",
                initial_loader=lambda: _coerce_records(
                    _load("auth_records.json", "auth_records")))
_store.register("auth_collections", primary_key="id",
                initial_loader=lambda: _coerce_collections(
                    _load("auth_collections.json", "auth_collections")))
_store.register("external_auths", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("external_auths.json", "external_auths")])
_store.register("oauth2_providers", primary_key="name",
                initial_loader=lambda: _coerce_providers(
                    _load("oauth2_providers.json", "oauth2_providers")))
_store.register("mail_tokens", primary_key="token",
                initial_loader=lambda: _coerce_flags(
                    _load("mail_tokens.json", "mail_tokens"), ("used",)))
_store.register("otp_requests", primary_key="id",
                initial_loader=lambda: _coerce_flags(
                    _load("otp_requests.json", "otp_requests"), ("used",)))
_store.register("mfa_records", primary_key="id",
                initial_loader=lambda: _coerce_flags(
                    _load("mfa_records.json", "mfa_records"), ("used",)))
_store.register("auth_logs", primary_key="id",
                initial_loader=lambda: _coerce_logs(
                    _load("auth_logs.json", "auth_logs")))
_store.register_document("settings", initial_loader=_load_settings)


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

_RECORD_BOOLS = ("emailVisibility", "verified", "oncall", "mfaEnabled")


def _coerce_records(rows):
    return [{**_strip_ctx(r),
             **{f: opt_str(r, f, default="false") == "true" for f in _RECORD_BOOLS}}
            for r in rows]


_COLLECTION_BOOLS = ("system", "authAlert", "passwordAuth", "otpEnabled",
                     "mfaEnabled", "oauth2Enabled", "allowUsernameAuth",
                     "allowEmailAuth", "allowOAuth2Auth", "requireEmail")
_COLLECTION_INTS = ("otpDuration", "otpLength", "mfaDuration",
                    "minPasswordLength", "authToken", "verificationToken",
                    "passwordResetToken", "emailChangeToken", "fileToken")


def _coerce_collections(rows):
    return [{**_strip_ctx(r),
             **{f: opt_str(r, f, default="false") == "true" for f in _COLLECTION_BOOLS},
             **{f: opt_int(r, f, default=0) for f in _COLLECTION_INTS},
             "identityFields": _semi_list(r, "identityFields"),
             "oauth2Providers": _semi_list(r, "oauth2Providers")}
            for r in rows]


def _coerce_providers(rows):
    return [{**_strip_ctx(r),
             "scopes": _semi_list(r, "scopes"),
             "pkce": opt_str(r, "pkce", default="false") == "true",
             "enabled": opt_str(r, "enabled", default="false") == "true"}
            for r in rows]


def _coerce_flags(rows, flags):
    return [{**_strip_ctx(r),
             **{f: bool(opt_int(r, f, default=0)) for f in flags}} for r in rows]


def _coerce_logs(rows):
    return [{**_strip_ctx(r), "level": opt_int(r, "level", default=0),
             "status": opt_int(r, "status", default=200),
             "execTime": opt_int(r, "execTime", default=0)} for r in rows]


def _semi_list(row, column):
    raw = opt_str(row, column, default="")
    return [part for part in raw.split(";") if part]


# ---------------------------------------------------------------------------
# Table accessors
# ---------------------------------------------------------------------------

def _records():
    return _store.table("auth_records").rows()


def _collections():
    return _store.table("auth_collections").rows()


def _external_auths():
    return _store.table("external_auths").rows()


def _providers():
    return _store.table("oauth2_providers").rows()


def _logs():
    return _store.table("auth_logs").rows()


def _settings_doc():
    return _store.document("settings").get()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000Z")


def _in_seconds(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)) \
        .strftime("%Y-%m-%d %H:%M:%S.000Z")


def _expired(stamp):
    if not stamp:
        return False
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.000Z").replace(
            tzinfo=timezone.utc) < datetime.now(timezone.utc)
    except ValueError:
        return False


def _pb_id(prefix):
    """PocketBase record ids are 15 lowercase alphanumerics."""
    return (prefix + uuid.uuid4().hex)[:15]


# ---------------------------------------------------------------------------
# Errors -- PocketBase shape
# ---------------------------------------------------------------------------

def _error(code, message, data=None):
    """PocketBase-shaped error body. The house `error` key drives the response."""
    return {"error": message, "code": code, "status": code, "message": message,
            "data": data or {}}


def _field_error(code, message, field, field_code, field_message):
    return _error(code, message,
                  {field: {"code": field_code, "message": field_message}})


# ---------------------------------------------------------------------------
# Collections and identities
# ---------------------------------------------------------------------------

def find_collection(name):
    return _store.table("auth_collections").find_one(
        lambda c: c["name"] == name or c["id"] == name)


def _collection_or_error(name):
    collection = find_collection(name)
    if not collection:
        return None, _error(404, "Missing collection context.")
    return collection, None


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def _rotate_token_key(record_id):
    """Rotate a record's tokenKey, which invalidates every token issued for it.

    This is how PocketBase revokes sessions -- there is nothing to delete, the
    old tokens simply stop verifying.
    """
    return _store.table("auth_records").patch(
        record_id, {"tokenKey": f"tk_{uuid.uuid4().hex[:12]}",
                    "updated": _now()})


def _issue_token(record):
    return f"{TOKEN_HEADER}.{record['id']}.{record['tokenKey']}"


def resolve_identity(authorization=None):
    """Map an Authorization header onto (kind, record).

    PocketBase accepts the raw token or a `Bearer`-prefixed one. A token is
    `<header>.<recordId>.<tokenKey>`; it resolves only while the record still
    carries that tokenKey. The legacy superuser token from `pocketbase-api` is
    accepted too, so a token minted there works here.
    """
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        return GUEST, None
    settings = _settings_doc()
    if token == settings["tokens"].get("legacySuperuser"):
        record = _store.table("auth_records").find_one(
            lambda r: r["collectionName"] == SUPERUSER_COLLECTION)
        return SUPERUSER, record
    parts = token.split(".")
    if len(parts) != 3:
        return GUEST, None
    record = _store.table("auth_records").get(parts[1])
    if not record or record["tokenKey"] != parts[2]:
        return GUEST, None
    kind = SUPERUSER if record["collectionName"] == SUPERUSER_COLLECTION else USER
    return kind, record


_HIDDEN_FIELDS = ("passwordHash", "passwordSalt", "tokenKey", "mfaEnabled",
                  "lastResetSentAt", "lastVerificationSentAt")


def public_record(record, viewer_kind=GUEST, viewer=None):
    """The record body PocketBase returns. Secrets never appear.

    `email` is masked unless the record opts in with `emailVisibility`, the
    viewer is the record itself, or the viewer is a superuser -- PocketBase's
    actual rule.
    """
    if not record:
        return None
    body = {k: v for k, v in record.items() if k not in _HIDDEN_FIELDS}
    visible = (record["emailVisibility"] or viewer_kind == SUPERUSER
               or (viewer and viewer["id"] == record["id"]))
    if not visible:
        body["email"] = ""
    if record["collectionName"] == SUPERUSER_COLLECTION:
        for field in ("username", "name", "avatar", "role", "oncall",
                      "emailVisibility"):
            body.pop(field, None)
    return body


def _auth_response(record, viewer_kind=None):
    kind = viewer_kind or (SUPERUSER
                           if record["collectionName"] == SUPERUSER_COLLECTION
                           else USER)
    return {"token": _issue_token(record),
            "record": public_record(record, viewer_kind=kind, viewer=record)}


def _log(message, url, status, record=None, collection="guest",
         ip="203.0.113.41", user_agent="orbit-status/2.1"):
    entry = {
        "id": _pb_id("log"),
        "level": 0 if status < 400 else 4,
        "message": message,
        "method": "POST",
        "url": url,
        "status": status,
        "auth": collection,
        "authId": record["id"] if record else "",
        "userIP": ip,
        "userAgent": user_agent,
        "execTime": 12,
        "created": _now(),
    }
    _store_insert("auth_logs", entry)
    return entry


# ---------------------------------------------------------------------------
# Health, settings, auth methods
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def api_health():
    settings = _settings_doc()
    return {"code": 200, "message": "API is healthy.",
            "data": {"canBackup": True, "realtime": False,
                     "version": settings["version"]}}


def auth_methods(collection_name):
    """PocketBase's auth-methods discovery document for one collection."""
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    providers = []
    if collection["oauth2Enabled"]:
        for name in collection["oauth2Providers"]:
            provider = _store.table("oauth2_providers").get(name)
            if not provider or not provider["enabled"]:
                continue
            state = uuid.uuid4().hex
            verifier = uuid.uuid4().hex + uuid.uuid4().hex
            providers.append({
                "name": provider["name"],
                "displayName": provider["displayName"],
                "state": state,
                "authURL": f"{provider['authURL']}?client_id={provider['clientId']}"
                           f"&response_type=code&scope={'+'.join(provider['scopes'])}"
                           f"&state={state}&redirect_uri=",
                "codeVerifier": verifier,
                "codeChallenge": hashlib.sha256(verifier.encode()).hexdigest()[:43],
                "codeChallengeMethod": "S256" if provider["pkce"] else "",
                "pkce": provider["pkce"],
            })
    return {
        "mfa": {"enabled": collection["mfaEnabled"],
                "duration": collection["mfaDuration"]},
        "otp": {"enabled": collection["otpEnabled"],
                "duration": collection["otpDuration"],
                "length": collection["otpLength"]},
        "password": {"enabled": collection["passwordAuth"],
                     "identityFields": collection["identityFields"]},
        "oauth2": {"enabled": collection["oauth2Enabled"], "providers": providers},
    }


def list_auth_collections(kind=GUEST):
    """The auth collections' configuration. Superuser-only, as in PocketBase."""
    if kind != SUPERUSER:
        return _error(403, "The request requires valid record authorization "
                           "token to be set.")
    return {"page": 1, "perPage": 30, "totalItems": len(_collections()),
            "totalPages": 1, "items": _collections()}


# ---------------------------------------------------------------------------
# auth-with-password
# ---------------------------------------------------------------------------

def _match_identity(collection, identity):
    """Resolve an identity against the collection's configured identityFields."""
    lowered = str(identity or "").lower()
    for field in collection["identityFields"]:
        record = _store.table("auth_records").find_one(
            lambda r, f=field: r["collectionId"] == collection["id"]
            and str(r.get(f, "")).lower() == lowered)
        if record:
            return record
    return None


def _auth_rule_allows(collection, record):
    """Evaluate the collection's seeded authRule against a record.

    PocketBase's authRule is a filter expression; the seed uses the one this
    instance really carries -- `verified = true` on `users`, empty on
    `_superusers` (empty means "no extra restriction").
    """
    rule = collection.get("authRule", "")
    if not rule:
        return True
    if rule == "verified = true":
        return bool(record["verified"])
    return True


def auth_with_password(collection_name, identity=None, password=None,
                       mfa_id=None, ip="203.0.113.41"):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    url = f"/api/collections/{collection['name']}/auth-with-password"
    if not collection["passwordAuth"]:
        return _error(400, "Password authentication is not enabled for this "
                           "collection.")
    if not identity or not password:
        missing = "identity" if not identity else "password"
        _log("auth-with-password", url, 400, ip=ip)
        return _field_error(400, "Failed to authenticate.", missing,
                            "validation_required", "Missing required value.")
    record = _match_identity(collection, identity)
    # An unknown identity and a wrong password are reported identically so the
    # endpoint cannot be used to enumerate accounts. A record with no password
    # hash (OAuth2-only) lands here too.
    if (not record or not record["passwordHash"]
            or _hash_password(record["passwordSalt"], password)
            != record["passwordHash"]):
        _log("auth-with-password", url, 400, ip=ip)
        return _error(400, "Failed to authenticate.",
                      {"identity": {"code": "validation_invalid_credentials",
                                    "message": "Invalid login credentials."}})
    if not _auth_rule_allows(collection, record):
        _log("auth-with-password", url, 403, record=record,
             collection=collection["name"], ip=ip)
        return _error(403, "The request doesn't satisfy the collection "
                           "requirements to authenticate.")
    if collection["mfaEnabled"] and record["mfaEnabled"] and not mfa_id:
        # First factor accepted: PocketBase answers 401 with an mfaId that the
        # second factor must quote.
        pending = {
            "id": _pb_id("mfa"), "collectionRef": collection["id"],
            "recordRef": record["id"], "method": "password", "used": False,
            "created": _now(), "expires": _in_seconds(collection["mfaDuration"]),
        }
        _store_insert("mfa_records", pending)
        _log("auth-with-password", url, 401, record=record,
             collection=collection["name"], ip=ip)
        return _error(401, "Missing second auth factor.",
                      {"mfaId": pending["id"]})
    if mfa_id:
        denied = _consume_mfa(mfa_id, record, "password")
        if denied:
            return denied
    _log("auth-with-password", url, 200, record=record,
         collection=collection["name"], ip=ip)
    return _auth_response(record)


def _consume_mfa(mfa_id, record, method):
    pending = _store.table("mfa_records").get(mfa_id)
    if not pending or pending["recordRef"] != record["id"]:
        return _error(400, "Invalid or expired MFA session.",
                      {"mfaId": {"code": "mfa_not_found",
                                 "message": "Missing or expired MFA record."}})
    if pending["used"] or _expired(pending["expires"]):
        return _error(400, "Invalid or expired MFA session.",
                      {"mfaId": {"code": "mfa_expired",
                                 "message": "Missing or expired MFA record."}})
    if pending["method"] == method:
        # PocketBase requires the two factors to be *different* methods.
        return _error(400, "The second factor must differ from the first.",
                      {"mfaId": {"code": "mfa_same_method",
                                 "message": "Duplicated authentication method."}})
    _store.table("mfa_records").patch(mfa_id, {"used": True})
    return None


# ---------------------------------------------------------------------------
# auth-refresh, impersonate
# ---------------------------------------------------------------------------

def auth_refresh(collection_name, kind=GUEST, viewer=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    if kind == GUEST or not viewer:
        return _error(401, "The request requires valid record authorization "
                           "token to be set.")
    if viewer["collectionId"] != collection["id"]:
        return _error(403, "The authorized record model is not allowed to "
                           "perform this action.")
    _log("auth-refresh", f"/api/collections/{collection['name']}/auth-refresh",
         200, record=viewer, collection=collection["name"])
    return _auth_response(viewer)


def impersonate(collection_name, record_id, duration=None, kind=GUEST):
    """Mint a token for another record. Superusers only."""
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    if kind != SUPERUSER:
        return _error(403, "The request requires superuser authorization token "
                           "to be set.")
    record = _store.table("auth_records").get(record_id)
    if not record or record["collectionId"] != collection["id"]:
        return _error(404, "The requested resource wasn't found.")
    response = _auth_response(record)
    response["duration"] = int(duration or collection["authToken"])
    return response


# ---------------------------------------------------------------------------
# OTP
# ---------------------------------------------------------------------------

def request_otp(collection_name, email=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    if not collection["otpEnabled"]:
        return _error(400, "The collection is not configured to allow OTP "
                           "authentication.")
    if not email:
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "email",
                            "validation_required", "Missing required value.")
    record = _store.table("auth_records").find_one(
        lambda r: r["collectionId"] == collection["id"]
        and str(r["email"]).lower() == str(email).lower())
    request_id = _pb_id("otp")
    if not record:
        # PocketBase still returns an otpId for an unknown address, so the
        # response cannot be used to enumerate accounts.
        return {"otpId": request_id}
    code = _digits(request_id, collection["otpLength"])
    _store_insert("otp_requests", {
        "id": request_id, "collectionRef": collection["id"],
        "recordRef": record["id"], "email": record["email"], "password": code,
        "sentTo": record["email"], "used": False, "created": _now(),
        "expires": _in_seconds(collection["otpDuration"])})
    _log("request-otp", f"/api/collections/{collection['name']}/request-otp", 200)
    return {"otpId": request_id, "password": code,
            "note": "the one-time password is returned because no mail is "
                    "actually delivered by the mock"}


def _digits(seed, length):
    """Derive a stable numeric code from a seed string.

    `hash()` is salted per process, so codes derived from it would differ across
    restarts.
    """
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    return str(int(digest[:12], 16)).zfill(length)[-length:]


def auth_with_otp(collection_name, otp_id=None, password=None, mfa_id=None,
                  ip="203.0.113.41"):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    url = f"/api/collections/{collection['name']}/auth-with-otp"
    request = _store.table("otp_requests").get(otp_id) if otp_id else None
    if not request or request["collectionRef"] != collection["id"]:
        return _field_error(400, "Failed to authenticate.", "otpId",
                            "validation_invalid_otp_id",
                            "Invalid or expired OTP.")
    if request["used"] or _expired(request["expires"]):
        return _field_error(400, "Failed to authenticate.", "otpId",
                            "validation_expired_otp", "Invalid or expired OTP.")
    if password != request["password"]:
        return _field_error(400, "Failed to authenticate.", "password",
                            "validation_invalid_password",
                            "Invalid or expired OTP.")
    record = _store.table("auth_records").get(request["recordRef"])
    if not _auth_rule_allows(collection, record):
        return _error(403, "The request doesn't satisfy the collection "
                           "requirements to authenticate.")
    _store.table("otp_requests").patch(request["id"], {"used": True})
    if collection["mfaEnabled"] and record["mfaEnabled"] and not mfa_id:
        pending = {
            "id": _pb_id("mfa"), "collectionRef": collection["id"],
            "recordRef": record["id"], "method": "otp", "used": False,
            "created": _now(), "expires": _in_seconds(collection["mfaDuration"]),
        }
        _store_insert("mfa_records", pending)
        return _error(401, "Missing second auth factor.",
                      {"mfaId": pending["id"]})
    if mfa_id:
        denied = _consume_mfa(mfa_id, record, "otp")
        if denied:
            return denied
    # An OTP login confirms the address, exactly as PocketBase does.
    if not record["verified"]:
        record = _store.table("auth_records").patch(
            record["id"], {"verified": True, "updated": _now()})
    _log("auth-with-otp", url, 200, record=record, collection=collection["name"],
         ip=ip)
    return _auth_response(record)


# ---------------------------------------------------------------------------
# OAuth2
# ---------------------------------------------------------------------------

def auth_with_oauth2(collection_name, provider=None, code=None,
                     code_verifier=None, redirect_url=None, ip="203.0.113.41"):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    url = f"/api/collections/{collection['name']}/auth-with-oauth2"
    if not collection["oauth2Enabled"]:
        return _error(400, "The collection is not configured to allow OAuth2 "
                           "authentication.")
    registered = _store.table("oauth2_providers").get(provider) if provider else None
    if (not registered or not registered["enabled"]
            or provider not in collection["oauth2Providers"]):
        return _field_error(400, "An error occurred while submitting the form.",
                            "provider", "validation_invalid_provider",
                            "Missing or invalid provider.")
    if not code:
        return _field_error(400, "An error occurred while submitting the form.",
                            "code", "validation_required",
                            "Missing required value.")
    # The mock cannot talk to the provider, so the authorization code names the
    # external account: `<providerId>` for a linked one, anything else for a new
    # sign-up.
    link = _store.table("external_auths").find_one(
        lambda e: e["provider"] == provider and e["providerId"] == str(code)
        and e["collectionRef"] == collection["id"])
    is_new = link is None
    if link:
        record = _store.table("auth_records").get(link["recordRef"])
        _store.table("external_auths").patch(link["id"], {"updated": _now()})
    else:
        now = _now()
        record = {
            "id": _pb_id("usr"), "collectionId": collection["id"],
            "collectionName": collection["name"],
            "username": f"{provider}_{str(code)[:8]}",
            "email": f"{str(code)[:8]}@users.noreply.{provider}.com",
            "emailVisibility": False, "verified": True, "name": "", "avatar": "",
            "role": "support", "oncall": False,
            "passwordSalt": "", "passwordHash": "",
            "tokenKey": f"tk_{uuid.uuid4().hex[:12]}", "mfaEnabled": False,
            "lastResetSentAt": "", "lastVerificationSentAt": "",
            "created": now, "updated": now,
        }
        _store_insert("auth_records", record)
        _store_insert("external_auths", {
            "id": _pb_id("eah"), "collectionRef": collection["id"],
            "recordRef": record["id"], "provider": provider,
            "providerId": str(code), "created": now, "updated": now})
    if not _auth_rule_allows(collection, record):
        return _error(403, "The request doesn't satisfy the collection "
                           "requirements to authenticate.")
    _log("auth-with-oauth2", url, 200, record=record,
         collection=collection["name"], ip=ip)
    response = _auth_response(record)
    response["meta"] = {
        "id": str(code), "name": record["name"] or record["username"],
        "username": record["username"], "email": record["email"],
        "isNew": is_new, "avatarURL": "",
        "accessToken": f"gho_{uuid.uuid4().hex[:24]}",
        "refreshToken": "", "expiry": _in_seconds(28800),
        "rawUser": {"id": str(code), "login": record["username"]},
    }
    return response


def list_external_auths(collection_name, record_id, kind=GUEST, viewer=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    record = _store.table("auth_records").get(record_id)
    if not record or record["collectionId"] != collection["id"]:
        return _error(404, "The requested resource wasn't found.")
    if kind != SUPERUSER and (not viewer or viewer["id"] != record_id):
        return _error(403, "The authorized record model is not allowed to "
                           "perform this action.")
    return [e for e in _external_auths() if e["recordRef"] == record_id]


def unlink_external_auth(collection_name, record_id, provider, kind=GUEST,
                         viewer=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    record = _store.table("auth_records").get(record_id)
    if not record or record["collectionId"] != collection["id"]:
        return _error(404, "The requested resource wasn't found.")
    if kind != SUPERUSER and (not viewer or viewer["id"] != record_id):
        return _error(403, "The authorized record model is not allowed to "
                           "perform this action.")
    link = _store.table("external_auths").find_one(
        lambda e: e["recordRef"] == record_id and e["provider"] == provider)
    if not link:
        return _error(404, "The requested resource wasn't found.")
    remaining = [e for e in _external_auths()
                 if e["recordRef"] == record_id and e["id"] != link["id"]]
    if not remaining and not record["passwordHash"]:
        # Unlinking the only sign-in method would lock the record out for good.
        return _error(400, "Cannot unlink the last external auth provider from "
                           "a record without a password.")
    _store.table("external_auths").delete(link["id"])
    return {}


# ---------------------------------------------------------------------------
# Verification, password reset, email change
# ---------------------------------------------------------------------------

def _mint_mail_token(collection, record, token_type, new_email=""):
    ttl = {"verification": collection["verificationToken"],
           "passwordReset": collection["passwordResetToken"],
           "emailChange": collection["emailChangeToken"]}[token_type]
    prefix = {"verification": "verif", "passwordReset": "reset",
              "emailChange": "email"}[token_type]
    token = f"pb_{prefix}_{uuid.uuid4().hex[:16]}"
    _store_insert("mail_tokens", {
        "token": token, "type": token_type, "collectionRef": collection["id"],
        "recordRef": record["id"], "email": record["email"],
        "newEmail": new_email, "used": False, "created": _now(),
        "expires": _in_seconds(ttl)})
    return token


def _mail_token_or_error(token, token_type, collection):
    record_token = _store.table("mail_tokens").get(token) if token else None
    if (not record_token or record_token["type"] != token_type
            or record_token["collectionRef"] != collection["id"]):
        return None, _field_error(400, "An error occurred while validating the "
                                       "submitted data.", "token",
                                  "validation_invalid_token",
                                  "Invalid or expired token.")
    if record_token["used"] or _expired(record_token["expires"]):
        return None, _field_error(400, "An error occurred while validating the "
                                       "submitted data.", "token",
                                  "validation_expired_token",
                                  "Invalid or expired token.")
    return record_token, None


def request_verification(collection_name, email=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    if not email:
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "email",
                            "validation_required", "Missing required value.")
    record = _store.table("auth_records").find_one(
        lambda r: r["collectionId"] == collection["id"]
        and str(r["email"]).lower() == str(email).lower())
    if not record or record["verified"]:
        # Already verified or unknown: PocketBase answers 204 either way.
        return {"__status__": 204}
    _store.table("auth_records").patch(record["id"],
                                       {"lastVerificationSentAt": _now()})
    token = _mint_mail_token(collection, record, "verification")
    _log("request-verification",
         f"/api/collections/{collection['name']}/request-verification", 204)
    return {"__status__": 204, "token": token,
            "note": "the token is returned because no mail is actually "
                    "delivered by the mock"}


def confirm_verification(collection_name, token=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    record_token, denied = _mail_token_or_error(token, "verification", collection)
    if denied:
        return denied
    _store.table("mail_tokens").patch(token, {"used": True})
    _store.table("auth_records").patch(record_token["recordRef"],
                                       {"verified": True, "updated": _now()})
    return {"__status__": 204}


def request_password_reset(collection_name, email=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    if not email:
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "email",
                            "validation_required", "Missing required value.")
    record = _store.table("auth_records").find_one(
        lambda r: r["collectionId"] == collection["id"]
        and str(r["email"]).lower() == str(email).lower())
    if not record:
        return {"__status__": 204}
    _store.table("auth_records").patch(record["id"], {"lastResetSentAt": _now()})
    token = _mint_mail_token(collection, record, "passwordReset")
    _log("request-password-reset",
         f"/api/collections/{collection['name']}/request-password-reset", 204)
    return {"__status__": 204, "token": token,
            "note": "the token is returned because no mail is actually "
                    "delivered by the mock"}


def confirm_password_reset(collection_name, token=None, password=None,
                           password_confirm=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    record_token, denied = _mail_token_or_error(token, "passwordReset", collection)
    if denied:
        return denied
    denied = _validate_password(collection, password, password_confirm)
    if denied:
        return denied
    _store.table("mail_tokens").patch(token, {"used": True})
    _set_password(record_token["recordRef"], password)
    return {"__status__": 204}


def _validate_password(collection, password, password_confirm):
    if not password:
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "password",
                            "validation_required", "Missing required value.")
    if len(password) < collection["minPasswordLength"]:
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "password",
                            "validation_length_out_of_range",
                            f"The length must be at least "
                            f"{collection['minPasswordLength']} characters.")
    if password_confirm is not None and password != password_confirm:
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "passwordConfirm",
                            "validation_values_mismatch",
                            "Values don't match.")
    return None


def _set_password(record_id, password):
    """Set a password and rotate the token key, invalidating issued tokens."""
    salt = uuid.uuid4().hex[:16]
    return _store.table("auth_records").patch(record_id, {
        "passwordSalt": salt, "passwordHash": _hash_password(salt, password),
        "tokenKey": f"tk_{uuid.uuid4().hex[:12]}", "updated": _now()})


def request_email_change(collection_name, new_email=None, kind=GUEST,
                         viewer=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    if kind == GUEST or not viewer:
        return _error(401, "The request requires valid record authorization "
                           "token to be set.")
    if not new_email:
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "newEmail",
                            "validation_required", "Missing required value.")
    taken = _store.table("auth_records").find_one(
        lambda r: r["collectionId"] == collection["id"]
        and str(r["email"]).lower() == str(new_email).lower())
    if taken:
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "newEmail",
                            "validation_invalid_email",
                            "The email address is invalid or already in use.")
    token = _mint_mail_token(collection, viewer, "emailChange",
                             new_email=new_email)
    return {"__status__": 204, "token": token,
            "note": "the token is returned because no mail is actually "
                    "delivered by the mock"}


def confirm_email_change(collection_name, token=None, password=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    record_token, denied = _mail_token_or_error(token, "emailChange", collection)
    if denied:
        return denied
    record = _store.table("auth_records").get(record_token["recordRef"])
    # PocketBase re-checks the password here: an email change is the one action
    # a stolen token alone must not complete.
    if (not record["passwordHash"]
            or _hash_password(record["passwordSalt"], password or "")
            != record["passwordHash"]):
        return _field_error(400, "An error occurred while validating the "
                                 "submitted data.", "password",
                            "validation_invalid_password",
                            "Missing or invalid password.")
    _store.table("mail_tokens").patch(token, {"used": True})
    _store.table("auth_records").patch(record["id"], {
        "email": record_token["newEmail"], "verified": True,
        "tokenKey": f"tk_{uuid.uuid4().hex[:12]}", "updated": _now()})
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Auth records CRUD
# ---------------------------------------------------------------------------

def list_records(collection_name, page=1, per_page=30, filter_role=None,
                 verified=None, kind=GUEST, viewer=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    if collection["name"] == SUPERUSER_COLLECTION and kind != SUPERUSER:
        return _error(403, "The request requires superuser authorization token "
                           "to be set.")
    if kind == GUEST:
        # `users` carries listRule = @auth in this instance.
        return _error(403, "The request requires valid record authorization "
                           "token to be set.")
    rows = [r for r in _records() if r["collectionId"] == collection["id"]]
    if filter_role:
        rows = [r for r in rows if r["role"] == filter_role]
    if verified is not None:
        rows = [r for r in rows if r["verified"] == verified]
    per_page = max(1, min(int(per_page or 30), 500))
    page = max(1, int(page or 1))
    start = (page - 1) * per_page
    total = len(rows)
    items = [public_record(r, viewer_kind=kind, viewer=viewer)
             for r in rows[start:start + per_page]]
    return {"page": page, "perPage": per_page, "totalItems": total,
            "totalPages": (total + per_page - 1) // per_page if per_page else 0,
            "items": items}


def get_record(collection_name, record_id, kind=GUEST, viewer=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    if collection["name"] == SUPERUSER_COLLECTION and kind != SUPERUSER:
        return _error(403, "The request requires superuser authorization token "
                           "to be set.")
    if kind == GUEST:
        return _error(403, "The request requires valid record authorization "
                           "token to be set.")
    record = _store.table("auth_records").get(record_id)
    if not record or record["collectionId"] != collection["id"]:
        return _error(404, "The requested resource wasn't found.")
    return public_record(record, viewer_kind=kind, viewer=viewer)


def create_record(collection_name, body, kind=GUEST):
    """Sign-up. `users` allows it publicly; `_superusers` needs a superuser."""
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    body = body or {}
    if collection["name"] == SUPERUSER_COLLECTION and kind != SUPERUSER:
        return _error(403, "The request requires superuser authorization token "
                           "to be set.")
    email = body.get("email")
    if collection["requireEmail"] and not email:
        return _field_error(400, "Failed to create record.", "email",
                            "validation_required", "Missing required value.")
    if email and _store.table("auth_records").find_one(
            lambda r: r["collectionId"] == collection["id"]
            and str(r["email"]).lower() == str(email).lower()):
        return _field_error(400, "Failed to create record.", "email",
                            "validation_not_unique",
                            "Value must be unique.")
    username = body.get("username", "")
    if username and _store.table("auth_records").find_one(
            lambda r: r["collectionId"] == collection["id"]
            and r["username"] == username):
        return _field_error(400, "Failed to create record.", "username",
                            "validation_not_unique", "Value must be unique.")
    denied = _validate_password(collection, body.get("password"),
                                body.get("passwordConfirm"))
    if denied:
        return denied
    now = _now()
    salt = uuid.uuid4().hex[:16]
    record = {
        "id": _pb_id("usr" if collection["name"] != SUPERUSER_COLLECTION else "sup"),
        "collectionId": collection["id"], "collectionName": collection["name"],
        "username": username, "email": email or "",
        "emailVisibility": bool(body.get("emailVisibility", False)),
        "verified": False, "name": body.get("name", ""), "avatar": "",
        "role": body.get("role", "support"), "oncall": False,
        "passwordSalt": salt,
        "passwordHash": _hash_password(salt, body["password"]),
        "tokenKey": f"tk_{uuid.uuid4().hex[:12]}", "mfaEnabled": False,
        "lastResetSentAt": "", "lastVerificationSentAt": "",
        "created": now, "updated": now,
    }
    _store_insert("auth_records", record)
    return public_record(record, viewer_kind=SUPERUSER)


def update_record(collection_name, record_id, body, kind=GUEST, viewer=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    record = _store.table("auth_records").get(record_id)
    if not record or record["collectionId"] != collection["id"]:
        return _error(404, "The requested resource wasn't found.")
    is_self = viewer is not None and viewer["id"] == record_id
    if kind != SUPERUSER and not is_self:
        return _error(403, "The authorized record model is not allowed to "
                           "perform this action.")
    body = body or {}
    patch = {"updated": _now()}
    for field in ("name", "avatar", "username"):
        if field in body:
            patch[field] = body[field]
    if "emailVisibility" in body:
        patch["emailVisibility"] = bool(body["emailVisibility"])
    if "role" in body or "verified" in body:
        # PocketBase gates the fields the manageRule protects: a record may not
        # promote itself or mark itself verified.
        if kind != SUPERUSER:
            return _error(403, "The authorized record model is not allowed to "
                               "perform this action.")
        if "role" in body:
            patch["role"] = body["role"]
        if "verified" in body:
            patch["verified"] = bool(body["verified"])
    if "password" in body:
        if kind != SUPERUSER:
            if not body.get("oldPassword"):
                return _field_error(400, "Failed to update record.",
                                    "oldPassword", "validation_required",
                                    "Missing required value.")
            if (_hash_password(record["passwordSalt"], body["oldPassword"])
                    != record["passwordHash"]):
                return _field_error(400, "Failed to update record.",
                                    "oldPassword",
                                    "validation_invalid_old_password",
                                    "Missing or invalid old password.")
        denied = _validate_password(collection, body["password"],
                                    body.get("passwordConfirm"))
        if denied:
            return denied
        _set_password(record_id, body["password"])
        record = _store.table("auth_records").get(record_id)
    updated = _store.table("auth_records").patch(record_id, patch)
    return public_record(updated, viewer_kind=kind, viewer=viewer)


def delete_record(collection_name, record_id, kind=GUEST, viewer=None):
    collection, err = _collection_or_error(collection_name)
    if err:
        return err
    record = _store.table("auth_records").get(record_id)
    if not record or record["collectionId"] != collection["id"]:
        return _error(404, "The requested resource wasn't found.")
    is_self = viewer is not None and viewer["id"] == record_id
    if kind != SUPERUSER and not is_self:
        return _error(403, "The authorized record model is not allowed to "
                           "perform this action.")
    if record["collectionName"] == SUPERUSER_COLLECTION:
        remaining = [r for r in _records()
                     if r["collectionName"] == SUPERUSER_COLLECTION
                     and r["id"] != record_id]
        if not remaining:
            return _error(400, "You can't delete the only existing superuser.")
    _store.table("external_auths").delete_where(
        lambda e: e["recordRef"] == record_id)
    _store.table("otp_requests").delete_where(
        lambda o: o["recordRef"] == record_id)
    _store.table("mail_tokens").delete_where(
        lambda t: t["recordRef"] == record_id)
    _store.table("auth_records").delete(record_id)
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------

def list_logs(page=1, per_page=30, auth_id=None, status=None, kind=GUEST):
    if kind != SUPERUSER:
        return _error(403, "The request requires superuser authorization token "
                           "to be set.")
    rows = _logs()
    if auth_id:
        rows = [r for r in rows if r["authId"] == auth_id]
    if status is not None:
        rows = [r for r in rows if r["status"] == int(status)]
    rows.sort(key=lambda r: r["created"], reverse=True)
    per_page = max(1, min(int(per_page or 30), 500))
    page = max(1, int(page or 1))
    start = (page - 1) * per_page
    total = len(rows)
    return {"page": page, "perPage": per_page, "totalItems": total,
            "totalPages": (total + per_page - 1) // per_page if per_page else 0,
            "items": rows[start:start + per_page]}


def logs_stats(kind=GUEST):
    if kind != SUPERUSER:
        return _error(403, "The request requires superuser authorization token "
                           "to be set.")
    buckets = {}
    for row in _logs():
        buckets[row["message"]] = buckets.get(row["message"], 0) + 1
    return [{"total": total, "date": "", "message": message}
            for message, total in sorted(buckets.items())]


_store.eager_load()
