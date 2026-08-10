#!/usr/bin/env python3
"""CLI helper for the Ory Kratos API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$ORY_KRATOS_API_URL (override with --url). POST/PUT/PATCH bodies are read from
--data (JSON string) or --data-file; --session-token sets the X-Session-Token
header.

Kratos is flow-based, so most work is two calls: create a flow, then submit
against its id. `--login-then` does both in one go for the common case.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, session_token=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if session_token:
        headers["X-Session-Token"] = session_token
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
    p = argparse.ArgumentParser(description="Query the Ory Kratos API (Mock) mock API")
    p.add_argument("--alive", action="store_true", help="GET /health/alive")
    p.add_argument("--ready", action="store_true", help="GET /health/ready")
    p.add_argument("--version", action="store_true", help="GET /version")
    p.add_argument("--schemas", action="store_true", help="GET /schemas")
    p.add_argument("--schema", metavar="SCHEMA_ID", nargs=1, help="GET /schemas/{id}")
    p.add_argument("--create-flow", metavar=("TYPE", "CLIENT"), nargs=2,
                   help="GET /self-service/{type}/{api|browser}")
    p.add_argument("--get-flow", metavar=("TYPE", "FLOW_ID"), nargs=2,
                   help="GET /self-service/{type}/flows?id=")
    p.add_argument("--submit", metavar=("TYPE", "FLOW_ID"), nargs=2,
                   help="POST /self-service/{type}?flow=")
    p.add_argument("--login-then", metavar=("IDENTIFIER", "PASSWORD"), nargs=2,
                   help="create a login flow and submit it in one go")
    p.add_argument("--logout", action="store_true",
                   help="DELETE /self-service/logout/api")
    p.add_argument("--whoami", action="store_true", help="GET /sessions/whoami")
    p.add_argument("--my-sessions", action="store_true", help="GET /sessions")
    p.add_argument("--revoke-my-sessions", action="store_true",
                   help="DELETE /sessions")
    p.add_argument("--revoke-my-session", metavar="SESSION_ID", nargs=1,
                   help="DELETE /sessions/{id}")
    p.add_argument("--identities", action="store_true", help="GET /admin/identities")
    p.add_argument("--identity", metavar="IDENTITY_ID", nargs=1,
                   help="GET /admin/identities/{id}")
    p.add_argument("--create-identity", action="store_true",
                   help="POST /admin/identities")
    p.add_argument("--replace-identity", metavar="IDENTITY_ID", nargs=1,
                   help="PUT /admin/identities/{id}")
    p.add_argument("--patch-identity", metavar="IDENTITY_ID", nargs=1,
                   help="PATCH /admin/identities/{id} (JSON Patch in --data)")
    p.add_argument("--delete-identity", metavar="IDENTITY_ID", nargs=1,
                   help="DELETE /admin/identities/{id}")
    p.add_argument("--identity-sessions", metavar="IDENTITY_ID", nargs=1,
                   help="GET /admin/identities/{id}/sessions")
    p.add_argument("--revoke-identity-sessions", metavar="IDENTITY_ID", nargs=1,
                   help="DELETE /admin/identities/{id}/sessions")
    p.add_argument("--delete-credential", metavar=("IDENTITY_ID", "TYPE"), nargs=2,
                   help="DELETE /admin/identities/{id}/credentials/{type}")
    p.add_argument("--recovery-code", action="store_true",
                   help="POST /admin/recovery/code")
    p.add_argument("--recovery-link", action="store_true",
                   help="POST /admin/recovery/link")
    p.add_argument("--sessions", action="store_true", help="GET /admin/sessions")
    p.add_argument("--session", metavar="SESSION_ID", nargs=1,
                   help="GET /admin/sessions/{id}")
    p.add_argument("--extend-session", metavar="SESSION_ID", nargs=1,
                   help="PATCH /admin/sessions/{id}/extend")
    p.add_argument("--disable-session", metavar="SESSION_ID", nargs=1,
                   help="DELETE /admin/sessions/{id}")
    p.add_argument("--courier", action="store_true",
                   help="GET /admin/courier/messages")
    p.add_argument("--courier-message", metavar="MESSAGE_ID", nargs=1,
                   help="GET /admin/courier/messages/{id}")
    p.add_argument("--query", metavar="QS", default="",
                   help="Query string appended to reads, e.g. 'page_size=5'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--session-token", metavar="TOKEN",
                   help="X-Session-Token header value")
    p.add_argument("--url", default=os.environ.get("ORY_KRATOS_API_URL",
                                                   "http://localhost:8119"),
                   help="API base URL (default: $ORY_KRATOS_API_URL or http://localhost:8119)")
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


_FLAT_GETS = [("alive", "/health/alive"), ("ready", "/health/ready"),
              ("version", "/version"), ("schemas", "/schemas"),
              ("whoami", "/sessions/whoami"), ("my_sessions", "/sessions"),
              ("identities", "/admin/identities"),
              ("sessions", "/admin/sessions"),
              ("courier", "/admin/courier/messages")]

_ONE_ARG = [("schema", "/schemas/{id}", "GET"),
            ("revoke_my_session", "/sessions/{id}", "DELETE"),
            ("identity", "/admin/identities/{id}", "GET"),
            ("replace_identity", "/admin/identities/{id}", "PUT"),
            ("patch_identity", "/admin/identities/{id}", "PATCH"),
            ("delete_identity", "/admin/identities/{id}", "DELETE"),
            ("identity_sessions", "/admin/identities/{id}/sessions", "GET"),
            ("revoke_identity_sessions", "/admin/identities/{id}/sessions",
             "DELETE"),
            ("session", "/admin/sessions/{id}", "GET"),
            ("extend_session", "/admin/sessions/{id}/extend", "PATCH"),
            ("disable_session", "/admin/sessions/{id}", "DELETE"),
            ("courier_message", "/admin/courier/messages/{id}", "GET")]


def _dispatch(args, base):
    token = args.session_token
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, _qs(args, path), "GET",
                                 session_token=token))
    if args.create_flow:
        flow_type, client = args.create_flow
        path = f"/self-service/{urllib.parse.quote(flow_type, safe='')}/" \
               f"{urllib.parse.quote(client, safe='')}"
        return show(_request(base, _qs(args, path), "GET", session_token=token))
    if args.get_flow:
        flow_type, flow_id = args.get_flow
        path = (f"/self-service/{urllib.parse.quote(flow_type, safe='')}/flows"
                f"?id={urllib.parse.quote(flow_id, safe='')}")
        return show(_request(base, path, "GET", session_token=token))
    if args.submit:
        flow_type, flow_id = args.submit
        path = (f"/self-service/{urllib.parse.quote(flow_type, safe='')}"
                f"?flow={urllib.parse.quote(flow_id, safe='')}")
        return show(_request(base, path, "POST", _body(args),
                             session_token=token))
    if args.login_then:
        identifier, password = args.login_then
        flow = _request(base, "/self-service/login/api", "GET")
        return show(_request(base, f"/self-service/login?flow={flow['id']}",
                             "POST", {"method": "password",
                                      "identifier": identifier,
                                      "password": password}))
    if args.logout:
        body = _body(args)
        if token and "session_token" not in body:
            body["session_token"] = token
        return show(_request(base, "/self-service/logout/api", "DELETE", body))
    if args.revoke_my_sessions:
        return show(_request(base, "/sessions", "DELETE", session_token=token))
    if args.create_identity:
        return show(_request(base, "/admin/identities", "POST", _body(args)))
    if args.recovery_code:
        return show(_request(base, "/admin/recovery/code", "POST", _body(args)))
    if args.recovery_link:
        return show(_request(base, "/admin/recovery/link", "POST", _body(args)))
    if args.delete_credential:
        identity_id, credential_type = args.delete_credential
        path = (f"/admin/identities/{urllib.parse.quote(identity_id, safe='')}"
                f"/credentials/{urllib.parse.quote(credential_type, safe='')}")
        return show(_request(base, path, "DELETE"))
    for flag, path, method in _ONE_ARG:
        value = getattr(args, flag)
        if value:
            full = _fill(path, value)
            if method == "GET":
                return show(_request(base, _qs(args, full), "GET",
                                     session_token=token))
            payload = _body(args) if method in ("PUT", "PATCH", "POST") else None
            return show(_request(base, full, method, payload,
                                 session_token=token))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
