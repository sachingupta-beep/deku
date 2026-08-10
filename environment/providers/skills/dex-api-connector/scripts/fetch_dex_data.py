#!/usr/bin/env python3
"""CLI helper for the Dex API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$DEX_API_URL (override with --url). POST/PUT bodies are read from --data (JSON
string) or --data-file.

Remember two things about Dex: identities come from connectors, so most token
calls take a --connector; and the /api/v2 surface answers 200 with an
`already_exists` or `not_found` flag rather than 409 or 404.
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


def _request(base, path, method, body=None, authorization=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if authorization:
        headers["Authorization"] = f"Bearer {authorization}"
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
    p = argparse.ArgumentParser(description="Query the Dex API (Mock) mock API")
    p.add_argument("--healthz", action="store_true", help="GET /healthz")
    p.add_argument("--discovery", action="store_true",
                   help="GET /dex/.well-known/openid-configuration")
    p.add_argument("--keys", action="store_true", help="GET /dex/keys")
    p.add_argument("--connectors", action="store_true", help="GET /dex/connectors")
    p.add_argument("--authorize", action="store_true", help="GET /dex/auth")
    p.add_argument("--approve", action="store_true", help="POST /dex/approval")
    p.add_argument("--token", dest="token_request", action="store_true",
                   help="POST /dex/token")
    p.add_argument("--login", metavar=("USERNAME", "PASSWORD"), nargs=2,
                   help="password grant against --client with --connector")
    p.add_argument("--introspect", action="store_true",
                   help="POST /dex/token/introspect")
    p.add_argument("--userinfo", action="store_true", help="GET /dex/userinfo")
    p.add_argument("--device-code", action="store_true",
                   help="POST /dex/device/code")
    p.add_argument("--device-lookup", metavar="USER_CODE", nargs=1,
                   help="GET /dex/device?user_code=")
    p.add_argument("--device-approve", metavar="USER_CODE", nargs=1,
                   help="POST /dex/device/auth/verify")
    p.add_argument("--device-token", metavar="DEVICE_CODE", nargs=1,
                   help="POST /dex/device/token")
    p.add_argument("--api-version", action="store_true", help="GET /api/v2/version")
    p.add_argument("--clients", action="store_true", help="GET /api/v2/clients")
    p.add_argument("--client", metavar="CLIENT_ID", nargs=1,
                   help="GET /api/v2/clients/{id}")
    p.add_argument("--create-client", action="store_true",
                   help="POST /api/v2/clients")
    p.add_argument("--update-client", metavar="CLIENT_ID", nargs=1,
                   help="PUT /api/v2/clients/{id}")
    p.add_argument("--delete-client", metavar="CLIENT_ID", nargs=1,
                   help="DELETE /api/v2/clients/{id}")
    p.add_argument("--passwords", action="store_true", help="GET /api/v2/passwords")
    p.add_argument("--create-password", action="store_true",
                   help="POST /api/v2/passwords")
    p.add_argument("--update-password", metavar="EMAIL", nargs=1,
                   help="PUT /api/v2/passwords/{email}")
    p.add_argument("--delete-password", metavar="EMAIL", nargs=1,
                   help="DELETE /api/v2/passwords/{email}")
    p.add_argument("--verify-password", metavar=("EMAIL", "PASSWORD"), nargs=2,
                   help="POST /api/v2/passwords/verify")
    p.add_argument("--refresh-list", metavar="USER_ID", nargs=1,
                   help="GET /api/v2/refresh/{user_id}")
    p.add_argument("--revoke-refresh", metavar="USER_ID", nargs=1,
                   help="POST /api/v2/refresh/revoke")
    p.add_argument("--offline-sessions", action="store_true",
                   help="GET /api/v2/offline-sessions")
    p.add_argument("--query", metavar="QS", default="",
                   help="Query string appended to reads")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--client-id", default="orbit-status-web",
                   help="Client id for token calls (default: orbit-status-web)")
    p.add_argument("--client-secret", default="dex-secret-status-web-9f14c73e0b2a",
                   help="Client secret for token calls")
    p.add_argument("--connector", default="local",
                   help="Connector id for password and device approvals")
    p.add_argument("--scope", default="openid profile email groups offline_access",
                   help="Requested scope for the password grant")
    p.add_argument("--bearer", metavar="TOKEN",
                   help="Bearer token for /dex/userinfo")
    p.add_argument("--url", default=os.environ.get("DEX_API_URL",
                                                   "http://localhost:8120"),
                   help="API base URL (default: $DEX_API_URL or http://localhost:8120)")
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


_FLAT_GETS = [("healthz", "/healthz"),
              ("discovery", "/dex/.well-known/openid-configuration"),
              ("keys", "/dex/keys"), ("connectors", "/dex/connectors"),
              ("authorize", "/dex/auth"),
              ("api_version", "/api/v2/version"),
              ("clients", "/api/v2/clients"),
              ("passwords", "/api/v2/passwords"),
              ("offline_sessions", "/api/v2/offline-sessions")]

_ONE_ARG = [("client", "/api/v2/clients/{id}", "GET"),
            ("update_client", "/api/v2/clients/{id}", "PUT"),
            ("delete_client", "/api/v2/clients/{id}", "DELETE"),
            ("update_password", "/api/v2/passwords/{email}", "PUT"),
            ("delete_password", "/api/v2/passwords/{email}", "DELETE"),
            ("refresh_list", "/api/v2/refresh/{user_id}", "GET")]


def _client_credentials(args, body):
    body["client_id"] = args.client_id
    if args.client_secret:
        body["client_secret"] = args.client_secret
    return body


def _dispatch(args, base):
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, _qs(args, path), "GET"))
    if args.userinfo:
        return show(_request(base, "/dex/userinfo", "GET",
                             authorization=args.bearer))
    if args.approve:
        return show(_request(base, "/dex/approval", "POST", _body(args)))
    if args.token_request:
        return show(_request(base, "/dex/token", "POST", _body(args)))
    if args.login:
        username, password = args.login
        body = _client_credentials(args, {
            "grant_type": "password", "connector_id": args.connector,
            "username": username, "password": password, "scope": args.scope})
        return show(_request(base, "/dex/token", "POST", body))
    if args.introspect:
        return show(_request(base, "/dex/token/introspect", "POST", _body(args)))
    if args.device_code:
        return show(_request(base, "/dex/device/code", "POST",
                             {"client_id": args.client_id,
                              "scope": args.scope}))
    if args.device_lookup:
        code = urllib.parse.quote(args.device_lookup[0], safe="")
        return show(_request(base, f"/dex/device?user_code={code}", "GET"))
    if args.device_approve:
        body = {**_body(args), "user_code": args.device_approve[0],
                "connector_id": args.connector}
        return show(_request(base, "/dex/device/auth/verify", "POST", body))
    if args.device_token:
        return show(_request(base, "/dex/device/token", "POST",
                             {"client_id": args.client_id,
                              "device_code": args.device_token[0]}))
    if args.create_client:
        return show(_request(base, "/api/v2/clients", "POST", _body(args)))
    if args.create_password:
        return show(_request(base, "/api/v2/passwords", "POST", _body(args)))
    if args.verify_password:
        email, password = args.verify_password
        return show(_request(base, "/api/v2/passwords/verify", "POST",
                             {"email": email, "password": password}))
    if args.revoke_refresh:
        body = {**_body(args), "user_id": args.revoke_refresh[0]}
        return show(_request(base, "/api/v2/refresh/revoke", "POST", body))
    for flag, path, method in _ONE_ARG:
        value = getattr(args, flag)
        if value:
            # `user_id` may be an LDAP DN, so it is not percent-encoded away.
            full = (path.replace("{user_id}", value[0]) if "{user_id}" in path
                    else _fill(path, value))
            if method == "GET":
                return show(_request(base, _qs(args, full), "GET"))
            payload = _body(args) if method == "PUT" else None
            return show(_request(base, full, method, payload))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
