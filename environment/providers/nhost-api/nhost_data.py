"""Data access module for the Nhost API mock service.

Models a self-hosted Nhost project ("Orbit Insights"): Hasura GraphQL over
Postgres at /v1/graphql, Hasura Auth at /v1/auth, Hasura Storage at
/v1/storage and serverless functions at /v1/functions.

The GraphQL surface is served by `graphql_engine`, which this module wires to
the store's tables, the relationship graph and the role permissions seeded in
`permissions.json` — the same shape Hasura keeps in its metadata, so drifting a
permission row changes what a role can see. Mutations are held in process
memory and reset on restart.
"""

import json
import time
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str, strict_bool)

import graphql_engine
from graphql_engine import GraphQLError

_store = get_store("nhost-api")
_API = "nhost-api"


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


def _load_project():
    with open(DATA_DIR / "project.json", encoding="utf-8") as f:
        return json.load(f)


_store.register("users", primary_key="id",
                initial_loader=lambda: _coerce_users(_load("users.json", "users")))
_store.register("workspaces", primary_key="id",
                initial_loader=lambda: _coerce_workspaces(_load("workspaces.json", "workspaces")))
_store.register("workspace_members", primary_key="id",
                initial_loader=lambda: _coerce_members(_load("workspace_members.json", "workspace_members")))
_store.register("dashboards", primary_key="id",
                initial_loader=lambda: _coerce_dashboards(_load("dashboards.json", "dashboards")))
_store.register("saved_queries", primary_key="id",
                initial_loader=lambda: _coerce_queries(_load("saved_queries.json", "saved_queries")))
_store.register("permissions", primary_key="id",
                initial_loader=lambda: _coerce_permissions(_load("permissions.json", "permissions")))
_store.register("buckets", primary_key="id",
                initial_loader=lambda: _coerce_buckets(_load("buckets.json", "buckets")))
_store.register("files", primary_key="id",
                initial_loader=lambda: _coerce_files(_load("files.json", "files")))
_store.register("functions", primary_key="name",
                initial_loader=lambda: _coerce_functions(_load("functions.json", "functions")))
_store.register_document("project", initial_loader=_load_project)
# Born-empty: refresh sessions are minted at runtime by the auth endpoints.
_store.register("sessions", primary_key="refresh_token", initial_loader=lambda: [])


def _users_rows():
    return _store.table("users").rows()


def _workspaces_rows():
    return _store.table("workspaces").rows()


def _members_rows():
    return _store.table("workspace_members").rows()


def _dashboards_rows():
    return _store.table("dashboards").rows()


def _queries_rows():
    return _store.table("saved_queries").rows()


def _permissions_rows():
    return _store.table("permissions").rows()


def _buckets_rows():
    return _store.table("buckets").rows()


def _files_rows():
    return _store.table("files").rows()


def _functions_rows():
    return _store.table("functions").rows()


def _project_doc():
    return _store.document("project").get()


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "+00:00"


def _semi_list(r, column):
    raw = opt_str(r, column, default="")
    return [part for part in raw.split(";") if part]


# ---------------------------------------------------------------------------
# Load + coerce
# ---------------------------------------------------------------------------

def _coerce_users(rows):
    return [{**_strip_ctx(r), "roles": _semi_list(r, "roles"),
             "email_verified": strict_bool(r, "email_verified"),
             "disabled": strict_bool(r, "disabled")} for r in rows]


def _coerce_workspaces(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "seats": opt_int(r, "seats", default=0),
             "monthly_events": opt_int(r, "monthly_events", default=0)} for r in rows]


def _coerce_members(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "workspace_id": opt_int(r, "workspace_id", default=0)} for r in rows]


def _coerce_dashboards(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "workspace_id": opt_int(r, "workspace_id", default=0),
             "widget_count": opt_int(r, "widget_count", default=0),
             "starred": strict_bool(r, "starred")} for r in rows]


def _coerce_queries(rows):
    return [{**_strip_ctx(r), "id": opt_int(r, "id", default=0),
             "dashboard_id": opt_int(r, "dashboard_id", default=0),
             "runtime_ms": opt_int(r, "runtime_ms", default=0),
             "rows_returned": opt_int(r, "rows_returned", default=0),
             "cached": strict_bool(r, "cached")} for r in rows]


def _coerce_permissions(rows):
    out = []
    for r in rows:
        columns = opt_str(r, "columns", default="*")
        out.append({**_strip_ctx(r), "id": opt_int(r, "id", default=0),
                    "filter": json.loads(opt_str(r, "filter", default="{}") or "{}"),
                    "columns": None if columns.strip() == "*" else
                    [c.strip() for c in columns.split(",") if c.strip()],
                    "limit": opt_int(r, "limit", default=None)})
    return out


def _coerce_buckets(rows):
    return [{**_strip_ctx(r),
             "min_upload_file_size": opt_int(r, "min_upload_file_size", default=1),
             "max_upload_file_size": opt_int(r, "max_upload_file_size", default=0),
             "download_expiration": opt_int(r, "download_expiration", default=30),
             "presigned_urls_enabled": strict_bool(r, "presigned_urls_enabled")}
            for r in rows]


def _coerce_files(rows):
    return [{**_strip_ctx(r), "size": opt_int(r, "size", default=0),
             "is_uploaded": strict_bool(r, "is_uploaded")} for r in rows]


def _coerce_functions(rows):
    return [{**_strip_ctx(r), "enabled": strict_bool(r, "enabled"),
             "timeout_seconds": opt_int(r, "timeout_seconds", default=15),
             "invocation_count": opt_int(r, "invocation_count", default=0)}
            for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(status, message, code="invalid-request"):
    """Nhost/Hasura-shaped error body. The house `error` key drives the response."""
    return {"error": message, "message": message, "status": status,
            "extensions": {"code": code}}


def _next_serial(table):
    """Next auto-increment id. Scans live rows so admin-plane injections cannot
    collide with a cached counter."""
    ids = [r["id"] for r in _store.table(table).rows() if isinstance(r.get("id"), int)]
    return (max(ids) + 1) if ids else 1


GRAPHQL_TABLES = {
    "users": _users_rows,
    "workspaces": _workspaces_rows,
    "workspace_members": _members_rows,
    "dashboards": _dashboards_rows,
    "saved_queries": _queries_rows,
}

_PRIMARY_KEYS = {name: "id" for name in GRAPHQL_TABLES}

# (table, field) -> (target, local column, remote column, kind)
_RELATIONSHIPS = {
    ("workspaces", "owner"): ("users", "owner_id", "id", "object"),
    ("workspaces", "members"): ("workspace_members", "id", "workspace_id", "array"),
    ("workspaces", "dashboards"): ("dashboards", "id", "workspace_id", "array"),
    ("workspace_members", "workspace"): ("workspaces", "workspace_id", "id", "object"),
    ("workspace_members", "user"): ("users", "user_id", "id", "object"),
    ("dashboards", "workspace"): ("workspaces", "workspace_id", "id", "object"),
    ("dashboards", "creator"): ("users", "created_by", "id", "object"),
    ("dashboards", "queries"): ("saved_queries", "id", "dashboard_id", "array"),
    ("saved_queries", "dashboard"): ("dashboards", "dashboard_id", "id", "object"),
    ("users", "memberships"): ("workspace_members", "id", "user_id", "array"),
}


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

ADMIN_ROLE = "admin"
USER_ROLE = "user"
PUBLIC_ROLE = "public"


def resolve_role(admin_secret=None, authorization=None, requested_role=None):
    """Map Nhost auth headers onto (role, user_id).

    `x-hasura-admin-secret` grants the `admin` role, which bypasses every
    permission. A bearer access token authenticates as the project's session
    user with the `user` role -- any token is accepted, matching the fleet
    convention. Without either, the caller is the `public` role.
    `x-hasura-role` may narrow an admin request to another role, exactly as
    Hasura allows.
    """
    credentials = _project_doc().get("credentials", {})
    if (admin_secret or "").strip():
        role = (requested_role or ADMIN_ROLE).strip() or ADMIN_ROLE
        user_id = credentials.get("sessionUserId", "") if role != ADMIN_ROLE else ""
        return role, user_id
    token = (authorization or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if token:
        return USER_ROLE, credentials.get("sessionUserId", "")
    return PUBLIC_ROLE, ""


def _permission_lookup(role):
    """Return a `permission_for(table, action)` callable for the engine."""
    if role == ADMIN_ROLE:
        return lambda table, action: {}
    rows = _permissions_rows()

    def lookup(table, action):
        match = next((p for p in rows
                      if p["role"] == role and p["table"] == table
                      and p["action"] == action), None)
        if not match:
            return None
        return {"filter": match["filter"], "columns": match["columns"],
                "limit": match["limit"]}
    return lookup


def _schema_for(role, user_id):
    return graphql_engine.Schema(
        tables=GRAPHQL_TABLES, primary_keys=_PRIMARY_KEYS,
        relationships=_RELATIONSHIPS,
        session={"x-hasura-user-id": user_id, "x-hasura-role": role},
    )


# ---------------------------------------------------------------------------
# GraphQL
# ---------------------------------------------------------------------------

def run_graphql(query=None, variables=None, operation_name=None,
                role=PUBLIC_ROLE, user_id=""):
    if not query or not str(query).strip():
        return {"errors": [{"message": "query is required",
                            "extensions": {"code": "validation-failed",
                                           "path": "$"}}]}
    schema = _schema_for(role, user_id)
    executor = graphql_engine.Executor(
        schema, permission_for=_permission_lookup(role),
        mutations=_mutation_handlers(role, user_id),
    )
    try:
        operations = graphql_engine.parse(query)
        operation = _pick_operation(operations, operation_name)
        return {"data": executor.execute(operation, variables or {})}
    except GraphQLError as exc:
        return {"errors": [{"message": exc.message,
                            "extensions": {"code": exc.code, "path": "$"}}]}


def _pick_operation(operations, operation_name):
    if operation_name:
        match = next((o for o in operations if o["name"] == operation_name), None)
        if not match:
            raise GraphQLError(f"operation '{operation_name}' not found in document")
        return match
    if len(operations) > 1:
        raise GraphQLError("operationName is required for a multi-operation document")
    return operations[0]


def _mutation_handlers(role, user_id):
    """Build the mutation root fields available to this role."""

    def insert_dashboard(args):
        _require_write(role, "dashboards", "insert")
        payload = args.get("object") or {}
        workspace_id = payload.get("workspace_id")
        if not _store.table("workspaces").get(workspace_id):
            raise GraphQLError(
                f'Foreign key violation. insert or update on table "dashboards" '
                f'violates foreign key constraint "dashboards_workspace_id_fkey"',
                "constraint-violation")
        if role != ADMIN_ROLE and not _is_member(workspace_id, user_id):
            raise GraphQLError("check constraint of an insert permission has failed",
                               "permission-error")
        now = _now()
        row = {
            "id": _next_serial("dashboards"),
            "workspace_id": workspace_id,
            "name": payload.get("name", ""),
            "slug": payload.get("slug", ""),
            "visibility": payload.get("visibility", "workspace"),
            "widget_count": int(payload.get("widget_count") or 0),
            "created_by": user_id or payload.get("created_by", ""),
            "starred": bool(payload.get("starred", False)),
            "created_at": now,
            "updated_at": now,
        }
        _store_insert("dashboards", row)
        return "dashboards", row

    def update_dashboard(args):
        _require_write(role, "dashboards", "update")
        pk = (args.get("pk_columns") or {}).get("id")
        row = _store.table("dashboards").get(pk)
        if not row:
            return "dashboards", None
        if role != ADMIN_ROLE and not _is_member(row["workspace_id"], user_id):
            return "dashboards", None
        patch = dict(args.get("_set") or {})
        if "widget_count" in patch:
            patch["widget_count"] = int(patch["widget_count"])
        patch["updated_at"] = _now()
        return "dashboards", _store.table("dashboards").patch(pk, patch)

    def delete_dashboard(args):
        if role != ADMIN_ROLE:
            raise GraphQLError(
                "field 'delete_dashboards_by_pk' not found in type: 'mutation_root'",
                "validation-failed")
        row = _store.table("dashboards").get(args.get("id"))
        if not row:
            return "dashboards", None
        _store.table("saved_queries").delete_where(
            lambda q: q["dashboard_id"] == row["id"])
        _store.table("dashboards").delete(row["id"])
        return "dashboards", row

    return {
        "insert_dashboards_one": insert_dashboard,
        "update_dashboards_by_pk": update_dashboard,
        "delete_dashboards_by_pk": delete_dashboard,
    }


def _require_write(role, table, action):
    if role == ADMIN_ROLE:
        return
    rows = _permissions_rows()
    if not any(p["role"] == role and p["table"] == table and p["action"] == action
               for p in rows):
        raise GraphQLError(
            f"field '{action}_{table}_one' not found in type: 'mutation_root'",
            "validation-failed")


def _is_member(workspace_id, user_id):
    return any(m["workspace_id"] == workspace_id and m["user_id"] == user_id
               for m in _members_rows())


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def sign_in(email=None, password=None):
    credentials = _project_doc().get("credentials", {})
    if email != credentials.get("email") or password != credentials.get("password"):
        return _error(401, "Incorrect email or password", "invalid-email-password")
    return {"session": _new_session(credentials.get("sessionUserId", "")), "mfa": None}


def refresh_session(refresh_token=None):
    session = _store.table("sessions").get(refresh_token)
    credentials = _project_doc().get("credentials", {})
    if not session and refresh_token != credentials.get("refreshToken"):
        return _error(401, "Invalid or expired refresh token", "invalid-refresh-token")
    user_id = session["user_id"] if session else credentials.get("sessionUserId", "")
    return _new_session(user_id)


def _new_session(user_id):
    project = _project_doc()
    user = _store.table("users").get(user_id)
    session = {
        "refresh_token": str(uuid.uuid4()),
        "user_id": user_id,
        "created_at": _now(),
    }
    _store.table("sessions").upsert(session)
    return {
        "accessToken": f"eyJhbGciOiJIUzI1NiJ9.user.{uuid.uuid4().hex[:16]}",
        "accessTokenExpiresIn": project["auth"]["access_token_expires_in"],
        "refreshToken": session["refresh_token"],
        "refreshTokenId": session["refresh_token"],
        "user": _public_user(user) if user else None,
    }


def _public_user(user):
    return {"id": user["id"], "email": user["email"],
            "displayName": user["display_name"], "avatarUrl": user["avatar_url"],
            "defaultRole": user["default_role"], "roles": user["roles"],
            "locale": user["locale"], "emailVerified": user["email_verified"],
            "isAnonymous": False, "createdAt": user["created_at"]}


def get_session_user(role=PUBLIC_ROLE, user_id=""):
    if role == PUBLIC_ROLE or not user_id:
        return _error(401, "User is not logged in", "unauthenticated-user")
    user = _store.table("users").get(user_id)
    if not user:
        return _error(401, "User is not logged in", "unauthenticated-user")
    return {"user": _public_user(user)}


def sign_out(refresh_token=None, all_sessions=False):
    if all_sessions:
        cleared = len(_store.table("sessions").rows())
        _store.table("sessions").delete_where(lambda s: True)
        return {"signedOut": True, "sessionsCleared": cleared}
    cleared = 1 if refresh_token and _store.table("sessions").delete(refresh_token) else 0
    return {"signedOut": True, "sessionsCleared": cleared}


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def list_buckets(role=PUBLIC_ROLE, user_id=""):
    if role == PUBLIC_ROLE:
        return _error(403, "You are not authorized to list buckets", "forbidden")
    return {"buckets": _buckets_rows()}


def list_files(bucket_id=None, role=PUBLIC_ROLE, user_id=""):
    if role == PUBLIC_ROLE:
        return _error(403, "You are not authorized to list files", "forbidden")
    rows = _files_rows()
    if bucket_id:
        if not _store.table("buckets").get(bucket_id):
            return _error(404, f"Bucket {bucket_id} not found", "bucket-not-found")
        rows = [f for f in rows if f["bucket_id"] == bucket_id]
    if role != ADMIN_ROLE:
        rows = [f for f in rows if f["uploaded_by_user_id"] == user_id]
    return {"files": rows}


def get_file(file_id, role=PUBLIC_ROLE, user_id=""):
    row = _store.table("files").get(file_id)
    if not row:
        return _error(404, "File not found", "file-not-found")
    if role == PUBLIC_ROLE or (role != ADMIN_ROLE
                               and row["uploaded_by_user_id"] != user_id):
        return _error(403, "You are not authorized to access this file", "forbidden")
    return row


def delete_file(file_id, role=PUBLIC_ROLE, user_id=""):
    if role != ADMIN_ROLE:
        return _error(403, "You are not authorized to delete this file", "forbidden")
    if not _store.table("files").get(file_id):
        return _error(404, "File not found", "file-not-found")
    _store.table("files").delete(file_id)
    return {"deleted": file_id}


# ---------------------------------------------------------------------------
# Functions / metadata / version
# ---------------------------------------------------------------------------

def list_functions():
    return {"functions": _functions_rows()}


def invoke_function(name, payload=None, role=PUBLIC_ROLE, user_id=""):
    fn = _store.table("functions").get(name)
    if not fn:
        return _error(404, f"Function {name} not found", "function-not-found")
    if not fn["enabled"]:
        # A disabled function is simply not deployed, so it is not routed either.
        return _error(404, f"Function {name} is not deployed", "function-not-deployed")
    if role == PUBLIC_ROLE:
        return _error(401, "Missing authorization header", "unauthenticated-user")
    body = _function_output(name, payload or {}, user_id)
    _store.table("functions").patch(name, {
        "invocation_count": fn["invocation_count"] + 1,
        "last_invoked_at": _now(),
    })
    return {"function": name, "statusCode": 200, "body": body}


def _function_output(name, payload, user_id):
    if name == "refresh-usage":
        workspaces = _workspaces_rows()
        return {"refreshed": len(workspaces),
                "total_monthly_events": sum(w["monthly_events"] for w in workspaces),
                "billable_workspaces": len([w for w in workspaces
                                            if w["monthly_events"] > 0])}
    if name == "export-dashboard":
        dashboard = _store.table("dashboards").get(payload.get("dashboard_id"))
        if not dashboard:
            return {"exported": False, "reason": "dashboard not found"}
        return {"exported": True, "dashboard": dashboard["slug"],
                "widgets": dashboard["widget_count"],
                "file": f"{dashboard['slug']}-{time.strftime('%Y-%m-%d', time.gmtime())}.csv"}
    return {"ok": True, "echo": payload, "invoked_by": user_id}


def get_metadata(role=ADMIN_ROLE):
    """Hasura metadata: tracked tables, relationships and select permissions."""
    if role != ADMIN_ROLE:
        return _error(401, "x-hasura-admin-secret is required", "access-denied")
    permissions = _permissions_rows()
    tables = []
    for name in GRAPHQL_TABLES:
        object_relationships, array_relationships = [], []
        for (table, field), (target, local, remote, kind) in _RELATIONSHIPS.items():
            if table != name:
                continue
            entry = {"name": field,
                     "using": {"foreign_key_constraint_on": local if kind == "object"
                               else {"table": target, "column": remote}}}
            (object_relationships if kind == "object" else array_relationships).append(entry)
        tables.append({
            "table": {"schema": "public", "name": name},
            "object_relationships": object_relationships,
            "array_relationships": array_relationships,
            "select_permissions": [
                {"role": p["role"],
                 "permission": {"columns": p["columns"] or "*", "filter": p["filter"],
                                "limit": p["limit"]}}
                for p in permissions if p["table"] == name and p["action"] == "select"],
        })
    return {"resource_version": 41, "metadata": {"version": 3,
                                                 "sources": [{"name": "default",
                                                              "kind": "postgres",
                                                              "tables": tables}]}}


def get_version():
    project = _project_doc()
    return {"subdomain": project["subdomain"], "name": project["name"],
            "region": project["region"], "plan": project["plan"],
            "versions": project["versions"], "endpoints": project["endpoints"]}


def healthz():
    return {"status": "ok", "services": {"hasura": "ok", "auth": "ok",
                                         "storage": "ok", "postgres": "ok"}}


_store.eager_load()
