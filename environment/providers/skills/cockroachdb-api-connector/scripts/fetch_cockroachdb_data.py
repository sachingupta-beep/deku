#!/usr/bin/env python3
"""CLI helper for the CockroachDB API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$COCKROACHDB_API_URL (override with --url). SQL goes through --sql with optional
--params; --transaction takes a JSON array of statements. Use --max-retries to
handle the 40001 serialization restarts the cluster raises on contended rows,
and --as-of-system-time for a historical read.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

USERS = ("root", "orbit_app", "orbit_readonly", "orbit_fleet_admin",
         "orbit_changefeed")


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
        headers["X-CRDB-User"] = user
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
    if args.as_of_system_time:
        body["as_of_system_time"] = args.as_of_system_time
    return body


def main():
    p = argparse.ArgumentParser(description="Query the CockroachDB API (Mock) mock API")
    p.add_argument("--query", action="store_true", help="POST /api/v1/query (read-only)")
    p.add_argument("--execute", action="store_true", help="POST /api/v1/execute")
    p.add_argument("--explain", action="store_true", help="POST /api/v1/explain")
    p.add_argument("--transaction", metavar="JSON",
                   help="POST /api/v1/transaction with a JSON array of {sql, params}")
    p.add_argument("--priority", default="NORMAL",
                   help="Transaction priority: LOW, NORMAL, HIGH")
    p.add_argument("--max-retries", metavar="N", default="0",
                   help="Retry budget for a serializable restart (SQLSTATE 40001)")
    p.add_argument("--analyze", action="store_true", help="EXPLAIN ANALYZE")
    p.add_argument("--verbose", action="store_true", help="EXPLAIN VERBOSE")
    p.add_argument("--get-databases", action="store_true", help="GET /api/v1/databases")
    p.add_argument("--get-tables", action="store_true", help="GET /api/v1/tables")
    p.add_argument("--get-table", metavar="NAME", nargs=1, help="GET /api/v1/tables/{name}")
    p.add_argument("--table-ranges", metavar="NAME", nargs=1,
                   help="GET /api/v1/tables/{name}/ranges")
    p.add_argument("--ranges", action="store_true", help="GET /api/v1/ranges")
    p.add_argument("--nodes", action="store_true", help="GET /api/v1/nodes")
    p.add_argument("--regions", action="store_true", help="GET /api/v1/regions")
    p.add_argument("--jobs", action="store_true", help="GET /api/v1/jobs")
    p.add_argument("--job-status", metavar="STATUS", help="Filter for --jobs")
    p.add_argument("--job-type", metavar="TYPE", help="Filter for --jobs")
    p.add_argument("--settings", action="store_true", help="GET /api/v1/cluster/settings")
    p.add_argument("--setting", metavar="NAME", nargs=1,
                   help="GET /api/v1/cluster/settings?name=")
    p.add_argument("--cluster-status", action="store_true",
                   help="GET /api/v1/cluster/status")
    p.add_argument("--statements", action="store_true", help="GET /api/v1/statements")
    p.add_argument("--order-by", metavar="COLUMN", help="Sort column for --statements")
    p.add_argument("--limit", metavar="N", help="Row limit for --statements")
    p.add_argument("--get-users", action="store_true", help="GET /api/v1/users")
    p.add_argument("--grants", action="store_true", help="GET /api/v1/grants")
    p.add_argument("--grants-for", metavar="USER", help="GET /api/v1/grants?user=")
    p.add_argument("--get-version", action="store_true", help="GET /api/v1/version")
    p.add_argument("--health-db", action="store_true", help="GET /health/db")
    p.add_argument("--sql", metavar="SQL", help="Statement for --query/--execute/--explain")
    p.add_argument("--params", metavar="JSON", help="Bind parameters: JSON array or object")
    p.add_argument("--max-rows", metavar="N", help="Cap the number of rows returned")
    p.add_argument("--as-of-system-time", metavar="TS",
                   help="Historical read, e.g. '-10s' or follower_read_timestamp()")
    p.add_argument("--user", default="", choices=("",) + USERS,
                   help="X-CRDB-User header (default: the service's orbit_app)")
    p.add_argument("--url", default=os.environ.get("COCKROACHDB_API_URL",
                                                   "http://localhost:8112"),
                   help="API base URL (default: $COCKROACHDB_API_URL or http://localhost:8112)")
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
        body = {"sql": args.sql, "analyze": args.analyze, "verbose": args.verbose}
        return show(api_send(base, "/api/v1/explain", "POST", body, user))
    if args.transaction:
        body = {"statements": json.loads(args.transaction),
                "priority": args.priority,
                "max_retries": int(args.max_retries or 0)}
        return show(api_send(base, "/api/v1/transaction", "POST", body, user))
    if args.get_databases:
        return show(api_get(base, "/api/v1/databases", user))
    if args.get_tables:
        return show(api_get(base, "/api/v1/tables", user))
    if args.get_table:
        return show(api_get(base, _fill('/api/v1/tables/{name}', args.get_table), user))
    if args.table_ranges:
        return show(api_get(base, _fill('/api/v1/tables/{name}/ranges',
                                        args.table_ranges), user))
    if args.ranges:
        return show(api_get(base, "/api/v1/ranges", user))
    if args.nodes:
        return show(api_get(base, "/api/v1/nodes", user))
    if args.regions:
        return show(api_get(base, "/api/v1/regions", user))
    if args.jobs:
        params = {}
        if args.job_status:
            params["status"] = args.job_status
        if args.job_type:
            params["job_type"] = args.job_type
        path = "/api/v1/jobs"
        if params:
            path += "?" + urllib.parse.urlencode(params)
        return show(api_get(base, path, user))
    if args.settings:
        return show(api_get(base, "/api/v1/cluster/settings", user))
    if args.setting:
        return show(api_get(base, "/api/v1/cluster/settings?"
                            + urllib.parse.urlencode({"name": args.setting[0]}), user))
    if args.cluster_status:
        return show(api_get(base, "/api/v1/cluster/status", user))
    if args.statements:
        params = {}
        if args.order_by:
            params["order_by"] = args.order_by
        if args.limit:
            params["limit"] = args.limit
        path = "/api/v1/statements"
        if params:
            path += "?" + urllib.parse.urlencode(params)
        return show(api_get(base, path, user))
    if args.get_users:
        return show(api_get(base, "/api/v1/users", user))
    if args.grants or args.grants_for:
        path = "/api/v1/grants"
        if args.grants_for:
            path += "?" + urllib.parse.urlencode({"user": args.grants_for})
        return show(api_get(base, path, user))
    if args.get_version:
        return show(api_get(base, "/api/v1/version", user))
    if args.health_db:
        return show(api_get(base, "/health/db", user))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
