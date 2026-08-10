#!/usr/bin/env python3
"""CLI helper for the smtp4dev API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$SMTP4DEV_API_URL (override with --url). POST bodies are read from --data (JSON
string) or --data-file.

Two things to remember about smtp4dev: lists are paged (`--page` is 1-based, not
an offset), and sessions are a separate store from messages -- deleting every
message leaves every session in place.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _quote(value):
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
    p = argparse.ArgumentParser(description="Query the smtp4dev API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /health")
    p.add_argument("--version", action="store_true", help="GET /api/Version")
    p.add_argument("--mailboxes", action="store_true", help="GET /api/Mailboxes")
    p.add_argument("--server", action="store_true", help="GET /api/Server")
    p.add_argument("--set-server", action="store_true",
                   help="POST /api/Server with --data (the Settings dialog)")
    p.add_argument("--messages", action="store_true", help="GET /api/Messages")
    p.add_argument("--message", metavar="ID", nargs=1,
                   help="GET /api/Messages/{id}")
    p.add_argument("--source", metavar="ID", nargs=1,
                   help="GET /api/Messages/{id}/source")
    p.add_argument("--html", metavar="ID", nargs=1,
                   help="GET /api/Messages/{id}/html")
    p.add_argument("--plaintext", metavar="ID", nargs=1,
                   help="GET /api/Messages/{id}/plaintext")
    p.add_argument("--part", metavar=("ID", "PART"), nargs=2,
                   help="GET /api/Messages/{id}/part/{partId}/content")
    p.add_argument("--part-source", metavar=("ID", "PART"), nargs=2,
                   help="GET /api/Messages/{id}/part/{partId}/source")
    p.add_argument("--mark-read", metavar="ID", nargs=1,
                   help="POST /api/Messages/{id}/markRead")
    p.add_argument("--mark-all-read", action="store_true",
                   help="POST /api/Messages/markAllRead (honours --mailbox)")
    p.add_argument("--relay", metavar="ID", nargs=1,
                   help="POST /api/Messages/{id}/relay (honours --to)")
    p.add_argument("--deliver", action="store_true",
                   help="POST /api/Messages with --data")
    p.add_argument("--delete", metavar="ID", nargs=1,
                   help="DELETE /api/Messages/{id}")
    p.add_argument("--delete-all", action="store_true",
                   help="DELETE /api/Messages/* (honours --mailbox)")
    p.add_argument("--sessions", action="store_true", help="GET /api/Sessions")
    p.add_argument("--session", metavar="ID", nargs=1,
                   help="GET /api/Sessions/{id}")
    p.add_argument("--session-log", metavar="ID", nargs=1,
                   help="GET /api/Sessions/{id}/log")
    p.add_argument("--delete-session", metavar="ID", nargs=1,
                   help="DELETE /api/Sessions/{id}")
    p.add_argument("--delete-all-sessions", action="store_true",
                   help="DELETE /api/Sessions/*")
    p.add_argument("--mailbox", metavar="NAME",
                   help="mailboxName filter for the message routes")
    p.add_argument("--search", metavar="TERMS", help="searchTerms filter")
    p.add_argument("--sort", metavar="COLUMN", help="sortColumn")
    p.add_argument("--ascending", action="store_true",
                   help="sortIsDescending=false (the default is descending)")
    p.add_argument("--page", type=int, default=1,
                   help="1-based page number (default: 1)")
    p.add_argument("--page-size", type=int, default=25,
                   help="Rows per page (default: 25)")
    p.add_argument("--to", metavar="EMAIL", nargs="*", default=[],
                   help="overrideRecipientAddresses for --relay")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--url", default=os.environ.get("SMTP4DEV_API_URL",
                                                   "http://localhost:8124"),
                   help="API base URL (default: $SMTP4DEV_API_URL or http://localhost:8124)")
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


_FLAT_GETS = [("health", "/health"), ("version", "/api/Version"),
              ("mailboxes", "/api/Mailboxes"), ("server", "/api/Server")]

_MESSAGE_GETS = [("source", "/source"), ("html", "/html"),
                 ("plaintext", "/plaintext")]


def _paging(args):
    query = [f"page={args.page}", f"pageSize={args.page_size}"]
    if args.sort:
        query.append(f"sortColumn={_quote(args.sort)}")
    query.append(f"sortIsDescending={'false' if args.ascending else 'true'}")
    if args.mailbox:
        query.append(f"mailboxName={_quote(args.mailbox)}")
    if args.search:
        query.append(f"searchTerms={_quote(args.search)}")
    return "&".join(query)


def _dispatch(args, base):
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, path, "GET"))
    if args.set_server:
        return show(_request(base, "/api/Server", "POST", _body(args)))
    if args.messages:
        return show(_request(base, f"/api/Messages?{_paging(args)}", "GET"))
    if args.message:
        return show(_request(base, f"/api/Messages/{_quote(args.message[0])}",
                             "GET"))
    for flag, suffix in _MESSAGE_GETS:
        value = getattr(args, flag)
        if value:
            return show(_request(base, f"/api/Messages/{_quote(value[0])}"
                                       f"{suffix}", "GET"))
    if args.part:
        message_id, part_id = args.part
        return show(_request(base, f"/api/Messages/{_quote(message_id)}"
                                   f"/part/{_quote(part_id)}/content", "GET"))
    if args.part_source:
        message_id, part_id = args.part_source
        return show(_request(base, f"/api/Messages/{_quote(message_id)}"
                                   f"/part/{_quote(part_id)}/source", "GET"))
    if args.mark_read:
        return show(_request(base, f"/api/Messages/{_quote(args.mark_read[0])}"
                                   f"/markRead", "POST", {}))
    if args.mark_all_read:
        suffix = f"?mailboxName={_quote(args.mailbox)}" if args.mailbox else ""
        return show(_request(base, f"/api/Messages/markAllRead{suffix}",
                             "POST", {}))
    if args.relay:
        body = {**_body(args)}
        if args.to:
            body["overrideRecipientAddresses"] = args.to
        return show(_request(base, f"/api/Messages/{_quote(args.relay[0])}"
                                   f"/relay", "POST", body))
    if args.deliver:
        return show(_request(base, "/api/Messages", "POST", _body(args)))
    if args.delete:
        return show(_request(base, f"/api/Messages/{_quote(args.delete[0])}",
                             "DELETE"))
    if args.delete_all:
        suffix = f"?mailboxName={_quote(args.mailbox)}" if args.mailbox else ""
        return show(_request(base, f"/api/Messages/*{suffix}", "DELETE"))
    if args.sessions:
        return show(_request(base, f"/api/Sessions?{_paging(args)}", "GET"))
    if args.session:
        return show(_request(base, f"/api/Sessions/{_quote(args.session[0])}",
                             "GET"))
    if args.session_log:
        return show(_request(base, f"/api/Sessions/"
                                   f"{_quote(args.session_log[0])}/log", "GET"))
    if args.delete_session:
        return show(_request(base, f"/api/Sessions/"
                                   f"{_quote(args.delete_session[0])}",
                             "DELETE"))
    if args.delete_all_sessions:
        return show(_request(base, "/api/Sessions/*", "DELETE"))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
