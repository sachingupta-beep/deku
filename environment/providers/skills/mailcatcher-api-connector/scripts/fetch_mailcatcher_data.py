#!/usr/bin/env python3
"""CLI helper for the MailCatcher API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$MAILCATCHER_API_URL (override with --url). POST bodies are read from --data
(JSON string) or --data-file.

Remember that MailCatcher puts the format in the file extension, and that each
message advertises which extensions will work in its `formats` array -- so read
`--message ID` before reaching for `--html` or `--plain`.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _quote(value):
    """Percent-encode a path segment. A Content-ID contains an '@'."""
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
    p = argparse.ArgumentParser(description="Query the MailCatcher API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /health")
    p.add_argument("--info", action="store_true", help="GET /info")
    p.add_argument("--messages", action="store_true", help="GET /messages")
    p.add_argument("--message", metavar="ID", nargs=1,
                   help="GET /messages/{id}.json")
    p.add_argument("--html", metavar="ID", nargs=1,
                   help="GET /messages/{id}.html (cid: refs rewritten)")
    p.add_argument("--plain", metavar="ID", nargs=1,
                   help="GET /messages/{id}.plain")
    p.add_argument("--source", metavar="ID", nargs=1,
                   help="GET /messages/{id}.source")
    p.add_argument("--eml", metavar="ID", nargs=1,
                   help="GET /messages/{id}.eml")
    p.add_argument("--format", metavar=("ID", "EXT"), nargs=2,
                   help="GET /messages/{id}.{ext} for any extension")
    p.add_argument("--part", metavar=("ID", "CID"), nargs=2,
                   help="GET /messages/{id}/parts/{cid}")
    p.add_argument("--deliver", action="store_true",
                   help="POST /messages with --data")
    p.add_argument("--delete", metavar="ID", nargs=1,
                   help="DELETE /messages/{id} (204, no body)")
    p.add_argument("--clear", action="store_true",
                   help="DELETE /messages (ids restart at 1 afterwards)")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--url", default=os.environ.get("MAILCATCHER_API_URL",
                                                   "http://localhost:8125"),
                   help="API base URL (default: $MAILCATCHER_API_URL or http://localhost:8125)")
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


_FLAT_GETS = [("health", "/health"), ("info", "/info"),
              ("messages", "/messages")]

# The format really is the file extension, so each of these is one suffix.
_EXTENSIONS = [("message", "json"), ("html", "html"), ("plain", "plain"),
               ("source", "source"), ("eml", "eml")]


def _dispatch(args, base):
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, path, "GET"))
    for flag, extension in _EXTENSIONS:
        value = getattr(args, flag)
        if value:
            return show(_request(base, f"/messages/{_quote(value[0])}"
                                       f".{extension}", "GET"))
    if args.format:
        message_id, extension = args.format
        return show(_request(base, f"/messages/{_quote(message_id)}"
                                   f".{_quote(extension)}", "GET"))
    if args.part:
        message_id, cid = args.part
        return show(_request(base, f"/messages/{_quote(message_id)}"
                                   f"/parts/{_quote(cid)}", "GET"))
    if args.deliver:
        return show(_request(base, "/messages", "POST", _body(args)))
    if args.delete:
        return show(_request(base, f"/messages/{_quote(args.delete[0])}",
                             "DELETE"))
    if args.clear:
        return show(_request(base, "/messages", "DELETE"))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
