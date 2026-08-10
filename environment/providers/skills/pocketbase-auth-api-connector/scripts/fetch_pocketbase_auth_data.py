#!/usr/bin/env python3
"""CLI helper for the PocketBase Auth API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$POCKETBASE_AUTH_API_URL (override with --url). POST/PATCH bodies are read from
--data (JSON string) or --data-file. Pass --token to send a PocketBase auth
token; auth is per collection, so most flags take the collection as their first
positional value.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SUPERUSER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.sup0admin000001.tk_ops_e64a"


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
        headers["Authorization"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    if not raw:
        return {"status": resp.status}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path, token=None):
    return _request(base, path, "GET", token=token)


def api_delete(base, path, token=None):
    return _request(base, path, "DELETE", token=token)


def api_send(base, path, method, body, token=None):
    return _request(base, path, method, body if body is not None else {},
                    token=token)


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
    p = argparse.ArgumentParser(description="Query the PocketBase Auth API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /api/health")
    p.add_argument("--collections", action="store_true", help="GET /api/collections")
    p.add_argument("--auth-methods", metavar="COLLECTION", nargs=1,
                   help="GET /api/collections/{collection}/auth-methods")
    p.add_argument("--auth-with-password", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/auth-with-password")
    p.add_argument("--request-otp", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/request-otp")
    p.add_argument("--auth-with-otp", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/auth-with-otp")
    p.add_argument("--auth-with-oauth2", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/auth-with-oauth2")
    p.add_argument("--auth-refresh", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/auth-refresh")
    p.add_argument("--impersonate", metavar=("COLLECTION", "RECORD_ID"), nargs=2,
                   help="POST /api/collections/{collection}/impersonate/{record_id}")
    p.add_argument("--request-verification", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/request-verification")
    p.add_argument("--confirm-verification", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/confirm-verification")
    p.add_argument("--request-password-reset", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/request-password-reset")
    p.add_argument("--confirm-password-reset", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/confirm-password-reset")
    p.add_argument("--request-email-change", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/request-email-change")
    p.add_argument("--confirm-email-change", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/confirm-email-change")
    p.add_argument("--list-records", metavar="COLLECTION", nargs=1,
                   help="GET /api/collections/{collection}/records")
    p.add_argument("--get-record", metavar=("COLLECTION", "RECORD_ID"), nargs=2,
                   help="GET /api/collections/{collection}/records/{record_id}")
    p.add_argument("--create-record", metavar="COLLECTION", nargs=1,
                   help="POST /api/collections/{collection}/records")
    p.add_argument("--update-record", metavar=("COLLECTION", "RECORD_ID"), nargs=2,
                   help="PATCH /api/collections/{collection}/records/{record_id}")
    p.add_argument("--delete-record", metavar=("COLLECTION", "RECORD_ID"), nargs=2,
                   help="DELETE /api/collections/{collection}/records/{record_id}")
    p.add_argument("--external-auths", metavar=("COLLECTION", "RECORD_ID"), nargs=2,
                   help="GET /api/collections/{collection}/records/{record_id}/external-auths")
    p.add_argument("--unlink-external-auth",
                   metavar=("COLLECTION", "RECORD_ID", "PROVIDER"), nargs=3,
                   help="DELETE .../records/{record_id}/external-auths/{provider}")
    p.add_argument("--logs", action="store_true", help="GET /api/logs")
    p.add_argument("--logs-stats", action="store_true", help="GET /api/logs/stats")
    p.add_argument("--query", metavar="QS", default="",
                   help="Query string appended to reads, e.g. 'page=1&perPage=5'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--token", default=SUPERUSER_TOKEN,
                   help="Authorization header value (default: the seeded superuser token)")
    p.add_argument("--url", default=os.environ.get("POCKETBASE_AUTH_API_URL",
                                                   "http://localhost:8114"),
                   help="API base URL (default: $POCKETBASE_AUTH_API_URL or http://localhost:8114)")
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


def _collection_path(collection, suffix):
    return f"/api/collections/{urllib.parse.quote(collection, safe='')}{suffix}"


def _dispatch(args, base):
    token = args.token
    if args.health:
        return show(api_get(base, "/api/health"))
    if args.collections:
        return show(api_get(base, "/api/collections", token))
    if args.auth_methods:
        return show(api_get(base, _collection_path(args.auth_methods[0],
                                                   "/auth-methods")))
    for flag, suffix in (("auth_with_password", "/auth-with-password"),
                         ("request_otp", "/request-otp"),
                         ("auth_with_otp", "/auth-with-otp"),
                         ("auth_with_oauth2", "/auth-with-oauth2"),
                         ("request_verification", "/request-verification"),
                         ("confirm_verification", "/confirm-verification"),
                         ("request_password_reset", "/request-password-reset"),
                         ("confirm_password_reset", "/confirm-password-reset"),
                         ("request_email_change", "/request-email-change"),
                         ("confirm_email_change", "/confirm-email-change")):
        value = getattr(args, flag)
        if value:
            return show(api_send(base, _collection_path(value[0], suffix),
                                 "POST", _body(args), token))
    if args.auth_refresh:
        return show(api_send(base, _collection_path(args.auth_refresh[0],
                                                    "/auth-refresh"),
                             "POST", {}, token))
    if args.impersonate:
        collection, record_id = args.impersonate
        return show(api_send(base, _collection_path(
            collection, f"/impersonate/{urllib.parse.quote(record_id, safe='')}"),
            "POST", _body(args), token))
    if args.list_records:
        return show(api_get(base, _qs(args, _collection_path(
            args.list_records[0], "/records")), token))
    if args.get_record:
        collection, record_id = args.get_record
        return show(api_get(base, _collection_path(
            collection, f"/records/{urllib.parse.quote(record_id, safe='')}"),
            token))
    if args.create_record:
        return show(api_send(base, _collection_path(args.create_record[0],
                                                    "/records"),
                             "POST", _body(args), token))
    if args.update_record:
        collection, record_id = args.update_record
        return show(api_send(base, _collection_path(
            collection, f"/records/{urllib.parse.quote(record_id, safe='')}"),
            "PATCH", _body(args), token))
    if args.delete_record:
        collection, record_id = args.delete_record
        return show(api_delete(base, _collection_path(
            collection, f"/records/{urllib.parse.quote(record_id, safe='')}"),
            token))
    if args.external_auths:
        collection, record_id = args.external_auths
        return show(api_get(base, _collection_path(
            collection,
            f"/records/{urllib.parse.quote(record_id, safe='')}/external-auths"),
            token))
    if args.unlink_external_auth:
        collection, record_id, provider = args.unlink_external_auth
        return show(api_delete(base, _collection_path(
            collection,
            f"/records/{urllib.parse.quote(record_id, safe='')}"
            f"/external-auths/{urllib.parse.quote(provider, safe='')}"), token))
    if args.logs:
        return show(api_get(base, _qs(args, "/api/logs"), token))
    if args.logs_stats:
        return show(api_get(base, "/api/logs/stats", token))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
