#!/usr/bin/env python3
"""CLI helper for the Logto API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$LOGTO_API_URL (override with --url). POST/PATCH bodies are read from --data
(JSON string) or --data-file.

Management API calls need a bearer issued FOR https://default.logto.app/api;
--token defaults to the seeded full-access one. OIDC calls need no bearer.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MANAGEMENT_TOKEN = "logto_at_ci_full_9f14c73e0b2a"


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
    if not raw:
        return {"status": resp.status}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


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
    p = argparse.ArgumentParser(description="Query the Logto API (Mock) mock API")
    # OIDC plane
    p.add_argument("--discovery", action="store_true",
                   help="GET /oidc/.well-known/openid-configuration")
    p.add_argument("--jwks", action="store_true", help="GET /oidc/jwks")
    p.add_argument("--authorize", action="store_true", help="GET /oidc/auth")
    p.add_argument("--token", dest="token_request", action="store_true",
                   help="POST /oidc/token")
    p.add_argument("--introspect", action="store_true",
                   help="POST /oidc/token/introspection")
    p.add_argument("--revoke", action="store_true",
                   help="POST /oidc/token/revocation")
    p.add_argument("--userinfo", action="store_true", help="GET /oidc/me")
    # Management API
    p.add_argument("--status", action="store_true", help="GET /api/status")
    p.add_argument("--users", action="store_true", help="GET /api/users")
    p.add_argument("--create-user", action="store_true", help="POST /api/users")
    p.add_argument("--user", metavar="USER_ID", nargs=1, help="GET /api/users/{id}")
    p.add_argument("--update-user", metavar="USER_ID", nargs=1,
                   help="PATCH /api/users/{id}")
    p.add_argument("--delete-user", metavar="USER_ID", nargs=1,
                   help="DELETE /api/users/{id}")
    p.add_argument("--set-password", metavar="USER_ID", nargs=1,
                   help="PATCH /api/users/{id}/password")
    p.add_argument("--verify-password", metavar="USER_ID", nargs=1,
                   help="POST /api/users/{id}/password/verify")
    p.add_argument("--set-suspended", metavar="USER_ID", nargs=1,
                   help="PATCH /api/users/{id}/is-suspended")
    p.add_argument("--custom-data", metavar="USER_ID", nargs=1,
                   help="GET /api/users/{id}/custom-data")
    p.add_argument("--patch-custom-data", metavar="USER_ID", nargs=1,
                   help="PATCH /api/users/{id}/custom-data")
    p.add_argument("--identities", metavar="USER_ID", nargs=1,
                   help="GET /api/users/{id}/identities")
    p.add_argument("--unlink-identity", metavar=("USER_ID", "TARGET"), nargs=2,
                   help="DELETE /api/users/{id}/identities/{target}")
    p.add_argument("--user-roles", metavar="USER_ID", nargs=1,
                   help="GET /api/users/{id}/roles")
    p.add_argument("--grant-role", metavar="USER_ID", nargs=1,
                   help="POST /api/users/{id}/roles")
    p.add_argument("--revoke-role", metavar=("USER_ID", "ROLE_ID"), nargs=2,
                   help="DELETE /api/users/{id}/roles/{roleId}")
    p.add_argument("--user-organizations", metavar="USER_ID", nargs=1,
                   help="GET /api/users/{id}/organizations")
    p.add_argument("--roles", action="store_true", help="GET /api/roles")
    p.add_argument("--create-role", action="store_true", help="POST /api/roles")
    p.add_argument("--role", metavar="ROLE_ID", nargs=1, help="GET /api/roles/{id}")
    p.add_argument("--delete-role", metavar="ROLE_ID", nargs=1,
                   help="DELETE /api/roles/{id}")
    p.add_argument("--applications", action="store_true",
                   help="GET /api/applications")
    p.add_argument("--create-application", action="store_true",
                   help="POST /api/applications")
    p.add_argument("--application", metavar="APP_ID", nargs=1,
                   help="GET /api/applications/{id}")
    p.add_argument("--delete-application", metavar="APP_ID", nargs=1,
                   help="DELETE /api/applications/{id}")
    p.add_argument("--resources", action="store_true", help="GET /api/resources")
    p.add_argument("--resource-scopes", metavar="RESOURCE_ID", nargs=1,
                   help="GET /api/resources/{id}/scopes")
    p.add_argument("--organizations", action="store_true",
                   help="GET /api/organizations")
    p.add_argument("--create-organization", action="store_true",
                   help="POST /api/organizations")
    p.add_argument("--organization", metavar="ORG_ID", nargs=1,
                   help="GET /api/organizations/{id}")
    p.add_argument("--delete-organization", metavar="ORG_ID", nargs=1,
                   help="DELETE /api/organizations/{id}")
    p.add_argument("--organization-users", metavar="ORG_ID", nargs=1,
                   help="GET /api/organizations/{id}/users")
    p.add_argument("--add-organization-users", metavar="ORG_ID", nargs=1,
                   help="POST /api/organizations/{id}/users")
    p.add_argument("--remove-organization-user", metavar=("ORG_ID", "USER_ID"),
                   nargs=2, help="DELETE /api/organizations/{id}/users/{userId}")
    p.add_argument("--set-organization-roles", metavar=("ORG_ID", "USER_ID"),
                   nargs=2,
                   help="POST /api/organizations/{id}/users/{userId}/roles")
    p.add_argument("--organization-roles", action="store_true",
                   help="GET /api/organization-roles")
    p.add_argument("--organization-scopes", action="store_true",
                   help="GET /api/organization-scopes")
    p.add_argument("--my-organization", action="store_true",
                   help="GET /api/my-organization (needs an organization token)")
    p.add_argument("--connectors", action="store_true", help="GET /api/connectors")
    p.add_argument("--connector", metavar="CONNECTOR_ID", nargs=1,
                   help="GET /api/connectors/{id}")
    p.add_argument("--sign-in-exp", action="store_true", help="GET /api/sign-in-exp")
    p.add_argument("--update-sign-in-exp", action="store_true",
                   help="PATCH /api/sign-in-exp")
    p.add_argument("--logs", action="store_true", help="GET /api/logs")
    p.add_argument("--log", metavar="LOG_ID", nargs=1, help="GET /api/logs/{id}")
    p.add_argument("--dashboard", action="store_true",
                   help="GET /api/dashboard/users/total")
    p.add_argument("--query", metavar="QS", default="",
                   help="Query string appended to reads, e.g. 'page=1&page_size=5'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--bearer", default=MANAGEMENT_TOKEN,
                   help="Bearer token (default: the seeded full-access management token)")
    p.add_argument("--url", default=os.environ.get("LOGTO_API_URL",
                                                   "http://localhost:8116"),
                   help="API base URL (default: $LOGTO_API_URL or http://localhost:8116)")
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
    return f"{path}?{args.query}" if args.query else path


_SIMPLE_GETS = [("discovery", "/oidc/.well-known/openid-configuration", False),
                ("jwks", "/oidc/jwks", False),
                ("authorize", "/oidc/auth", False),
                ("userinfo", "/oidc/me", True),
                ("status", "/api/status", False),
                ("users", "/api/users", True),
                ("roles", "/api/roles", True),
                ("applications", "/api/applications", True),
                ("resources", "/api/resources", True),
                ("organizations", "/api/organizations", True),
                ("organization_roles", "/api/organization-roles", True),
                ("organization_scopes", "/api/organization-scopes", True),
                ("my_organization", "/api/my-organization", True),
                ("connectors", "/api/connectors", True),
                ("sign_in_exp", "/api/sign-in-exp", True),
                ("logs", "/api/logs", True),
                ("dashboard", "/api/dashboard/users/total", True)]

_SIMPLE_SENDS = [("token_request", "/oidc/token", "POST", False),
                 ("introspect", "/oidc/token/introspection", "POST", False),
                 ("revoke", "/oidc/token/revocation", "POST", False),
                 ("create_user", "/api/users", "POST", True),
                 ("create_role", "/api/roles", "POST", True),
                 ("create_application", "/api/applications", "POST", True),
                 ("create_organization", "/api/organizations", "POST", True),
                 ("update_sign_in_exp", "/api/sign-in-exp", "PATCH", True)]

_ONE_ARG = [("user", "/api/users/{id}", "GET"),
            ("update_user", "/api/users/{id}", "PATCH"),
            ("delete_user", "/api/users/{id}", "DELETE"),
            ("set_password", "/api/users/{id}/password", "PATCH"),
            ("verify_password", "/api/users/{id}/password/verify", "POST"),
            ("set_suspended", "/api/users/{id}/is-suspended", "PATCH"),
            ("custom_data", "/api/users/{id}/custom-data", "GET"),
            ("patch_custom_data", "/api/users/{id}/custom-data", "PATCH"),
            ("identities", "/api/users/{id}/identities", "GET"),
            ("user_roles", "/api/users/{id}/roles", "GET"),
            ("grant_role", "/api/users/{id}/roles", "POST"),
            ("user_organizations", "/api/users/{id}/organizations", "GET"),
            ("role", "/api/roles/{id}", "GET"),
            ("delete_role", "/api/roles/{id}", "DELETE"),
            ("application", "/api/applications/{id}", "GET"),
            ("delete_application", "/api/applications/{id}", "DELETE"),
            ("resource_scopes", "/api/resources/{id}/scopes", "GET"),
            ("organization", "/api/organizations/{id}", "GET"),
            ("delete_organization", "/api/organizations/{id}", "DELETE"),
            ("organization_users", "/api/organizations/{id}/users", "GET"),
            ("add_organization_users", "/api/organizations/{id}/users", "POST"),
            ("connector", "/api/connectors/{id}", "GET"),
            ("log", "/api/logs/{id}", "GET")]

_TWO_ARGS = [("unlink_identity", "/api/users/{id}/identities/{target}", "DELETE"),
             ("revoke_role", "/api/users/{id}/roles/{roleId}", "DELETE"),
             ("remove_organization_user",
              "/api/organizations/{id}/users/{userId}", "DELETE"),
             ("set_organization_roles",
              "/api/organizations/{id}/users/{userId}/roles", "POST")]


def _dispatch(args, base):
    token = args.bearer
    for flag, path, needs_token in _SIMPLE_GETS:
        if getattr(args, flag):
            return show(_request(base, _qs(args, path), "GET",
                                 token=token if needs_token else None))
    for flag, path, method, needs_token in _SIMPLE_SENDS:
        if getattr(args, flag):
            return show(_request(base, path, method, _body(args),
                                 token=token if needs_token else None))
    for flag, path, method in _ONE_ARG:
        value = getattr(args, flag)
        if value:
            full = _qs(args, _fill(path, value)) if method == "GET" \
                else _fill(path, value)
            payload = _body(args) if method in ("POST", "PATCH") else None
            return show(_request(base, full, method, payload, token=token))
    for flag, path, method in _TWO_ARGS:
        value = getattr(args, flag)
        if value:
            payload = _body(args) if method == "POST" else None
            return show(_request(base, _fill(path, value), method, payload,
                                 token=token))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
