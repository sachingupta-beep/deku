"""Data access module for the Ory Kratos mock service.

Kratos does not have a login endpoint. It has **self-service flows**, and they
are first-class resources:

    GET  /self-service/login/api          -> a flow object with a `ui`
    POST /self-service/login?flow=<id>    -> submit against that flow

The `ui` is a renderable form description --- `action`, `method`, and a list of
`nodes`, each with its own attributes and messages. Validation failures do not
produce a bare error: they come back as **400 with the whole flow re-rendered**,
the offending node carrying a numbered message (`4000001` required, `4000002`
too short, `4000006` invalid credentials, and so on). That is the shape a client
renders, so it is the shape modelled here.

Two more Kratos-specific pieces are modelled rather than flattened:

* **Traits are validated against the identity's JSON Schema.** Two schemas are
  seeded with different required fields, so the same registration payload
  succeeds against one and fails against the other, with the error attached to
  the node for the offending trait.
* **`continue_with`** tells the client what to do next --- show the verification
  UI, or store an `ory_session_token`. A successful registration returns both.

Passwords are verified as `sha256(salt + password)`; Kratos uses Argon2id, and
the credential config says so. Mutations are held in process memory and reset on
restart.
"""

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("ory-kratos-api")
_API = "ory-kratos-api"

PUBLIC_URL = "https://kratos.orbit-labs.com"
FLOW_LIFETIME_SECONDS = 3600
SESSION_LIFETIME_SECONDS = 86400 * 30
MIN_PASSWORD_LENGTH = 8

# Kratos message ids. Clients switch on these rather than on the text.
MSG_REQUIRED = 4000001
MSG_TOO_SHORT = 4000002
MSG_INVALID_FORMAT = 4000003
MSG_INVALID_CREDENTIALS = 4000006
MSG_IDENTIFIER_EXISTS = 4000007
MSG_PASSWORD_TOO_SHORT = 4000032
MSG_INVALID_ENUM = 4000038
MSG_UNKNOWN_TRAIT = 4000040
MSG_INVALID_CODE = 4060006
MSG_RECOVERY_SENT = 1060003
MSG_VERIFICATION_SENT = 1080003
MSG_SETTINGS_SAVED = 1050001


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

    Kratos's `metadata_public`, `metadata_admin` and credential `config` are
    free-form JSON; the seed keeps them flat so a CSV overlay can shadow the
    JSON.
    """
    out = {}
    for part in _semi_list(row, column):
        key, _, value = part.partition("=")
        if key:
            out[key] = value
    return out


def _flag(row, column, default="0"):
    return opt_str(row, column, default=default) == "1"


def _load_schemas():
    with open(DATA_DIR / "identity_schemas.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("identity_schemas", primary_key="id",
                initial_loader=_load_schemas)
_store.register("identities", primary_key="id",
                initial_loader=lambda: _coerce_identities(
                    _load("identities.json", "identities")))
_store.register("credentials", primary_key="id",
                initial_loader=lambda: _coerce_credentials(
                    _load("credentials.json", "credentials")))
_store.register("flows", primary_key="id",
                initial_loader=lambda: _coerce_flows(_load("flows.json", "flows")))
_store.register("sessions", primary_key="id",
                initial_loader=lambda: _coerce_sessions(
                    _load("sessions.json", "sessions")))
_store.register("codes", primary_key="id",
                initial_loader=lambda: _coerce_codes(_load("codes.json", "codes")))
_store.register("courier_messages", primary_key="id",
                initial_loader=lambda: _coerce_messages(
                    _load("courier_messages.json", "courier_messages")))


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def _coerce_identities(rows):
    return [{**_strip_ctx(r), "emailVerified": _flag(r, "emailVerified"),
             "metadataPublic": _semi_map(r, "metadataPublic"),
             "metadataAdmin": _semi_map(r, "metadataAdmin")} for r in rows]


def _coerce_credentials(rows):
    return [{**_strip_ctx(r), "identifiers": _semi_list(r, "identifiers"),
             "config": _semi_map(r, "config")} for r in rows]


def _coerce_flows(rows):
    return [{**_strip_ctx(r), "refresh": _flag(r, "refresh")} for r in rows]


def _coerce_sessions(rows):
    out = []
    for r in rows:
        methods = []
        for entry in _semi_list(r, "authenticationMethods"):
            parts = entry.split(":")
            if len(parts) >= 3:
                methods.append({"method": parts[0],
                                "completed_at": ":".join(parts[1:-1]),
                                "aal": parts[-1]})
        out.append({**_strip_ctx(r), "active": _flag(r, "active"),
                    "authenticationMethods": methods})
    return out


def _coerce_codes(rows):
    return [{**_strip_ctx(r), "used": _flag(r, "used")} for r in rows]


def _coerce_messages(rows):
    return [{**_strip_ctx(r), "sendCount": opt_int(r, "sendCount", default=0)}
            for r in rows]


# ---------------------------------------------------------------------------
# Table accessors
# ---------------------------------------------------------------------------

def _schemas():
    return _store.table("identity_schemas").rows()


def _identities():
    return _store.table("identities").rows()


def _credentials():
    return _store.table("credentials").rows()


def _flows():
    return _store.table("flows").rows()


def _sessions():
    return _store.table("sessions").rows()


def _codes():
    return _store.table("codes").rows()


def _messages():
    return _store.table("courier_messages").rows()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _in_seconds(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)) \
        .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def _digits(seed, length=6):
    """Derive a stable numeric code from a seed string.

    `hash()` is salted per process, so codes derived from it would differ across
    restarts.
    """
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    return str(int(digest[:12], 16)).zfill(length)[-length:]


# ---------------------------------------------------------------------------
# Errors
#
# Kratos wraps every non-flow error in a `{"error": {...}}` envelope with its own
# `id`; clients switch on that id, not on the HTTP status alone.
# ---------------------------------------------------------------------------

def _error(status, error_id, reason, message=None, extra=None):
    body = {"id": error_id, "code": status,
            "status": {400: "Bad Request", 401: "Unauthorized",
                       403: "Forbidden", 404: "Not Found", 409: "Conflict",
                       410: "Gone", 422: "Unprocessable Entity"}.get(
                           status, "Error"),
            "reason": reason, "message": message or reason}
    if extra:
        body.update(extra)
    return {"error": body, "code": status, "kratos_error": True}


def _not_found(reason="Unable to locate the resource"):
    return _error(404, "not_found", reason)


# ---------------------------------------------------------------------------
# UI nodes
#
# A flow's `ui` is a renderable form. Validation errors attach to the node they
# belong to, which is why they are built here rather than raised.
# ---------------------------------------------------------------------------

def _text(message_id, text, message_type="info", context=None):
    return {"id": message_id, "text": text, "type": message_type,
            "context": context or {}}


def _input_node(name, node_type="text", value="", required=False,
                node_group="password", label=None, disabled=False,
                messages=None):
    return {"type": "input", "group": node_group,
            "attributes": {"name": name, "type": node_type, "value": value,
                           "required": required, "disabled": disabled,
                           "node_type": "input"},
            "messages": messages or [],
            "meta": {"label": _text(1070000, label, "info")} if label else {}}


def _ui(action, method="POST", nodes=None, messages=None):
    return {"action": action, "method": method, "nodes": nodes or [],
            "messages": messages or []}


def _csrf_node(token):
    return _input_node("csrf_token", node_type="hidden", value=token,
                       required=True, node_group="default")


def _login_nodes(flow):
    nodes = []
    if flow["csrfToken"]:
        nodes.append(_csrf_node(flow["csrfToken"]))
    if flow["requestedAal"] == "aal2":
        nodes.append(_input_node("totp_code", required=True, node_group="totp",
                                 label="Authentication code"))
        nodes.append(_input_node("method", node_type="submit", value="totp",
                                 node_group="totp", label="Use authenticator"))
        nodes.append(_input_node("lookup_secret", required=False,
                                 node_group="lookup_secret",
                                 label="Backup recovery code"))
    else:
        nodes.append(_input_node("identifier", required=True, label="E-Mail"))
        nodes.append(_input_node("password", node_type="password",
                                 required=True, label="Password"))
        nodes.append(_input_node("method", node_type="submit", value="password",
                                 label="Sign in"))
        nodes.append(_input_node("provider", node_type="submit", value="github",
                                 node_group="oidc", label="Sign in with GitHub"))
    return nodes


def _registration_nodes(flow, schema_id="default"):
    nodes = []
    if flow["csrfToken"]:
        nodes.append(_csrf_node(flow["csrfToken"]))
    nodes.append(_input_node("traits.email", node_type="email", required=True,
                             label="E-Mail"))
    if schema_id == "partner":
        nodes.append(_input_node("traits.company", required=True,
                                 label="Company"))
    else:
        nodes.append(_input_node("traits.name.first", required=True,
                                 label="First name"))
        nodes.append(_input_node("traits.name.last", required=True,
                                 label="Last name"))
        nodes.append(_input_node("traits.role", required=False, label="Role"))
        nodes.append(_input_node("traits.seat_id", required=False,
                                 label="Seat id"))
    nodes.append(_input_node("password", node_type="password", required=True,
                             label="Password"))
    nodes.append(_input_node("method", node_type="submit", value="password",
                             label="Sign up"))
    return nodes


def _recovery_nodes(flow, sent=False):
    nodes = []
    if flow["csrfToken"]:
        nodes.append(_csrf_node(flow["csrfToken"]))
    if sent:
        nodes.append(_input_node("code", required=True, node_group="code",
                                 label="Recovery code"))
        nodes.append(_input_node("method", node_type="submit", value="code",
                                 node_group="code", label="Submit"))
    else:
        nodes.append(_input_node("email", node_type="email", required=True,
                                 node_group="code", label="E-Mail"))
        nodes.append(_input_node("method", node_type="submit", value="code",
                                 node_group="code", label="Submit"))
    return nodes


def _verification_nodes(flow, sent=False):
    return _recovery_nodes(flow, sent=sent)


def _settings_nodes(flow, identity):
    nodes = []
    if flow["csrfToken"]:
        nodes.append(_csrf_node(flow["csrfToken"]))
    nodes.append(_input_node("traits.email", node_type="email",
                             value=identity["email"] if identity else "",
                             required=True, node_group="profile",
                             label="E-Mail"))
    if identity and identity["schemaId"] == "default":
        nodes.append(_input_node("traits.name.first",
                                 value=identity["firstName"], required=True,
                                 node_group="profile", label="First name"))
        nodes.append(_input_node("traits.name.last",
                                 value=identity["lastName"], required=True,
                                 node_group="profile", label="Last name"))
    nodes.append(_input_node("password", node_type="password", required=False,
                             label="New password"))
    nodes.append(_input_node("method", node_type="submit", value="profile",
                             node_group="profile", label="Save"))
    return nodes


_NODE_BUILDERS = {
    "login": lambda flow, **kw: _login_nodes(flow),
    "registration": lambda flow, **kw: _registration_nodes(
        flow, kw.get("schema_id", "default")),
    "recovery": lambda flow, **kw: _recovery_nodes(flow, kw.get("sent", False)),
    "verification": lambda flow, **kw: _verification_nodes(
        flow, kw.get("sent", False)),
    "settings": lambda flow, **kw: _settings_nodes(flow, kw.get("identity")),
}


def flow_representation(flow, messages=None, node_messages=None, **kwargs):
    """Render a flow, optionally attaching messages to named nodes."""
    action = f"{PUBLIC_URL}/self-service/{flow['type']}?flow={flow['id']}"
    if flow["type"] == "settings":
        action = f"{PUBLIC_URL}/self-service/settings?flow={flow['id']}"
    # A caller that already has the (possibly just-updated) identity may pass it
    # in; otherwise it is read from the flow.
    identity = kwargs.pop("identity", None) or (
        _store.table("identities").get(flow["identityId"])
        if flow["identityId"] else None)
    nodes = _NODE_BUILDERS[flow["type"]](flow, identity=identity, **kwargs)
    for node in nodes:
        attached = (node_messages or {}).get(node["attributes"]["name"])
        if attached:
            node["messages"] = attached
    body = {
        "id": flow["id"],
        "type": flow["clientType"],
        "expires_at": flow["expiresAt"],
        "issued_at": flow["issuedAt"],
        "request_url": f"{PUBLIC_URL}/self-service/{flow['type']}/"
                       f"{flow['clientType']}",
        "ui": _ui(action, nodes=nodes, messages=messages or []),
        "state": flow["state"],
    }
    if flow["type"] == "login":
        body["refresh"] = flow["refresh"]
        body["requested_aal"] = flow["requestedAal"]
    if flow["type"] == "settings" and identity:
        body["identity"] = identity_representation(identity)
    if flow["returnTo"]:
        body["return_to"] = flow["returnTo"]
    return body


def _flow_error(flow, node_messages=None, messages=None, status=400, **kwargs):
    """A failed submission re-renders the whole flow -- that is Kratos's shape."""
    return {"__status__": status,
            **flow_representation(flow, messages=messages,
                                  node_messages=node_messages, **kwargs)}


# ---------------------------------------------------------------------------
# Identities
# ---------------------------------------------------------------------------

def _traits(identity):
    if identity["schemaId"] == "partner":
        return {"email": identity["email"], "company": identity["company"]}
    traits = {"email": identity["email"],
              "name": {"first": identity["firstName"],
                       "last": identity["lastName"]}}
    if identity["role"]:
        traits["role"] = identity["role"]
    if identity["seatId"]:
        traits["seat_id"] = identity["seatId"]
    return traits


def identity_representation(identity, include_credentials=None):
    if not identity:
        return None
    schema = _store.table("identity_schemas").get(identity["schemaId"])
    body = {
        "id": identity["id"],
        "schema_id": identity["schemaId"],
        "schema_url": f"{PUBLIC_URL}/schemas/{identity['schemaId']}",
        "state": identity["state"],
        "state_changed_at": identity["stateChangedAt"],
        "traits": _traits(identity),
        "verifiable_addresses": [{
            "id": f"va-{identity['id'][:8]}", "value": identity["email"],
            "verified": identity["emailVerified"], "via": "email",
            "status": "completed" if identity["emailVerified"] else "pending",
            "verified_at": identity["verifiedAt"] or None,
            "created_at": identity["createdAt"],
            "updated_at": identity["updatedAt"]}],
        "recovery_addresses": [{
            "id": f"ra-{identity['id'][:8]}", "value": identity["email"],
            "via": "email", "created_at": identity["createdAt"],
            "updated_at": identity["updatedAt"]}],
        "metadata_public": identity["metadataPublic"],
        "created_at": identity["createdAt"],
        "updated_at": identity["updatedAt"],
    }
    if schema:
        body["schema_url"] = f"{PUBLIC_URL}/schemas/{identity['schemaId']}"
    if include_credentials:
        # Admin-only, and even then the hash is never returned.
        body["credentials"] = {
            c["type"]: {"type": c["type"], "identifiers": c["identifiers"],
                        "config": {k: v for k, v in c["config"].items()
                                   if k != "hashed_password"},
                        "created_at": c["createdAt"]}
            for c in _credentials() if c["identityId"] == identity["id"]
            and (include_credentials == "all"
                 or c["type"] in include_credentials)}
    return body


def _admin_identity_representation(identity, include_credentials=None):
    body = identity_representation(identity,
                                   include_credentials=include_credentials)
    if body:
        body["metadata_admin"] = identity["metadataAdmin"]
    return body


def _find_identity_by_identifier(identifier):
    if not identifier:
        return None
    lowered = str(identifier).lower()
    credential = _store.table("credentials").find_one(
        lambda c: any(i.lower() == lowered for i in c["identifiers"]))
    if credential:
        return _store.table("identities").get(credential["identityId"])
    return _store.table("identities").find_one(
        lambda i: i["email"].lower() == lowered)


def _credential(identity_id, credential_type):
    return _store.table("credentials").find_one(
        lambda c: c["identityId"] == identity_id and c["type"] == credential_type)


# ---------------------------------------------------------------------------
# Trait validation against the identity's JSON Schema
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_traits(schema_id, traits):
    """Validate `traits` against the seeded JSON Schema.

    Returns a `{node_name: [message]}` map so the caller can attach each failure
    to the form node it belongs to, which is what Kratos does.
    """
    schema = _store.table("identity_schemas").get(schema_id)
    if not schema:
        return {"traits.email": [_text(MSG_INVALID_FORMAT,
                                       f"Unknown schema {schema_id}", "error")]}
    spec = schema["schema"]["properties"]["traits"]
    errors = {}
    _validate_object(spec, traits or {}, "traits", errors)
    return errors


def _validate_object(spec, value, prefix, errors):
    properties = spec.get("properties", {})
    for name in spec.get("required", []):
        child = value.get(name)
        if child is None or child == "" or child == {}:
            errors.setdefault(f"{prefix}.{name}", []).append(
                _text(MSG_REQUIRED, "Property " + name + " is missing.",
                      "error", {"property": name}))
    if not spec.get("additionalProperties", True):
        for name in value:
            if name not in properties:
                errors.setdefault(f"{prefix}.{name}", []).append(
                    _text(MSG_UNKNOWN_TRAIT,
                          f"additionalProperties '{name}' not allowed", "error",
                          {"property": name}))
    for name, child_spec in properties.items():
        if name not in value or value[name] in (None, ""):
            continue
        child = value[name]
        path = f"{prefix}.{name}"
        if child_spec.get("type") == "object":
            if not isinstance(child, dict):
                errors.setdefault(path, []).append(
                    _text(MSG_INVALID_FORMAT, "expected object", "error"))
                continue
            _validate_object(child_spec, child, path, errors)
            continue
        if child_spec.get("type") == "string" and not isinstance(child, str):
            errors.setdefault(path, []).append(
                _text(MSG_INVALID_FORMAT, "expected string", "error"))
            continue
        minimum = child_spec.get("minLength")
        if minimum and len(str(child)) < minimum:
            errors.setdefault(path, []).append(
                _text(MSG_TOO_SHORT,
                      f"length must be >= {minimum}, but got {len(str(child))}",
                      "error", {"expected_length": minimum}))
        if child_spec.get("format") == "email" and not _EMAIL_RE.match(str(child)):
            errors.setdefault(path, []).append(
                _text(MSG_INVALID_FORMAT,
                      f'"{child}" is not valid "email"', "error"))
        if "enum" in child_spec and child not in child_spec["enum"]:
            errors.setdefault(path, []).append(
                _text(MSG_INVALID_ENUM,
                      f'value must be one of {", ".join(child_spec["enum"])}',
                      "error", {"expected": child_spec["enum"]}))
        if "pattern" in child_spec and not re.match(child_spec["pattern"],
                                                    str(child)):
            errors.setdefault(path, []).append(
                _text(MSG_INVALID_FORMAT,
                      f'"{child}" does not match pattern '
                      f'"{child_spec["pattern"]}"', "error"))


def _flatten_traits(traits, prefix="traits"):
    """Turn nested traits into the dotted node names the UI uses."""
    out = {}
    for key, value in (traits or {}).items():
        path = f"{prefix}.{key}"
        if isinstance(value, dict):
            out.update(_flatten_traits(value, path))
        else:
            out[path] = value
    return out


# ---------------------------------------------------------------------------
# Flows
# ---------------------------------------------------------------------------

def _expired(flow):
    return flow["expiresAt"] < _now()


def _new_flow(flow_type, client_type, requested_aal="aal1", identity_id="",
              refresh=False, return_to=""):
    now = _now()
    flow = {
        "id": str(uuid.uuid4()), "type": flow_type, "clientType": client_type,
        "state": "sent_email" if flow_type == "verification" else
                 ("show_form" if flow_type == "settings" else "choose_method"),
        "refresh": bool(refresh), "requestedAal": requested_aal,
        "identityId": identity_id,
        # Only browser flows carry an anti-CSRF token; API flows never do.
        "csrfToken": f"csrf-{secrets.token_hex(8)}"
                     if client_type == "browser" else "",
        "expiresAt": _in_seconds(FLOW_LIFETIME_SECONDS), "issuedAt": now,
        "returnTo": return_to, "note": "",
    }
    _store_insert("flows", flow)
    return flow


def create_login_flow(client_type, refresh=False, aal="aal1", return_to="",
                      session_token=None):
    identity_id = ""
    if aal == "aal2" or refresh:
        session = resolve_session(session_token)
        if not session:
            return _error(401, "session_inactive",
                          "No active session was found in this request.")
        identity_id = session["identityId"]
    flow = _new_flow("login", client_type, requested_aal=aal,
                     identity_id=identity_id, refresh=refresh,
                     return_to=return_to)
    return flow_representation(flow)


def create_registration_flow(client_type, return_to=""):
    flow = _new_flow("registration", client_type, return_to=return_to)
    return flow_representation(flow)


def create_recovery_flow(client_type, return_to=""):
    flow = _new_flow("recovery", client_type, return_to=return_to)
    return flow_representation(flow)


def create_verification_flow(client_type, return_to=""):
    flow = _new_flow("verification", client_type, return_to=return_to)
    flow = _store.table("flows").patch(flow["id"], {"state": "choose_method"})
    return flow_representation(flow)


def create_settings_flow(client_type, session_token=None, return_to=""):
    session = resolve_session(session_token)
    if not session:
        return _error(401, "session_inactive",
                      "No active session was found in this request.")
    flow = _new_flow("settings", client_type,
                     identity_id=session["identityId"], return_to=return_to)
    return flow_representation(flow)


def get_flow(flow_type, flow_id):
    flow = _store.table("flows").get(flow_id) if flow_id else None
    if not flow or flow["type"] != flow_type:
        return _error(404, "self_service_flow_not_found",
                      f"Unable to locate the {flow_type} flow you are looking "
                      f"for.")
    if _expired(flow):
        # Kratos answers 410 Gone for a flow whose lifetime has elapsed.
        return _error(410, "self_service_flow_expired",
                      "The self-service flow expired 0.00 minutes ago, "
                      "initialize a new one.",
                      extra={"details": {"redirect_to":
                                         f"{PUBLIC_URL}/self-service/"
                                         f"{flow_type}/browser",
                                         "expired_at": flow["expiresAt"]}})
    kwargs = {}
    if flow["type"] in ("recovery", "verification"):
        kwargs["sent"] = flow["state"] == "sent_email"
    return flow_representation(flow, **kwargs)


def _resolve_flow_for_submit(flow_type, flow_id):
    flow = _store.table("flows").get(flow_id) if flow_id else None
    if not flow or flow["type"] != flow_type:
        return None, _error(404, "self_service_flow_not_found",
                            f"Unable to locate the {flow_type} flow you are "
                            f"looking for.")
    if _expired(flow):
        return None, _error(410, "self_service_flow_expired",
                            "The self-service flow expired 0.00 minutes ago, "
                            "initialize a new one.",
                            extra={"details": {"expired_at": flow["expiresAt"]}})
    return flow, None


def _check_csrf(flow, payload):
    """Browser flows must echo the anti-CSRF token; API flows never carry one."""
    if not flow["csrfToken"]:
        return None
    if (payload or {}).get("csrf_token") != flow["csrfToken"]:
        return _error(403, "security_csrf_violation",
                      "The request was rejected to protect you from "
                      "Cross-Site-Request-Forgery (CSRF) which could cause "
                      "account takeover, leaking personal information, and "
                      "other serious security issues.")
    return None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def resolve_session(session_token=None):
    if not session_token:
        return None
    session = _store.table("sessions").find_one(
        lambda s: s["token"] == session_token)
    if not session or not session["active"] or session["expiresAt"] < _now():
        return None
    return session


def session_representation(session, with_identity=True, with_devices=True):
    body = {
        "id": session["id"],
        "active": session["active"],
        "expires_at": session["expiresAt"],
        "authenticated_at": session["authenticatedAt"],
        "authenticator_assurance_level": session["aal"],
        "authentication_methods": session["authenticationMethods"],
        "issued_at": session["issuedAt"],
    }
    if with_identity:
        body["identity"] = identity_representation(
            _store.table("identities").get(session["identityId"]))
    if with_devices:
        body["devices"] = [{"id": f"dev-{session['id'][:8]}",
                            "ip_address": session["deviceIp"],
                            "user_agent": session["deviceUserAgent"],
                            "location": "San Francisco, US"}]
    return body


def _issue_session(identity, methods, aal="aal1", ip="203.0.113.41",
                   user_agent="orbit-status/2.1"):
    now = _now()
    session = {
        "id": str(uuid.uuid4()), "identityId": identity["id"],
        "token": f"ory_st_{secrets.token_hex(12)}", "active": True, "aal": aal,
        "authenticationMethods": methods, "issuedAt": now,
        "authenticatedAt": now,
        "expiresAt": _in_seconds(SESSION_LIFETIME_SECONDS),
        "deviceIp": ip, "deviceUserAgent": user_agent,
    }
    _store_insert("sessions", session)
    return session


def whoami(session_token=None):
    session = resolve_session(session_token)
    if not session:
        return _error(401, "session_inactive",
                      "No active session was found in this request.")
    return session_representation(session)


def list_my_sessions(session_token=None):
    session = resolve_session(session_token)
    if not session:
        return _error(401, "session_inactive",
                      "No active session was found in this request.")
    return [session_representation(s, with_identity=False)
            for s in _sessions()
            if s["identityId"] == session["identityId"] and s["active"]]


def revoke_my_sessions(session_token=None):
    session = resolve_session(session_token)
    if not session:
        return _error(401, "session_inactive",
                      "No active session was found in this request.")
    revoked = _store.table("sessions").update_where(
        lambda s: s["identityId"] == session["identityId"]
        and s["id"] != session["id"] and s["active"], {"active": False})
    return {"count": revoked}


def revoke_my_session(session_id, session_token=None):
    session = resolve_session(session_token)
    if not session:
        return _error(401, "session_inactive",
                      "No active session was found in this request.")
    target = _store.table("sessions").get(session_id)
    if not target or target["identityId"] != session["identityId"]:
        return _not_found("Unable to locate the session you are looking for.")
    _store.table("sessions").patch(session_id, {"active": False})
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Courier
# ---------------------------------------------------------------------------

def _send_message(recipient, subject, body, template_type):
    entry = {"id": f"msg-{uuid.uuid4().hex[:12]}", "status": "queued",
             "type": "email", "recipient": recipient, "subject": subject,
             "templateType": template_type, "body": body, "sendCount": 0,
             "createdAt": _now()}
    _store_insert("courier_messages", entry)
    return entry


def list_courier_messages(status=None, recipient=None, page_size=20):
    rows = _messages()
    if status:
        rows = [m for m in rows if m["status"] == status]
    if recipient:
        rows = [m for m in rows if m["recipient"] == recipient]
    rows.sort(key=lambda m: m["createdAt"], reverse=True)
    return rows[:max(1, min(int(page_size or 20), 500))]


def get_courier_message(message_id):
    message = _store.table("courier_messages").get(message_id)
    if not message:
        return _not_found("Unable to locate the message you are looking for.")
    return message


# ---------------------------------------------------------------------------
# Login submission
# ---------------------------------------------------------------------------

def submit_login(flow_id, payload, ip="203.0.113.41"):
    flow, denied = _resolve_flow_for_submit("login", flow_id)
    if denied:
        return denied
    denied = _check_csrf(flow, payload)
    if denied:
        return denied
    payload = payload or {}
    method = payload.get("method", "password")
    if flow["requestedAal"] == "aal2":
        return _submit_login_aal2(flow, payload, method)
    if method == "oidc":
        return _submit_login_oidc(flow, payload, ip)
    identifier = payload.get("identifier")
    password = payload.get("password")
    node_messages = {}
    if not identifier:
        node_messages["identifier"] = [
            _text(MSG_REQUIRED, "Property identifier is missing.", "error")]
    if not password:
        node_messages["password"] = [
            _text(MSG_REQUIRED, "Property password is missing.", "error")]
    if node_messages:
        return _flow_error(flow, node_messages=node_messages)
    identity = _find_identity_by_identifier(identifier)
    credential = _credential(identity["id"], "password") if identity else None
    # An unknown identifier, a wrong password and an OIDC-only account are the
    # same message, so the response cannot enumerate accounts.
    if (not identity or not credential
            or _hash_password(credential["salt"], password)
            != credential["hash"]):
        return _flow_error(flow, messages=[
            _text(MSG_INVALID_CREDENTIALS,
                  "The provided credentials are invalid, check for spelling "
                  "mistakes in your password or username, email address, or "
                  "phone number.", "error")])
    if identity["state"] != "active":
        return _flow_error(flow, messages=[
            _text(4000035, "This account is inactive. Contact an administrator.",
                  "error")])
    has_totp = _credential(identity["id"], "totp") is not None
    if has_totp:
        # Kratos issues an aal1 session and tells the client to step up.
        session = _issue_session(
            identity, [{"method": "password", "completed_at": _now(),
                        "aal": "aal1"}], aal="aal1", ip=ip)
        step_up = _new_flow("login", flow["clientType"], requested_aal="aal2",
                            identity_id=identity["id"])
        _store.table("flows").patch(flow["id"], {"state": "passed_challenge"})
        return {"session_token": session["token"],
                "session": session_representation(session),
                "continue_with": [
                    {"action": "set_ory_session_token",
                     "ory_session_token": session["token"]},
                    {"action": "redirect_browser_to",
                     "redirect_browser_to":
                         f"{PUBLIC_URL}/self-service/login?flow="
                         f"{step_up['id']}"}],
                "aal2_flow_id": step_up["id"],
                "note": "the session is aal1; submit the aal2 flow above with a "
                        "totp or lookup_secret method to step it up"}
    session = _issue_session(
        identity, [{"method": "password", "completed_at": _now(),
                    "aal": "aal1"}], aal="aal1", ip=ip)
    _store.table("flows").patch(flow["id"], {"state": "passed_challenge"})
    return {"session_token": session["token"],
            "session": session_representation(session),
            "continue_with": [{"action": "set_ory_session_token",
                               "ory_session_token": session["token"]}]}


def _submit_login_aal2(flow, payload, method):
    identity = _store.table("identities").get(flow["identityId"])
    if not identity:
        return _flow_error(flow, messages=[
            _text(MSG_INVALID_CREDENTIALS,
                  "The provided credentials are invalid.", "error")])
    if method == "lookup_secret":
        credential = _credential(identity["id"], "lookup_secret")
        codes = (credential["config"].get("codes", "").split(",")
                 if credential else [])
        supplied = payload.get("lookup_secret")
        if not supplied or supplied not in codes:
            return _flow_error(flow, node_messages={"lookup_secret": [
                _text(MSG_INVALID_CODE,
                      "The backup recovery code is not valid.", "error")]})
        remaining = [c for c in codes if c != supplied]
        _store.table("credentials").patch(
            credential["id"], {"config": {**credential["config"],
                                          "codes": ",".join(remaining)}})
        completed = "lookup_secret"
    else:
        credential = _credential(identity["id"], "totp")
        if not credential:
            return _flow_error(flow, node_messages={"totp_code": [
                _text(MSG_INVALID_CODE,
                      "You have no TOTP device set up.", "error")]})
        if payload.get("totp_code") != credential["config"].get("code"):
            return _flow_error(flow, node_messages={"totp_code": [
                _text(MSG_INVALID_CODE,
                      "The provided authentication code is invalid, please try "
                      "again.", "error")]})
        completed = "totp"
    session = _issue_session(
        identity, [{"method": "password", "completed_at": _now(), "aal": "aal1"},
                   {"method": completed, "completed_at": _now(), "aal": "aal2"}],
        aal="aal2")
    _store.table("flows").patch(flow["id"], {"state": "passed_challenge"})
    return {"session_token": session["token"],
            "session": session_representation(session),
            "continue_with": [{"action": "set_ory_session_token",
                               "ory_session_token": session["token"]}]}


def _submit_login_oidc(flow, payload, ip):
    provider = payload.get("provider")
    if not provider:
        return _flow_error(flow, node_messages={"provider": [
            _text(MSG_REQUIRED, "Property provider is missing.", "error")]})
    subject = payload.get("subject") or ""
    credential = _store.table("credentials").find_one(
        lambda c: c["type"] == "oidc"
        and f"{provider}:{subject}" in c["identifiers"])
    if not credential:
        return _flow_error(flow, messages=[
            _text(MSG_INVALID_CREDENTIALS,
                  f"No account is linked to {provider} subject "
                  f"{subject or '(none)'}.", "error")])
    identity = _store.table("identities").get(credential["identityId"])
    session = _issue_session(
        identity, [{"method": "oidc", "completed_at": _now(), "aal": "aal1"}],
        aal="aal1", ip=ip)
    _store.table("flows").patch(flow["id"], {"state": "passed_challenge"})
    return {"session_token": session["token"],
            "session": session_representation(session),
            "continue_with": [{"action": "set_ory_session_token",
                               "ory_session_token": session["token"]}]}


# ---------------------------------------------------------------------------
# Registration submission
# ---------------------------------------------------------------------------

def submit_registration(flow_id, payload, ip="203.0.113.41"):
    flow, denied = _resolve_flow_for_submit("registration", flow_id)
    if denied:
        return denied
    denied = _check_csrf(flow, payload)
    if denied:
        return denied
    payload = payload or {}
    schema_id = payload.get("schema_id", "default")
    traits = payload.get("traits") or {}
    password = payload.get("password")
    node_messages = {}
    for path, messages in validate_traits(schema_id, traits).items():
        node_messages[path] = messages
    if not password:
        node_messages["password"] = [
            _text(MSG_REQUIRED, "Property password is missing.", "error")]
    elif len(password) < MIN_PASSWORD_LENGTH:
        node_messages["password"] = [
            _text(MSG_PASSWORD_TOO_SHORT,
                  f"The password must be at least {MIN_PASSWORD_LENGTH} "
                  f"characters long.", "error")]
    if node_messages:
        return _flow_error(flow, node_messages=node_messages,
                           schema_id=schema_id)
    email = traits.get("email")
    if _find_identity_by_identifier(email):
        return _flow_error(flow, node_messages={"traits.email": [
            _text(MSG_IDENTIFIER_EXISTS,
                  "An account with the same identifier (email, phone, "
                  "username, ...) exists already.", "error")]},
            schema_id=schema_id)
    now = _now()
    identity = {
        "id": str(uuid.uuid4()), "schemaId": schema_id, "state": "active",
        "email": email, "firstName": (traits.get("name") or {}).get("first", ""),
        "lastName": (traits.get("name") or {}).get("last", ""),
        "role": traits.get("role", ""), "seatId": traits.get("seat_id", ""),
        "company": traits.get("company", ""), "emailVerified": False,
        "verifiedAt": "", "stateChangedAt": now, "metadataPublic": {},
        "metadataAdmin": {}, "createdAt": now, "updatedAt": now,
    }
    _store_insert("identities", identity)
    salt = uuid.uuid4().hex[:16]
    _store_insert("credentials", {
        "id": f"cr-{uuid.uuid4().hex[:14]}", "identityId": identity["id"],
        "type": "password", "identifiers": [email], "salt": salt,
        "hash": _hash_password(salt, password),
        "config": {"hashed_password": "$argon2id$v=19$m=65536"},
        "createdAt": now})
    verification = _new_flow("verification", flow["clientType"],
                             identity_id=identity["id"])
    _store.table("flows").patch(verification["id"], {"state": "sent_email"})
    code = _digits(f"verify:{identity['id']}")
    _store_insert("codes", {
        "id": f"code-{uuid.uuid4().hex[:12]}", "type": "verification",
        "flowId": verification["id"], "identityId": identity["id"],
        "address": email, "code": code, "used": False,
        "expiresAt": _in_seconds(900), "issuedAt": now})
    _send_message(email, "Please verify your email address",
                  f"Hi, please verify your account by entering the following "
                  f"code: {code}", "verification_code_valid")
    session = _issue_session(
        identity, [{"method": "password", "completed_at": now, "aal": "aal1"}],
        ip=ip)
    _store.table("flows").patch(flow["id"], {"state": "passed_challenge"})
    return {"__status__": 200,
            "identity": identity_representation(identity),
            "session_token": session["token"],
            "session": session_representation(session),
            # `continue_with` is how Kratos tells the client what to do next.
            "continue_with": [
                {"action": "set_ory_session_token",
                 "ory_session_token": session["token"]},
                {"action": "show_verification_ui",
                 "flow": {"id": verification["id"], "verifiable_address": email,
                          "url": f"{PUBLIC_URL}/self-service/verification?flow="
                                 f"{verification['id']}"}}],
            "verification_code": code,
            "note": "the verification code is returned because no mail is "
                    "actually delivered by the mock"}


# ---------------------------------------------------------------------------
# Recovery and verification submissions
# ---------------------------------------------------------------------------

def submit_recovery(flow_id, payload):
    flow, denied = _resolve_flow_for_submit("recovery", flow_id)
    if denied:
        return denied
    denied = _check_csrf(flow, payload)
    if denied:
        return denied
    payload = payload or {}
    if payload.get("code"):
        return _consume_recovery_code(flow, payload["code"])
    email = payload.get("email")
    if not email:
        return _flow_error(flow, node_messages={"email": [
            _text(MSG_REQUIRED, "Property email is missing.", "error")]})
    identity = _find_identity_by_identifier(email)
    code = ""
    if identity:
        code = _digits(f"recover:{identity['id']}")
        _store_insert("codes", {
            "id": f"code-{uuid.uuid4().hex[:12]}", "type": "recovery",
            "flowId": flow["id"], "identityId": identity["id"],
            "address": email, "code": code, "used": False,
            "expiresAt": _in_seconds(900), "issuedAt": _now()})
        _send_message(email, "Recover access to your account",
                      f"Hi, please recover access to your account by entering "
                      f"the following code: {code}", "recovery_code_valid")
    else:
        # Kratos still sends mail to an unknown address, so the response cannot
        # confirm whether the account exists.
        _send_message(email, "Account access attempted",
                      "Hi, you (or someone else) entered this email address "
                      "when trying to recover access to an account. However, "
                      "this email address is not on our database of registered "
                      "users.", "recovery_invalid")
    updated = _store.table("flows").patch(flow["id"], {"state": "sent_email"})
    body = flow_representation(
        updated, sent=True,
        messages=[_text(MSG_RECOVERY_SENT,
                        "An email containing a recovery code has been sent to "
                        "the email address you provided.", "info")])
    if code:
        body["recovery_code"] = code
        body["note"] = ("the recovery code is returned because no mail is "
                        "actually delivered by the mock")
    return body


def _consume_recovery_code(flow, code):
    record = _store.table("codes").find_one(
        lambda c: c["type"] == "recovery" and c["code"] == code
        and not c["used"] and c["expiresAt"] > _now())
    if not record:
        return _flow_error(flow, node_messages={"code": [
            _text(MSG_INVALID_CODE,
                  "The recovery code is invalid or has already been used. "
                  "Please try again.", "error")]}, sent=True)
    _store.table("codes").patch(record["id"], {"used": True})
    identity = _store.table("identities").get(record["identityId"])
    session = _issue_session(
        identity, [{"method": "code_recovery", "completed_at": _now(),
                    "aal": "aal1"}])
    settings = _new_flow("settings", flow["clientType"],
                         identity_id=identity["id"])
    _store.table("flows").patch(flow["id"], {"state": "passed_challenge"})
    return {"session_token": session["token"],
            "session": session_representation(session),
            # After recovery Kratos forces the user through settings to set a
            # new password.
            "continue_with": [
                {"action": "set_ory_session_token",
                 "ory_session_token": session["token"]},
                {"action": "show_settings_ui",
                 "flow": {"id": settings["id"],
                          "url": f"{PUBLIC_URL}/self-service/settings?flow="
                                 f"{settings['id']}"}}]}


def submit_verification(flow_id, payload):
    flow, denied = _resolve_flow_for_submit("verification", flow_id)
    if denied:
        return denied
    denied = _check_csrf(flow, payload)
    if denied:
        return denied
    payload = payload or {}
    if payload.get("code"):
        record = _store.table("codes").find_one(
            lambda c: c["type"] == "verification" and c["code"] == payload["code"]
            and not c["used"] and c["expiresAt"] > _now())
        if not record:
            return _flow_error(flow, node_messages={"code": [
                _text(MSG_INVALID_CODE,
                      "The verification code is invalid or has already been "
                      "used. Please try again.", "error")]}, sent=True)
        _store.table("codes").patch(record["id"], {"used": True})
        _store.table("identities").patch(record["identityId"], {
            "emailVerified": True, "verifiedAt": _now(), "updatedAt": _now()})
        updated = _store.table("flows").patch(flow["id"],
                                              {"state": "passed_challenge"})
        return flow_representation(
            updated, sent=True,
            messages=[_text(1080002,
                            "You successfully verified your email address.",
                            "success")])
    email = payload.get("email")
    if not email:
        return _flow_error(flow, node_messages={"email": [
            _text(MSG_REQUIRED, "Property email is missing.", "error")]})
    identity = _find_identity_by_identifier(email)
    code = ""
    if identity and not identity["emailVerified"]:
        code = _digits(f"verify:{identity['id']}")
        _store_insert("codes", {
            "id": f"code-{uuid.uuid4().hex[:12]}", "type": "verification",
            "flowId": flow["id"], "identityId": identity["id"],
            "address": email, "code": code, "used": False,
            "expiresAt": _in_seconds(900), "issuedAt": _now()})
        _send_message(email, "Please verify your email address",
                      f"Hi, please verify your account by entering the "
                      f"following code: {code}", "verification_code_valid")
    updated = _store.table("flows").patch(flow["id"], {"state": "sent_email"})
    body = flow_representation(
        updated, sent=True,
        messages=[_text(MSG_VERIFICATION_SENT,
                        "An email containing a verification code has been sent "
                        "to the email address you provided.", "info")])
    if code:
        body["verification_code"] = code
        body["note"] = ("the verification code is returned because no mail is "
                        "actually delivered by the mock")
    return body


# ---------------------------------------------------------------------------
# Settings submission
# ---------------------------------------------------------------------------

def submit_settings(flow_id, payload, session_token=None):
    flow, denied = _resolve_flow_for_submit("settings", flow_id)
    if denied:
        return denied
    denied = _check_csrf(flow, payload)
    if denied:
        return denied
    session = resolve_session(session_token)
    if not session:
        return _error(401, "session_inactive",
                      "No active session was found in this request.")
    if session["identityId"] != flow["identityId"]:
        return _error(403, "session_refresh_required",
                      "The login session is too old and thus not allowed to "
                      "update these fields. Please re-authenticate.")
    identity = _store.table("identities").get(flow["identityId"])
    payload = payload or {}
    method = payload.get("method", "profile")
    if method == "password":
        password = payload.get("password")
        if not password:
            return _flow_error(flow, node_messages={"password": [
                _text(MSG_REQUIRED, "Property password is missing.", "error")]},
                identity=identity)
        if len(password) < MIN_PASSWORD_LENGTH:
            return _flow_error(flow, node_messages={"password": [
                _text(MSG_PASSWORD_TOO_SHORT,
                      f"The password must be at least {MIN_PASSWORD_LENGTH} "
                      f"characters long.", "error")]}, identity=identity)
        credential = _credential(identity["id"], "password")
        salt = uuid.uuid4().hex[:16]
        if credential:
            _store.table("credentials").patch(credential["id"], {
                "salt": salt, "hash": _hash_password(salt, password)})
        else:
            _store_insert("credentials", {
                "id": f"cr-{uuid.uuid4().hex[:14]}",
                "identityId": identity["id"], "type": "password",
                "identifiers": [identity["email"]], "salt": salt,
                "hash": _hash_password(salt, password),
                "config": {"hashed_password": "$argon2id$v=19$m=65536"},
                "createdAt": _now()})
        # Changing a password revokes every other session.
        _store.table("sessions").update_where(
            lambda s: s["identityId"] == identity["id"]
            and s["id"] != session["id"] and s["active"], {"active": False})
        updated = _store.table("flows").patch(flow["id"], {"state": "success"})
        return {**flow_representation(
            updated, identity=identity,
            messages=[_text(MSG_SETTINGS_SAVED,
                            "Your changes have been saved!", "success")]),
            "identity": identity_representation(identity),
            "continue_with": []}
    traits = payload.get("traits") or {}
    node_messages = validate_traits(identity["schemaId"], traits)
    if node_messages:
        return _flow_error(flow, node_messages=node_messages, identity=identity)
    email = traits.get("email")
    clash = _store.table("identities").find_one(
        lambda i: i["id"] != identity["id"]
        and i["email"].lower() == str(email).lower()) if email else None
    if clash:
        return _flow_error(flow, node_messages={"traits.email": [
            _text(MSG_IDENTIFIER_EXISTS,
                  "An account with the same identifier (email, phone, "
                  "username, ...) exists already.", "error")]},
            identity=identity)
    patch = {"updatedAt": _now()}
    continue_with = []
    if email and email.lower() != identity["email"].lower():
        patch["email"] = email
        # A changed address is unverified again, and Kratos hands back a
        # verification flow to run.
        patch["emailVerified"] = False
        patch["verifiedAt"] = ""
        verification = _new_flow("verification", flow["clientType"],
                                 identity_id=identity["id"])
        _store.table("flows").patch(verification["id"], {"state": "sent_email"})
        continue_with.append(
            {"action": "show_verification_ui",
             "flow": {"id": verification["id"], "verifiable_address": email,
                      "url": f"{PUBLIC_URL}/self-service/verification?flow="
                             f"{verification['id']}"}})
    name = traits.get("name") or {}
    if "first" in name:
        patch["firstName"] = name["first"]
    if "last" in name:
        patch["lastName"] = name["last"]
    for source, target in (("role", "role"), ("seat_id", "seatId"),
                           ("company", "company")):
        if source in traits:
            patch[target] = traits[source]
    updated_identity = _store.table("identities").patch(identity["id"], patch)
    updated = _store.table("flows").patch(flow["id"], {"state": "success"})
    return {**flow_representation(
        updated, identity=updated_identity,
        messages=[_text(MSG_SETTINGS_SAVED, "Your changes have been saved!",
                        "success")]),
        "identity": identity_representation(updated_identity),
        "continue_with": continue_with}


def submit_logout(session_token=None):
    session = resolve_session(session_token)
    if not session:
        return _error(401, "session_inactive",
                      "No active session was found in this request.")
    _store.table("sessions").patch(session["id"], {"active": False})
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

def list_schemas():
    return [{"id": s["id"], "schema": s["schema"]} for s in _schemas()]


def get_schema(schema_id):
    schema = _store.table("identity_schemas").get(schema_id)
    if not schema:
        return _not_found("Unable to locate the schema you are looking for.")
    return schema["schema"]


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------

def admin_list_identities(page_size=20, page_token=None, credentials_identifier=None,
                          include_credential=None, ids=None):
    rows = _identities()
    if credentials_identifier:
        lowered = str(credentials_identifier).lower()
        rows = [i for i in rows if i["email"].lower() == lowered]
    if ids:
        wanted = set(ids)
        rows = [i for i in rows if i["id"] in wanted]
    page_size = max(1, min(int(page_size or 20), 500))
    start = 0
    if page_token:
        all_ids = [i["id"] for i in rows]
        start = all_ids.index(page_token) if page_token in all_ids else 0
    return [_admin_identity_representation(i, include_credentials=include_credential)
            for i in rows[start:start + page_size]]


def admin_get_identity(identity_id, include_credential=None):
    identity = _store.table("identities").get(identity_id)
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    return _admin_identity_representation(identity,
                                          include_credentials=include_credential)


def admin_create_identity(payload):
    payload = payload or {}
    schema_id = payload.get("schema_id", "default")
    if not _store.table("identity_schemas").get(schema_id):
        return _error(400, "schema_not_found",
                      f"The identity schema {schema_id} could not be found.")
    traits = payload.get("traits") or {}
    errors = validate_traits(schema_id, traits)
    if errors:
        return _error(400, "identity_schema_validation_failed",
                      "The request was malformed or contained invalid "
                      "parameters.",
                      extra={"details": {"errors": [
                          {"field": field, "message": m["text"],
                           "id": m["id"]}
                          for field, messages in errors.items()
                          for m in messages]}})
    email = traits.get("email")
    if _find_identity_by_identifier(email):
        return _error(409, "identity_conflict",
                      "An account with the same identifier (email, phone, "
                      "username, ...) exists already.")
    now = _now()
    identity = {
        "id": str(uuid.uuid4()), "schemaId": schema_id,
        "state": payload.get("state", "active"), "email": email,
        "firstName": (traits.get("name") or {}).get("first", ""),
        "lastName": (traits.get("name") or {}).get("last", ""),
        "role": traits.get("role", ""), "seatId": traits.get("seat_id", ""),
        "company": traits.get("company", ""),
        "emailVerified": bool(payload.get("verifiable_addresses_verified",
                                          False)),
        "verifiedAt": now if payload.get("verifiable_addresses_verified")
                      else "",
        "stateChangedAt": now,
        "metadataPublic": payload.get("metadata_public") or {},
        "metadataAdmin": payload.get("metadata_admin") or {},
        "createdAt": now, "updatedAt": now,
    }
    _store_insert("identities", identity)
    password = ((payload.get("credentials") or {}).get("password") or {}) \
        .get("config", {}).get("password")
    if password:
        salt = uuid.uuid4().hex[:16]
        _store_insert("credentials", {
            "id": f"cr-{uuid.uuid4().hex[:14]}", "identityId": identity["id"],
            "type": "password", "identifiers": [email], "salt": salt,
            "hash": _hash_password(salt, password),
            "config": {"hashed_password": "$argon2id$v=19$m=65536"},
            "createdAt": now})
    return {"__status__": 201,
            **_admin_identity_representation(identity)}


def admin_update_identity(identity_id, payload):
    identity = _store.table("identities").get(identity_id)
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    payload = payload or {}
    schema_id = payload.get("schema_id", identity["schemaId"])
    traits = payload.get("traits")
    if traits is not None:
        errors = validate_traits(schema_id, traits)
        if errors:
            return _error(400, "identity_schema_validation_failed",
                          "The request was malformed or contained invalid "
                          "parameters.",
                          extra={"details": {"errors": [
                              {"field": field, "message": m["text"],
                               "id": m["id"]}
                              for field, messages in errors.items()
                              for m in messages]}})
    patch = {"updatedAt": _now(), "schemaId": schema_id}
    if traits is not None:
        patch.update({
            "email": traits.get("email", identity["email"]),
            "firstName": (traits.get("name") or {}).get("first",
                                                        identity["firstName"]),
            "lastName": (traits.get("name") or {}).get("last",
                                                       identity["lastName"]),
            "role": traits.get("role", identity["role"]),
            "seatId": traits.get("seat_id", identity["seatId"]),
            "company": traits.get("company", identity["company"])})
    if "state" in payload:
        if payload["state"] not in ("active", "inactive"):
            return _error(400, "identity_state_invalid",
                          "The identity state must be active or inactive.")
        patch["state"] = payload["state"]
        patch["stateChangedAt"] = _now()
        if payload["state"] == "inactive":
            _store.table("sessions").update_where(
                lambda s: s["identityId"] == identity_id and s["active"],
                {"active": False})
    if "metadata_public" in payload:
        patch["metadataPublic"] = payload["metadata_public"]
    if "metadata_admin" in payload:
        patch["metadataAdmin"] = payload["metadata_admin"]
    updated = _store.table("identities").patch(identity_id, patch)
    return _admin_identity_representation(updated)


_PATCHABLE = {
    "/state": "state",
    "/metadata_public": "metadataPublic",
    "/metadata_admin": "metadataAdmin",
    "/traits/email": "email",
    "/traits/name/first": "firstName",
    "/traits/name/last": "lastName",
    "/traits/role": "role",
    "/traits/seat_id": "seatId",
    "/traits/company": "company",
}


def admin_patch_identity(identity_id, operations):
    """JSON Patch (RFC 6902) against an identity.

    Kratos exposes this alongside the whole-document PUT, and the two behave
    differently enough to be worth modelling: a patch touches only the paths it
    names, and an unsupported path is rejected rather than ignored.
    """
    identity = _store.table("identities").get(identity_id)
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    patch = {"updatedAt": _now()}
    for operation in (operations or []):
        op = operation.get("op")
        path = operation.get("path")
        value = operation.get("value")
        if op not in ("replace", "add", "remove"):
            return _error(400, "patch_op_invalid",
                          f"The JSON Patch operation '{op}' is not supported. "
                          f"Use replace, add or remove.")
        if path not in _PATCHABLE:
            return _error(400, "patch_path_invalid",
                          f"The JSON Patch path '{path}' cannot be modified.",
                          extra={"details": {
                              "supported_paths": sorted(_PATCHABLE)}})
        field = _PATCHABLE[path]
        if op == "remove":
            patch[field] = {} if field.startswith("metadata") else ""
            continue
        if path == "/state" and value not in ("active", "inactive"):
            return _error(400, "identity_state_invalid",
                          "The identity state must be active or inactive.")
        patch[field] = value
        if path == "/state":
            patch["stateChangedAt"] = _now()
            if value == "inactive":
                _store.table("sessions").update_where(
                    lambda s: s["identityId"] == identity_id and s["active"],
                    {"active": False})
    updated = _store.table("identities").patch(identity_id, patch)
    return _admin_identity_representation(updated)


def admin_delete_identity(identity_id):
    identity = _store.table("identities").get(identity_id)
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    _store.table("sessions").delete_where(
        lambda s: s["identityId"] == identity_id)
    _store.table("credentials").delete_where(
        lambda c: c["identityId"] == identity_id)
    _store.table("codes").delete_where(lambda c: c["identityId"] == identity_id)
    _store.table("identities").delete(identity_id)
    return {"__status__": 204}


def admin_identity_sessions(identity_id, active=None):
    identity = _store.table("identities").get(identity_id)
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    rows = [s for s in _sessions() if s["identityId"] == identity_id]
    if active is not None:
        rows = [s for s in rows if s["active"] == active]
    return [session_representation(s, with_identity=False) for s in rows]


def admin_delete_identity_sessions(identity_id):
    identity = _store.table("identities").get(identity_id)
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    revoked = _store.table("sessions").update_where(
        lambda s: s["identityId"] == identity_id and s["active"],
        {"active": False})
    if not revoked:
        return _not_found("This identity has no active sessions.")
    return {"__status__": 204}


def admin_delete_credential(identity_id, credential_type):
    identity = _store.table("identities").get(identity_id)
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    if credential_type == "password":
        # Kratos refuses to remove the password credential this way.
        return _error(400, "credential_type_not_removable",
                      "The password credential cannot be removed; use a "
                      "settings flow instead.")
    credential = _credential(identity_id, credential_type)
    if not credential:
        return _not_found(f"This identity has no {credential_type} credential.")
    _store.table("credentials").delete(credential["id"])
    return {"__status__": 204}


def admin_create_recovery_code(payload):
    payload = payload or {}
    identity_id = payload.get("identity_id")
    identity = _store.table("identities").get(identity_id) if identity_id else None
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    flow = _new_flow("recovery", "browser", identity_id=identity_id)
    _store.table("flows").patch(flow["id"], {"state": "sent_email"})
    code = _digits(f"admin-recover:{identity_id}")
    _store_insert("codes", {
        "id": f"code-{uuid.uuid4().hex[:12]}", "type": "recovery",
        "flowId": flow["id"], "identityId": identity_id,
        "address": identity["email"], "code": code, "used": False,
        "expiresAt": _in_seconds(int(payload.get("expires_in_seconds", 3600))),
        "issuedAt": _now()})
    return {"__status__": 201, "recovery_code": code,
            "recovery_link": f"{PUBLIC_URL}/self-service/recovery?flow="
                             f"{flow['id']}",
            "expires_at": _in_seconds(int(payload.get("expires_in_seconds",
                                                      3600)))}


def admin_create_recovery_link(payload):
    payload = payload or {}
    identity_id = payload.get("identity_id")
    identity = _store.table("identities").get(identity_id) if identity_id else None
    if not identity:
        return _not_found("Unable to locate the identity you are looking for.")
    flow = _new_flow("recovery", "browser", identity_id=identity_id)
    token = secrets.token_urlsafe(24)
    _store_insert("codes", {
        "id": f"code-{uuid.uuid4().hex[:12]}", "type": "recovery",
        "flowId": flow["id"], "identityId": identity_id,
        "address": identity["email"], "code": token, "used": False,
        "expiresAt": _in_seconds(3600), "issuedAt": _now()})
    return {"recovery_link": f"{PUBLIC_URL}/self-service/recovery?flow="
                             f"{flow['id']}&token={token}",
            "expires_at": _in_seconds(3600)}


def admin_list_sessions(active=None, page_size=20):
    rows = _sessions()
    if active is not None:
        rows = [s for s in rows if s["active"] == active]
    return [session_representation(s) for s in
            rows[:max(1, min(int(page_size or 20), 500))]]


def admin_get_session(session_id):
    session = _store.table("sessions").get(session_id)
    if not session:
        return _not_found("Unable to locate the session you are looking for.")
    return session_representation(session)


def admin_extend_session(session_id):
    session = _store.table("sessions").get(session_id)
    if not session:
        return _not_found("Unable to locate the session you are looking for.")
    if not session["active"]:
        return _error(400, "session_inactive",
                      "The session is not active and cannot be extended.")
    updated = _store.table("sessions").patch(
        session_id, {"expiresAt": _in_seconds(SESSION_LIFETIME_SECONDS)})
    return session_representation(updated)


def admin_disable_session(session_id):
    session = _store.table("sessions").get(session_id)
    if not session:
        return _not_found("Unable to locate the session you are looking for.")
    _store.table("sessions").patch(session_id, {"active": False})
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def health_alive():
    return {"status": "ok"}


def health_ready():
    return {"status": "ok"}


def version():
    return {"version": "v1.3.1"}


_store.eager_load()
