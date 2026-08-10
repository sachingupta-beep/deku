#!/usr/bin/env python3
"""CLI helper for the SuperTokens Core API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$SUPERTOKENS_API_URL (override with --url). POST/PUT bodies are read from --data
(JSON string) or --data-file. Every request carries the core `api-key` and
`cdi-version` headers; --tenant scopes a recipe call to a tenant other than
`public`.

Remember the core's contract: domain outcomes come back with HTTP 200 and a
`status` string in the body, so check `status` rather than the exit code.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_KEY = "orbit-labs-supertokens-core-key"
CDI_VERSION = "5.1"
DEFAULT_APP_ID = "public"


def _request(base, path, method, body=None, api_key=None, cdi_version=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if api_key:
        headers["api-key"] = api_key
    if cdi_version:
        headers["cdi-version"] = cdi_version
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
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
    p = argparse.ArgumentParser(description="Query the SuperTokens Core API (Mock) mock API")
    p.add_argument("--hello", action="store_true", help="GET /hello")
    p.add_argument("--apiversion", action="store_true", help="GET /apiversion")
    p.add_argument("--config", action="store_true", help="GET /config")
    p.add_argument("--jwks", action="store_true", help="GET /recipe/jwt/jwks")
    p.add_argument("--signup", action="store_true", help="POST /recipe/signup")
    p.add_argument("--signin", action="store_true", help="POST /recipe/signin")
    p.add_argument("--get-user", action="store_true", help="GET /recipe/user")
    p.add_argument("--update-user", action="store_true", help="PUT /recipe/user")
    p.add_argument("--reset-token", action="store_true",
                   help="POST /recipe/user/password/reset/token")
    p.add_argument("--reset-password", action="store_true",
                   help="POST /recipe/user/password/reset")
    p.add_argument("--signinup", action="store_true", help="POST /recipe/signinup")
    p.add_argument("--create-code", action="store_true",
                   help="POST /recipe/signinup/code")
    p.add_argument("--consume-code", action="store_true",
                   help="POST /recipe/signinup/code/consume")
    p.add_argument("--create-session", action="store_true", help="POST /recipe/session")
    p.add_argument("--verify-session", action="store_true",
                   help="POST /recipe/session/verify")
    p.add_argument("--refresh-session", action="store_true",
                   help="POST /recipe/session/refresh")
    p.add_argument("--remove-sessions", action="store_true",
                   help="POST /recipe/session/remove")
    p.add_argument("--user-sessions", action="store_true",
                   help="GET /recipe/session/user")
    p.add_argument("--session-data", action="store_true",
                   help="GET /recipe/session/data")
    p.add_argument("--put-session-data", action="store_true",
                   help="PUT /recipe/session/data")
    p.add_argument("--email-verify-token", action="store_true",
                   help="POST /recipe/user/email/verify/token")
    p.add_argument("--email-verify", action="store_true",
                   help="POST /recipe/user/email/verify")
    p.add_argument("--is-email-verified", action="store_true",
                   help="GET /recipe/user/email/verify")
    p.add_argument("--metadata", action="store_true",
                   help="GET /recipe/user/metadata")
    p.add_argument("--put-metadata", action="store_true",
                   help="PUT /recipe/user/metadata")
    p.add_argument("--remove-metadata", action="store_true",
                   help="POST /recipe/user/metadata/remove")
    p.add_argument("--put-role", action="store_true", help="PUT /recipe/role")
    p.add_argument("--roles", action="store_true", help="GET /recipe/roles")
    p.add_argument("--role-permissions", action="store_true",
                   help="GET /recipe/role/permissions")
    p.add_argument("--remove-role", action="store_true",
                   help="POST /recipe/role/remove")
    p.add_argument("--grant-role", action="store_true", help="PUT /recipe/user/role")
    p.add_argument("--user-roles", action="store_true", help="GET /recipe/user/roles")
    p.add_argument("--revoke-role", action="store_true",
                   help="POST /recipe/user/role/remove")
    p.add_argument("--role-users", action="store_true", help="GET /recipe/role/users")
    p.add_argument("--tenants", action="store_true",
                   help="GET /recipe/multitenancy/tenant/list")
    p.add_argument("--tenant", action="store_true",
                   help="GET /appid-{appId}/{tenantId}/recipe/multitenancy/tenant")
    p.add_argument("--put-tenant", action="store_true",
                   help="PUT /recipe/multitenancy/tenant")
    p.add_argument("--remove-tenant", action="store_true",
                   help="POST /recipe/multitenancy/tenant/remove")
    p.add_argument("--associate-user", action="store_true",
                   help="POST /recipe/multitenancy/tenant/user")
    p.add_argument("--make-primary", action="store_true",
                   help="POST /recipe/accountlinking/user/primary")
    p.add_argument("--link-accounts", action="store_true",
                   help="POST /recipe/accountlinking/user/link")
    p.add_argument("--unlink-account", action="store_true",
                   help="POST /recipe/accountlinking/user/unlink")
    p.add_argument("--users", action="store_true", help="GET /users")
    p.add_argument("--users-count", action="store_true", help="GET /users/count")
    p.add_argument("--user-by-id", action="store_true", help="GET /user/id")
    p.add_argument("--remove-user", action="store_true", help="POST /user/remove")
    p.add_argument("--query", metavar="QS", default="",
                   help="Query string appended to reads, e.g. 'userId=...&limit=10'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--tenant-id", default=None,
                   help="Scope recipe calls to this tenant (default: public)")
    p.add_argument("--app-id", default=DEFAULT_APP_ID, help="App id (default: public)")
    p.add_argument("--api-key", default=API_KEY,
                   help="api-key header value (default: the core key)")
    p.add_argument("--cdi-version", default=CDI_VERSION,
                   help="cdi-version header value (default: 5.1)")
    p.add_argument("--url", default=os.environ.get("SUPERTOKENS_API_URL",
                                                   "http://localhost:8115"),
                   help="API base URL (default: $SUPERTOKENS_API_URL or http://localhost:8115)")
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


def _prefix(args):
    """Tenant-scoped path prefix; empty when the public tenant is wanted."""
    if not args.tenant_id:
        return ""
    return (f"/appid-{urllib.parse.quote(args.app_id, safe='')}"
            f"/{urllib.parse.quote(args.tenant_id, safe='')}")


def _get(args, base, path, scoped=True):
    full = (_prefix(args) if scoped else "") + path
    if args.query:
        full = f"{full}?{args.query}"
    return show(_request(base, full, "GET", api_key=args.api_key,
                         cdi_version=args.cdi_version))


def _send(args, base, path, method="POST", scoped=True):
    full = (_prefix(args) if scoped else "") + path
    return show(_request(base, full, method, _body(args), api_key=args.api_key,
                         cdi_version=args.cdi_version))


_GETS = [("hello", "/hello", False), ("apiversion", "/apiversion", False),
         ("config", "/config", False), ("jwks", "/recipe/jwt/jwks", False),
         ("get_user", "/recipe/user", True),
         ("user_sessions", "/recipe/session/user", True),
         ("session_data", "/recipe/session/data", False),
         ("is_email_verified", "/recipe/user/email/verify", False),
         ("metadata", "/recipe/user/metadata", False),
         ("roles", "/recipe/roles", False),
         ("role_permissions", "/recipe/role/permissions", False),
         ("user_roles", "/recipe/user/roles", True),
         ("role_users", "/recipe/role/users", True),
         ("tenants", "/recipe/multitenancy/tenant/list", False),
         ("tenant", "/recipe/multitenancy/tenant", True),
         ("users", "/users", True), ("users_count", "/users/count", True),
         ("user_by_id", "/user/id", False)]

_SENDS = [("signup", "/recipe/signup", "POST", True),
          ("signin", "/recipe/signin", "POST", True),
          ("update_user", "/recipe/user", "PUT", True),
          ("reset_token", "/recipe/user/password/reset/token", "POST", True),
          ("reset_password", "/recipe/user/password/reset", "POST", True),
          ("signinup", "/recipe/signinup", "POST", True),
          ("create_code", "/recipe/signinup/code", "POST", True),
          ("consume_code", "/recipe/signinup/code/consume", "POST", True),
          ("create_session", "/recipe/session", "POST", True),
          ("verify_session", "/recipe/session/verify", "POST", False),
          ("refresh_session", "/recipe/session/refresh", "POST", False),
          ("remove_sessions", "/recipe/session/remove", "POST", False),
          ("put_session_data", "/recipe/session/data", "PUT", False),
          ("email_verify_token", "/recipe/user/email/verify/token", "POST", True),
          ("email_verify", "/recipe/user/email/verify", "POST", True),
          ("put_metadata", "/recipe/user/metadata", "PUT", False),
          ("remove_metadata", "/recipe/user/metadata/remove", "POST", False),
          ("put_role", "/recipe/role", "PUT", False),
          ("remove_role", "/recipe/role/remove", "POST", False),
          ("grant_role", "/recipe/user/role", "PUT", True),
          ("revoke_role", "/recipe/user/role/remove", "POST", True),
          ("put_tenant", "/recipe/multitenancy/tenant", "PUT", False),
          ("remove_tenant", "/recipe/multitenancy/tenant/remove", "POST", False),
          ("associate_user", "/recipe/multitenancy/tenant/user", "POST", True),
          ("make_primary", "/recipe/accountlinking/user/primary", "POST", False),
          ("link_accounts", "/recipe/accountlinking/user/link", "POST", False),
          ("unlink_account", "/recipe/accountlinking/user/unlink", "POST", False),
          ("remove_user", "/user/remove", "POST", False)]


def _dispatch(args, base):
    # `--tenant` needs an explicit tenant id to be meaningful.
    if args.tenant and not args.tenant_id:
        args.tenant_id = "public"
    for flag, path, scoped in _GETS:
        if getattr(args, flag):
            return _get(args, base, path, scoped)
    for flag, path, method, scoped in _SENDS:
        if getattr(args, flag):
            return _send(args, base, path, method, scoped)
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
