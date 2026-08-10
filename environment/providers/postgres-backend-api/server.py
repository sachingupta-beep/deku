"""FastAPI server wrapping postgres_backend_data module as REST endpoints.

A plain hand-rolled backend over PostgreSQL -- no BaaS framework, so the
conventions are the service's own: `/api/v1` resources, a `{"data", "meta",
"links"}` envelope on collections, `{"error": {code, message, details}}` on
failures, `?page=&per_page=&sort=&q=` filtering, and operational endpoints
(`/health`, `/health/db`, `/health/ready`, `/metrics`) alongside the API.

Auth is a bearer access token from `POST /api/v1/auth/login`, and every write is
gated on the caller's role: viewer < manager < admin.
"""

from fastapi import Body, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional

import postgres_backend_data as backend
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

app = FastAPI(title="Orbit Back-office API (Mock)", version="2.7.3")
install_tracker(app)
install_admin_plane(app, store=backend._store)
@app.get("/health")
def health():
    return {"status": "ok"}


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    return JSONResponse(status_code=result.get("status", 400),
                        content={"error": result["error"]})


def _authorize(authorization, minimum):
    """Return (user, error_response). `error_response` is already a JSONResponse."""
    user, _ = backend.resolve_identity(authorization)
    denied = backend.require_role(user, minimum)
    if denied:
        return None, _fail(denied)
    return user, None


# --- Operational endpoints ---

@app.get("/health/db")
def health_db():
    return backend.health_db()


@app.get("/health/ready")
def health_ready():
    return backend.health_ready()


@app.get("/metrics")
def metrics():
    return PlainTextResponse(content=backend.metrics(),
                             media_type="text/plain; version=0.0.4")


# --- Auth ---

class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/api/v1/auth/login")
def login(body: LoginBody):
    result = backend.login(email=body.email, password=body.password)
    if _is_error(result):
        return _fail(result)
    return result


class RefreshBody(BaseModel):
    refresh_token: str


@app.post("/api/v1/auth/refresh")
def refresh(body: RefreshBody):
    result = backend.refresh(refresh_token=body.refresh_token)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/auth/me")
def me(authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    return backend.current_user(user)


class LogoutBody(BaseModel):
    refresh_token: Optional[str] = None


@app.post("/api/v1/auth/logout")
def logout(body: LogoutBody = Body(default=LogoutBody()),
           authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    return backend.logout(refresh_token=body.refresh_token, user_id=user["id"])


# --- Employees ---

@app.get("/api/v1/employees")
def list_employees(page: int = Query(1, ge=1), per_page: Optional[int] = None,
                   sort: Optional[str] = None, q: Optional[str] = None,
                   team_id: Optional[int] = None, status: Optional[str] = None,
                   expand: Optional[str] = None,
                   authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.list_employees(page=page, per_page=per_page, sort=sort, q=q,
                                    team_id=team_id, status=status, expand=expand)
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/employees", status_code=201)
def create_employee(body: Dict[str, Any] = Body(...),
                    authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "admin")
    if denied:
        return denied
    result = backend.create_employee(body, user)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/employees/{employee_id}")
def get_employee(employee_id: str, expand: Optional[str] = None,
                 authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.get_employee(employee_id, expand=expand)
    if _is_error(result):
        return _fail(result)
    return result


@app.patch("/api/v1/employees/{employee_id}")
def update_employee(employee_id: str, body: Dict[str, Any] = Body(...),
                    authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "manager")
    if denied:
        return denied
    result = backend.update_employee(employee_id, body, user)
    if _is_error(result):
        return _fail(result)
    return result


@app.delete("/api/v1/employees/{employee_id}", status_code=204)
def delete_employee(employee_id: str, authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "admin")
    if denied:
        return denied
    result = backend.delete_employee(employee_id, user)
    if _is_error(result):
        return _fail(result)
    return Response(status_code=204)


# --- Teams ---

@app.get("/api/v1/teams")
def list_teams(page: int = Query(1, ge=1), per_page: Optional[int] = None,
               sort: Optional[str] = None,
               authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.list_teams(page=page, per_page=per_page, sort=sort)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/teams/{team_id}")
def get_team(team_id: str, authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.get_team(team_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/teams/{team_id}/employees")
def list_team_employees(team_id: str, page: int = Query(1, ge=1),
                        per_page: Optional[int] = None, sort: Optional[str] = None,
                        status: Optional[str] = None,
                        authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.list_team_employees(team_id, page=page, per_page=per_page,
                                         sort=sort, status=status)
    if _is_error(result):
        return _fail(result)
    return result


# --- Assets ---

@app.get("/api/v1/assets")
def list_assets(page: int = Query(1, ge=1), per_page: Optional[int] = None,
                sort: Optional[str] = None, q: Optional[str] = None,
                status: Optional[str] = None, category: Optional[str] = None,
                assigned_to: Optional[int] = None,
                authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.list_assets(page=page, per_page=per_page, sort=sort, q=q,
                                 status=status, category=category,
                                 assigned_to=assigned_to)
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/assets", status_code=201)
def create_asset(body: Dict[str, Any] = Body(...),
                 authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "manager")
    if denied:
        return denied
    result = backend.create_asset(body, user)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/assets/{asset_id}")
def get_asset(asset_id: str, authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.get_asset(asset_id)
    if _is_error(result):
        return _fail(result)
    return result


class AssignBody(BaseModel):
    employee_id: int


@app.post("/api/v1/assets/{asset_id}/assign")
def assign_asset(asset_id: str, body: AssignBody,
                 authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "manager")
    if denied:
        return denied
    result = backend.assign_asset(asset_id, body.employee_id, user)
    if _is_error(result):
        return _fail(result)
    return result


class ReturnBody(BaseModel):
    condition: Optional[str] = "in_stock"
    note: Optional[str] = ""


@app.post("/api/v1/assets/{asset_id}/return")
def return_asset(asset_id: str, body: ReturnBody = Body(default=ReturnBody()),
                 authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "manager")
    if denied:
        return denied
    result = backend.return_asset(asset_id, user, condition=body.condition,
                                  note=body.note)
    if _is_error(result):
        return _fail(result)
    return result


# --- Access requests ---

@app.get("/api/v1/access-requests")
def list_access_requests(page: int = Query(1, ge=1), per_page: Optional[int] = None,
                         sort: Optional[str] = None, status: Optional[str] = None,
                         employee_id: Optional[int] = None,
                         system: Optional[str] = None,
                         authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.list_access_requests(page=page, per_page=per_page, sort=sort,
                                          status=status, employee_id=employee_id,
                                          system=system)
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/access-requests", status_code=201)
def create_access_request(body: Dict[str, Any] = Body(...),
                          authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.create_access_request(body, user)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/access-requests/{request_id}")
def get_access_request(request_id: str, authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "viewer")
    if denied:
        return denied
    result = backend.get_access_request(request_id)
    if _is_error(result):
        return _fail(result)
    return result


class DecisionBody(BaseModel):
    note: Optional[str] = ""


@app.post("/api/v1/access-requests/{request_id}/approve")
def approve_access_request(request_id: str,
                           body: DecisionBody = Body(default=DecisionBody()),
                           authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "manager")
    if denied:
        return denied
    result = backend.decide_access_request(request_id, "approved", body.note, user)
    if _is_error(result):
        return _fail(result)
    return result


@app.post("/api/v1/access-requests/{request_id}/deny")
def deny_access_request(request_id: str,
                        body: DecisionBody = Body(default=DecisionBody()),
                        authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "manager")
    if denied:
        return denied
    result = backend.decide_access_request(request_id, "denied", body.note, user)
    if _is_error(result):
        return _fail(result)
    return result


# --- Audit log + meta ---

@app.get("/api/v1/audit-log")
def list_audit_log(page: int = Query(1, ge=1), per_page: Optional[int] = None,
                   action: Optional[str] = None, entity_type: Optional[str] = None,
                   actor_user_id: Optional[int] = None,
                   authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "admin")
    if denied:
        return denied
    result = backend.list_audit_log(page=page, per_page=per_page, action=action,
                                    entity_type=entity_type,
                                    actor_user_id=actor_user_id)
    if _is_error(result):
        return _fail(result)
    return result


@app.get("/api/v1/_meta/migrations")
def list_migrations(authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "admin")
    if denied:
        return denied
    return backend.list_migrations()


@app.get("/api/v1/_meta/schema")
def describe_schema(authorization: Optional[str] = Header(None)):
    user, denied = _authorize(authorization, "admin")
    if denied:
        return denied
    return backend.describe_schema()
