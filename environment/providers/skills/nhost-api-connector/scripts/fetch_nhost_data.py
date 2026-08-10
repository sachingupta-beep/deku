#!/usr/bin/env python3
"""CLI helper for the Nhost API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$NHOST_API_URL (override with --url). GraphQL goes through --graphql (with
optional --variables); REST bodies are read from --data (JSON string) or
--data-file. Use --admin-secret or --token to choose the role.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ADMIN_SECRET = "nhost_admin_secret_5b71c9e0a482"
USER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.user.orbitinsights"


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, headers=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    hdrs = dict(headers or {})
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path, headers=None):
    return _request(base, path, "GET", headers=headers)


def api_delete(base, path, headers=None):
    return _request(base, path, "DELETE", headers=headers)


def api_send(base, path, method, body, headers=None):
    return _request(base, path, method, body if body is not None else {}, headers=headers)


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
    p = argparse.ArgumentParser(description="Query the Nhost API (Mock) mock API")
    p.add_argument("--graphql", metavar="QUERY", help="POST /v1/graphql with this query")
    p.add_argument("--variables", metavar="JSON", help="GraphQL variables as a JSON object")
    p.add_argument("--operation-name", metavar="NAME", help="GraphQL operationName")
    p.add_argument("--get-healthz", action="store_true", help="GET /healthz")
    p.add_argument("--get-version", action="store_true", help="GET /v1/version")
    p.add_argument("--get-metadata", action="store_true", help="GET /v1/metadata")
    p.add_argument("--post-signin", action="store_true", help="POST /v1/auth/signin/email-password")
    p.add_argument("--post-token", action="store_true", help="POST /v1/auth/token")
    p.add_argument("--get-auth-user", action="store_true", help="GET /v1/auth/user")
    p.add_argument("--post-signout", action="store_true", help="POST /v1/auth/signout")
    p.add_argument("--get-buckets", action="store_true", help="GET /v1/storage/buckets")
    p.add_argument("--get-files", action="store_true", help="GET /v1/storage/files")
    p.add_argument("--get-file", metavar="FILE_ID", nargs=1, help="GET /v1/storage/files/{file_id}")
    p.add_argument("--delete-file", metavar="FILE_ID", nargs=1, help="DELETE /v1/storage/files/{file_id}")
    p.add_argument("--get-functions", action="store_true", help="GET /v1/functions")
    p.add_argument("--post-function", metavar="NAME", nargs=1, help="POST /v1/functions/{name}")
    p.add_argument("--bucket-id", metavar="ID", help="bucketId filter for --get-files")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST)")
    p.add_argument("--admin-secret", default=ADMIN_SECRET,
                   help="x-hasura-admin-secret header ('' to drop it)")
    p.add_argument("--token", default="", help="Bearer access token (overrides --admin-secret)")
    p.add_argument("--role", default="", help="x-hasura-role header, to narrow an admin request")
    p.add_argument("--url", default=os.environ.get("NHOST_API_URL", "http://localhost:8106"),
                   help="API base URL (default: $NHOST_API_URL or http://localhost:8106)")
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


def _headers(args):
    headers = {}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    elif args.admin_secret:
        headers["x-hasura-admin-secret"] = args.admin_secret
    if args.role:
        headers["x-hasura-role"] = args.role
    return headers


def _dispatch(args, base):
    h = _headers(args)
    if args.graphql:
        payload = {"query": args.graphql}
        if args.variables:
            payload["variables"] = json.loads(args.variables)
        if args.operation_name:
            payload["operationName"] = args.operation_name
        return show(api_send(base, "/v1/graphql", "POST", payload, h))
    if args.get_healthz:
        return show(api_get(base, "/healthz", h))
    if args.get_version:
        return show(api_get(base, "/v1/version", h))
    if args.get_metadata:
        return show(api_get(base, "/v1/metadata", h))
    if args.post_signin:
        return show(api_send(base, "/v1/auth/signin/email-password", "POST", _body(args), {}))
    if args.post_token:
        return show(api_send(base, "/v1/auth/token", "POST", _body(args), {}))
    if args.get_auth_user:
        return show(api_get(base, "/v1/auth/user", h))
    if args.post_signout:
        return show(api_send(base, "/v1/auth/signout", "POST", _body(args), h))
    if args.get_buckets:
        return show(api_get(base, "/v1/storage/buckets", h))
    if args.get_files:
        path = "/v1/storage/files"
        if args.bucket_id:
            path += "?" + urllib.parse.urlencode({"bucketId": args.bucket_id})
        return show(api_get(base, path, h))
    if args.get_file:
        return show(api_get(base, _fill('/v1/storage/files/{file_id}', args.get_file), h))
    if args.delete_file:
        return show(api_delete(base, _fill('/v1/storage/files/{file_id}', args.delete_file), h))
    if args.get_functions:
        return show(api_get(base, "/v1/functions", h))
    if args.post_function:
        return show(api_send(base, _fill('/v1/functions/{name}', args.post_function), 'POST', _body(args), h))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
