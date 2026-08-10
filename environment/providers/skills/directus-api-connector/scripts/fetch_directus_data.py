#!/usr/bin/env python3
"""CLI helper for the Directus API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$DIRECTUS_API_URL (override with --url). POST/PATCH bodies are read from --data
(JSON string) or --data-file; DELETE/GET take only path params. Use --filter,
--fields, --sort and friends for the Directus query language, and --token to
choose the role.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ADMIN_TOKEN = "dr_static_admin_4f81c6a930b7e254"


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
    p = argparse.ArgumentParser(description="Query the Directus API (Mock) mock API")
    p.add_argument("--get-ping", action="store_true", help="GET /server/ping")
    p.add_argument("--get-server-health", action="store_true", help="GET /server/health")
    p.add_argument("--get-server-info", action="store_true", help="GET /server/info")
    p.add_argument("--post-login", action="store_true", help="POST /auth/login")
    p.add_argument("--get-items", metavar="COLLECTION", nargs=1, help="GET /items/{collection}")
    p.add_argument("--post-item", metavar="COLLECTION", nargs=1, help="POST /items/{collection}")
    p.add_argument("--get-item", metavar=("COLLECTION", "ITEM_ID"), nargs=2, help="GET /items/{collection}/{item_id}")
    p.add_argument("--patch-item", metavar=("COLLECTION", "ITEM_ID"), nargs=2, help="PATCH /items/{collection}/{item_id}")
    p.add_argument("--delete-item", metavar=("COLLECTION", "ITEM_ID"), nargs=2, help="DELETE /items/{collection}/{item_id}")
    p.add_argument("--get-collections", action="store_true", help="GET /collections")
    p.add_argument("--get-collection", metavar="COLLECTION", nargs=1, help="GET /collections/{collection}")
    p.add_argument("--get-fields", action="store_true", help="GET /fields")
    p.add_argument("--get-collection-fields", metavar="COLLECTION", nargs=1, help="GET /fields/{collection}")
    p.add_argument("--get-users", action="store_true", help="GET /users")
    p.add_argument("--get-me", action="store_true", help="GET /users/me")
    p.add_argument("--get-user", metavar="USER_ID", nargs=1, help="GET /users/{user_id}")
    p.add_argument("--get-roles", action="store_true", help="GET /roles")
    p.add_argument("--get-role", metavar="ROLE_ID", nargs=1, help="GET /roles/{role_id}")
    p.add_argument("--get-permissions", action="store_true", help="GET /permissions")
    p.add_argument("--get-files", action="store_true", help="GET /files")
    p.add_argument("--get-file", metavar="FILE_ID", nargs=1, help="GET /files/{file_id}")
    p.add_argument("--get-activity", action="store_true", help="GET /activity")
    p.add_argument("--get-flows", action="store_true", help="GET /flows")
    p.add_argument("--get-settings", action="store_true", help="GET /settings")
    p.add_argument("--filter", metavar="JSON", help="Directus filter JSON")
    p.add_argument("--fields", metavar="LIST", help="Field selection, e.g. 'id,title,category.name'")
    p.add_argument("--sort", metavar="LIST", help="Sort spec, e.g. '-publish_date,title'")
    p.add_argument("--search", metavar="TERM", help="Full-text search term")
    p.add_argument("--limit", metavar="N", help="Page size")
    p.add_argument("--offset", metavar="N", help="Row offset")
    p.add_argument("--meta", metavar="SPEC", help="Meta spec, e.g. '*' or 'total_count'")
    p.add_argument("--aggregate", metavar="JSON", help="Aggregate spec, e.g. '{\"count\":\"*\"}'")
    p.add_argument("--group-by", metavar="LIST", help="Group-by fields for --aggregate")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PATCH)")
    p.add_argument("--token", default=ADMIN_TOKEN,
                   help="Static token (default: the admin token; '' for the Public role)")
    p.add_argument("--url", default=os.environ.get("DIRECTUS_API_URL", "http://localhost:8105"),
                   help="API base URL (default: $DIRECTUS_API_URL or http://localhost:8105)")
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
    for name in ("filter", "fields", "sort", "search", "limit", "offset", "meta",
                 "aggregate"):
        value = getattr(args, name, None)
        if value:
            params.append((name, value))
    if getattr(args, "group_by", None):
        params.append(("groupBy", args.group_by))
    return f"{path}?{urllib.parse.urlencode(params)}" if params else path


def _dispatch(args, base):
    token = args.token
    if args.get_ping:
        return show(api_get(base, "/server/ping", token))
    if args.get_server_health:
        return show(api_get(base, "/server/health", token))
    if args.get_server_info:
        return show(api_get(base, "/server/info", token))
    if args.post_login:
        return show(api_send(base, '/auth/login', 'POST', _body(args), None))
    if args.get_items:
        return show(api_get(base, _qs(args, _fill('/items/{collection}', args.get_items)), token))
    if args.post_item:
        return show(api_send(base, _fill('/items/{collection}', args.post_item), 'POST', _body(args), token))
    if args.get_item:
        return show(api_get(base, _qs(args, _fill('/items/{collection}/{item_id}', args.get_item)), token))
    if args.patch_item:
        return show(api_send(base, _fill('/items/{collection}/{item_id}', args.patch_item), 'PATCH', _body(args), token))
    if args.delete_item:
        return show(api_delete(base, _fill('/items/{collection}/{item_id}', args.delete_item), token))
    if args.get_collections:
        return show(api_get(base, "/collections", token))
    if args.get_collection:
        return show(api_get(base, _fill('/collections/{collection}', args.get_collection), token))
    if args.get_fields:
        return show(api_get(base, "/fields", token))
    if args.get_collection_fields:
        return show(api_get(base, _fill('/fields/{collection}', args.get_collection_fields), token))
    if args.get_users:
        return show(api_get(base, _qs(args, "/users"), token))
    if args.get_me:
        return show(api_get(base, "/users/me", token))
    if args.get_user:
        return show(api_get(base, _fill('/users/{user_id}', args.get_user), token))
    if args.get_roles:
        return show(api_get(base, "/roles", token))
    if args.get_role:
        return show(api_get(base, _fill('/roles/{role_id}', args.get_role), token))
    if args.get_permissions:
        return show(api_get(base, "/permissions", token))
    if args.get_files:
        return show(api_get(base, _qs(args, "/files"), token))
    if args.get_file:
        return show(api_get(base, _fill('/files/{file_id}', args.get_file), token))
    if args.get_activity:
        return show(api_get(base, _qs(args, "/activity"), token))
    if args.get_flows:
        return show(api_get(base, "/flows", token))
    if args.get_settings:
        return show(api_get(base, "/settings", token))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
