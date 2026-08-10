"""Data access module for the Supabase Auth (GoTrue) mock service.

Models the GoTrue component of the same self-hosted Supabase project that
`supabase-api` serves: identical `anon` / `service_role` keys, and `auth.users`
ids that match the `public.profiles` rows there, so the two services describe one
system.

Password verification is real -- `sha256(password_salt + password)` against
`users.json`; the hash is never returned by the API. The seed carries the failure
modes that matter for an auth service: an unconfirmed email, a banned account, an
OAuth-only identity with no password, a verified TOTP factor and an unverified
one, and an anonymous user. Mutations are held in process memory and reset on
restart.
"""

import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("supabase-auth-api")
_API = "supabase-auth-api"


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


def _load_settings():
    with open(DATA_DIR / "settings.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json", "users")))
_store.register("identities", primary_key="id",
                initial_loader=lambda: _coerce_identities(_load("identities.json", "identities")))
_store.register("mfa_factors", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in _load("mfa_factors.json", "mfa_factors")])
_store.register("audit_log", primary_key="id",
                initial_loader=lambda: _coerce_audit(_load("audit_log.json", "audit_log")))
_store.register_document("settings", initial_loader=_load_settings)
# Live session state. Seeded rather than born-empty so the collection can quote
# a bearer token literally: the harness substitutes variables in the URL and
# body but not in headers, and a token minted at runtime cannot be referenced.
_store.register("sessions", primary_key="id",
                initial_loader=lambda: _coerce_flags(
                    _load("sessions.json", "sessions"), ("revoked",)))
_store.register("refresh_tokens", primary_key="token",
                initial_loader=lambda: _coerce_flags(
                    _load("refresh_tokens.json", "refresh_tokens"), ("revoked",)))
_store.register("one_time_tokens", primary_key="token",
                initial_loader=lambda: _coerce_flags(
                    _load("one_time_tokens.json", "one_time_tokens"), ("used",)))
_store.register("mfa_challenges", primary_key="id",
                initial_loader=lambda: _coerce_flags(
                    _load("mfa_challenges.json", "mfa_challenges"), ("verified",)))


def _users_rows():
    return _store.table("users").rows()


def _identities_rows():
    return _store.table("identities").rows()


def _factors_rows():
    return _store.table("mfa_factors").rows()


def _audit_rows():
    return _store.table("audit_log").rows()


def _sessions_rows():
    return _store.table("sessions").rows()


def _one_time_tokens_rows():
    return _store.table("one_time_tokens").rows()


def _settings_doc():
    return _store.document("settings").get()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _blank_to_none(row, column):
    value = opt_str(row, column, default="")
    return value if value else None


def _semi_list(row, column):
    raw = opt_str(row, column, default="")
    return [part for part in raw.split(";") if part]


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

_NULLABLE_USER_FIELDS = ("email_confirmed_at", "phone_confirmed_at",
                         "confirmation_sent_at", "recovery_sent_at",
                         "last_sign_in_at", "banned_until", "deleted_at")


def _coerce_users(rows):
    out = []
    for r in rows:
        out.append({
            **_strip_ctx(r),
            **{f: _blank_to_none(r, f) for f in _NULLABLE_USER_FIELDS},
            "is_anonymous": bool(opt_int(r, "is_anonymous", default=0)),
            "is_sso_user": bool(opt_int(r, "is_sso_user", default=0)),
            "app_metadata_providers": _semi_list(r, "app_metadata_providers"),
        })
    return out


def _coerce_identities(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "last_sign_in_at": _blank_to_none(r, "last_sign_in_at")} for r in rows]


def _coerce_audit(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0)} for r in rows]


def _coerce_flags(rows, flags):
    """Turn the seed's "0"/"1" cells back into booleans."""
    return [{**_strip_ctx(r),
             **{f: bool(opt_int(r, f, default=0)) for f in flags}} for r in rows]


# ---------------------------------------------------------------------------
# Errors -- GoTrue v2 shape
# ---------------------------------------------------------------------------

def _error(status, error_code, message):
    """GoTrue returns `{code, error_code, msg}` with the HTTP status in `code`."""
    return {"error": message, "code": status, "error_code": error_code,
            "msg": message, "status": status}


# ---------------------------------------------------------------------------
# Keys and tokens
# ---------------------------------------------------------------------------

ANON = "anon"
SERVICE_ROLE = "service_role"


def resolve_key(apikey=None, authorization=None):
    """Map the `apikey` header onto the project role.

    Mirrors `supabase-api`: absent or the anon key is `anon`, the service key is
    `service_role`, and any other token is accepted as `anon` so a request is
    never rejected purely for carrying an unfamiliar key.
    """
    token = (apikey or "").strip()
    if not token and authorization:
        raw = str(authorization).strip()
        if raw.lower().startswith("bearer "):
            token = raw[7:].strip()
    keys = _settings_doc()["keys"]
    return SERVICE_ROLE if token == keys["service_role"] else ANON


def _bearer(authorization):
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def resolve_session(authorization=None):
    """Resolve a bearer access token to its live session row."""
    token = _bearer(authorization)
    if not token:
        return None
    keys = _settings_doc()["keys"]
    if token in (keys["anon"], keys["service_role"]):
        return None
    return _store.table("sessions").find_one(lambda s: s["access_token"] == token)


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def _six_digits(seed):
    """Derive a stable six-digit code from a seed string.

    `hash()` is salted per process, so deriving codes from it would make the
    same token produce different OTPs across restarts.
    """
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    return f"{int(digest[:8], 16) % 1000000:06d}"


def _issue_session(user, aal="aal1", provider="email", ip="203.0.113.41",
                   user_agent="orbit-app/4.8.1"):
    settings = _settings_doc()
    now = _now()
    expires_in = settings["jwt"]["exp_seconds"]
    session = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "access_token": f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{uuid.uuid4().hex}.sig",
        "refresh_token": uuid.uuid4().hex[:24],
        "aal": aal,
        "provider": provider,
        "created_at": now,
        "refreshed_at": now,
        "not_after": _in_seconds(expires_in),
        "ip": ip,
        "user_agent": user_agent,
        "revoked": False,
    }
    _store_insert("sessions", session)
    _store.table("refresh_tokens").upsert({
        "token": session["refresh_token"], "session_id": session["id"],
        "user_id": user["id"], "revoked": False, "parent": None,
        "created_at": now,
    })
    _store.table("users").patch(user["id"], {"last_sign_in_at": now,
                                             "updated_at": now})
    _record_audit("login", user, provider, ip)
    return _session_payload(session, _store.table("users").get(user["id"]))


def _in_seconds(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_payload(session, user):
    settings = _settings_doc()
    return {
        "access_token": session["access_token"],
        "token_type": "bearer",
        "expires_in": settings["jwt"]["exp_seconds"],
        "expires_at": int(time.time()) + settings["jwt"]["exp_seconds"],
        "refresh_token": session["refresh_token"],
        "user": public_user(user),
    }


def public_user(user):
    """The user object GoTrue returns. The password hash never appears."""
    if not user:
        return None
    identities = [
        {"identity_id": i["identity_id"], "id": i["provider_id"],
         "user_id": i["user_id"], "provider": i["provider"],
         "identity_data": {"email": i["email"], "sub": i["provider_id"]},
         "last_sign_in_at": i["last_sign_in_at"], "created_at": i["created_at"]}
        for i in _identities_rows() if i["user_id"] == user["id"]]
    return {
        "id": user["id"],
        "aud": user["aud"],
        "role": user["role"],
        "email": user["email"],
        "phone": user["phone"],
        "email_confirmed_at": user["email_confirmed_at"],
        "phone_confirmed_at": user["phone_confirmed_at"],
        "confirmed_at": user["email_confirmed_at"] or user["phone_confirmed_at"],
        "last_sign_in_at": user["last_sign_in_at"],
        "banned_until": user["banned_until"],
        "is_anonymous": user["is_anonymous"],
        "is_sso_user": user["is_sso_user"],
        "app_metadata": {"provider": user["app_metadata_provider"],
                         "providers": user["app_metadata_providers"]},
        "user_metadata": {k: v for k, v in
                          (("full_name", user["user_metadata_full_name"]),
                           ("role", user["user_metadata_role"])) if v},
        "identities": identities,
        "factors": [{"id": f["id"], "friendly_name": f["friendly_name"],
                     "factor_type": f["factor_type"], "status": f["status"],
                     "created_at": f["created_at"], "updated_at": f["updated_at"]}
                    for f in _factors_rows() if f["user_id"] == user["id"]],
        "created_at": user["created_at"],
        "updated_at": user["updated_at"],
    }


def _record_audit(action, user, provider, ip, log_type="account"):
    rows = _audit_rows()
    entry = {
        "id": (max((r["id"] for r in rows), default=0) + 1),
        "action": action,
        "actor_id": user["id"] if user else "",
        "actor_username": (user or {}).get("email", ""),
        "log_type": log_type,
        "traits_provider": provider,
        "ip_address": ip,
        "created_at": _now(),
    }
    _store_insert("audit_log", entry)
    return entry


def _is_banned(user):
    until = user.get("banned_until")
    if not until:
        return False
    try:
        return datetime.strptime(until, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc) > datetime.now(timezone.utc)
    except ValueError:
        return False


def _find_user(email=None, phone=None, user_id=None):
    if user_id:
        return _store.table("users").get(user_id)
    if email:
        return _store.table("users").find_one(
            lambda u: (u["email"] or "").lower() == str(email).lower()
            and not u["deleted_at"])
    if phone:
        return _store.table("users").find_one(
            lambda u: u["phone"] == phone and not u["deleted_at"])
    return None


# ---------------------------------------------------------------------------
# Health and settings
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def gotrue_health():
    settings = _settings_doc()
    return {"version": settings["gotrue_version"], "name": settings["name"],
            "description": settings["description"]}


def get_settings():
    settings = _settings_doc()
    return {
        "external": settings["external"],
        "disable_signup": settings["disable_signup"],
        "mailer_autoconfirm": settings["mailer_autoconfirm"],
        "phone_autoconfirm": settings["phone_autoconfirm"],
        "sms_provider": settings["sms_provider"],
        "mfa_enabled": settings["mfa_enabled"],
        "saml_enabled": settings["saml_enabled"],
        "security": settings["security"],
    }


# ---------------------------------------------------------------------------
# Sign up / sign in
# ---------------------------------------------------------------------------

def sign_up(email=None, phone=None, password=None, data=None,
            ip="203.0.113.41"):
    settings = _settings_doc()
    if settings["disable_signup"]:
        return _error(422, "signup_disabled", "Signups not allowed for this instance")
    if not email and not phone:
        return _error(422, "validation_failed",
                      "To signup, please provide your email or phone number")
    if not password or len(password) < 6:
        return _error(422, "weak_password",
                      "Password should be at least 6 characters")
    if _find_user(email=email, phone=phone):
        return _error(422, "user_already_exists", "User already registered")
    now = _now()
    salt = uuid.uuid4().hex[:16]
    user = {
        "id": str(uuid.uuid4()),
        "aud": "authenticated",
        "role": "authenticated",
        "email": email or "",
        "phone": phone or "",
        "password_salt": salt,
        "password_hash": _hash_password(salt, password),
        "email_confirmed_at": now if settings["mailer_autoconfirm"] else None,
        "phone_confirmed_at": None,
        "confirmation_sent_at": now,
        "recovery_sent_at": None,
        "last_sign_in_at": None,
        "banned_until": None,
        "deleted_at": None,
        "is_anonymous": False,
        "is_sso_user": False,
        "app_metadata_provider": "email" if email else "phone",
        "app_metadata_providers": ["email" if email else "phone"],
        "user_metadata_full_name": (data or {}).get("full_name", ""),
        "user_metadata_role": (data or {}).get("role", ""),
        "created_at": now,
        "updated_at": now,
    }
    _store_insert("users", user)
    _store_insert("identities", {
        "id": max((i["id"] for i in _identities_rows()), default=0) + 1,
        "user_id": user["id"], "identity_id": str(uuid.uuid4()),
        "provider": user["app_metadata_provider"],
        "provider_id": user["id"], "email": user["email"],
        "last_sign_in_at": None, "created_at": now})
    _record_audit("user_signedup", user, user["app_metadata_provider"], ip,
                  log_type="team")
    if not settings["mailer_autoconfirm"]:
        _mint_one_time_token(user, "confirmation")
        # GoTrue returns the user with no session until the email is confirmed.
        return {"user": public_user(user), "session": None}
    return _issue_session(user, provider=user["app_metadata_provider"], ip=ip)


def sign_in_password(email=None, phone=None, password=None, ip="203.0.113.41"):
    user = _find_user(email=email, phone=phone)
    if not user or not user["password_hash"]:
        # An OAuth-only account has no password identity; GoTrue reports the
        # same generic failure so the response cannot enumerate accounts.
        return _error(400, "invalid_credentials", "Invalid login credentials")
    if _hash_password(user["password_salt"], password or "") != user["password_hash"]:
        return _error(400, "invalid_credentials", "Invalid login credentials")
    if _is_banned(user):
        return _error(403, "user_banned", "User is banned")
    if not user["email_confirmed_at"] and not user["phone_confirmed_at"]:
        return _error(400, "email_not_confirmed", "Email not confirmed")
    aal = "aal1"
    session = _issue_session(user, aal=aal, ip=ip)
    verified = [f for f in _factors_rows()
                if f["user_id"] == user["id"] and f["status"] == "verified"]
    if verified:
        session["weak_password"] = None
        session["mfa"] = {
            "current_level": "aal1", "next_level": "aal2",
            "current_authentication_methods": [{"method": "password"}],
            "factors": [{"id": f["id"], "friendly_name": f["friendly_name"],
                         "factor_type": f["factor_type"]} for f in verified],
            "note": "a verified factor is enrolled; challenge and verify it to "
                    "reach aal2",
        }
    return session


def sign_in_anonymous(ip="203.0.113.41"):
    settings = _settings_doc()
    if not settings["external"]["anonymous_users"]:
        return _error(422, "anonymous_provider_disabled",
                      "Anonymous sign-ins are disabled")
    now = _now()
    user = {
        "id": str(uuid.uuid4()), "aud": "authenticated", "role": "authenticated",
        "email": "", "phone": "", "password_salt": "", "password_hash": "",
        "email_confirmed_at": None, "phone_confirmed_at": None,
        "confirmation_sent_at": None, "recovery_sent_at": None,
        "last_sign_in_at": None, "banned_until": None, "deleted_at": None,
        "is_anonymous": True, "is_sso_user": False,
        "app_metadata_provider": "anonymous",
        "app_metadata_providers": ["anonymous"],
        "user_metadata_full_name": "", "user_metadata_role": "",
        "created_at": now, "updated_at": now,
    }
    _store_insert("users", user)
    return _issue_session(user, provider="anonymous", ip=ip)


def refresh(refresh_token=None, ip="203.0.113.41"):
    record = _store.table("refresh_tokens").get(refresh_token)
    if not record or record["revoked"]:
        return _error(400, "refresh_token_not_found", "Invalid Refresh Token: "
                      "Refresh Token Not Found")
    user = _store.table("users").get(record["user_id"])
    if not user or _is_banned(user):
        return _error(403, "user_banned", "User is banned")
    session = _store.table("sessions").get(record["session_id"])
    settings = _settings_doc()
    if settings["security"]["refresh_token_rotation_enabled"]:
        # Rotation: the presented token is revoked and a descendant is issued.
        _store.table("refresh_tokens").patch(refresh_token, {"revoked": True})
        rotated = uuid.uuid4().hex[:24]
        _store.table("refresh_tokens").upsert({
            "token": rotated, "session_id": session["id"], "user_id": user["id"],
            "revoked": False, "parent": refresh_token, "created_at": _now()})
        session = _store.table("sessions").patch(session["id"], {
            "refresh_token": rotated, "refreshed_at": _now(),
            "access_token": f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                            f"{uuid.uuid4().hex}.sig",
            "not_after": _in_seconds(settings["jwt"]["exp_seconds"])})
    return _session_payload(session, user)


def sign_out(authorization=None, scope="global"):
    session = resolve_session(authorization)
    if not session:
        return _error(401, "no_authorization", "This endpoint requires a Bearer "
                      "token")
    user = _store.table("users").get(session["user_id"])
    if scope == "global":
        removed = _store.table("sessions").delete_where(
            lambda s: s["user_id"] == session["user_id"])
        _store.table("refresh_tokens").delete_where(
            lambda t: t["user_id"] == session["user_id"])
    else:
        removed = 1 if _store.table("sessions").delete(session["id"]) else 0
        _store.table("refresh_tokens").delete_where(
            lambda t: t["session_id"] == session["id"])
    _record_audit("logout", user, session["provider"], session["ip"])
    return {"signed_out": True, "scope": scope, "sessions_revoked": removed}


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

def get_user(authorization=None):
    session = resolve_session(authorization)
    if not session:
        return _error(401, "no_authorization",
                      "This endpoint requires a Bearer token")
    user = _store.table("users").get(session["user_id"])
    if not user:
        return _error(404, "user_not_found", "User from sub claim in JWT does "
                      "not exist")
    return public_user(user)


def update_user(authorization=None, email=None, phone=None, password=None,
                data=None):
    session = resolve_session(authorization)
    if not session:
        return _error(401, "no_authorization",
                      "This endpoint requires a Bearer token")
    user = _store.table("users").get(session["user_id"])
    patch = {"updated_at": _now()}
    if email and email != user["email"]:
        if _find_user(email=email):
            return _error(422, "email_exists", "A user with this email address "
                          "has already been registered")
        # GoTrue keeps the old address until the new one is confirmed.
        patch["confirmation_sent_at"] = _now()
        _mint_one_time_token(user, "email_change", email)
    if phone:
        patch["phone"] = phone
    if password:
        if len(password) < 6:
            return _error(422, "weak_password",
                          "Password should be at least 6 characters")
        salt = uuid.uuid4().hex[:16]
        patch["password_salt"] = salt
        patch["password_hash"] = _hash_password(salt, password)
    for key, value in (data or {}).items():
        if key == "full_name":
            patch["user_metadata_full_name"] = value
        elif key == "role":
            patch["user_metadata_role"] = value
    updated = _store.table("users").patch(user["id"], patch)
    _record_audit("user_updated_password" if password else "user_modified",
                  updated, session["provider"], session["ip"], log_type="user")
    return public_user(updated)


# ---------------------------------------------------------------------------
# One-time tokens: recovery, magic link, OTP, verification
# ---------------------------------------------------------------------------

_TOKEN_TYPES = ("confirmation", "recovery", "magiclink", "email_change",
                "invite", "sms")


def _mint_one_time_token(user, token_type, new_email=None):
    settings = _settings_doc()
    token = uuid.uuid4().hex
    otp = _six_digits(token)
    record = {
        "token": token,
        "otp": otp,
        "user_id": user["id"],
        "token_type": token_type,
        "email": new_email or user["email"],
        "created_at": _now(),
        "expires_at": _in_seconds(settings["security"]["otp_expiry_seconds"]),
        "used": False,
    }
    _store_insert("one_time_tokens", record)
    return record


def recover(email=None, ip="203.0.113.41"):
    user = _find_user(email=email)
    if user:
        _store.table("users").patch(user["id"], {"recovery_sent_at": _now()})
        token = _mint_one_time_token(user, "recovery")
        _record_audit("user_recovery_requested", user, "email", ip,
                      log_type="user")
        return {"message": "Recovery email sent", "email": email,
                "otp": token["otp"], "token": token["token"],
                "note": "the OTP and token are returned because no mail is "
                        "actually delivered by the mock"}
    # GoTrue answers 200 for an unknown address so it cannot enumerate accounts.
    return {"message": "Recovery email sent", "email": email}


def magic_link(email=None, ip="203.0.113.41"):
    user = _find_user(email=email)
    if not user:
        return {"message": "Magic link sent", "email": email}
    token = _mint_one_time_token(user, "magiclink")
    _record_audit("user_recovery_requested", user, "magiclink", ip,
                  log_type="user")
    return {"message": "Magic link sent", "email": email, "otp": token["otp"],
            "token": token["token"]}


def send_otp(email=None, phone=None, ip="203.0.113.41"):
    user = _find_user(email=email, phone=phone)
    if not user:
        settings = _settings_doc()
        if settings["disable_signup"]:
            return _error(422, "otp_disabled", "Signups not allowed for otp")
        return {"message": "OTP sent", "email": email, "phone": phone}
    token = _mint_one_time_token(user, "sms" if phone else "magiclink")
    return {"message": "OTP sent", "email": email, "phone": phone,
            "otp": token["otp"], "token": token["token"]}


def verify(token_type=None, token=None, otp=None, email=None, ip="203.0.113.41"):
    if token_type not in _TOKEN_TYPES:
        return _error(400, "validation_failed",
                      f"Verify requires a token type of one of "
                      f"{', '.join(_TOKEN_TYPES)}")
    record = None
    if token:
        record = _store.table("one_time_tokens").get(token)
    elif otp and email:
        record = _store.table("one_time_tokens").find_one(
            lambda t: t["otp"] == otp and (t["email"] or "").lower()
            == str(email).lower())
    if not record or record["used"] or record["token_type"] != token_type:
        return _error(403, "otp_expired", "Token has expired or is invalid")
    user = _store.table("users").get(record["user_id"])
    _store.table("one_time_tokens").patch(record["token"], {"used": True})
    now = _now()
    if token_type == "confirmation":
        _store.table("users").patch(user["id"], {"email_confirmed_at": now,
                                                 "updated_at": now})
    elif token_type == "email_change":
        _store.table("users").patch(user["id"], {"email": record["email"],
                                                 "email_confirmed_at": now,
                                                 "updated_at": now})
    elif token_type == "sms":
        _store.table("users").patch(user["id"], {"phone_confirmed_at": now,
                                                 "updated_at": now})
    user = _store.table("users").get(user["id"])
    _record_audit("user_confirmation_requested" if token_type == "confirmation"
                  else "token_verified", user, token_type, ip, log_type="user")
    return _issue_session(user, provider=token_type, ip=ip)


def resend(token_type=None, email=None, phone=None):
    if token_type not in ("signup", "email_change", "sms", "phone_change"):
        return _error(400, "validation_failed",
                      "Resend requires a type of signup, email_change, sms or "
                      "phone_change")
    settings = _settings_doc()
    user = _find_user(email=email, phone=phone)
    if not user:
        return {"message": "Confirmation resent"}
    if user["email_confirmed_at"] and token_type == "signup":
        return _error(422, "email_address_already_confirmed",
                      "Email address already confirmed")
    token = _mint_one_time_token(
        user, "confirmation" if token_type == "signup" else token_type)
    return {"message": "Confirmation resent", "otp": token["otp"],
            "token": token["token"],
            "max_frequency_seconds": settings["security"]["max_frequency_seconds"]}


def authorize(provider=None, redirect_to=None):
    settings = _settings_doc()
    if not provider:
        return _error(400, "validation_failed", "Provider is required")
    if not settings["external"].get(provider):
        return _error(400, "provider_disabled",
                      f"Unsupported provider: provider is not enabled")
    state = uuid.uuid4().hex
    target = redirect_to or settings["site_url"]
    return {"provider": provider, "state": state,
            "url": f"https://{provider}.example.com/login/oauth/authorize"
                   f"?client_id=orbit-labs&state={state}"
                   f"&redirect_uri={settings['jwt']['issuer']}/callback",
            "redirect_to": target,
            "note": "the mock returns the URL rather than issuing a 302 so the "
                    "flow stays inspectable"}


# ---------------------------------------------------------------------------
# MFA
# ---------------------------------------------------------------------------

def enroll_factor(authorization=None, factor_type="totp", friendly_name=None):
    session = resolve_session(authorization)
    if not session:
        return _error(401, "no_authorization",
                      "This endpoint requires a Bearer token")
    if factor_type != "totp":
        return _error(422, "validation_failed",
                      "factor_type must be totp")
    user = _store.table("users").get(session["user_id"])
    existing = [f for f in _factors_rows()
                if f["user_id"] == user["id"]
                and f["friendly_name"] == (friendly_name or "")]
    if existing:
        return _error(422, "mfa_factor_name_conflict",
                      "A factor with the friendly name already exists")
    now = _now()
    factor = {
        "id": str(uuid.uuid4()), "user_id": user["id"],
        "friendly_name": friendly_name or "Authenticator", "factor_type": "totp",
        "status": "unverified",
        "verification_code": _six_digits(user["id"]),
        "secret": "JBSWY3DPEHPK3PXP", "created_at": now, "updated_at": now,
    }
    _store_insert("mfa_factors", factor)
    return {"id": factor["id"], "type": "totp",
            "friendly_name": factor["friendly_name"],
            "totp": {"qr_code": f"otpauth://totp/OrbitLabs:{user['email']}"
                                f"?secret={factor['secret']}&issuer=OrbitLabs",
                     "secret": factor["secret"],
                     "uri": f"otpauth://totp/OrbitLabs:{user['email']}"
                            f"?secret={factor['secret']}"},
            "verification_code": factor["verification_code"],
            "note": "the verification code is returned because no authenticator "
                    "app is actually enrolled"}


def challenge_factor(factor_id, authorization=None):
    session = resolve_session(authorization)
    if not session:
        return _error(401, "no_authorization",
                      "This endpoint requires a Bearer token")
    factor = _store.table("mfa_factors").get(factor_id)
    if not factor or factor["user_id"] != session["user_id"]:
        return _error(404, "mfa_factor_not_found", "MFA factor not found")
    settings = _settings_doc()
    challenge = {
        "id": str(uuid.uuid4()), "factor_id": factor_id,
        "user_id": session["user_id"], "created_at": _now(),
        "expires_at": _in_seconds(settings["security"]["otp_expiry_seconds"]),
        "verified": False,
    }
    _store_insert("mfa_challenges", challenge)
    return {"id": challenge["id"], "type": factor["factor_type"],
            "expires_at": challenge["expires_at"],
            "expected_code": factor["verification_code"],
            "note": "the expected code is returned because no authenticator app "
                    "is actually enrolled"}


def verify_factor(factor_id, challenge_id=None, code=None, authorization=None,
                  ip="203.0.113.41"):
    session = resolve_session(authorization)
    if not session:
        return _error(401, "no_authorization",
                      "This endpoint requires a Bearer token")
    factor = _store.table("mfa_factors").get(factor_id)
    if not factor or factor["user_id"] != session["user_id"]:
        return _error(404, "mfa_factor_not_found", "MFA factor not found")
    challenge = _store.table("mfa_challenges").get(challenge_id) if challenge_id \
        else None
    if not challenge or challenge["factor_id"] != factor_id:
        return _error(404, "mfa_challenge_not_found", "MFA challenge not found")
    if code != factor["verification_code"]:
        return _error(400, "mfa_verification_failed", "Invalid TOTP code entered")
    now = _now()
    _store.table("mfa_challenges").patch(challenge_id, {"verified": True})
    if factor["status"] != "verified":
        _store.table("mfa_factors").patch(factor_id, {"status": "verified",
                                                      "updated_at": now})
    user = _store.table("users").get(session["user_id"])
    _store.table("sessions").patch(session["id"], {"aal": "aal2"})
    _record_audit("factor_verified", user, "totp", ip, log_type="factor")
    elevated = _store.table("sessions").get(session["id"])
    payload = _session_payload(elevated, user)
    payload["aal"] = "aal2"
    return payload


def unenroll_factor(factor_id, authorization=None):
    session = resolve_session(authorization)
    if not session:
        return _error(401, "no_authorization",
                      "This endpoint requires a Bearer token")
    factor = _store.table("mfa_factors").get(factor_id)
    if not factor or factor["user_id"] != session["user_id"]:
        return _error(404, "mfa_factor_not_found", "MFA factor not found")
    _store.table("mfa_factors").delete(factor_id)
    return {"id": factor_id}


# ---------------------------------------------------------------------------
# Admin (service_role)
# ---------------------------------------------------------------------------

def _require_service_role(key):
    if key != SERVICE_ROLE:
        return _error(403, "not_admin", "User not allowed")
    return None


def admin_list_users(page=1, per_page=50, key=ANON):
    denied = _require_service_role(key)
    if denied:
        return denied
    rows = [u for u in _users_rows() if not u["deleted_at"]]
    per_page = max(1, min(int(per_page or 50), 1000))
    page = max(1, int(page or 1))
    start = (page - 1) * per_page
    return {"users": [public_user(u) for u in rows[start:start + per_page]],
            "aud": "authenticated",
            "total": len(rows), "page": page, "per_page": per_page,
            "next_page": page + 1 if start + per_page < len(rows) else None}


def admin_get_user(user_id, key=ANON):
    denied = _require_service_role(key)
    if denied:
        return denied
    user = _store.table("users").get(user_id)
    if not user:
        return _error(404, "user_not_found", "User not found")
    return public_user(user)


def admin_create_user(payload, key=ANON, ip="203.0.113.41"):
    denied = _require_service_role(key)
    if denied:
        return denied
    email = (payload or {}).get("email")
    phone = (payload or {}).get("phone")
    if not email and not phone:
        return _error(422, "validation_failed",
                      "Cannot create user without email or phone")
    if _find_user(email=email, phone=phone):
        return _error(422, "email_exists", "A user with this email address has "
                      "already been registered")
    now = _now()
    password = (payload or {}).get("password")
    salt = uuid.uuid4().hex[:16] if password else ""
    metadata = (payload or {}).get("user_metadata") or {}
    user = {
        "id": str(uuid.uuid4()), "aud": "authenticated",
        "role": (payload or {}).get("role", "authenticated"),
        "email": email or "", "phone": phone or "",
        "password_salt": salt,
        "password_hash": _hash_password(salt, password) if password else "",
        "email_confirmed_at": now if (payload or {}).get("email_confirm") else None,
        "phone_confirmed_at": now if (payload or {}).get("phone_confirm") else None,
        "confirmation_sent_at": None, "recovery_sent_at": None,
        "last_sign_in_at": None, "banned_until": None, "deleted_at": None,
        "is_anonymous": False, "is_sso_user": False,
        "app_metadata_provider": "email" if email else "phone",
        "app_metadata_providers": ["email" if email else "phone"],
        "user_metadata_full_name": metadata.get("full_name", ""),
        "user_metadata_role": metadata.get("role", ""),
        "created_at": now, "updated_at": now,
    }
    _store_insert("users", user)
    _store_insert("identities", {
        "id": max((i["id"] for i in _identities_rows()), default=0) + 1,
        "user_id": user["id"], "identity_id": str(uuid.uuid4()),
        "provider": user["app_metadata_provider"], "provider_id": user["id"],
        "email": user["email"], "last_sign_in_at": None, "created_at": now})
    _record_audit("user_signedup", user, "admin", ip, log_type="team")
    return public_user(user)


def admin_update_user(user_id, payload, key=ANON, ip="203.0.113.41"):
    denied = _require_service_role(key)
    if denied:
        return denied
    user = _store.table("users").get(user_id)
    if not user:
        return _error(404, "user_not_found", "User not found")
    patch = {"updated_at": _now()}
    payload = payload or {}
    if "email" in payload:
        patch["email"] = payload["email"]
    if "phone" in payload:
        patch["phone"] = payload["phone"]
    if payload.get("email_confirm"):
        patch["email_confirmed_at"] = _now()
    if "role" in payload:
        patch["role"] = payload["role"]
    if "password" in payload and payload["password"]:
        salt = uuid.uuid4().hex[:16]
        patch["password_salt"] = salt
        patch["password_hash"] = _hash_password(salt, payload["password"])
    if "ban_duration" in payload:
        duration = str(payload["ban_duration"])
        if duration == "none":
            patch["banned_until"] = None
        else:
            hours = _parse_duration_hours(duration)
            if hours is None:
                return _error(422, "validation_failed",
                              "ban_duration must be a duration such as 24h, or "
                              "'none' to unban")
            patch["banned_until"] = (datetime.now(timezone.utc)
                                     + timedelta(hours=hours)).strftime(
                                         "%Y-%m-%dT%H:%M:%SZ")
    for key_name, value in (payload.get("user_metadata") or {}).items():
        if key_name == "full_name":
            patch["user_metadata_full_name"] = value
        elif key_name == "role":
            patch["user_metadata_role"] = value
    updated = _store.table("users").patch(user_id, patch)
    if "ban_duration" in payload:
        _record_audit("user_banned" if patch.get("banned_until")
                      else "user_unbanned", updated, "admin", ip, log_type="team")
    return public_user(updated)


def _parse_duration_hours(text):
    try:
        if text.endswith("h"):
            return int(text[:-1])
        if text.endswith("m"):
            return int(text[:-1]) / 60
        if text.endswith("s"):
            return int(text[:-1]) / 3600
    except ValueError:
        return None
    return None


def admin_delete_user(user_id, should_soft_delete=False, key=ANON,
                      ip="203.0.113.41"):
    denied = _require_service_role(key)
    if denied:
        return denied
    user = _store.table("users").get(user_id)
    if not user:
        return _error(404, "user_not_found", "User not found")
    _store.table("sessions").delete_where(lambda s: s["user_id"] == user_id)
    _store.table("refresh_tokens").delete_where(lambda t: t["user_id"] == user_id)
    if should_soft_delete:
        _store.table("users").patch(user_id, {"deleted_at": _now()})
    else:
        _store.table("identities").delete_where(lambda i: i["user_id"] == user_id)
        _store.table("mfa_factors").delete_where(lambda f: f["user_id"] == user_id)
        _store.table("users").delete(user_id)
    _record_audit("user_deleted", user, "admin", ip, log_type="team")
    return {}


_LINK_TYPES = ("signup", "invite", "magiclink", "recovery", "email_change_current",
               "email_change_new")


def admin_generate_link(link_type=None, email=None, password=None,
                        redirect_to=None, key=ANON):
    denied = _require_service_role(key)
    if denied:
        return denied
    if link_type not in _LINK_TYPES:
        return _error(422, "validation_failed",
                      f"Invalid type. Must be one of {', '.join(_LINK_TYPES)}")
    user = _find_user(email=email)
    if not user and link_type in ("magiclink", "recovery"):
        return _error(404, "user_not_found", "User not found")
    if not user:
        created = admin_create_user({"email": email, "password": password},
                                    key=SERVICE_ROLE)
        user = _store.table("users").get(created["id"])
    token_type = {"signup": "confirmation", "invite": "invite",
                  "magiclink": "magiclink", "recovery": "recovery",
                  "email_change_current": "email_change",
                  "email_change_new": "email_change"}[link_type]
    record = _mint_one_time_token(user, token_type)
    settings = _settings_doc()
    target = redirect_to or settings["site_url"]
    return {"action_link": f"{settings['jwt']['issuer']}/verify"
                           f"?token={record['token']}&type={token_type}"
                           f"&redirect_to={target}",
            "email_otp": record["otp"], "hashed_token": record["token"],
            "verification_type": token_type, "redirect_to": target,
            "user": public_user(user)}


def admin_audit(page=1, per_page=25, action=None, key=ANON):
    denied = _require_service_role(key)
    if denied:
        return denied
    rows = _audit_rows()
    if action:
        rows = [r for r in rows if r["action"] == action]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    per_page = max(1, min(int(per_page or 25), 100))
    page = max(1, int(page or 1))
    start = (page - 1) * per_page
    return {"logs": rows[start:start + per_page], "total": len(rows),
            "page": page, "per_page": per_page}


def admin_list_sessions(user_id=None, key=ANON):
    denied = _require_service_role(key)
    if denied:
        return denied
    rows = _sessions_rows()
    if user_id:
        rows = [s for s in rows if s["user_id"] == user_id]
    return {"sessions": [{k: v for k, v in s.items()
                          if k not in ("access_token", "refresh_token")}
                         for s in rows], "total": len(rows)}


_store.eager_load()
