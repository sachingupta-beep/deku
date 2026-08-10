#!/usr/bin/env python3
"""CLI helper for the Orbit Payments API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$INHOUSE_PAYMENTS_API_URL (override with --url). POST bodies are read from
--data (JSON string) or --data-file.

Every write needs an idempotency key. Pass one with --key; without it the
service answers 400, which is the point. Amounts are integers in the currency's
minor unit.
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


def _request(base, path, method, body=None, key=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if key:
        headers["Idempotency-Key"] = key
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
    p = argparse.ArgumentParser(
        description="Query the Orbit Payments API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /health")
    p.add_argument("--service", action="store_true", help="GET /v1/service")
    p.add_argument("--customers", action="store_true", help="GET /v1/customers")
    p.add_argument("--customer", metavar="ID", nargs=1,
                   help="GET /v1/customers/{id}")
    p.add_argument("--create-customer", action="store_true",
                   help="POST /v1/customers with --data and --key")
    p.add_argument("--payment-methods", action="store_true",
                   help="GET /v1/payment_methods (honours --customer-filter)")
    p.add_argument("--payment-method", metavar="ID", nargs=1,
                   help="GET /v1/payment_methods/{id}")
    p.add_argument("--payments", action="store_true", help="GET /v1/payments")
    p.add_argument("--payment", metavar="ID", nargs=1,
                   help="GET /v1/payments/{id}")
    p.add_argument("--charge", action="store_true",
                   help="POST /v1/payments with --data and --key")
    p.add_argument("--confirm", metavar="ID", nargs=1,
                   help="POST /v1/payments/{id}/confirm")
    p.add_argument("--capture", metavar="ID", nargs=1,
                   help="POST /v1/payments/{id}/capture (honours --amount)")
    p.add_argument("--cancel", metavar="ID", nargs=1,
                   help="POST /v1/payments/{id}/cancel")
    p.add_argument("--refunds", action="store_true", help="GET /v1/refunds")
    p.add_argument("--refund", metavar="ID", nargs=1,
                   help="GET /v1/refunds/{id}")
    p.add_argument("--create-refund", metavar="PAYMENT", nargs=1,
                   help="POST /v1/refunds (honours --amount and --reason)")
    p.add_argument("--disputes", action="store_true", help="GET /v1/disputes")
    p.add_argument("--dispute", metavar="ID", nargs=1,
                   help="GET /v1/disputes/{id}")
    p.add_argument("--evidence", metavar=("ID", "TEXT"), nargs=2,
                   help="POST /v1/disputes/{id}/evidence")
    p.add_argument("--close-dispute", metavar=("ID", "RESOLUTION"), nargs=2,
                   help="POST /v1/disputes/{id}/close, won or lost")
    p.add_argument("--ledger", action="store_true",
                   help="GET /v1/ledger/entries (honours --source, --account)")
    p.add_argument("--trial-balance", action="store_true",
                   help="GET /v1/ledger/trial_balance")
    p.add_argument("--balance", action="store_true", help="GET /v1/balance")
    p.add_argument("--payouts", action="store_true", help="GET /v1/payouts")
    p.add_argument("--payout", metavar="ID", nargs=1,
                   help="GET /v1/payouts/{id}")
    p.add_argument("--create-payout", action="store_true",
                   help="POST /v1/payouts (honours --amount and --currency)")
    p.add_argument("--events", action="store_true", help="GET /v1/events")
    p.add_argument("--key", metavar="IDEMPOTENCY_KEY",
                   help="Idempotency-Key header; required by every write")
    p.add_argument("--amount", type=int, metavar="MINOR",
                   help="amount_minor for capture, refund and payout")
    p.add_argument("--currency", metavar="CODE", help="Currency filter or field")
    p.add_argument("--reason", metavar="REASON", help="Refund reason")
    p.add_argument("--status", metavar="STATUS", help="Status filter")
    p.add_argument("--customer-filter", metavar="ID",
                   help="customer filter for the list endpoints")
    p.add_argument("--source", metavar="ID", help="Ledger source filter")
    p.add_argument("--account", metavar="NAME", help="Ledger account filter")
    p.add_argument("--object", metavar="ID", help="Event object filter")
    p.add_argument("--type", metavar="TYPE", help="Event type filter")
    p.add_argument("--limit", type=int, default=100, help="Page size")
    p.add_argument("--offset", type=int, default=0, help="Page offset")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--url",
                   default=os.environ.get("INHOUSE_PAYMENTS_API_URL",
                                          "http://localhost:8126"),
                   help="API base URL (default: $INHOUSE_PAYMENTS_API_URL or http://localhost:8126)")
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


_FLAT_GETS = [("health", "/health"), ("service", "/v1/service"),
              ("trial_balance", "/v1/ledger/trial_balance"),
              ("balance", "/v1/balance")]

_ONE_ARG_GETS = [("customer", "/v1/customers/{}"),
                 ("payment_method", "/v1/payment_methods/{}"),
                 ("payment", "/v1/payments/{}"),
                 ("refund", "/v1/refunds/{}"),
                 ("dispute", "/v1/disputes/{}"),
                 ("payout", "/v1/payouts/{}")]


def _query(args, *fields):
    parts = [f"limit={args.limit}", f"offset={args.offset}"]
    for name, value in fields:
        if value:
            parts.append(f"{name}={_quote(value)}")
    return "?" + "&".join(parts)


def _dispatch(args, base):
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, path, "GET"))
    for flag, template in _ONE_ARG_GETS:
        value = getattr(args, flag)
        if value:
            return show(_request(base, template.format(_quote(value[0])), "GET"))
    if args.customers:
        return show(_request(base, "/v1/customers"
                                   + _query(args, ("status", args.status)),
                             "GET"))
    if args.create_customer:
        return show(_request(base, "/v1/customers", "POST", _body(args),
                             args.key))
    if args.payment_methods:
        return show(_request(base, "/v1/payment_methods"
                                   + _query(args,
                                            ("customer", args.customer_filter)),
                             "GET"))
    if args.payments:
        return show(_request(base, "/v1/payments"
                                   + _query(args,
                                            ("customer", args.customer_filter),
                                            ("status", args.status),
                                            ("currency", args.currency)),
                             "GET"))
    if args.charge:
        return show(_request(base, "/v1/payments", "POST", _body(args),
                             args.key))
    if args.confirm:
        return show(_request(base, f"/v1/payments/{_quote(args.confirm[0])}"
                                   f"/confirm", "POST", _body(args), args.key))
    if args.capture:
        body = _body(args)
        if args.amount is not None:
            body["amount_minor"] = args.amount
        return show(_request(base, f"/v1/payments/{_quote(args.capture[0])}"
                                   f"/capture", "POST", body, args.key))
    if args.cancel:
        return show(_request(base, f"/v1/payments/{_quote(args.cancel[0])}"
                                   f"/cancel", "POST", _body(args), args.key))
    if args.refunds:
        return show(_request(base, "/v1/refunds"
                                   + _query(args, ("payment", args.source)),
                             "GET"))
    if args.create_refund:
        body = {**_body(args), "payment": args.create_refund[0]}
        if args.amount is not None:
            body["amount_minor"] = args.amount
        if args.reason:
            body["reason"] = args.reason
        return show(_request(base, "/v1/refunds", "POST", body, args.key))
    if args.disputes:
        return show(_request(base, "/v1/disputes"
                                   + _query(args, ("status", args.status)),
                             "GET"))
    if args.evidence:
        dispute_id, text = args.evidence
        return show(_request(base, f"/v1/disputes/{_quote(dispute_id)}"
                                   f"/evidence", "POST", {"evidence": text},
                             args.key))
    if args.close_dispute:
        dispute_id, resolution = args.close_dispute
        return show(_request(base, f"/v1/disputes/{_quote(dispute_id)}/close",
                             "POST", {"resolution": resolution}, args.key))
    if args.ledger:
        return show(_request(base, "/v1/ledger/entries"
                                   + _query(args, ("source", args.source),
                                            ("account", args.account),
                                            ("currency", args.currency)),
                             "GET"))
    if args.payouts:
        return show(_request(base, "/v1/payouts"
                                   + _query(args, ("currency", args.currency)),
                             "GET"))
    if args.create_payout:
        body = _body(args)
        if args.amount is not None:
            body["amount_minor"] = args.amount
        if args.currency:
            body["currency"] = args.currency
        return show(_request(base, "/v1/payouts", "POST", body, args.key))
    if args.events:
        return show(_request(base, "/v1/events"
                                   + _query(args, ("object", args.object),
                                            ("type", args.type)), "GET"))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
