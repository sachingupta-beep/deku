#!/usr/bin/env python3
"""CLI helper for the Mailpit API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$MAILPIT_API_URL (override with --url). POST/PUT bodies are read from --data
(JSON string) or --data-file.

Two things to remember about Mailpit: search takes a query language rather than
a kind parameter, and reading a message marks it read.
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
    p = argparse.ArgumentParser(description="Query the Mailpit API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /health")
    p.add_argument("--livez", action="store_true", help="GET /livez")
    p.add_argument("--readyz", action="store_true", help="GET /readyz")
    p.add_argument("--info", action="store_true", help="GET /api/v1/info")
    p.add_argument("--webui", action="store_true", help="GET /api/v1/webui")
    p.add_argument("--messages", action="store_true",
                   help="GET /api/v1/messages")
    p.add_argument("--search", metavar="QUERY", nargs=1,
                   help='GET /api/v1/search, e.g. "from:billing is:unread"')
    p.add_argument("--delete-search", metavar="QUERY", nargs=1,
                   help="DELETE /api/v1/search")
    p.add_argument("--message", metavar="ID", nargs=1,
                   help="GET /api/v1/message/{id} (marks it read)")
    p.add_argument("--raw", metavar="ID", nargs=1,
                   help="GET /api/v1/message/{id}/raw")
    p.add_argument("--headers", metavar="ID", nargs=1,
                   help="GET /api/v1/message/{id}/headers")
    p.add_argument("--part", metavar=("ID", "PART"), nargs=2,
                   help="GET /api/v1/message/{id}/part/{partId}")
    p.add_argument("--thumbnail", metavar=("ID", "PART"), nargs=2,
                   help="GET /api/v1/message/{id}/part/{partId}/thumbnail")
    p.add_argument("--html-check", metavar="ID", nargs=1,
                   help="GET /api/v1/message/{id}/html-check")
    p.add_argument("--link-check", metavar="ID", nargs=1,
                   help="GET /api/v1/message/{id}/link-check")
    p.add_argument("--sa-check", metavar="ID", nargs=1,
                   help="GET /api/v1/message/{id}/sa-check")
    p.add_argument("--release", metavar="ID", nargs=1,
                   help="POST /api/v1/message/{id}/release, with --to")
    p.add_argument("--send", action="store_true", help="POST /api/v1/send")
    p.add_argument("--set-read", metavar="READ", nargs=1,
                   choices=["true", "false"],
                   help="PUT /api/v1/messages, with --ids (empty means all)")
    p.add_argument("--delete", action="store_true",
                   help="DELETE /api/v1/messages, with --ids (empty means all)")
    p.add_argument("--tags", action="store_true", help="GET /api/v1/tags")
    p.add_argument("--set-tags", metavar="TAG", nargs="+",
                   help="PUT /api/v1/tags, with --ids")
    p.add_argument("--rename-tag", metavar=("TAG", "NEW"), nargs=2,
                   help="PUT /api/v1/tags/{tag}")
    p.add_argument("--delete-tag", metavar="TAG", nargs=1,
                   help="DELETE /api/v1/tags/{tag}")
    p.add_argument("--chaos", action="store_true", help="GET /api/v1/chaos")
    p.add_argument("--set-chaos", metavar=("TRIGGER", "CODE", "PERCENT"),
                   nargs=3,
                   help="PUT /api/v1/chaos, e.g. Recipient 451 50")
    p.add_argument("--ids", metavar="ID", nargs="*", default=[],
                   help="Message ids for the bulk operations")
    p.add_argument("--to", metavar="EMAIL", nargs="*", default=[],
                   help="Recipients for --release")
    p.add_argument("--follow", action="store_true",
                   help="Resolve redirects in --link-check")
    p.add_argument("--start", type=int, default=0,
                   help="Offset for the paginated reads (default: 0)")
    p.add_argument("--limit", type=int, default=50,
                   help="Page size for the paginated reads (default: 50)")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--url", default=os.environ.get("MAILPIT_API_URL",
                                                   "http://localhost:8122"),
                   help="API base URL (default: $MAILPIT_API_URL or http://localhost:8122)")
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


_FLAT_GETS = [("health", "/health"), ("livez", "/livez"), ("readyz", "/readyz"),
              ("info", "/api/v1/info"), ("webui", "/api/v1/webui"),
              ("tags", "/api/v1/tags"), ("chaos", "/api/v1/chaos")]

_MESSAGE_GETS = [("raw", "/raw"), ("headers", "/headers"),
                 ("html_check", "/html-check"), ("sa_check", "/sa-check")]


def _paged(path):
    return path


def _dispatch(args, base):
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, path, "GET"))
    if args.messages:
        return show(_request(base, f"/api/v1/messages?start={args.start}"
                                   f"&limit={args.limit}", "GET"))
    if args.search:
        return show(_request(base, f"/api/v1/search?query={_quote(args.search[0])}"
                                   f"&start={args.start}&limit={args.limit}",
                             "GET"))
    if args.delete_search:
        return show(_request(base, "/api/v1/search?query="
                                   f"{_quote(args.delete_search[0])}", "DELETE"))
    if args.message:
        return show(_request(base, f"/api/v1/message/{_quote(args.message[0])}",
                             "GET"))
    for flag, suffix in _MESSAGE_GETS:
        value = getattr(args, flag)
        if value:
            return show(_request(base, f"/api/v1/message/{_quote(value[0])}"
                                       f"{suffix}", "GET"))
    if args.link_check:
        follow = "?follow=true" if args.follow else ""
        return show(_request(base, f"/api/v1/message/{_quote(args.link_check[0])}"
                                   f"/link-check{follow}", "GET"))
    if args.part:
        message_id, part_id = args.part
        return show(_request(base, f"/api/v1/message/{_quote(message_id)}"
                                   f"/part/{_quote(part_id)}", "GET"))
    if args.thumbnail:
        message_id, part_id = args.thumbnail
        return show(_request(base, f"/api/v1/message/{_quote(message_id)}"
                                   f"/part/{_quote(part_id)}/thumbnail", "GET"))
    if args.release:
        body = {**_body(args)}
        if args.to:
            body["To"] = args.to
        return show(_request(base, f"/api/v1/message/{_quote(args.release[0])}"
                                   f"/release", "POST", body))
    if args.send:
        return show(_request(base, "/api/v1/send", "POST", _body(args)))
    if args.set_read:
        return show(_request(base, "/api/v1/messages", "PUT",
                             {"IDs": args.ids,
                              "Read": args.set_read[0] == "true"}))
    if args.delete:
        return show(_request(base, "/api/v1/messages", "DELETE",
                             {"IDs": args.ids}))
    if args.set_tags:
        return show(_request(base, "/api/v1/tags", "PUT",
                             {"IDs": args.ids, "Tags": args.set_tags}))
    if args.rename_tag:
        tag, new_name = args.rename_tag
        return show(_request(base, f"/api/v1/tags/{_quote(tag)}", "PUT",
                             {"Name": new_name}))
    if args.delete_tag:
        return show(_request(base, f"/api/v1/tags/{_quote(args.delete_tag[0])}",
                             "DELETE"))
    if args.set_chaos:
        trigger, code, percent = args.set_chaos
        return show(_request(base, "/api/v1/chaos", "PUT",
                             {trigger: {"ErrorCode": int(code),
                                        "Probability": int(percent)}}))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
