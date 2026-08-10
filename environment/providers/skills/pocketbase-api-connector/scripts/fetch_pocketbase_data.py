#!/usr/bin/env python3
"""CLI helper for the PocketBase API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$POCKETBASE_API_URL (override with --url). POST/PATCH bodies are read from --data
(JSON string) or --data-file; DELETE/GET take only path params. Pass --token to
choose the identity the request is evaluated as.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SUPERUSER_TOKEN = "eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status"


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
    p = argparse.ArgumentParser(description="Query the PocketBase API (Mock) mock API")
    p.add_argument("--get-health", action="store_true", help="GET /api/health")
    p.add_argument("--get-collections", action="store_true", help="GET /api/collections")
    p.add_argument("--get-collection", metavar="COLLECTION", nargs=1, help="GET /api/collections/{collection}")
    p.add_argument("--get-records", metavar="COLLECTION", nargs=1, help="GET /api/collections/{collection}/records")
    p.add_argument("--get-record", metavar=("COLLECTION", "RECORD_ID"), nargs=2, help="GET /api/collections/{collection}/records/{record_id}")
    p.add_argument("--post-record", metavar="COLLECTION", nargs=1, help="POST /api/collections/{collection}/records")
    p.add_argument("--patch-record", metavar=("COLLECTION", "RECORD_ID"), nargs=2, help="PATCH /api/collections/{collection}/records/{record_id}")
    p.add_argument("--delete-record", metavar=("COLLECTION", "RECORD_ID"), nargs=2, help="DELETE /api/collections/{collection}/records/{record_id}")
    p.add_argument("--get-file", metavar=("COLLECTION", "RECORD_ID", "FILENAME"), nargs=3, help="GET /api/files/{collection}/{record_id}/{filename}")
    p.add_argument("--post-file-token", action="store_true", help="POST /api/files/token")
    p.add_argument("--get-logs", action="store_true", help="GET /api/logs")
    p.add_argument("--get-log-stats", action="store_true", help="GET /api/logs/stats")
    p.add_argument("--get-backups", action="store_true", help="GET /api/backups")
    p.add_argument("--post-backup", action="store_true", help="POST /api/backups")
    p.add_argument("--delete-backup", metavar="KEY", nargs=1, help="DELETE /api/backups/{key}")
    p.add_argument("--get-crons", action="store_true", help="GET /api/crons")
    p.add_argument("--get-settings", action="store_true", help="GET /api/settings")
    p.add_argument("--post-realtime", action="store_true", help="POST /api/realtime")
    p.add_argument("--get-realtime", action="store_true", help="GET /api/realtime")
    p.add_argument("--query", metavar="QS", default="",
                   help="Query string appended to list reads, e.g. 'filter=status!=\"resolved\"&expand=service'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PATCH)")
    p.add_argument("--token", default=SUPERUSER_TOKEN,
                   help="Authorization header value (default: the superuser token)")
    p.add_argument("--url", default=os.environ.get("POCKETBASE_API_URL", "http://localhost:8103"),
                   help="API base URL (default: $POCKETBASE_API_URL or http://localhost:8103)")
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
    parts = urllib.parse.parse_qsl(args.query, keep_blank_values=True)
    return f"{path}?{urllib.parse.urlencode(parts)}"


def _dispatch(args, base):
    token = args.token
    if args.get_health:
        return show(api_get(base, "/api/health", token))
    if args.get_collections:
        return show(api_get(base, _qs(args, "/api/collections"), token))
    if args.get_collection:
        return show(api_get(base, _fill('/api/collections/{collection}', args.get_collection), token))
    if args.get_records:
        return show(api_get(base, _qs(args, _fill('/api/collections/{collection}/records', args.get_records)), token))
    if args.get_record:
        return show(api_get(base, _qs(args, _fill('/api/collections/{collection}/records/{record_id}', args.get_record)), token))
    if args.post_record:
        return show(api_send(base, _fill('/api/collections/{collection}/records', args.post_record), 'POST', _body(args), token))
    if args.patch_record:
        return show(api_send(base, _fill('/api/collections/{collection}/records/{record_id}', args.patch_record), 'PATCH', _body(args), token))
    if args.delete_record:
        return show(api_delete(base, _fill('/api/collections/{collection}/records/{record_id}', args.delete_record), token))
    if args.get_file:
        collection, record_id, filename = args.get_file
        return show(api_get(base, _qs(args, f"/api/files/{collection}/{record_id}/{urllib.parse.quote(filename)}"), token))
    if args.post_file_token:
        return show(api_send(base, '/api/files/token', 'POST', _body(args), token))
    if args.get_logs:
        return show(api_get(base, _qs(args, "/api/logs"), token))
    if args.get_log_stats:
        return show(api_get(base, _qs(args, "/api/logs/stats"), token))
    if args.get_backups:
        return show(api_get(base, "/api/backups", token))
    if args.post_backup:
        return show(api_send(base, '/api/backups', 'POST', _body(args), token))
    if args.delete_backup:
        return show(api_delete(base, _fill('/api/backups/{key}', args.delete_backup), token))
    if args.get_crons:
        return show(api_get(base, "/api/crons", token))
    if args.get_settings:
        return show(api_get(base, "/api/settings", token))
    if args.post_realtime:
        return show(api_send(base, '/api/realtime', 'POST', _body(args), token))
    if args.get_realtime:
        return show(api_get(base, "/api/realtime", token))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
