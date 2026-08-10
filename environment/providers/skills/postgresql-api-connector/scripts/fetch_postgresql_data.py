#!/usr/bin/env python3
"""CLI helper for the PostgreSQL API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$POSTGRESQL_API_URL (override with --url). SQL goes through --sql with optional
--params; --transaction takes a JSON array of statements. Use --role to pick the
cluster role the statement runs as.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROLES = ("postgres", "orbit_app", "orbit_readonly", "orbit_analytics")


def _fill(path, values):
    """Substitute {placeholders} in path order with the provided positional values."""
    import re as _re
    it = iter(values or [])
    return _re.sub(r"\{[^}]+\}", lambda _m: urllib.parse.quote(str(next(it, "")), safe=""), path)


def _request(base, path, method, body=None, role=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if role:
        headers["X-DB-Role"] = role
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def api_get(base, path, role=None):
    return _request(base, path, "GET", role=role)


def api_send(base, path, method, body, role=None):
    return _request(base, path, method, body if body is not None else {}, role=role)


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
    p = argparse.ArgumentParser(description="Query the PostgreSQL API (Mock) mock API")
    p.add_argument("--query", action="store_true", help="POST /api/v1/query (read-only)")
    p.add_argument("--execute", action="store_true", help="POST /api/v1/execute")
    p.add_argument("--explain", action="store_true", help="POST /api/v1/explain")
    p.add_argument("--transaction", metavar="JSON",
                   help="POST /api/v1/transaction with a JSON array of {sql, params}")
    p.add_argument("--isolation-level", default="read committed",
                   help="Isolation level for --transaction")
    p.add_argument("--analyze", action="store_true", help="EXPLAIN ANALYZE")
    p.add_argument("--buffers", action="store_true", help="EXPLAIN BUFFERS")
    p.add_argument("--format", default="json", help="EXPLAIN output format: json or text")
    p.add_argument("--get-schemas", action="store_true", help="GET /api/v1/schemas")
    p.add_argument("--get-tables", action="store_true", help="GET /api/v1/tables")
    p.add_argument("--get-table", metavar="NAME", nargs=1, help="GET /api/v1/tables/{name}")
    p.add_argument("--get-indexes", action="store_true", help="GET /api/v1/indexes")
    p.add_argument("--stat-activity", action="store_true", help="GET /api/v1/catalog/pg_stat_activity")
    p.add_argument("--stat-statements", action="store_true", help="GET /api/v1/catalog/pg_stat_statements")
    p.add_argument("--stat-user-tables", action="store_true", help="GET /api/v1/catalog/pg_stat_user_tables")
    p.add_argument("--stat-replication", action="store_true", help="GET /api/v1/catalog/pg_stat_replication")
    p.add_argument("--settings", action="store_true", help="GET /api/v1/catalog/pg_settings")
    p.add_argument("--setting", metavar="NAME", nargs=1, help="GET /api/v1/catalog/pg_settings?name=")
    p.add_argument("--extensions", action="store_true", help="GET /api/v1/catalog/pg_extension")
    p.add_argument("--roles", action="store_true", help="GET /api/v1/catalog/pg_roles")
    p.add_argument("--grants", action="store_true", help="GET /api/v1/catalog/grants")
    p.add_argument("--get-database", action="store_true", help="GET /api/v1/database")
    p.add_argument("--get-version", action="store_true", help="GET /api/v1/version")
    p.add_argument("--health-db", action="store_true", help="GET /health/db")
    p.add_argument("--sql", metavar="SQL", help="Statement for --query/--execute/--explain")
    p.add_argument("--params", metavar="JSON", help="Bind parameters: JSON array or object")
    p.add_argument("--max-rows", metavar="N", help="Cap the number of rows returned")
    p.add_argument("--order-by", metavar="COLUMN", help="Sort column for --stat-statements")
    p.add_argument("--limit", metavar="N", help="Row limit for --stat-statements")
    p.add_argument("--role", default="", choices=("",) + ROLES,
                   help="X-DB-Role header (default: the service's orbit_app)")
    p.add_argument("--url", default=os.environ.get("POSTGRESQL_API_URL",
                                                   "http://localhost:8109"),
                   help="API base URL (default: $POSTGRESQL_API_URL or http://localhost:8109)")
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
    role = args.role or None
    if args.query or args.execute:
        if not args.sql:
            print("--sql is required with --query/--execute", file=sys.stderr)
            return 2
        path = "/api/v1/query" if args.query else "/api/v1/execute"
        return show(api_send(base, path, "POST", _statement(args), role))
    if args.explain:
        if not args.sql:
            print("--sql is required with --explain", file=sys.stderr)
            return 2
        body = {"sql": args.sql, "analyze": args.analyze, "buffers": args.buffers,
                "format": args.format}
        return show(api_send(base, "/api/v1/explain", "POST", body, role))
    if args.transaction:
        body = {"statements": json.loads(args.transaction),
                "isolation_level": args.isolation_level}
        return show(api_send(base, "/api/v1/transaction", "POST", body, role))
    if args.get_schemas:
        return show(api_get(base, "/api/v1/schemas", role))
    if args.get_tables:
        return show(api_get(base, "/api/v1/tables", role))
    if args.get_table:
        return show(api_get(base, _fill('/api/v1/tables/{name}', args.get_table), role))
    if args.get_indexes:
        return show(api_get(base, "/api/v1/indexes", role))
    if args.stat_activity:
        return show(api_get(base, "/api/v1/catalog/pg_stat_activity", role))
    if args.stat_statements:
        params = {}
        if args.order_by:
            params["order_by"] = args.order_by
        if args.limit:
            params["limit"] = args.limit
        path = "/api/v1/catalog/pg_stat_statements"
        if params:
            path += "?" + urllib.parse.urlencode(params)
        return show(api_get(base, path, role))
    if args.stat_user_tables:
        return show(api_get(base, "/api/v1/catalog/pg_stat_user_tables", role))
    if args.stat_replication:
        return show(api_get(base, "/api/v1/catalog/pg_stat_replication", role))
    if args.settings:
        return show(api_get(base, "/api/v1/catalog/pg_settings", role))
    if args.setting:
        return show(api_get(base, "/api/v1/catalog/pg_settings?"
                            + urllib.parse.urlencode({"name": args.setting[0]}), role))
    if args.extensions:
        return show(api_get(base, "/api/v1/catalog/pg_extension", role))
    if args.roles:
        return show(api_get(base, "/api/v1/catalog/pg_roles", role))
    if args.grants:
        path = "/api/v1/catalog/grants"
        if args.role:
            path += "?" + urllib.parse.urlencode({"role": args.role})
        return show(api_get(base, path, role))
    if args.get_database:
        return show(api_get(base, "/api/v1/database", role))
    if args.get_version:
        return show(api_get(base, "/api/v1/version", role))
    if args.health_db:
        return show(api_get(base, "/health/db", role))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
