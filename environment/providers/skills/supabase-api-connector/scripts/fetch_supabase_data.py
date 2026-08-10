#!/usr/bin/env python3
"""CLI helper for the Supabase API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$SUPABASE_API_URL (override with --url). POST/PATCH bodies are read from --data
(JSON string) or --data-file; DELETE/GET take only path params. Pass --apikey to
choose the Postgres role the request is evaluated as.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost"


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, apikey=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if apikey:
        headers["apikey"] = apikey
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path, apikey=None):
    return _request(base, path, "GET", apikey=apikey)


def api_delete(base, path, apikey=None):
    return _request(base, path, "DELETE", apikey=apikey)


def api_send(base, path, method, body, apikey=None):
    return _request(base, path, method, body if body is not None else {}, apikey=apikey)


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
    p = argparse.ArgumentParser(description="Query the Supabase API (Mock) mock API")
    p.add_argument("--get-rest-root", action="store_true", help="GET /rest/v1/")
    p.add_argument("--get-table", metavar="TABLE", nargs=1, help="GET /rest/v1/{table}")
    p.add_argument("--post-table", metavar="TABLE", nargs=1, help="POST /rest/v1/{table}")
    p.add_argument("--patch-table", metavar="TABLE", nargs=1, help="PATCH /rest/v1/{table}")
    p.add_argument("--delete-table", metavar="TABLE", nargs=1, help="DELETE /rest/v1/{table}")
    p.add_argument("--post-rpc", metavar="FN_NAME", nargs=1, help="POST /rest/v1/rpc/{fn_name}")
    p.add_argument("--get-buckets", action="store_true", help="GET /storage/v1/bucket")
    p.add_argument("--get-bucket", metavar="BUCKET_ID", nargs=1, help="GET /storage/v1/bucket/{bucket_id}")
    p.add_argument("--post-bucket", action="store_true", help="POST /storage/v1/bucket")
    p.add_argument("--delete-bucket", metavar="BUCKET_ID", nargs=1, help="DELETE /storage/v1/bucket/{bucket_id}")
    p.add_argument("--post-object-list", metavar="BUCKET_ID", nargs=1, help="POST /storage/v1/object/list/{bucket_id}")
    p.add_argument("--get-object-info", metavar=("BUCKET_ID", "PATH"), nargs=2, help="GET /storage/v1/object/info/{bucket_id}/{path}")
    p.add_argument("--post-object-sign", metavar=("BUCKET_ID", "PATH"), nargs=2, help="POST /storage/v1/object/sign/{bucket_id}/{path}")
    p.add_argument("--delete-object", metavar=("BUCKET_ID", "PATH"), nargs=2, help="DELETE /storage/v1/object/{bucket_id}/{path}")
    p.add_argument("--get-functions", action="store_true", help="GET /functions/v1")
    p.add_argument("--post-function", metavar="SLUG", nargs=1, help="POST /functions/v1/{slug}")
    p.add_argument("--get-channels", action="store_true", help="GET /realtime/v1/channels")
    p.add_argument("--post-broadcast", action="store_true", help="POST /realtime/v1/api/broadcast")
    p.add_argument("--get-projects", action="store_true", help="GET /v1/projects")
    p.add_argument("--get-project", metavar="REF", nargs=1, help="GET /v1/projects/{ref}")
    p.add_argument("--query", metavar="QS", default="",
                   help="PostgREST query string appended to /rest/v1 reads and writes, e.g. 'id=eq.101&select=*'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PATCH)")
    p.add_argument("--apikey", default=SERVICE_KEY,
                   help="apikey header value (default: the project service key)")
    p.add_argument("--url", default=os.environ.get("SUPABASE_API_URL", "http://localhost:8102"),
                   help="API base URL (default: $SUPABASE_API_URL or http://localhost:8102)")
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


def _dispatch(args, base):
    key = args.apikey
    if args.get_rest_root:
        return show(api_get(base, "/rest/v1/", key))
    if args.get_table:
        return show(api_get(base, _qs(args, _fill('/rest/v1/{table}', args.get_table)), key))
    if args.post_table:
        return show(api_send(base, _fill('/rest/v1/{table}', args.post_table), 'POST', _body(args), key))
    if args.patch_table:
        return show(api_send(base, _qs(args, _fill('/rest/v1/{table}', args.patch_table)), 'PATCH', _body(args), key))
    if args.delete_table:
        return show(api_delete(base, _qs(args, _fill('/rest/v1/{table}', args.delete_table)), key))
    if args.post_rpc:
        return show(api_send(base, _fill('/rest/v1/rpc/{fn_name}', args.post_rpc), 'POST', _body(args), key))
    if args.get_buckets:
        return show(api_get(base, "/storage/v1/bucket", key))
    if args.get_bucket:
        return show(api_get(base, _fill('/storage/v1/bucket/{bucket_id}', args.get_bucket), key))
    if args.post_bucket:
        return show(api_send(base, '/storage/v1/bucket', 'POST', _body(args), key))
    if args.delete_bucket:
        return show(api_delete(base, _fill('/storage/v1/bucket/{bucket_id}', args.delete_bucket), key))
    if args.post_object_list:
        return show(api_send(base, _fill('/storage/v1/object/list/{bucket_id}', args.post_object_list), 'POST', _body(args), key))
    if args.get_object_info:
        bucket, path = args.get_object_info
        return show(api_get(base, f"/storage/v1/object/info/{urllib.parse.quote(bucket)}/{path}", key))
    if args.post_object_sign:
        bucket, path = args.post_object_sign
        return show(api_send(base, f"/storage/v1/object/sign/{urllib.parse.quote(bucket)}/{path}", 'POST', _body(args), key))
    if args.delete_object:
        bucket, path = args.delete_object
        return show(api_delete(base, f"/storage/v1/object/{urllib.parse.quote(bucket)}/{path}", key))
    if args.get_functions:
        return show(api_get(base, "/functions/v1", key))
    if args.post_function:
        return show(api_send(base, _fill('/functions/v1/{slug}', args.post_function), 'POST', _body(args), key))
    if args.get_channels:
        return show(api_get(base, "/realtime/v1/channels", key))
    if args.post_broadcast:
        return show(api_send(base, '/realtime/v1/api/broadcast', 'POST', _body(args), key))
    if args.get_projects:
        return show(api_get(base, "/v1/projects", key))
    if args.get_project:
        return show(api_get(base, _fill('/v1/projects/{ref}', args.get_project), key))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
