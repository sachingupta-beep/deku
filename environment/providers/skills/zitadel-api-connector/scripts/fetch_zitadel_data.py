#!/usr/bin/env python3
"""CLI helper for the Zitadel API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$ZITADEL_API_URL (override with --url). POST/PUT/PATCH bodies are read from
--data (JSON string) or --data-file.

The organization is a header: --org sets `x-zitadel-orgid` (default Orbit Labs).
Management and admin calls need a bearer; --token defaults to the seeded
orbit-ci PAT. The session endpoints take no bearer -- the session token is the
credential, so pass it in the body or via --session-token.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CI_TOKEN = "zt-pat-orbit-ci-9f14c73e0b2a"
ORBIT_LABS = "280310551611113987"


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, token=None, org=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if org:
        headers["x-zitadel-orgid"] = org
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


def _session_body(args):
    """Merge --session-token into the body, since it is the session credential."""
    body = _body(args)
    if args.session_token and "sessionToken" not in body:
        body["sessionToken"] = args.session_token
    return body


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data)
    return 0


def main():
    p = argparse.ArgumentParser(description="Query the Zitadel API (Mock) mock API")
    p.add_argument("--healthz", action="store_true", help="GET /debug/healthz")
    p.add_argument("--instance", action="store_true", help="GET /admin/v1/instance")
    p.add_argument("--orgs", action="store_true", help="POST /admin/v1/orgs/_search")
    p.add_argument("--events", action="store_true", help="POST /admin/v1/events/_search")
    p.add_argument("--my-org", action="store_true", help="GET /management/v1/orgs/me")
    p.add_argument("--login-policy", action="store_true",
                   help="GET /management/v1/policies/login")
    p.add_argument("--users", action="store_true", help="POST /v2/users/_search")
    p.add_argument("--create-user", action="store_true", help="POST /v2/users/human")
    p.add_argument("--user", metavar="USER_ID", nargs=1, help="GET /v2/users/{id}")
    p.add_argument("--update-user", metavar="USER_ID", nargs=1,
                   help="PUT /v2/users/human/{id}")
    p.add_argument("--delete-user", metavar="USER_ID", nargs=1,
                   help="DELETE /v2/users/{id}")
    p.add_argument("--set-email", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/email")
    p.add_argument("--verify-email", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/email/_verify")
    p.add_argument("--set-password", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/password")
    p.add_argument("--password-reset", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/password_reset")
    p.add_argument("--deactivate", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/deactivate")
    p.add_argument("--reactivate", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/reactivate")
    p.add_argument("--lock", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/lock")
    p.add_argument("--unlock", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/unlock")
    p.add_argument("--factors", metavar="USER_ID", nargs=1,
                   help="GET /v2/users/{id}/authentication_factors")
    p.add_argument("--register-totp", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/totp")
    p.add_argument("--verify-totp", metavar="USER_ID", nargs=1,
                   help="POST /v2/users/{id}/totp/_verify")
    p.add_argument("--remove-factor", metavar=("USER_ID", "FACTOR_ID"), nargs=2,
                   help="DELETE /v2/users/{id}/authentication_factors/{factorId}")
    p.add_argument("--create-session", action="store_true", help="POST /v2/sessions")
    p.add_argument("--session", metavar="SESSION_ID", nargs=1,
                   help="GET /v2/sessions/{id} (needs --session-token)")
    p.add_argument("--update-session", metavar="SESSION_ID", nargs=1,
                   help="PATCH /v2/sessions/{id}")
    p.add_argument("--delete-session", metavar="SESSION_ID", nargs=1,
                   help="DELETE /v2/sessions/{id}")
    p.add_argument("--sessions", action="store_true",
                   help="POST /v2/sessions/_search")
    p.add_argument("--auth-request", metavar="REQUEST_ID", nargs=1,
                   help="GET /v2/oidc/auth_requests/{id}")
    p.add_argument("--finalize-auth-request", metavar="REQUEST_ID", nargs=1,
                   help="POST /v2/oidc/auth_requests/{id}")
    p.add_argument("--projects", action="store_true",
                   help="POST /management/v1/projects/_search")
    p.add_argument("--project", metavar="PROJECT_ID", nargs=1,
                   help="GET /management/v1/projects/{id}")
    p.add_argument("--create-project", action="store_true",
                   help="POST /management/v1/projects")
    p.add_argument("--project-roles", metavar="PROJECT_ID", nargs=1,
                   help="POST /management/v1/projects/{id}/roles/_search")
    p.add_argument("--add-project-role", metavar="PROJECT_ID", nargs=1,
                   help="POST /management/v1/projects/{id}/roles")
    p.add_argument("--grants", action="store_true",
                   help="POST /management/v1/users/grants/_search")
    p.add_argument("--create-grant", metavar="USER_ID", nargs=1,
                   help="POST /management/v1/users/{id}/grants")
    p.add_argument("--update-grant", metavar=("USER_ID", "GRANT_ID"), nargs=2,
                   help="PUT /management/v1/users/{id}/grants/{grantId}")
    p.add_argument("--delete-grant", metavar=("USER_ID", "GRANT_ID"), nargs=2,
                   help="DELETE /management/v1/users/{id}/grants/{grantId}")
    p.add_argument("--members", action="store_true",
                   help="POST /management/v1/orgs/me/members/_search")
    p.add_argument("--add-member", action="store_true",
                   help="POST /management/v1/orgs/me/members")
    p.add_argument("--remove-member", metavar="USER_ID", nargs=1,
                   help="DELETE /management/v1/orgs/me/members/{userId}")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--session-token", metavar="TOKEN",
                   help="Session token for the /v2/sessions endpoints")
    p.add_argument("--org", default=ORBIT_LABS,
                   help="x-zitadel-orgid header (default: the Orbit Labs org id)")
    p.add_argument("--token", default=CI_TOKEN,
                   help="Bearer PAT (default: the seeded orbit-ci PAT)")
    p.add_argument("--url", default=os.environ.get("ZITADEL_API_URL",
                                                   "http://localhost:8118"),
                   help="API base URL (default: $ZITADEL_API_URL or http://localhost:8118)")
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


# (flag, path, method, needs_bearer)
_FLAT = [("healthz", "/debug/healthz", "GET", False),
         ("instance", "/admin/v1/instance", "GET", True),
         ("orgs", "/admin/v1/orgs/_search", "POST", True),
         ("events", "/admin/v1/events/_search", "POST", True),
         ("my_org", "/management/v1/orgs/me", "GET", True),
         ("login_policy", "/management/v1/policies/login", "GET", True),
         ("users", "/v2/users/_search", "POST", True),
         ("create_user", "/v2/users/human", "POST", True),
         ("sessions", "/v2/sessions/_search", "POST", True),
         ("projects", "/management/v1/projects/_search", "POST", True),
         ("create_project", "/management/v1/projects", "POST", True),
         ("grants", "/management/v1/users/grants/_search", "POST", True),
         ("members", "/management/v1/orgs/me/members/_search", "POST", True),
         ("add_member", "/management/v1/orgs/me/members", "POST", True)]

# (flag, path, method, needs_bearer)
_ONE_ARG = [("user", "/v2/users/{id}", "GET", True),
            ("update_user", "/v2/users/human/{id}", "PUT", True),
            ("delete_user", "/v2/users/{id}", "DELETE", True),
            ("set_email", "/v2/users/{id}/email", "POST", True),
            ("verify_email", "/v2/users/{id}/email/_verify", "POST", True),
            ("set_password", "/v2/users/{id}/password", "POST", True),
            ("password_reset", "/v2/users/{id}/password_reset", "POST", True),
            ("deactivate", "/v2/users/{id}/deactivate", "POST", True),
            ("reactivate", "/v2/users/{id}/reactivate", "POST", True),
            ("lock", "/v2/users/{id}/lock", "POST", True),
            ("unlock", "/v2/users/{id}/unlock", "POST", True),
            ("factors", "/v2/users/{id}/authentication_factors", "GET", True),
            ("register_totp", "/v2/users/{id}/totp", "POST", True),
            ("verify_totp", "/v2/users/{id}/totp/_verify", "POST", True),
            ("auth_request", "/v2/oidc/auth_requests/{id}", "GET", False),
            ("finalize_auth_request", "/v2/oidc/auth_requests/{id}", "POST",
             False),
            ("project", "/management/v1/projects/{id}", "GET", True),
            ("project_roles", "/management/v1/projects/{id}/roles/_search",
             "POST", True),
            ("add_project_role", "/management/v1/projects/{id}/roles", "POST",
             True),
            ("create_grant", "/management/v1/users/{id}/grants", "POST", True),
            ("remove_member", "/management/v1/orgs/me/members/{userId}",
             "DELETE", True)]

_TWO_ARGS = [("update_grant", "/management/v1/users/{id}/grants/{grantId}",
              "PUT", True),
             ("delete_grant", "/management/v1/users/{id}/grants/{grantId}",
              "DELETE", True),
             ("remove_factor",
              "/v2/users/{id}/authentication_factors/{factorId}", "DELETE",
              True)]

# The session endpoints take no bearer; the session token is the credential.
_SESSION = [("session", "/v2/sessions/{id}", "GET"),
            ("update_session", "/v2/sessions/{id}", "PATCH"),
            ("delete_session", "/v2/sessions/{id}", "DELETE")]


def _dispatch(args, base):
    org = args.org
    for flag, path, method, needs_bearer in _FLAT:
        if getattr(args, flag):
            payload = _body(args) if method in ("POST", "PUT", "PATCH") else None
            return show(_request(base, path, method, payload,
                                 token=args.token if needs_bearer else None,
                                 org=org))
    if args.create_session:
        return show(_request(base, "/v2/sessions", "POST", _body(args), org=org))
    for flag, path, method in _SESSION:
        value = getattr(args, flag)
        if value:
            full = _fill(path, value)
            if method == "GET":
                if args.session_token:
                    full = f"{full}?sessionToken={urllib.parse.quote(args.session_token)}"
                return show(_request(base, full, "GET", org=org))
            return show(_request(base, full, method, _session_body(args),
                                 org=org))
    for flag, path, method, needs_bearer in _ONE_ARG:
        value = getattr(args, flag)
        if value:
            payload = _body(args) if method in ("POST", "PUT", "PATCH") else None
            return show(_request(base, _fill(path, value), method, payload,
                                 token=args.token if needs_bearer else None,
                                 org=org))
    for flag, path, method, needs_bearer in _TWO_ARGS:
        value = getattr(args, flag)
        if value:
            payload = _body(args) if method in ("POST", "PUT", "PATCH") else None
            return show(_request(base, _fill(path, value), method, payload,
                                 token=args.token if needs_bearer else None,
                                 org=org))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
