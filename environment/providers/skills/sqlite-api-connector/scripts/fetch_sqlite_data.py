#!/usr/bin/env python3
"""CLI helper for the SQLite API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$SQLITE_API_URL (override with --url). SQL goes through --sql with optional
--params; --transaction takes a JSON array of statements. Use --api-key to pick
the read-only key.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

READONLY_KEY = "sqlite_ro_2b90d7fc1e6a4830"


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, api_key=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path, api_key=None):
    return _request(base, path, "GET", api_key=api_key)


def api_send(base, path, method, body, api_key=None):
    return _request(base, path, method, body if body is not None else {}, api_key=api_key)


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data)
    return 0


def _statement(args):
    body = {"sql": args.sql}
    if args.params:
        body["params"] = json.loads(args.params)
    if args.max_rows:
        body["max_rows"] = int(args.max_rows)
    return body


def main():
    p = argparse.ArgumentParser(description="Query the SQLite API (Mock) mock API")
    p.add_argument("--query", action="store_true", help="POST /api/v1/query (read-only)")
    p.add_argument("--execute", action="store_true", help="POST /api/v1/execute")
    p.add_argument("--explain", action="store_true", help="POST /api/v1/explain")
    p.add_argument("--transaction", metavar="JSON",
                   help="POST /api/v1/transaction with a JSON array of {sql, params}")
    p.add_argument("--non-atomic", action="store_true",
                   help="Run --transaction without rolling back on failure")
    p.add_argument("--get-tables", action="store_true", help="GET /api/v1/tables")
    p.add_argument("--get-table", metavar="NAME", nargs=1, help="GET /api/v1/tables/{name}")
    p.add_argument("--get-indexes", action="store_true", help="GET /api/v1/indexes")
    p.add_argument("--get-schema", action="store_true", help="GET /api/v1/schema")
    p.add_argument("--get-database", action="store_true", help="GET /api/v1/database")
    p.add_argument("--get-pragma", metavar="NAME", nargs=1, help="GET /api/v1/pragma/{name}")
    p.add_argument("--integrity-check", action="store_true", help="GET /api/v1/integrity-check")
    p.add_argument("--health-db", action="store_true", help="GET /health/db")
    p.add_argument("--sql", metavar="SQL", help="Statement for --query/--execute/--explain")
    p.add_argument("--params", metavar="JSON", help="Bind parameters: JSON array or object")
    p.add_argument("--max-rows", metavar="N", help="Cap the number of rows returned")
    p.add_argument("--api-key", default="",
                   help=f"X-API-Key header; use {READONLY_KEY} for read-only access")
    p.add_argument("--url", default=os.environ.get("SQLITE_API_URL", "http://localhost:8108"),
                   help="API base URL (default: $SQLITE_API_URL or http://localhost:8108)")
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


def _dispatch(args, base):
    key = args.api_key
    if args.query or args.execute or args.explain:
        if not args.sql:
            print("--sql is required with --query/--execute/--explain", file=sys.stderr)
            return 2
        path = "/api/v1/query" if args.query else \
            ("/api/v1/execute" if args.execute else "/api/v1/explain")
        return show(api_send(base, path, "POST", _statement(args), key))
    if args.transaction:
        body = {"statements": json.loads(args.transaction),
                "atomic": not args.non_atomic}
        return show(api_send(base, "/api/v1/transaction", "POST", body, key))
    if args.get_tables:
        return show(api_get(base, "/api/v1/tables", key))
    if args.get_table:
        return show(api_get(base, _fill('/api/v1/tables/{name}', args.get_table), key))
    if args.get_indexes:
        return show(api_get(base, "/api/v1/indexes", key))
    if args.get_schema:
        return show(api_get(base, "/api/v1/schema", key))
    if args.get_database:
        return show(api_get(base, "/api/v1/database", key))
    if args.get_pragma:
        return show(api_get(base, _fill('/api/v1/pragma/{name}', args.get_pragma), key))
    if args.integrity_check:
        return show(api_get(base, "/api/v1/integrity-check", key))
    if args.health_db:
        return show(api_get(base, "/health/db", key))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
