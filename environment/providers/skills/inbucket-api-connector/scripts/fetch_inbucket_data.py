#!/usr/bin/env python3
"""CLI helper for the Inbucket API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$INBUCKET_API_URL (override with --url). POST/PATCH bodies are read from --data
(JSON string) or --data-file.

Remember that Inbucket has no global inbox: every call names a mailbox, and the
name may be a bare mailbox or a full address -- both go through the same naming
policy. `--resolve` shows what an address would resolve to without fetching.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _quote(value):
    """Percent-encode a path segment. A mailbox name may be a full address."""
    return urllib.parse.quote(str(value), safe="")


def _request(base, path, method, body=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
    if not raw:
        return {"status": resp.status}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _body(args):
    if getattr(args, "data_file", None):
        # utf-8-sig so a file written by a Windows editor (which leaves a BOM)
        # still parses.
        with open(args.data_file, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    if getattr(args, "data", None):
        return json.loads(args.data)
    return {}


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data)
    return 0


def main():
    p = argparse.ArgumentParser(description="Query the Inbucket API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /health")
    p.add_argument("--status", action="store_true", help="GET /status")
    p.add_argument("--vars", action="store_true", help="GET /debug/vars")
    p.add_argument("--mailbox", metavar="NAME", nargs=1,
                   help="GET /api/v1/mailbox/{name} (a name or an address)")
    p.add_argument("--deliver", metavar="NAME", nargs=1,
                   help="POST /api/v1/mailbox/{name}")
    p.add_argument("--purge", metavar="NAME", nargs=1,
                   help="DELETE /api/v1/mailbox/{name}")
    p.add_argument("--message", metavar=("NAME", "ID"), nargs=2,
                   help="GET /api/v1/mailbox/{name}/{id}")
    p.add_argument("--source", metavar=("NAME", "ID"), nargs=2,
                   help="GET /api/v1/mailbox/{name}/{id}/source")
    p.add_argument("--seen", metavar=("NAME", "ID", "TRUE_OR_FALSE"), nargs=3,
                   help="PATCH /api/v1/mailbox/{name}/{id}")
    p.add_argument("--delete", metavar=("NAME", "ID"), nargs=2,
                   help="DELETE /api/v1/mailbox/{name}/{id}")
    p.add_argument("--attach", metavar=("NAME", "ID", "INDEX", "FILENAME"),
                   nargs=4,
                   help="GET /api/v1/mailbox/{name}/{id}/attach/{n}/{filename}")
    p.add_argument("--monitor", action="store_true",
                   help="GET /api/v1/monitor/messages")
    p.add_argument("--monitor-mailbox", metavar="NAME", nargs=1,
                   help="GET /api/v1/monitor/mailbox/{name}")
    p.add_argument("--resolve", metavar="ADDRESS", nargs=1,
                   help="Show which mailbox an address resolves to, locally")
    p.add_argument("--limit", type=int, help="Cap on the monitor snapshots")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--url", default=os.environ.get("INBUCKET_API_URL",
                                                   "http://localhost:8123"),
                   help="API base URL (default: $INBUCKET_API_URL or http://localhost:8123)")
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


_FLAT_GETS = [("health", "/health"), ("status", "/status"),
              ("vars", "/debug/vars")]


def _resolve(address):
    """The same policy the service applies: local part, lowercased, no +tag.

    Done locally so a client can predict the mailbox without a round trip; the
    service remains the authority.
    """
    address = address.strip()
    if "<" in address and ">" in address:
        address = address[address.index("<") + 1:address.index(">")]
    local = address.partition("@")[0]
    return local.split("+", 1)[0].lower()


def _limit(args, path):
    return f"{path}?limit={args.limit}" if args.limit else path


def _dispatch(args, base):
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, path, "GET"))
    if args.resolve:
        return show({"address": args.resolve[0],
                     "mailbox": _resolve(args.resolve[0])})
    if args.mailbox:
        return show(_request(base, f"/api/v1/mailbox/{_quote(args.mailbox[0])}",
                             "GET"))
    if args.deliver:
        return show(_request(base, f"/api/v1/mailbox/{_quote(args.deliver[0])}",
                             "POST", _body(args)))
    if args.purge:
        return show(_request(base, f"/api/v1/mailbox/{_quote(args.purge[0])}",
                             "DELETE"))
    if args.message:
        name, message_id = args.message
        return show(_request(base, f"/api/v1/mailbox/{_quote(name)}"
                                   f"/{_quote(message_id)}", "GET"))
    if args.source:
        name, message_id = args.source
        return show(_request(base, f"/api/v1/mailbox/{_quote(name)}"
                                   f"/{_quote(message_id)}/source", "GET"))
    if args.seen:
        name, message_id, value = args.seen
        return show(_request(base, f"/api/v1/mailbox/{_quote(name)}"
                                   f"/{_quote(message_id)}", "PATCH",
                             {"seen": value.lower() == "true"}))
    if args.delete:
        name, message_id = args.delete
        return show(_request(base, f"/api/v1/mailbox/{_quote(name)}"
                                   f"/{_quote(message_id)}", "DELETE"))
    if args.attach:
        name, message_id, index, filename = args.attach
        return show(_request(base, f"/api/v1/mailbox/{_quote(name)}"
                                   f"/{_quote(message_id)}/attach/"
                                   f"{_quote(index)}/{_quote(filename)}", "GET"))
    if args.monitor:
        return show(_request(base, _limit(args, "/api/v1/monitor/messages"),
                             "GET"))
    if args.monitor_mailbox:
        path = f"/api/v1/monitor/mailbox/{_quote(args.monitor_mailbox[0])}"
        return show(_request(base, _limit(args, path), "GET"))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
