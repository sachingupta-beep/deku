#!/usr/bin/env python3
"""CLI helper for the Appwrite API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$APPWRITE_API_URL (override with --url). POST/PATCH bodies are read from --data
(JSON string) or --data-file; DELETE/GET take only path params. Use --query to
pass Query DSL entries (repeat the flag) and --session to switch scope.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PROJECT = "orbit-app"
API_KEY = "standard_9f3c1a7e5b2d4086af51c7e93b0d6248"
SESSION = "session_orbit_priya_9f3c1a7e"


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
    p = argparse.ArgumentParser(description="Query the Appwrite API (Mock) mock API")
    p.add_argument("--get-health", action="store_true", help="GET /v1/health")
    p.add_argument("--get-health-db", action="store_true", help="GET /v1/health/db")
    p.add_argument("--get-health-storage", action="store_true", help="GET /v1/health/storage")
    p.add_argument("--get-locale", action="store_true", help="GET /v1/locale")
    p.add_argument("--get-project", action="store_true", help="GET /v1/project")
    p.add_argument("--get-databases", action="store_true", help="GET /v1/databases")
    p.add_argument("--get-database", metavar="DATABASE_ID", nargs=1, help="GET /v1/databases/{database_id}")
    p.add_argument("--get-collections", metavar="DATABASE_ID", nargs=1, help="GET /v1/databases/{database_id}/collections")
    p.add_argument("--get-collection", metavar=("DATABASE_ID", "COLLECTION_ID"), nargs=2, help="GET /v1/databases/{database_id}/collections/{collection_id}")
    p.add_argument("--get-documents", metavar=("DATABASE_ID", "COLLECTION_ID"), nargs=2, help="GET /v1/databases/{db}/collections/{col}/documents")
    p.add_argument("--post-document", metavar=("DATABASE_ID", "COLLECTION_ID"), nargs=2, help="POST /v1/databases/{db}/collections/{col}/documents")
    p.add_argument("--get-document", metavar=("DATABASE_ID", "COLLECTION_ID", "DOCUMENT_ID"), nargs=3, help="GET /v1/databases/{db}/collections/{col}/documents/{id}")
    p.add_argument("--patch-document", metavar=("DATABASE_ID", "COLLECTION_ID", "DOCUMENT_ID"), nargs=3, help="PATCH /v1/databases/{db}/collections/{col}/documents/{id}")
    p.add_argument("--delete-document", metavar=("DATABASE_ID", "COLLECTION_ID", "DOCUMENT_ID"), nargs=3, help="DELETE /v1/databases/{db}/collections/{col}/documents/{id}")
    p.add_argument("--get-buckets", action="store_true", help="GET /v1/storage/buckets")
    p.add_argument("--get-bucket", metavar="BUCKET_ID", nargs=1, help="GET /v1/storage/buckets/{bucket_id}")
    p.add_argument("--get-files", metavar="BUCKET_ID", nargs=1, help="GET /v1/storage/buckets/{bucket_id}/files")
    p.add_argument("--get-file", metavar=("BUCKET_ID", "FILE_ID"), nargs=2, help="GET /v1/storage/buckets/{bucket_id}/files/{file_id}")
    p.add_argument("--delete-file", metavar=("BUCKET_ID", "FILE_ID"), nargs=2, help="DELETE /v1/storage/buckets/{bucket_id}/files/{file_id}")
    p.add_argument("--get-functions", action="store_true", help="GET /v1/functions")
    p.add_argument("--get-function", metavar="FUNCTION_ID", nargs=1, help="GET /v1/functions/{function_id}")
    p.add_argument("--get-executions", metavar="FUNCTION_ID", nargs=1, help="GET /v1/functions/{function_id}/executions")
    p.add_argument("--post-execution", metavar="FUNCTION_ID", nargs=1, help="POST /v1/functions/{function_id}/executions")
    p.add_argument("--get-teams", action="store_true", help="GET /v1/teams")
    p.add_argument("--get-team", metavar="TEAM_ID", nargs=1, help="GET /v1/teams/{team_id}")
    p.add_argument("--get-memberships", metavar="TEAM_ID", nargs=1, help="GET /v1/teams/{team_id}/memberships")
    p.add_argument("--get-users", action="store_true", help="GET /v1/users")
    p.add_argument("--get-user", metavar="USER_ID", nargs=1, help="GET /v1/users/{user_id}")
    p.add_argument("--get-account", action="store_true", help="GET /v1/account")
    p.add_argument("--query", metavar="QUERY", action="append", default=[],
                   help="Query DSL entry, repeatable, e.g. --query 'equal(\"status\", [\"open\"])'")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string (POST/PATCH)")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file (POST/PATCH)")
    p.add_argument("--project", default=PROJECT, help="X-Appwrite-Project header value")
    p.add_argument("--key", default=API_KEY, help="X-Appwrite-Key header value ('' to drop it)")
    p.add_argument("--session", default="", help="X-Appwrite-Session header value (overrides --key)")
    p.add_argument("--url", default=os.environ.get("APPWRITE_API_URL", "http://localhost:8104"),
                   help="API base URL (default: $APPWRITE_API_URL or http://localhost:8104)")
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
    if args.project:
        headers["X-Appwrite-Project"] = args.project
    if args.session:
        headers["X-Appwrite-Session"] = args.session
    elif args.key:
        headers["X-Appwrite-Key"] = args.key
    return headers


def _qs(args, path):
    if not args.query:
        return path
    encoded = urllib.parse.urlencode([("queries[]", q) for q in args.query])
    return f"{path}?{encoded}"


def _dispatch(args, base):
    h = _headers(args)
    if args.get_health:
        return show(api_get(base, "/v1/health", h))
    if args.get_health_db:
        return show(api_get(base, "/v1/health/db", h))
    if args.get_health_storage:
        return show(api_get(base, "/v1/health/storage", h))
    if args.get_locale:
        return show(api_get(base, "/v1/locale", h))
    if args.get_project:
        return show(api_get(base, "/v1/project", h))
    if args.get_databases:
        return show(api_get(base, _qs(args, "/v1/databases"), h))
    if args.get_database:
        return show(api_get(base, _fill('/v1/databases/{database_id}', args.get_database), h))
    if args.get_collections:
        return show(api_get(base, _qs(args, _fill('/v1/databases/{database_id}/collections', args.get_collections)), h))
    if args.get_collection:
        return show(api_get(base, _fill('/v1/databases/{database_id}/collections/{collection_id}', args.get_collection), h))
    if args.get_documents:
        return show(api_get(base, _qs(args, _fill('/v1/databases/{db}/collections/{col}/documents', args.get_documents)), h))
    if args.post_document:
        return show(api_send(base, _fill('/v1/databases/{db}/collections/{col}/documents', args.post_document), 'POST', _body(args), h))
    if args.get_document:
        return show(api_get(base, _fill('/v1/databases/{db}/collections/{col}/documents/{id}', args.get_document), h))
    if args.patch_document:
        return show(api_send(base, _fill('/v1/databases/{db}/collections/{col}/documents/{id}', args.patch_document), 'PATCH', _body(args), h))
    if args.delete_document:
        return show(api_delete(base, _fill('/v1/databases/{db}/collections/{col}/documents/{id}', args.delete_document), h))
    if args.get_buckets:
        return show(api_get(base, _qs(args, "/v1/storage/buckets"), h))
    if args.get_bucket:
        return show(api_get(base, _fill('/v1/storage/buckets/{bucket_id}', args.get_bucket), h))
    if args.get_files:
        return show(api_get(base, _qs(args, _fill('/v1/storage/buckets/{bucket_id}/files', args.get_files)), h))
    if args.get_file:
        return show(api_get(base, _fill('/v1/storage/buckets/{bucket_id}/files/{file_id}', args.get_file), h))
    if args.delete_file:
        return show(api_delete(base, _fill('/v1/storage/buckets/{bucket_id}/files/{file_id}', args.delete_file), h))
    if args.get_functions:
        return show(api_get(base, _qs(args, "/v1/functions"), h))
    if args.get_function:
        return show(api_get(base, _fill('/v1/functions/{function_id}', args.get_function), h))
    if args.get_executions:
        return show(api_get(base, _qs(args, _fill('/v1/functions/{function_id}/executions', args.get_executions)), h))
    if args.post_execution:
        return show(api_send(base, _fill('/v1/functions/{function_id}/executions', args.post_execution), 'POST', _body(args), h))
    if args.get_teams:
        return show(api_get(base, _qs(args, "/v1/teams"), h))
    if args.get_team:
        return show(api_get(base, _fill('/v1/teams/{team_id}', args.get_team), h))
    if args.get_memberships:
        return show(api_get(base, _qs(args, _fill('/v1/teams/{team_id}/memberships', args.get_memberships)), h))
    if args.get_users:
        return show(api_get(base, _qs(args, "/v1/users"), h))
    if args.get_user:
        return show(api_get(base, _fill('/v1/users/{user_id}', args.get_user), h))
    if args.get_account:
        return show(api_get(base, "/v1/account", h))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
