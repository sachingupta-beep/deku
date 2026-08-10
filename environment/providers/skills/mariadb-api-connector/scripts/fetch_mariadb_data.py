#!/usr/bin/env python3
"""CLI helper for the MariaDB API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$MARIADB_API_URL (override with --url). SQL goes through --sql with optional
--params; --transaction takes a JSON array of statements. Use --user to pick the
account the statement runs as.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ACCOUNTS = ("root", "forum_app", "forum_mod", "forum_analytics", "forum_import")


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, user=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if user:
        headers["X-MariaDB-User"] = user
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path, user=None):
    return _request(base, path, "GET", user=user)


def api_send(base, path, method, body, user=None):
    return _request(base, path, method, body if body is not None else {}, user=user)


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
    p = argparse.ArgumentParser(description="Query the MariaDB API (Mock) mock API")
    p.add_argument("--query", action="store_true", help="POST /api/v1/query (read-only)")
    p.add_argument("--execute", action="store_true", help="POST /api/v1/execute")
    p.add_argument("--explain", action="store_true", help="POST /api/v1/explain")
    p.add_argument("--transaction", metavar="JSON",
                   help="POST /api/v1/transaction with a JSON array of {sql, params}")
    p.add_argument("--isolation-level", default="REPEATABLE READ",
                   help="Isolation level for --transaction")
    p.add_argument("--analyze", action="store_true",
                   help="Run ANALYZE instead of EXPLAIN (adds measured r_rows)")
    p.add_argument("--get-databases", action="store_true", help="GET /api/v1/databases")
    p.add_argument("--get-tables", action="store_true", help="GET /api/v1/tables")
    p.add_argument("--get-table", metavar="NAME", nargs=1, help="GET /api/v1/tables/{name}")
    p.add_argument("--get-indexes", metavar="NAME", nargs=1, help="GET /api/v1/tables/{name}/indexes")
    p.add_argument("--variables", action="store_true", help="GET /api/v1/variables")
    p.add_argument("--counters", action="store_true", help="GET /api/v1/status/counters")
    p.add_argument("--sequences", action="store_true", help="GET /api/v1/sequences")
    p.add_argument("--engines", action="store_true", help="GET /api/v1/engines")
    p.add_argument("--replication", action="store_true", help="GET /api/v1/replication")
    p.add_argument("--get-accounts", action="store_true", help="GET /api/v1/accounts")
    p.add_argument("--grants", action="store_true", help="GET /api/v1/grants")
    p.add_argument("--grants-for", metavar="ACCOUNT", help="GET /api/v1/grants?user=")
    p.add_argument("--get-status", action="store_true", help="GET /api/v1/status")
    p.add_argument("--get-version", action="store_true", help="GET /api/v1/version")
    p.add_argument("--health-db", action="store_true", help="GET /health/db")
    p.add_argument("--sql", metavar="SQL", help="Statement for --query/--execute/--explain")
    p.add_argument("--params", metavar="JSON", help="Bind parameters: JSON array or object")
    p.add_argument("--max-rows", metavar="N", help="Cap the number of rows returned")
    p.add_argument("--like", metavar="PATTERN", help="Filter for --variables/--counters")
    p.add_argument("--user", default="", choices=("",) + ACCOUNTS,
                   help="X-MariaDB-User header (default: the service's forum_app)")
    p.add_argument("--url", default=os.environ.get("MARIADB_API_URL", "http://localhost:8111"),
                   help="API base URL (default: $MARIADB_API_URL or http://localhost:8111)")
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
    user = args.user or None
    if args.query or args.execute:
        if not args.sql:
            print("--sql is required with --query/--execute", file=sys.stderr)
            return 2
        path = "/api/v1/query" if args.query else "/api/v1/execute"
        return show(api_send(base, path, "POST", _statement(args), user))
    if args.explain:
        if not args.sql:
            print("--sql is required with --explain", file=sys.stderr)
            return 2
        return show(api_send(base, "/api/v1/explain", "POST",
                             {"sql": args.sql, "analyze": args.analyze}, user))
    if args.transaction:
        body = {"statements": json.loads(args.transaction),
                "isolation_level": args.isolation_level}
        return show(api_send(base, "/api/v1/transaction", "POST", body, user))
    if args.get_databases:
        return show(api_get(base, "/api/v1/databases", user))
    if args.get_tables:
        return show(api_get(base, "/api/v1/tables", user))
    if args.get_table:
        return show(api_get(base, _fill('/api/v1/tables/{name}', args.get_table), user))
    if args.get_indexes:
        return show(api_get(base, _fill('/api/v1/tables/{name}/indexes', args.get_indexes), user))
    if args.variables:
        path = "/api/v1/variables"
        if args.like:
            path += "?" + urllib.parse.urlencode({"like": args.like})
        return show(api_get(base, path, user))
    if args.counters:
        path = "/api/v1/status/counters"
        if args.like:
            path += "?" + urllib.parse.urlencode({"like": args.like})
        return show(api_get(base, path, user))
    if args.sequences:
        return show(api_get(base, "/api/v1/sequences", user))
    if args.engines:
        return show(api_get(base, "/api/v1/engines", user))
    if args.replication:
        return show(api_get(base, "/api/v1/replication", user))
    if args.get_accounts:
        return show(api_get(base, "/api/v1/accounts", user))
    if args.grants or args.grants_for:
        path = "/api/v1/grants"
        if args.grants_for:
            path += "?" + urllib.parse.urlencode({"user": args.grants_for})
        return show(api_get(base, path, user))
    if args.get_status:
        return show(api_get(base, "/api/v1/status", user))
    if args.get_version:
        return show(api_get(base, "/api/v1/version", user))
    if args.health_db:
        return show(api_get(base, "/health/db", user))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
