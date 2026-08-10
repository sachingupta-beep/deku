#!/usr/bin/env python3
"""CLI helper for the Lago API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$LAGO_API_URL (override with --url). POST/PUT bodies are read from --data (JSON
string) or --data-file.

Remember that nothing here charges anyone: you record usage with --meter, and
--usage computes what it costs. An event only counts if its timestamp falls
inside the subscription's declared period.
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
    p = argparse.ArgumentParser(description="Query the Lago API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /health")
    p.add_argument("--service", action="store_true", help="GET /api/v1/service")
    p.add_argument("--metrics", action="store_true",
                   help="GET /api/v1/billable_metrics")
    p.add_argument("--metric", metavar="CODE", nargs=1,
                   help="GET /api/v1/billable_metrics/{code}")
    p.add_argument("--create-metric", action="store_true",
                   help="POST /api/v1/billable_metrics with --data")
    p.add_argument("--plans", action="store_true", help="GET /api/v1/plans")
    p.add_argument("--plan", metavar="CODE", nargs=1,
                   help="GET /api/v1/plans/{code}")
    p.add_argument("--create-plan", action="store_true",
                   help="POST /api/v1/plans with --data")
    p.add_argument("--customers", action="store_true",
                   help="GET /api/v1/customers")
    p.add_argument("--customer", metavar="EXTERNAL_ID", nargs=1,
                   help="GET /api/v1/customers/{external_id}")
    p.add_argument("--upsert-customer", action="store_true",
                   help="POST /api/v1/customers with --data")
    p.add_argument("--usage", metavar=("CUSTOMER", "SUBSCRIPTION"), nargs=2,
                   help="GET /api/v1/customers/{id}/current_usage")
    p.add_argument("--subscriptions", action="store_true",
                   help="GET /api/v1/subscriptions")
    p.add_argument("--subscription", metavar="EXTERNAL_ID", nargs=1,
                   help="GET /api/v1/subscriptions/{external_id}")
    p.add_argument("--subscribe", action="store_true",
                   help="POST /api/v1/subscriptions with --data")
    p.add_argument("--terminate", metavar="EXTERNAL_ID", nargs=1,
                   help="DELETE /api/v1/subscriptions/{external_id}")
    p.add_argument("--events", action="store_true", help="GET /api/v1/events")
    p.add_argument("--event", metavar="TRANSACTION_ID", nargs=1,
                   help="GET /api/v1/events/{transaction_id}")
    p.add_argument("--meter", action="store_true",
                   help="POST /api/v1/events with --data")
    p.add_argument("--meter-batch", action="store_true",
                   help="POST /api/v1/events/batch with --data")
    p.add_argument("--estimate", action="store_true",
                   help="POST /api/v1/events/estimate_fees with --data")
    p.add_argument("--invoices", action="store_true", help="GET /api/v1/invoices")
    p.add_argument("--invoice", metavar="LAGO_ID", nargs=1,
                   help="GET /api/v1/invoices/{lago_id}")
    p.add_argument("--pay", metavar=("LAGO_ID", "STATUS"), nargs=2,
                   help="PUT /api/v1/invoices/{lago_id} payment_status")
    p.add_argument("--refresh", metavar="LAGO_ID", nargs=1,
                   help="POST /api/v1/invoices/{lago_id}/refresh")
    p.add_argument("--finalize", metavar="LAGO_ID", nargs=1,
                   help="POST /api/v1/invoices/{lago_id}/finalize")
    p.add_argument("--void", metavar="LAGO_ID", nargs=1,
                   help="POST /api/v1/invoices/{lago_id}/void")
    p.add_argument("--credit-notes", action="store_true",
                   help="GET /api/v1/credit_notes")
    p.add_argument("--credit-note", metavar="LAGO_ID", nargs=1,
                   help="GET /api/v1/credit_notes/{lago_id}")
    p.add_argument("--create-credit-note", action="store_true",
                   help="POST /api/v1/credit_notes with --data")
    p.add_argument("--wallets", action="store_true", help="GET /api/v1/wallets")
    p.add_argument("--wallet", metavar="LAGO_ID", nargs=1,
                   help="GET /api/v1/wallets/{lago_id}")
    p.add_argument("--create-wallet", action="store_true",
                   help="POST /api/v1/wallets with --data")
    p.add_argument("--gross-revenue", action="store_true",
                   help="GET /api/v1/analytics/gross_revenue")
    p.add_argument("--mrr", action="store_true",
                   help="GET /api/v1/analytics/mrr")
    p.add_argument("--customer-filter", metavar="EXTERNAL_ID",
                   help="external_customer_id filter for the list endpoints")
    p.add_argument("--subscription-filter", metavar="EXTERNAL_ID",
                   help="external_subscription_id filter for --events")
    p.add_argument("--code", metavar="CODE", help="Metric code filter")
    p.add_argument("--status", metavar="STATUS", help="Status filter")
    p.add_argument("--payment-status", metavar="STATUS",
                   help="payment_status filter for --invoices")
    p.add_argument("--currency", metavar="CODE", help="Currency filter")
    p.add_argument("--page", type=int, default=1, help="1-based page number")
    p.add_argument("--per-page", type=int, default=20, help="Page size")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--url", default=os.environ.get("LAGO_API_URL",
                                                   "http://localhost:8127"),
                   help="API base URL (default: $LAGO_API_URL or http://localhost:8127)")
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


_FLAT_GETS = [("health", "/health"), ("service", "/api/v1/service"),
              ("credit_notes", "/api/v1/credit_notes"),
              ("wallets", "/api/v1/wallets")]

_ONE_ARG_GETS = [("metric", "/api/v1/billable_metrics/{}"),
                 ("plan", "/api/v1/plans/{}"),
                 ("customer", "/api/v1/customers/{}"),
                 ("subscription", "/api/v1/subscriptions/{}"),
                 ("event", "/api/v1/events/{}"),
                 ("invoice", "/api/v1/invoices/{}"),
                 ("credit_note", "/api/v1/credit_notes/{}"),
                 ("wallet", "/api/v1/wallets/{}")]

_POSTS = [("create_metric", "/api/v1/billable_metrics"),
          ("create_plan", "/api/v1/plans"),
          ("upsert_customer", "/api/v1/customers"),
          ("subscribe", "/api/v1/subscriptions"),
          ("meter", "/api/v1/events"),
          ("meter_batch", "/api/v1/events/batch"),
          ("estimate", "/api/v1/events/estimate_fees"),
          ("create_credit_note", "/api/v1/credit_notes"),
          ("create_wallet", "/api/v1/wallets")]

_INVOICE_ACTIONS = [("refresh", "refresh"), ("finalize", "finalize"),
                    ("void", "void")]


def _query(args, *fields):
    parts = [f"page={args.page}", f"per_page={args.per_page}"]
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
    for flag, path in _POSTS:
        if getattr(args, flag):
            return show(_request(base, path, "POST", _body(args)))
    if args.metrics:
        return show(_request(base, "/api/v1/billable_metrics" + _query(args),
                             "GET"))
    if args.plans:
        return show(_request(base, "/api/v1/plans" + _query(args), "GET"))
    if args.customers:
        return show(_request(base, "/api/v1/customers" + _query(args), "GET"))
    if args.usage:
        customer, subscription = args.usage
        return show(_request(base, f"/api/v1/customers/{_quote(customer)}"
                                   f"/current_usage?external_subscription_id="
                                   f"{_quote(subscription)}", "GET"))
    if args.subscriptions:
        return show(_request(base, "/api/v1/subscriptions"
                                   + _query(args,
                                            ("external_customer_id",
                                             args.customer_filter),
                                            ("status", args.status)), "GET"))
    if args.terminate:
        return show(_request(base, f"/api/v1/subscriptions/"
                                   f"{_quote(args.terminate[0])}", "DELETE"))
    if args.events:
        return show(_request(base, "/api/v1/events"
                                   + _query(args,
                                            ("external_subscription_id",
                                             args.subscription_filter),
                                            ("code", args.code)), "GET"))
    if args.invoices:
        return show(_request(base, "/api/v1/invoices"
                                   + _query(args,
                                            ("external_customer_id",
                                             args.customer_filter),
                                            ("status", args.status),
                                            ("payment_status",
                                             args.payment_status)), "GET"))
    if args.pay:
        lago_id, status = args.pay
        return show(_request(base, f"/api/v1/invoices/{_quote(lago_id)}", "PUT",
                             {"invoice": {"payment_status": status}}))
    for flag, action in _INVOICE_ACTIONS:
        value = getattr(args, flag)
        if value:
            return show(_request(base, f"/api/v1/invoices/{_quote(value[0])}"
                                       f"/{action}", "POST", {}))
    if args.gross_revenue:
        suffix = f"?currency={_quote(args.currency)}" if args.currency else ""
        return show(_request(base, f"/api/v1/analytics/gross_revenue{suffix}",
                             "GET"))
    if args.mrr:
        suffix = f"?currency={_quote(args.currency)}" if args.currency else ""
        return show(_request(base, f"/api/v1/analytics/mrr{suffix}", "GET"))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
