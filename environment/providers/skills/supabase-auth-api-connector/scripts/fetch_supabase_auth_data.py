#!/usr/bin/env python3
"""CLI helper for the Supabase Auth API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$SUPABASE_AUTH_API_URL (override with --url). POST/PUT bodies are read from
--data (JSON string) or --data-file. Pass --apikey to choose the project role and
--token to send an end-user bearer.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost"
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost"


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, apikey=None, token=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if apikey:
        headers["apikey"] = apikey
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path, apikey=None, token=None):
    return _request(base, path, "GET", apikey=apikey, token=token)


def api_delete(base, path, body=None, apikey=None, token=None):
    return _request(base, path, "DELETE", body, apikey=apikey, token=token)


def api_send(base, path, method, body, apikey=None, token=None):
    return _request(base, path, method, body if body is not None else {},
                    apikey=apikey, token=token)


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
    p = argparse.ArgumentParser(description="Query the Supabase Auth API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /auth/v1/health")
    p.add_argument("--settings", action="store_true", help="GET /auth/v1/settings")
    p.add_argument("--signup", action="store_true", help="POST /auth/v1/signup")
    p.add_argument("--signup-anonymous", action="store_true", help="POST /auth/v1/signup/anonymous")
    p.add_argument("--sign-in", action="store_true", help="POST /auth/v1/token?grant_type=password")
    p.add_argument("--refresh", action="store_true", help="POST /auth/v1/token?grant_type=refresh_token")
    p.add_argument("--logout", action="store_true", help="POST /auth/v1/logout")
    p.add_argument("--get-user", action="store_true", help="GET /auth/v1/user")
    p.add_argument("--update-user", action="store_true", help="PUT /auth/v1/user")
    p.add_argument("--recover", action="store_true", help="POST /auth/v1/recover")
    p.add_argument("--magiclink", action="store_true", help="POST /auth/v1/magiclink")
    p.add_argument("--otp", action="store_true", help="POST /auth/v1/otp")
    p.add_argument("--verify", action="store_true", help="POST /auth/v1/verify")
    p.add_argument("--resend", action="store_true", help="POST /auth/v1/resend")
    p.add_argument("--authorize", metavar="PROVIDER", nargs=1, help="GET /auth/v1/authorize")
    p.add_argument("--enroll-factor", action="store_true", help="POST /auth/v1/factors")
    p.add_argument("--challenge-factor", metavar="FACTOR_ID", nargs=1,
                   help="POST /auth/v1/factors/{factor_id}/challenge")
    p.add_argument("--verify-factor", metavar="FACTOR_ID", nargs=1,
                   help="POST /auth/v1/factors/{factor_id}/verify")
    p.add_argument("--unenroll-factor", metavar="FACTOR_ID", nargs=1,
                   help="DELETE /auth/v1/factors/{factor_id}")
    p.add_argument("--admin-list-users", action="store_true", help="GET /auth/v1/admin/users")
    p.add_argument("--admin-create-user", action="store_true", help="POST /auth/v1/admin/users")
    p.add_argument("--admin-get-user", metavar="USER_ID", nargs=1, help="GET /auth/v1/admin/users/{user_id}")
    p.add_argument("--admin-update-user", metavar="USER_ID", nargs=1, help="PUT /auth/v1/admin/users/{user_id}")
    p.add_argument("--admin-delete-user", metavar="USER_ID", nargs=1, help="DELETE /auth/v1/admin/users/{user_id}")
    p.add_argument("--admin-generate-link", action="store_true", help="POST /auth/v1/admin/generate_link")
    p.add_argument("--admin-audit", action="store_true", help="GET /auth/v1/admin/audit")
    p.add_argument("--admin-sessions", action="store_true", help="GET /auth/v1/admin/sessions")
    p.add_argument("--query", metavar="QS", default="",
                   help="Query string appended to the request, e.g. 'page=1&per_page=5'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--apikey", default=SERVICE_KEY,
                   help="apikey header value (default: the project service key)")
    p.add_argument("--token", metavar="ACCESS_TOKEN",
                   help="Bearer access token for the end-user endpoints")
    p.add_argument("--url", default=os.environ.get("SUPABASE_AUTH_API_URL", "http://localhost:8113"),
                   help="API base URL (default: $SUPABASE_AUTH_API_URL or http://localhost:8113)")
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
    if not args.query:
        return path
    return f"{path}{'&' if '?' in path else '?'}{args.query}"


def _dispatch(args, base):
    key, token = args.apikey, args.token
    if args.health:
        return show(api_get(base, "/auth/v1/health", key))
    if args.settings:
        return show(api_get(base, "/auth/v1/settings", key))
    if args.signup:
        return show(api_send(base, "/auth/v1/signup", "POST", _body(args), key))
    if args.signup_anonymous:
        return show(api_send(base, "/auth/v1/signup/anonymous", "POST", {}, key))
    if args.sign_in:
        return show(api_send(base, "/auth/v1/token?grant_type=password", "POST", _body(args), key))
    if args.refresh:
        return show(api_send(base, "/auth/v1/token?grant_type=refresh_token", "POST", _body(args), key))
    if args.logout:
        return show(api_send(base, _qs(args, "/auth/v1/logout"), "POST", {}, key, token))
    if args.get_user:
        return show(api_get(base, "/auth/v1/user", key, token))
    if args.update_user:
        return show(api_send(base, "/auth/v1/user", "PUT", _body(args), key, token))
    if args.recover:
        return show(api_send(base, "/auth/v1/recover", "POST", _body(args), key))
    if args.magiclink:
        return show(api_send(base, "/auth/v1/magiclink", "POST", _body(args), key))
    if args.otp:
        return show(api_send(base, "/auth/v1/otp", "POST", _body(args), key))
    if args.verify:
        return show(api_send(base, "/auth/v1/verify", "POST", _body(args), key))
    if args.resend:
        return show(api_send(base, "/auth/v1/resend", "POST", _body(args), key))
    if args.authorize:
        provider = urllib.parse.quote(args.authorize[0], safe="")
        return show(api_get(base, _qs(args, f"/auth/v1/authorize?provider={provider}"), key))
    if args.enroll_factor:
        return show(api_send(base, "/auth/v1/factors", "POST", _body(args), key, token))
    if args.challenge_factor:
        return show(api_send(base, _fill("/auth/v1/factors/{factor_id}/challenge", args.challenge_factor),
                             "POST", {}, key, token))
    if args.verify_factor:
        return show(api_send(base, _fill("/auth/v1/factors/{factor_id}/verify", args.verify_factor),
                             "POST", _body(args), key, token))
    if args.unenroll_factor:
        return show(api_delete(base, _fill("/auth/v1/factors/{factor_id}", args.unenroll_factor),
                               None, key, token))
    if args.admin_list_users:
        return show(api_get(base, _qs(args, "/auth/v1/admin/users"), key))
    if args.admin_create_user:
        return show(api_send(base, "/auth/v1/admin/users", "POST", _body(args), key))
    if args.admin_get_user:
        return show(api_get(base, _fill("/auth/v1/admin/users/{user_id}", args.admin_get_user), key))
    if args.admin_update_user:
        return show(api_send(base, _fill("/auth/v1/admin/users/{user_id}", args.admin_update_user),
                             "PUT", _body(args), key))
    if args.admin_delete_user:
        return show(api_delete(base, _fill("/auth/v1/admin/users/{user_id}", args.admin_delete_user),
                               _body(args), key))
    if args.admin_generate_link:
        return show(api_send(base, "/auth/v1/admin/generate_link", "POST", _body(args), key))
    if args.admin_audit:
        return show(api_get(base, _qs(args, "/auth/v1/admin/audit"), key))
    if args.admin_sessions:
        return show(api_get(base, _qs(args, "/auth/v1/admin/sessions"), key))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
