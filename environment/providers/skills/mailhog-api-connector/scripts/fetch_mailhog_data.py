#!/usr/bin/env python3
"""CLI helper for the MailHog API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$MAILHOG_API_URL (override with --url). POST/PUT bodies are read from --data
(JSON string) or --data-file.

Two things to remember about MailHog: addresses come back as `Path` objects
rather than strings, and Jim answers 404 until he is switched on.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _quote(value):
    """Percent-encode a path segment. Message ids contain '@'."""
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
        with open(args.data_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if getattr(args, "data", None):
        return json.loads(args.data)
    return {}


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data)
    return 0


def main():
    p = argparse.ArgumentParser(description="Query the MailHog API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /health")
    p.add_argument("--info", action="store_true", help="GET /api/v1/info")
    p.add_argument("--events", action="store_true", help="GET /api/v1/events")
    p.add_argument("--messages", action="store_true",
                   help="GET /api/v1/messages (bare array)")
    p.add_argument("--messages-v2", action="store_true",
                   help="GET /api/v2/messages (paginated envelope)")
    p.add_argument("--message", metavar="ID", nargs=1,
                   help="GET /api/v1/messages/{id}")
    p.add_argument("--download", metavar="ID", nargs=1,
                   help="GET /api/v1/messages/{id}/download (raw RFC 822)")
    p.add_argument("--part", metavar=("ID", "INDEX"), nargs=2,
                   help="GET /api/v1/messages/{id}/mime/part/{n}/download")
    p.add_argument("--delete", metavar="ID", nargs=1,
                   help="DELETE /api/v1/messages/{id}")
    p.add_argument("--delete-all", action="store_true",
                   help="DELETE /api/v1/messages")
    p.add_argument("--search", metavar=("KIND", "QUERY"), nargs=2,
                   help="GET /api/v2/search — KIND is from, to or containing")
    p.add_argument("--release", metavar="ID", nargs=1,
                   help="POST /api/v1/messages/{id}/release")
    p.add_argument("--releases", action="store_true", help="GET /api/v1/releases")
    p.add_argument("--outgoing-smtp", action="store_true",
                   help="GET /api/v2/outgoing-smtp")
    p.add_argument("--jim", action="store_true",
                   help="GET /api/v2/jim (404 while chaos is disabled)")
    p.add_argument("--enable-jim", action="store_true", help="POST /api/v2/jim")
    p.add_argument("--update-jim", action="store_true", help="PUT /api/v2/jim")
    p.add_argument("--disable-jim", action="store_true", help="DELETE /api/v2/jim")
    p.add_argument("--start", type=int, default=0,
                   help="Offset for the paginated reads (default: 0)")
    p.add_argument("--limit", type=int, default=50,
                   help="Page size for the paginated reads (default: 50)")
    p.add_argument("--to", metavar="EMAIL",
                   help="Recipient for --release; Jim's roll is seeded from it")
    p.add_argument("--server", metavar="NAME",
                   help="Named outgoing SMTP server for --release")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--url", default=os.environ.get("MAILHOG_API_URL",
                                                   "http://localhost:8121"),
                   help="API base URL (default: $MAILHOG_API_URL or http://localhost:8121)")
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


_FLAT_GETS = [("health", "/health"), ("info", "/api/v1/info"),
              ("messages", "/api/v1/messages"), ("releases", "/api/v1/releases"),
              ("outgoing_smtp", "/api/v2/outgoing-smtp"), ("jim", "/api/v2/jim")]


def _paged(args, path):
    return f"{path}?start={args.start}&limit={args.limit}"


def _release_body(args):
    """Inline credentials, or a named server from the outgoing-smtp book."""
    body = _body(args)
    if args.server:
        body["Name"] = args.server
    elif "Host" not in body:
        body.setdefault("Host", "smtp.orbit-labs.com")
        body.setdefault("Port", "587")
    if args.to:
        body["Email"] = args.to
    return body


def _dispatch(args, base):
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, path, "GET"))
    if args.events:
        return show(_request(base, f"/api/v1/events?limit={args.limit}", "GET"))
    if args.messages_v2:
        return show(_request(base, _paged(args, "/api/v2/messages"), "GET"))
    if args.message:
        return show(_request(base, f"/api/v1/messages/{_quote(args.message[0])}", "GET"))
    if args.download:
        return show(_request(base,
                             f"/api/v1/messages/{_quote(args.download[0])}/download",
                             "GET"))
    if args.part:
        message_id, index = args.part
        return show(_request(base, f"/api/v1/messages/{_quote(message_id)}"
                                   f"/mime/part/{_quote(index)}/download", "GET"))
    if args.delete:
        return show(_request(base, f"/api/v1/messages/{_quote(args.delete[0])}",
                             "DELETE"))
    if args.delete_all:
        return show(_request(base, "/api/v1/messages", "DELETE"))
    if args.search:
        kind, query = args.search
        path = (f"/api/v2/search?kind={_quote(kind)}&query={_quote(query)}"
                f"&start={args.start}&limit={args.limit}")
        return show(_request(base, path, "GET"))
    if args.release:
        return show(_request(base,
                             f"/api/v1/messages/{_quote(args.release[0])}/release",
                             "POST", _release_body(args)))
    if args.enable_jim:
        return show(_request(base, "/api/v2/jim", "POST", _body(args)))
    if args.update_jim:
        return show(_request(base, "/api/v2/jim", "PUT", _body(args)))
    if args.disable_jim:
        return show(_request(base, "/api/v2/jim", "DELETE"))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
