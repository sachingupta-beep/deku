"""Data access module for the plain PostgreSQL backend mock service.

Models a hand-rolled REST API over Postgres -- the Orbit Labs back-office:
employees, teams, assets and access requests, with JWT-style bearer auth,
role-based authorization, offset pagination, an audit trail and the operational
endpoints a team ships alongside (health probes, Prometheus metrics, migration
history, schema introspection).

There is no BaaS framework here: the conventions are the ones a team picks for
itself -- a `{"data", "meta", "links"}` envelope, `{"error": {code, message,
details}}` failures, and `?page=&per_page=&sort=&q=` filtering. Mutations are
held in process memory and reset on restart.
"""

import hashlib
import json
import time
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("postgres-backend-api")
_API = "postgres-backend-api"


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


def _load_config():
    with open(DATA_DIR / "config.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json", "users")))
_store.register("teams", primary_key="id",
                initial_loader=lambda: _coerce_teams(_load("teams.json", "teams")))
_store.register("employees", primary_key="id",
                initial_loader=lambda: _coerce_employees(_load("employees.json", "employees")))
_store.register("assets", primary_key="id",
                initial_loader=lambda: _coerce_assets(_load("assets.json", "assets")))
_store.register("access_requests", primary_key="id",
                initial_loader=lambda: _coerce_requests(_load("access_requests.json", "access_requests")))
_store.register("audit_log", primary_key="id",
                initial_loader=lambda: _coerce_audit(_load("audit_log.json", "audit_log")))
_store.register("migrations", primary_key="version",
                initial_loader=lambda: _coerce_migrations(_load("migrations.json", "migrations")))
_store.register_document("config", initial_loader=_load_config)
# Born-empty: sessions are minted at runtime by POST /api/v1/auth/login.
_store.register("sessions", primary_key="refresh_token", initial_loader=lambda: [])


def _users_rows():
    return _store.table("users").rows()


def _teams_rows():
    return _store.table("teams").rows()


def _employees_rows():
    return _store.table("employees").rows()


def _assets_rows():
    return _store.table("assets").rows()


def _requests_rows():
    return _store.table("access_requests").rows()


def _audit_rows():
    return _store.table("audit_log").rows()


def _migrations_rows():
    return _store.table("migrations").rows()


def _config_doc():
    return _store.document("config").get()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

def _coerce_users(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "employee_id": opt_int(r, "employee_id", default=None),
             "failed_logins": opt_int(r, "failed_logins", default=0)} for r in rows]


def _coerce_teams(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "lead_employee_id": opt_int(r, "lead_employee_id", default=None),
             "headcount_budget": opt_int(r, "headcount_budget", default=0)} for r in rows]


def _coerce_employees(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "team_id": opt_int(r, "team_id", default=None),
             "manager_id": opt_int(r, "manager_id", default=None),
             "ended_on": opt_str(r, "ended_on", default="") or None} for r in rows]


def _coerce_assets(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "assigned_to": opt_int(r, "assigned_to", default=None),
             "purchase_cost_cents": opt_int(r, "purchase_cost_cents", default=0)}
            for r in rows]


def _coerce_requests(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "employee_id": opt_int(r, "employee_id", default=None),
             "decided_by": opt_int(r, "decided_by", default=None),
             "decided_at": opt_str(r, "decided_at", default="") or None,
             "expires_on": opt_str(r, "expires_on", default="") or None} for r in rows]


def _coerce_audit(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "actor_user_id": opt_int(r, "actor_user_id", default=None)} for r in rows]


def _coerce_migrations(rows):
    return [{**_strip_ctx(r), "execution_ms": opt_int(r, "execution_ms", default=0)}
            for r in rows]


# ---------------------------------------------------------------------------
# Errors, pagination, helpers
# ---------------------------------------------------------------------------

def _error(status, code, message, details=None):
    """House error envelope: the server emits `{"error": {...}}` at `status`."""
    body = {"code": code, "message": message}
    if details:
        body["details"] = details
    return {"error": body, "status": status}


def _not_found(resource, resource_id):
    return _error(404, "not_found", f"{resource} {resource_id} not found")


def _next_serial(table):
    """Next SERIAL value. Scans live rows so admin-plane injections cannot
    collide with a cached counter."""
    ids = [r["id"] for r in _store.table(table).rows() if isinstance(r.get("id"), int)]
    return (max(ids) + 1) if ids else 1


def _paginate(rows, page, per_page, path, extra_params=""):
    config = _config_doc()["pagination"]
    per_page = max(1, min(int(per_page or config["default_per_page"]),
                          config["max_per_page"]))
    page = max(1, int(page or 1))
    total = len(rows)
    total_pages = (total + per_page - 1) // per_page if per_page else 0
    start = (page - 1) * per_page
    window = rows[start:start + per_page]
    suffix = f"&{extra_params}" if extra_params else ""

    def link(target):
        return f"{path}?page={target}&per_page={per_page}{suffix}"

    return {
        "data": window,
        "meta": {"page": page, "per_page": per_page, "total": total,
                 "total_pages": total_pages},
        "links": {
            "self": link(page),
            "first": link(1),
            "last": link(total_pages) if total_pages else link(1),
            "prev": link(page - 1) if page > 1 else None,
            "next": link(page + 1) if page < total_pages else None,
        },
    }


def _sort_rows(rows, spec, allowed):
    """`sort=-started_on,last_name`; unknown columns are a client error."""
    if not spec:
        return rows, None
    out = list(rows)
    for clause in reversed([c.strip() for c in spec.split(",") if c.strip()]):
        descending = clause.startswith("-")
        column = clause.lstrip("+-")
        if column not in allowed:
            return rows, _error(400, "invalid_sort",
                                f"Cannot sort by unknown column '{column}'",
                                {"allowed": sorted(allowed)})
        out.sort(key=lambda r: (r.get(column) is None, _sort_key(r.get(column))),
                 reverse=descending)
    return out, None


def _sort_key(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return str(value)


def _search(rows, term, columns):
    if not term:
        return rows
    needle = str(term).lower()
    return [r for r in rows
            if any(needle in str(r.get(c, "")).lower() for c in columns)]


# ---------------------------------------------------------------------------
# Authentication + authorization
# ---------------------------------------------------------------------------

ROLE_RANK = {"viewer": 1, "manager": 2, "admin": 3}


def _hash_password(salt, password):
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def login(email=None, password=None, ip="203.0.113.41"):
    user = _store.table("users").find_one(lambda u: u["email"] == email)
    if not user or not password:
        return _error(401, "invalid_credentials", "Email or password is incorrect")
    if user["status"] == "locked":
        return _error(423, "account_locked",
                      "Account is locked after too many failed sign-in attempts",
                      {"failed_logins": user["failed_logins"]})
    if _hash_password(user["salt"], password) != user["password_hash"]:
        attempts = user["failed_logins"] + 1
        maximum = _config_doc()["auth"]["max_failed_logins"]
        _store.table("users").patch(user["id"], {
            "failed_logins": attempts,
            "status": "locked" if attempts >= maximum else user["status"],
        })
        _record_audit(user["id"], "auth.login_failed", "user", user["id"],
                      f"Bad password (attempt {attempts} of {maximum})", ip)
        return _error(401, "invalid_credentials", "Email or password is incorrect")
    now = _now()
    _store.table("users").patch(user["id"], {"failed_logins": 0, "last_login_at": now})
    _record_audit(user["id"], "auth.login", "user", user["id"],
                  "Successful password login", ip)
    return _issue_session(user)


def _issue_session(user):
    auth = _config_doc()["auth"]
    session = {
        "refresh_token": f"rt_{uuid.uuid4().hex}",
        "access_token": f"at_{uuid.uuid4().hex}",
        "user_id": user["id"],
        "role": user["role"],
        "issued_at": _now(),
    }
    _store.table("sessions").upsert(session)
    return {
        "access_token": session["access_token"],
        "refresh_token": session["refresh_token"],
        "token_type": "Bearer",
        "expires_in": auth["access_token_ttl_seconds"],
        "user": _public_user(user),
    }


def refresh(refresh_token=None):
    session = _store.table("sessions").get(refresh_token)
    if not session:
        return _error(401, "invalid_refresh_token",
                      "Refresh token is unknown, expired or already used")
    user = _store.table("users").get(session["user_id"])
    if not user or user["status"] != "active":
        return _error(401, "invalid_refresh_token", "Account is no longer active")
    _store.table("sessions").delete(refresh_token)
    return _issue_session(user)


def logout(refresh_token=None, user_id=None):
    if refresh_token:
        return {"revoked": 1 if _store.table("sessions").delete(refresh_token) else 0}
    revoked = _store.table("sessions").delete_where(
        lambda s: s["user_id"] == user_id)
    return {"revoked": revoked}


def resolve_identity(authorization=None):
    """Map a bearer token onto (user row, error).

    A token minted by `POST /auth/login` resolves to its session. The long-lived
    static service tokens in `config.json` resolve to their configured user, so a
    client can exercise each role without logging in first. Any other non-empty
    bearer token resolves to the seeded admin account, keeping the fleet
    convention that any token is accepted while still exercising the role checks.
    No token at all is anonymous.
    """
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        return None, None
    session = _store.table("sessions").find_one(lambda s: s["access_token"] == token)
    if session:
        return _store.table("users").get(session["user_id"]), None
    static = _config_doc()["credentials"].get("static_tokens", {})
    if token in static:
        return _store.table("users").get(static[token]), None
    return _store.table("users").find_one(lambda u: u["role"] == "admin"), None


def require_role(user, minimum):
    if not user:
        return _error(401, "unauthenticated",
                      "A bearer access token is required for this endpoint")
    if user["status"] != "active":
        return _error(403, "account_inactive",
                      f"Account status is '{user['status']}'")
    if ROLE_RANK.get(user["role"], 0) < ROLE_RANK[minimum]:
        return _error(403, "insufficient_role",
                      f"Role '{user['role']}' cannot perform this action",
                      {"required_role": minimum})
    return None


def _public_user(user):
    return {"id": user["id"], "email": user["email"], "role": user["role"],
            "status": user["status"], "employee_id": user["employee_id"],
            "last_login_at": user["last_login_at"]}


def current_user(user):
    employee = _store.table("employees").get(user["employee_id"])
    return {"data": {**_public_user(user), "employee": employee}}


def _record_audit(actor_user_id, action, entity_type, entity_id, summary,
                  ip="203.0.113.41"):
    entry = {
        "id": _next_serial("audit_log"),
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "summary": summary,
        "ip": ip,
        "created_at": _now(),
    }
    _store_insert("audit_log", entry)
    return entry


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

_EMPLOYEE_COLUMNS = {"id", "first_name", "last_name", "email", "title", "team_id",
                     "manager_id", "location", "employment_type", "status",
                     "started_on", "ended_on"}


def list_employees(page=1, per_page=None, sort=None, q=None, team_id=None,
                   status=None, expand=None):
    rows = _employees_rows()
    if team_id is not None:
        rows = [r for r in rows if r["team_id"] == int(team_id)]
    if status:
        rows = [r for r in rows if r["status"] == status]
    rows = _search(rows, q, ("first_name", "last_name", "email", "title", "location"))
    rows, err = _sort_rows(rows, sort, _EMPLOYEE_COLUMNS)
    if err:
        return err
    if expand:
        rows = [_expand_employee(r, expand) for r in rows]
    params = "&".join(filter(None, [
        f"team_id={team_id}" if team_id is not None else "",
        f"status={status}" if status else "",
        f"q={q}" if q else "",
    ]))
    return _paginate(rows, page, per_page, "/api/v1/employees", params)


def _expand_employee(row, expand):
    wanted = {e.strip() for e in str(expand).split(",") if e.strip()}
    out = dict(row)
    if "team" in wanted:
        out["team"] = _store.table("teams").get(row["team_id"])
    if "manager" in wanted:
        out["manager"] = _store.table("employees").get(row["manager_id"]) \
            if row["manager_id"] else None
    if "assets" in wanted:
        out["assets"] = [a for a in _assets_rows() if a["assigned_to"] == row["id"]]
    return out


def get_employee(employee_id, expand=None):
    row = _store.table("employees").get(_as_int(employee_id))
    if not row:
        return _not_found("Employee", employee_id)
    return {"data": _expand_employee(row, expand) if expand else row}


_REQUIRED_EMPLOYEE_FIELDS = ("first_name", "last_name", "email", "title", "team_id")


def create_employee(payload, actor):
    problems = [{"field": f, "issue": "required"}
                for f in _REQUIRED_EMPLOYEE_FIELDS
                if not (payload or {}).get(f)]
    if problems:
        return _error(422, "validation_error", "Request body failed validation",
                      problems)
    email = payload["email"]
    if _store.table("employees").find_one(lambda e: e["email"] == email):
        return _error(409, "duplicate_email",
                      f"An employee with email {email} already exists",
                      [{"field": "email", "issue": "unique"}])
    team_id = _as_int(payload["team_id"])
    if not _store.table("teams").get(team_id):
        return _error(422, "validation_error", "Request body failed validation",
                      [{"field": "team_id", "issue": "foreign_key",
                        "detail": f"team {payload['team_id']} does not exist"}])
    manager_id = _as_int(payload.get("manager_id")) if payload.get("manager_id") else None
    if manager_id and not _store.table("employees").get(manager_id):
        return _error(422, "validation_error", "Request body failed validation",
                      [{"field": "manager_id", "issue": "foreign_key"}])
    row = {
        "id": _next_serial("employees"),
        "first_name": payload["first_name"],
        "last_name": payload["last_name"],
        "email": email,
        "title": payload["title"],
        "team_id": team_id,
        "manager_id": manager_id,
        "location": payload.get("location", ""),
        "employment_type": payload.get("employment_type", "full_time"),
        "status": payload.get("status", "active"),
        "started_on": payload.get("started_on", time.strftime("%Y-%m-%d", time.gmtime())),
        "ended_on": None,
    }
    _store_insert("employees", row)
    _record_audit(actor["id"], "employee.created", "employee", row["id"],
                  f"Created {row['first_name']} {row['last_name']}")
    return {"data": row}


def update_employee(employee_id, payload, actor):
    row = _store.table("employees").get(_as_int(employee_id))
    if not row:
        return _not_found("Employee", employee_id)
    unknown = [k for k in (payload or {}) if k not in _EMPLOYEE_COLUMNS or k == "id"]
    if unknown:
        return _error(422, "validation_error", "Request body failed validation",
                      [{"field": unknown[0], "issue": "unknown_column"}])
    patch = dict(payload or {})
    for column in ("team_id", "manager_id"):
        if column in patch and patch[column] is not None:
            patch[column] = _as_int(patch[column])
    updated = _store.table("employees").patch(row["id"], patch)
    _record_audit(actor["id"], "employee.updated", "employee", row["id"],
                  "Updated " + ", ".join(sorted(patch)))
    return {"data": updated}


def delete_employee(employee_id, actor):
    row = _store.table("employees").get(_as_int(employee_id))
    if not row:
        return _not_found("Employee", employee_id)
    held = [a["asset_tag"] for a in _assets_rows() if a["assigned_to"] == row["id"]]
    if held:
        return _error(409, "conflict",
                      "Employee still holds assigned assets",
                      [{"field": "assets", "issue": "must_be_returned",
                        "asset_tags": held}])
    # access_requests.employee_id has no ON DELETE action, so the row must go first.
    referencing = [r["id"] for r in _requests_rows() if r["employee_id"] == row["id"]]
    if referencing:
        return _error(409, "conflict",
                      'update or delete on table "employees" violates foreign key '
                      'constraint "access_requests_employee_id_fkey"',
                      [{"field": "employee_id", "issue": "referenced",
                        "table": "access_requests", "request_ids": referencing}])
    reports = [e["id"] for e in _employees_rows() if e["manager_id"] == row["id"]]
    if reports:
        return _error(409, "conflict",
                      'update or delete on table "employees" violates foreign key '
                      'constraint "employees_manager_id_fkey"',
                      [{"field": "manager_id", "issue": "referenced",
                        "table": "employees", "employee_ids": reports}])
    _store.table("employees").delete(row["id"])
    _record_audit(actor["id"], "employee.deleted", "employee", row["id"],
                  f"Deleted {row['first_name']} {row['last_name']}")
    return None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

def list_teams(page=1, per_page=None, sort=None):
    rows, err = _sort_rows(_teams_rows(), sort,
                           {"id", "name", "slug", "cost_centre", "headcount_budget"})
    if err:
        return err
    rows = [{**t, "headcount": len([e for e in _employees_rows()
                                    if e["team_id"] == t["id"]
                                    and e["status"] != "offboarded"])} for t in rows]
    return _paginate(rows, page, per_page, "/api/v1/teams")


def get_team(team_id):
    row = _store.table("teams").get(_as_int(team_id))
    if not row:
        return _not_found("Team", team_id)
    members = [e for e in _employees_rows() if e["team_id"] == row["id"]]
    return {"data": {**row, "headcount": len([e for e in members
                                              if e["status"] != "offboarded"]),
                     "lead": _store.table("employees").get(row["lead_employee_id"])}}


def list_team_employees(team_id, page=1, per_page=None, sort=None, status=None):
    if not _store.table("teams").get(_as_int(team_id)):
        return _not_found("Team", team_id)
    rows = [e for e in _employees_rows() if e["team_id"] == _as_int(team_id)]
    if status:
        rows = [e for e in rows if e["status"] == status]
    rows, err = _sort_rows(rows, sort, _EMPLOYEE_COLUMNS)
    if err:
        return err
    return _paginate(rows, page, per_page, f"/api/v1/teams/{team_id}/employees")


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

_ASSET_COLUMNS = {"id", "asset_tag", "category", "model", "serial", "status",
                  "assigned_to", "purchase_cost_cents", "purchased_on",
                  "warranty_until"}


def list_assets(page=1, per_page=None, sort=None, q=None, status=None,
                category=None, assigned_to=None):
    rows = _assets_rows()
    if status:
        rows = [a for a in rows if a["status"] == status]
    if category:
        rows = [a for a in rows if a["category"] == category]
    if assigned_to is not None:
        rows = [a for a in rows if a["assigned_to"] == _as_int(assigned_to)]
    rows = _search(rows, q, ("asset_tag", "model", "serial", "notes"))
    rows, err = _sort_rows(rows, sort, _ASSET_COLUMNS)
    if err:
        return err
    params = "&".join(filter(None, [
        f"status={status}" if status else "",
        f"category={category}" if category else "",
    ]))
    return _paginate(rows, page, per_page, "/api/v1/assets", params)


def get_asset(asset_id):
    row = _store.table("assets").get(_as_int(asset_id))
    if not row:
        return _not_found("Asset", asset_id)
    holder = _store.table("employees").get(row["assigned_to"]) \
        if row["assigned_to"] else None
    return {"data": {**row, "holder": holder}}


def create_asset(payload, actor):
    problems = [{"field": f, "issue": "required"}
                for f in ("asset_tag", "category", "model")
                if not (payload or {}).get(f)]
    if problems:
        return _error(422, "validation_error", "Request body failed validation",
                      problems)
    tag = payload["asset_tag"]
    if _store.table("assets").find_one(lambda a: a["asset_tag"] == tag):
        return _error(409, "duplicate_asset_tag",
                      f"Asset tag {tag} is already in use",
                      [{"field": "asset_tag", "issue": "unique"}])
    row = {
        "id": _next_serial("assets"),
        "asset_tag": tag,
        "category": payload["category"],
        "model": payload["model"],
        "serial": payload.get("serial", ""),
        "status": "in_stock",
        "assigned_to": None,
        "purchase_cost_cents": int(payload.get("purchase_cost_cents") or 0),
        "purchased_on": payload.get("purchased_on",
                                    time.strftime("%Y-%m-%d", time.gmtime())),
        "warranty_until": payload.get("warranty_until", ""),
        "notes": payload.get("notes", ""),
    }
    _store_insert("assets", row)
    _record_audit(actor["id"], "asset.created", "asset", row["id"],
                  f"Registered {tag}")
    return {"data": row}


def assign_asset(asset_id, employee_id, actor):
    """Assign an asset. Writes the asset row and an audit entry together."""
    asset = _store.table("assets").get(_as_int(asset_id))
    if not asset:
        return _not_found("Asset", asset_id)
    employee = _store.table("employees").get(_as_int(employee_id))
    if not employee:
        return _error(422, "validation_error", "Request body failed validation",
                      [{"field": "employee_id", "issue": "foreign_key",
                        "detail": f"employee {employee_id} does not exist"}])
    if asset["status"] not in ("in_stock", "assigned"):
        return _error(409, "conflict",
                      f"Asset {asset['asset_tag']} is '{asset['status']}' and "
                      f"cannot be assigned")
    if asset["assigned_to"] and asset["assigned_to"] != employee["id"]:
        holder = _store.table("employees").get(asset["assigned_to"])
        return _error(409, "conflict",
                      f"Asset {asset['asset_tag']} is already assigned to "
                      f"{holder['first_name']} {holder['last_name']}",
                      [{"field": "assigned_to", "issue": "already_assigned"}])
    if employee["status"] == "offboarded":
        return _error(409, "conflict",
                      "Cannot assign an asset to an offboarded employee")
    updated = _store.table("assets").patch(asset["id"], {
        "status": "assigned", "assigned_to": employee["id"]})
    _record_audit(actor["id"], "asset.assigned", "asset", asset["id"],
                  f"Assigned {asset['asset_tag']} to "
                  f"{employee['first_name']} {employee['last_name']}")
    return {"data": updated}


def return_asset(asset_id, actor, condition="in_stock", note=""):
    asset = _store.table("assets").get(_as_int(asset_id))
    if not asset:
        return _not_found("Asset", asset_id)
    if not asset["assigned_to"]:
        return _error(409, "conflict",
                      f"Asset {asset['asset_tag']} is not currently assigned")
    if condition not in ("in_stock", "repair", "retired"):
        return _error(422, "validation_error", "Request body failed validation",
                      [{"field": "condition", "issue": "invalid",
                        "allowed": ["in_stock", "repair", "retired"]}])
    holder = _store.table("employees").get(asset["assigned_to"])
    updated = _store.table("assets").patch(asset["id"], {
        "status": condition, "assigned_to": None,
        "notes": note or asset["notes"]})
    _record_audit(actor["id"], "asset.returned", "asset", asset["id"],
                  f"{asset['asset_tag']} returned by "
                  f"{holder['first_name']} {holder['last_name']} as {condition}")
    return {"data": updated}


# ---------------------------------------------------------------------------
# Access requests
# ---------------------------------------------------------------------------

def list_access_requests(page=1, per_page=None, sort=None, status=None,
                         employee_id=None, system=None):
    rows = _requests_rows()
    if status:
        rows = [r for r in rows if r["status"] == status]
    if employee_id is not None:
        rows = [r for r in rows if r["employee_id"] == _as_int(employee_id)]
    if system:
        rows = [r for r in rows if r["system"] == system]
    rows, err = _sort_rows(rows, sort,
                           {"id", "employee_id", "system", "access_level", "status",
                            "requested_at", "decided_at", "expires_on"})
    if err:
        return err
    params = "&".join(filter(None, [
        f"status={status}" if status else "",
        f"system={system}" if system else "",
    ]))
    return _paginate(rows, page, per_page, "/api/v1/access-requests", params)


def get_access_request(request_id):
    row = _store.table("access_requests").get(_as_int(request_id))
    if not row:
        return _not_found("Access request", request_id)
    decider = _store.table("users").get(row["decided_by"]) if row["decided_by"] else None
    return {"data": {**row,
                     "employee": _store.table("employees").get(row["employee_id"]),
                     "decided_by_user": _public_user(decider) if decider else None}}


_ACCESS_LEVELS = ("read_only", "read_write", "admin")


def create_access_request(payload, actor):
    problems = [{"field": f, "issue": "required"}
                for f in ("employee_id", "system", "access_level", "justification")
                if not (payload or {}).get(f)]
    if problems:
        return _error(422, "validation_error", "Request body failed validation",
                      problems)
    if payload["access_level"] not in _ACCESS_LEVELS:
        return _error(422, "validation_error", "Request body failed validation",
                      [{"field": "access_level", "issue": "invalid",
                        "allowed": list(_ACCESS_LEVELS)}])
    employee = _store.table("employees").get(_as_int(payload["employee_id"]))
    if not employee:
        return _error(422, "validation_error", "Request body failed validation",
                      [{"field": "employee_id", "issue": "foreign_key"}])
    existing = _store.table("access_requests").find_one(
        lambda r: r["employee_id"] == employee["id"]
        and r["system"] == payload["system"] and r["status"] == "pending")
    if existing:
        return _error(409, "conflict",
                      f"A pending request for {payload['system']} already exists "
                      f"for this employee",
                      [{"field": "system", "issue": "duplicate_pending",
                        "request_id": existing["id"]}])
    row = {
        "id": _next_serial("access_requests"),
        "employee_id": employee["id"],
        "system": payload["system"],
        "access_level": payload["access_level"],
        "justification": payload["justification"],
        "status": "pending",
        "requested_at": _now(),
        "decided_at": None,
        "decided_by": None,
        "decision_note": "",
        "expires_on": payload.get("expires_on"),
    }
    _store_insert("access_requests", row)
    _record_audit(actor["id"], "access_request.created", "access_request", row["id"],
                  f"Requested {row['access_level']} on {row['system']} for "
                  f"{employee['first_name']} {employee['last_name']}")
    return {"data": row}


def decide_access_request(request_id, decision, note, actor):
    row = _store.table("access_requests").get(_as_int(request_id))
    if not row:
        return _not_found("Access request", request_id)
    if row["status"] != "pending":
        return _error(409, "conflict",
                      f"Request {row['id']} is already '{row['status']}' and "
                      f"cannot be decided again",
                      [{"field": "status", "issue": "not_pending"}])
    if actor["employee_id"] == row["employee_id"]:
        return _error(403, "self_approval_forbidden",
                      "You cannot decide your own access request")
    updated = _store.table("access_requests").patch(row["id"], {
        "status": decision, "decided_at": _now(),
        "decided_by": actor["id"], "decision_note": note or ""})
    employee = _store.table("employees").get(row["employee_id"])
    _record_audit(actor["id"], f"access_request.{decision}", "access_request",
                  row["id"],
                  f"{decision.capitalize()} {row['system']} {row['access_level']} "
                  f"for {employee['first_name']} {employee['last_name']}")
    return {"data": updated}


# ---------------------------------------------------------------------------
# Audit log / meta / ops
# ---------------------------------------------------------------------------

def list_audit_log(page=1, per_page=None, action=None, entity_type=None,
                   actor_user_id=None):
    rows = _audit_rows()
    if action:
        rows = [r for r in rows if r["action"] == action]
    if entity_type:
        rows = [r for r in rows if r["entity_type"] == entity_type]
    if actor_user_id is not None:
        rows = [r for r in rows if r["actor_user_id"] == _as_int(actor_user_id)]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return _paginate(rows, page, per_page, "/api/v1/audit-log")


def list_migrations():
    rows = sorted(_migrations_rows(), key=lambda m: m["version"])
    return {"data": rows,
            "meta": {"applied": len(rows),
                     "current_version": rows[-1]["version"] if rows else None,
                     "pending": 0}}


def describe_schema():
    """Introspection of the tables this service owns."""
    tables = []
    for name, columns in _SCHEMA.items():
        tables.append({
            "table": name,
            "primary_key": columns["primary_key"],
            "row_count": len(_store.table(name).rows()),
            "columns": columns["columns"],
            "foreign_keys": columns.get("foreign_keys", []),
        })
    config = _config_doc()
    return {"data": {"database": config["database"]["name"],
                     "schema": config["database"]["schema"],
                     "engine": f"{config['database']['engine']} "
                               f"{config['database']['version']}",
                     "tables": tables}}


_SCHEMA = {
    "teams": {
        "primary_key": "id",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False},
            {"name": "name", "type": "text", "nullable": False},
            {"name": "slug", "type": "text", "nullable": False},
            {"name": "cost_centre", "type": "text", "nullable": True},
            {"name": "lead_employee_id", "type": "integer", "nullable": True},
            {"name": "headcount_budget", "type": "integer", "nullable": True},
            {"name": "created_at", "type": "timestamptz", "nullable": False},
        ],
        "foreign_keys": [{"column": "lead_employee_id", "references": "employees(id)"}],
    },
    "employees": {
        "primary_key": "id",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False},
            {"name": "first_name", "type": "text", "nullable": False},
            {"name": "last_name", "type": "text", "nullable": False},
            {"name": "email", "type": "citext", "nullable": False},
            {"name": "title", "type": "text", "nullable": False},
            {"name": "team_id", "type": "integer", "nullable": False},
            {"name": "manager_id", "type": "integer", "nullable": True},
            {"name": "location", "type": "text", "nullable": True},
            {"name": "employment_type", "type": "text", "nullable": False},
            {"name": "status", "type": "text", "nullable": False},
            {"name": "started_on", "type": "date", "nullable": False},
            {"name": "ended_on", "type": "date", "nullable": True},
        ],
        "foreign_keys": [{"column": "team_id", "references": "teams(id)"},
                         {"column": "manager_id", "references": "employees(id)"}],
    },
    "users": {
        "primary_key": "id",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False},
            {"name": "employee_id", "type": "integer", "nullable": True},
            {"name": "email", "type": "citext", "nullable": False},
            {"name": "role", "type": "text", "nullable": False},
            {"name": "status", "type": "text", "nullable": False},
            {"name": "password_hash", "type": "text", "nullable": False},
            {"name": "failed_logins", "type": "integer", "nullable": False},
        ],
        "foreign_keys": [{"column": "employee_id", "references": "employees(id)"}],
    },
    "assets": {
        "primary_key": "id",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False},
            {"name": "asset_tag", "type": "text", "nullable": False},
            {"name": "category", "type": "text", "nullable": False},
            {"name": "model", "type": "text", "nullable": False},
            {"name": "serial", "type": "text", "nullable": True},
            {"name": "status", "type": "text", "nullable": False},
            {"name": "assigned_to", "type": "integer", "nullable": True},
            {"name": "purchase_cost_cents", "type": "integer", "nullable": True},
        ],
        "foreign_keys": [{"column": "assigned_to", "references": "employees(id)"}],
    },
    "access_requests": {
        "primary_key": "id",
        "columns": [
            {"name": "id", "type": "integer", "nullable": False},
            {"name": "employee_id", "type": "integer", "nullable": False},
            {"name": "system", "type": "text", "nullable": False},
            {"name": "access_level", "type": "text", "nullable": False},
            {"name": "status", "type": "text", "nullable": False},
            {"name": "requested_at", "type": "timestamptz", "nullable": False},
            {"name": "decided_at", "type": "timestamptz", "nullable": True},
            {"name": "decided_by", "type": "integer", "nullable": True},
        ],
        "foreign_keys": [{"column": "employee_id", "references": "employees(id)"},
                         {"column": "decided_by", "references": "users(id)"}],
    },
    "audit_log": {
        "primary_key": "id",
        "columns": [
            {"name": "id", "type": "bigint", "nullable": False},
            {"name": "actor_user_id", "type": "integer", "nullable": True},
            {"name": "action", "type": "text", "nullable": False},
            {"name": "entity_type", "type": "text", "nullable": False},
            {"name": "entity_id", "type": "text", "nullable": False},
            {"name": "created_at", "type": "timestamptz", "nullable": False},
        ],
        "foreign_keys": [{"column": "actor_user_id", "references": "users(id)"}],
    },
}


def health():
    return {"status": "ok"}


def health_db():
    database = _config_doc()["database"]
    return {"status": "ok", "engine": database["engine"],
            "version": database["version"], "latency_ms": 3.1,
            "pool": database["pool"], "replica_lag_ms": database["replica_lag_ms"]}


def health_ready():
    config = _config_doc()
    applied = len(_migrations_rows())
    return {"status": "ok", "version": config["version"], "commit": config["commit"][:12],
            "checks": {"database": "ok", "migrations": "ok", "cache": "ok"},
            "migrations_applied": applied,
            "current_migration": sorted(m["version"] for m in _migrations_rows())[-1]
            if applied else None}


def metrics():
    """Prometheus text exposition. Counts come from the live store."""
    config = _config_doc()
    counters = config["seeded_counters"]
    lines = [
        "# HELP http_requests_total Total HTTP requests served.",
        "# TYPE http_requests_total counter",
        f'http_requests_total{{service="{config["service"]}"}} '
        f'{counters["http_requests_total"]}',
        "# HELP http_request_errors_total HTTP responses with a 4xx or 5xx status.",
        "# TYPE http_request_errors_total counter",
        f'http_request_errors_total{{service="{config["service"]}"}} '
        f'{counters["http_request_errors_total"]}',
        "# HELP db_queries_total Statements issued to PostgreSQL.",
        "# TYPE db_queries_total counter",
        f'db_queries_total{{database="{config["database"]["name"]}"}} '
        f'{counters["db_queries_total"]}',
        "# HELP db_pool_connections Connections in the PostgreSQL pool.",
        "# TYPE db_pool_connections gauge",
        f'db_pool_connections{{state="in_use"}} {config["database"]["pool"]["in_use"]}',
        f'db_pool_connections{{state="idle"}} {config["database"]["pool"]["idle"]}',
        "# HELP table_rows Rows currently stored per table.",
        "# TYPE table_rows gauge",
    ]
    for name in _SCHEMA:
        lines.append(f'table_rows{{table="{name}"}} {len(_store.table(name).rows())}')
    lines += [
        "# HELP process_uptime_seconds Seconds since the process started.",
        "# TYPE process_uptime_seconds counter",
        f'process_uptime_seconds {counters["uptime_seconds"]}',
    ]
    return "\n".join(lines) + "\n"


_store.eager_load()
