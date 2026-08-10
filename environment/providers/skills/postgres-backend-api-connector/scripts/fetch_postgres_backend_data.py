#!/usr/bin/env python3
"""CLI helper for the Orbit Back-office API (Mock) — a plain PostgreSQL backend.

Generated read/write helper: one flag per endpoint. Base URL comes from
$POSTGRES_BACKEND_API_URL (override with --url). POST/PATCH bodies are read from
--data (JSON string) or --data-file; DELETE/GET take only path params. Use
--token to choose the role and the query flags for filtering.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ADMIN_TOKEN = "at_static_admin_9f3c1a7e"


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, token=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path, token=None):
    return _request(base, path, "GET", token=token)


def api_delete(base, path, token=None):
    return _request(base, path, "DELETE", token=token)


def api_send(base, path, method, body, token=None):
    return _request(base, path, method, body if body is not None else {}, token=token)


def _body(args):
    if getattr(args, "data_file", None):
        with open(args.data_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if getattr(args, "data", None):
        return json.loads(args.data)
    return {}


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data)
    return 0


def main():
    p = argparse.ArgumentParser(description="Query the Orbit Back-office API (Mock)")
    p.add_argument("--get-health-db", action="store_true", help="GET /health/db")
    p.add_argument("--get-health-ready", action="store_true", help="GET /health/ready")
    p.add_argument("--get-metrics", action="store_true", help="GET /metrics")
    p.add_argument("--post-login", action="store_true", help="POST /api/v1/auth/login")
    p.add_argument("--post-refresh", action="store_true", help="POST /api/v1/auth/refresh")
    p.add_argument("--get-me", action="store_true", help="GET /api/v1/auth/me")
    p.add_argument("--post-logout", action="store_true", help="POST /api/v1/auth/logout")
    p.add_argument("--get-employees", action="store_true", help="GET /api/v1/employees")
    p.add_argument("--post-employee", action="store_true", help="POST /api/v1/employees")
    p.add_argument("--get-employee", metavar="EMPLOYEE_ID", nargs=1, help="GET /api/v1/employees/{id}")
    p.add_argument("--patch-employee", metavar="EMPLOYEE_ID", nargs=1, help="PATCH /api/v1/employees/{id}")
    p.add_argument("--delete-employee", metavar="EMPLOYEE_ID", nargs=1, help="DELETE /api/v1/employees/{id}")
    p.add_argument("--get-teams", action="store_true", help="GET /api/v1/teams")
    p.add_argument("--get-team", metavar="TEAM_ID", nargs=1, help="GET /api/v1/teams/{id}")
    p.add_argument("--get-team-employees", metavar="TEAM_ID", nargs=1, help="GET /api/v1/teams/{id}/employees")
    p.add_argument("--get-assets", action="store_true", help="GET /api/v1/assets")
    p.add_argument("--post-asset", action="store_true", help="POST /api/v1/assets")
    p.add_argument("--get-asset", metavar="ASSET_ID", nargs=1, help="GET /api/v1/assets/{id}")
    p.add_argument("--assign-asset", metavar="ASSET_ID", nargs=1, help="POST /api/v1/assets/{id}/assign")
    p.add_argument("--return-asset", metavar="ASSET_ID", nargs=1, help="POST /api/v1/assets/{id}/return")
    p.add_argument("--get-access-requests", action="store_true", help="GET /api/v1/access-requests")
    p.add_argument("--post-access-request", action="store_true", help="POST /api/v1/access-requests")
    p.add_argument("--get-access-request", metavar="REQUEST_ID", nargs=1, help="GET /api/v1/access-requests/{id}")
    p.add_argument("--approve-request", metavar="REQUEST_ID", nargs=1, help="POST /api/v1/access-requests/{id}/approve")
    p.add_argument("--deny-request", metavar="REQUEST_ID", nargs=1, help="POST /api/v1/access-requests/{id}/deny")
    p.add_argument("--get-audit-log", action="store_true", help="GET /api/v1/audit-log")
    p.add_argument("--get-migrations", action="store_true", help="GET /api/v1/_meta/migrations")
    p.add_argument("--get-schema", action="store_true", help="GET /api/v1/_meta/schema")
    p.add_argument("--page", metavar="N", help="Page number")
    p.add_argument("--per-page", metavar="N", help="Page size (max 100)")
    p.add_argument("--sort", metavar="SPEC", help="Sort spec, e.g. '-started_on,last_name'")
    p.add_argument("--q", metavar="TERM", help="Substring search")
    p.add_argument("--status", metavar="VALUE", help="Status filter")
    p.add_argument("--team-id", metavar="ID", help="Team filter")
    p.add_argument("--category", metavar="VALUE", help="Asset category filter")
    p.add_argument("--system", metavar="VALUE", help="Access-request system filter")
    p.add_argument("--expand", metavar="LIST", help="Expansions, e.g. 'team,manager,assets'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PATCH)")
    p.add_argument("--token", default=ADMIN_TOKEN,
                   help="Bearer token (default: the admin static token; '' for anonymous)")
    p.add_argument("--url", default=os.environ.get("POSTGRES_BACKEND_API_URL",
                                                   "http://localhost:8107"),
                   help="API base URL (default: $POSTGRES_BACKEND_API_URL or http://localhost:8107)")
    args = p.parse_args()
    base = args.url.rstrip("/")

    try:
        return _dispatch(args, base)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        return 1


def _qs(args, path):
    params = []
    for flag, name in (("page", "page"), ("per_page", "per_page"), ("sort", "sort"),
                       ("q", "q"), ("status", "status"), ("team_id", "team_id"),
                       ("category", "category"), ("system", "system"),
                       ("expand", "expand")):
        value = getattr(args, flag, None)
        if value:
            params.append((name, value))
    return f"{path}?{urllib.parse.urlencode(params)}" if params else path


def _dispatch(args, base):
    token = args.token
    if args.get_health_db:
        return show(api_get(base, "/health/db", token))
    if args.get_health_ready:
        return show(api_get(base, "/health/ready", token))
    if args.get_metrics:
        return show(api_get(base, "/metrics", token))
    if args.post_login:
        return show(api_send(base, "/api/v1/auth/login", "POST", _body(args), None))
    if args.post_refresh:
        return show(api_send(base, "/api/v1/auth/refresh", "POST", _body(args), None))
    if args.get_me:
        return show(api_get(base, "/api/v1/auth/me", token))
    if args.post_logout:
        return show(api_send(base, "/api/v1/auth/logout", "POST", _body(args), token))
    if args.get_employees:
        return show(api_get(base, _qs(args, "/api/v1/employees"), token))
    if args.post_employee:
        return show(api_send(base, "/api/v1/employees", "POST", _body(args), token))
    if args.get_employee:
        return show(api_get(base, _qs(args, _fill('/api/v1/employees/{id}', args.get_employee)), token))
    if args.patch_employee:
        return show(api_send(base, _fill('/api/v1/employees/{id}', args.patch_employee), 'PATCH', _body(args), token))
    if args.delete_employee:
        return show(api_delete(base, _fill('/api/v1/employees/{id}', args.delete_employee), token))
    if args.get_teams:
        return show(api_get(base, _qs(args, "/api/v1/teams"), token))
    if args.get_team:
        return show(api_get(base, _fill('/api/v1/teams/{id}', args.get_team), token))
    if args.get_team_employees:
        return show(api_get(base, _qs(args, _fill('/api/v1/teams/{id}/employees', args.get_team_employees)), token))
    if args.get_assets:
        return show(api_get(base, _qs(args, "/api/v1/assets"), token))
    if args.post_asset:
        return show(api_send(base, "/api/v1/assets", "POST", _body(args), token))
    if args.get_asset:
        return show(api_get(base, _fill('/api/v1/assets/{id}', args.get_asset), token))
    if args.assign_asset:
        return show(api_send(base, _fill('/api/v1/assets/{id}/assign', args.assign_asset), 'POST', _body(args), token))
    if args.return_asset:
        return show(api_send(base, _fill('/api/v1/assets/{id}/return', args.return_asset), 'POST', _body(args), token))
    if args.get_access_requests:
        return show(api_get(base, _qs(args, "/api/v1/access-requests"), token))
    if args.post_access_request:
        return show(api_send(base, "/api/v1/access-requests", "POST", _body(args), token))
    if args.get_access_request:
        return show(api_get(base, _fill('/api/v1/access-requests/{id}', args.get_access_request), token))
    if args.approve_request:
        return show(api_send(base, _fill('/api/v1/access-requests/{id}/approve', args.approve_request), 'POST', _body(args), token))
    if args.deny_request:
        return show(api_send(base, _fill('/api/v1/access-requests/{id}/deny', args.deny_request), 'POST', _body(args), token))
    if args.get_audit_log:
        return show(api_get(base, _qs(args, "/api/v1/audit-log"), token))
    if args.get_migrations:
        return show(api_get(base, "/api/v1/_meta/migrations", token))
    if args.get_schema:
        return show(api_get(base, "/api/v1/_meta/schema", token))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
