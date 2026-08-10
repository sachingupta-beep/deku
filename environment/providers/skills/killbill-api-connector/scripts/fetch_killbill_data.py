#!/usr/bin/env python3
"""CLI helper for the Kill Bill API (Mock) mock API.

Generated read/write helper: one flag per endpoint. Base URL comes from
$KILLBILL_API_URL (override with --url). POST/PUT bodies are read from --data
(JSON string) or --data-file.

Two things to remember about Kill Bill: the tenant is a header pair, so
--tenant picks which data exists at all; and creates return 201 with a Location
header and no body, which this script prints for you.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TENANTS = {
    "orbit-labs": "orbit-labs-secret-9f14c73e",
    "acme-reseller": "acme-reseller-secret-5b07d21f",
}


def _quote(value):
    return urllib.parse.quote(str(value), safe="")


def _request(base, path, method, body=None, tenant="orbit-labs",
             created_by=None, secret=None):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if tenant:
        headers["X-Killbill-ApiKey"] = tenant
        headers["X-Killbill-ApiSecret"] = secret or TENANTS.get(tenant, "")
    if created_by:
        headers["X-Killbill-CreatedBy"] = created_by
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode()
        location = resp.headers.get("Location")
        if not raw:
            # Kill Bill answers a create with 201 + Location and no body, and a
            # 204 with nothing at all; surface both rather than printing "".
            return {"status": resp.status,
                    **({"location": location} if location else {})}
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
        description="Query the Kill Bill API (Mock) mock API")
    p.add_argument("--health", action="store_true", help="GET /health")
    p.add_argument("--nodes", action="store_true",
                   help="GET /1.0/kb/nodesInfo")
    p.add_argument("--catalog", action="store_true", help="GET /1.0/kb/catalog")
    p.add_argument("--base-plans", action="store_true",
                   help="GET /1.0/kb/catalog/availableBasePlans")
    p.add_argument("--accounts", action="store_true",
                   help="GET /1.0/kb/accounts (honours --external-key)")
    p.add_argument("--account", metavar="ID", nargs=1,
                   help="GET /1.0/kb/accounts/{id}")
    p.add_argument("--create-account", action="store_true",
                   help="POST /1.0/kb/accounts with --data")
    p.add_argument("--update-account", metavar="ID", nargs=1,
                   help="PUT /1.0/kb/accounts/{id} with --data")
    p.add_argument("--timeline", metavar="ID", nargs=1,
                   help="GET /1.0/kb/accounts/{id}/timeline")
    p.add_argument("--overdue", metavar="ID", nargs=1,
                   help="GET /1.0/kb/accounts/{id}/overdueState")
    p.add_argument("--bundles", metavar="ID", nargs=1,
                   help="GET /1.0/kb/accounts/{id}/bundles")
    p.add_argument("--bundle", metavar="ID", nargs=1,
                   help="GET /1.0/kb/bundles/{id}")
    p.add_argument("--invoices", metavar="ID", nargs=1,
                   help="GET /1.0/kb/accounts/{id}/invoices")
    p.add_argument("--invoice", metavar="ID", nargs=1,
                   help="GET /1.0/kb/invoices/{id}")
    p.add_argument("--invoice-html", metavar="ID", nargs=1,
                   help="GET /1.0/kb/invoices/{id}/html")
    p.add_argument("--commit-invoice", metavar="ID", nargs=1,
                   help="PUT /1.0/kb/invoices/{id}/commitInvoice")
    p.add_argument("--charge", metavar="ACCOUNT_ID", nargs=1,
                   help="POST /1.0/kb/invoices/charges/{accountId} with --data")
    p.add_argument("--subscription", metavar="ID", nargs=1,
                   help="GET /1.0/kb/subscriptions/{id}")
    p.add_argument("--subscribe", action="store_true",
                   help="POST /1.0/kb/subscriptions with --data")
    p.add_argument("--change-plan", metavar=("ID", "PLAN"), nargs=2,
                   help="PUT /1.0/kb/subscriptions/{id}")
    p.add_argument("--cancel", metavar="ID", nargs=1,
                   help="DELETE /1.0/kb/subscriptions/{id}; see --entitlement-policy")
    p.add_argument("--payments", action="store_true",
                   help="GET /1.0/kb/payments")
    p.add_argument("--account-payments", metavar="ID", nargs=1,
                   help="GET /1.0/kb/accounts/{id}/payments")
    p.add_argument("--payment", metavar="ID", nargs=1,
                   help="GET /1.0/kb/payments/{id}")
    p.add_argument("--pay", metavar="ACCOUNT_ID", nargs=1,
                   help="POST /1.0/kb/accounts/{id}/payments (honours --amount)")
    p.add_argument("--refund", metavar="PAYMENT_ID", nargs=1,
                   help="POST /1.0/kb/payments/{id}/refunds (honours --amount)")
    p.add_argument("--payment-methods", metavar="ACCOUNT_ID", nargs=1,
                   help="GET /1.0/kb/accounts/{id}/paymentMethods")
    p.add_argument("--payment-method", metavar="ID", nargs=1,
                   help="GET /1.0/kb/paymentMethods/{id}")
    p.add_argument("--add-payment-method", metavar="ACCOUNT_ID", nargs=1,
                   help="POST /1.0/kb/accounts/{id}/paymentMethods with --data")
    p.add_argument("--tags", metavar="ACCOUNT_ID", nargs=1,
                   help="GET /1.0/kb/accounts/{id}/tags")
    p.add_argument("--add-tags", metavar="ACCOUNT_ID", nargs=1,
                   help="POST /1.0/kb/accounts/{id}/tags (honours --tag)")
    p.add_argument("--remove-tags", metavar="ACCOUNT_ID", nargs=1,
                   help="DELETE /1.0/kb/accounts/{id}/tags (honours --tag)")
    p.add_argument("--tenant", default="orbit-labs", choices=list(TENANTS),
                   help="Which tenant's data to speak to (default: orbit-labs)")
    p.add_argument("--secret", metavar="SECRET",
                   help="Override the API secret, to exercise a 401")
    p.add_argument("--created-by", default="cli",
                   help="X-Killbill-CreatedBy for writes (default: cli)")
    p.add_argument("--external-key", metavar="KEY",
                   help="externalKey filter for --accounts")
    p.add_argument("--amount", type=int, metavar="MINOR",
                   help="amount for --pay and --refund")
    p.add_argument("--tag", metavar="NAME", nargs="*", default=[],
                   help="Tag definition names for --add-tags / --remove-tags")
    p.add_argument("--entitlement-policy", metavar="POLICY",
                   help="IMMEDIATE or END_OF_TERM for --cancel")
    p.add_argument("--billing-policy", metavar="POLICY",
                   help="IMMEDIATE, END_OF_TERM or START_OF_TERM for --cancel")
    p.add_argument("--default", action="store_true",
                   help="Make --add-payment-method the account default")
    p.add_argument("--data", metavar="JSON", help="Request body as a JSON string")
    p.add_argument("--data-file", metavar="PATH", help="Request body from a JSON file")
    p.add_argument("--url", default=os.environ.get("KILLBILL_API_URL",
                                                   "http://localhost:8128"),
                   help="API base URL (default: $KILLBILL_API_URL or http://localhost:8128)")
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


_FLAT_GETS = [("nodes", "/1.0/kb/nodesInfo"), ("catalog", "/1.0/kb/catalog"),
              ("base_plans", "/1.0/kb/catalog/availableBasePlans"),
              ("payments", "/1.0/kb/payments")]

_ONE_ARG_GETS = [("account", "/1.0/kb/accounts/{}"),
                 ("timeline", "/1.0/kb/accounts/{}/timeline"),
                 ("overdue", "/1.0/kb/accounts/{}/overdueState"),
                 ("bundles", "/1.0/kb/accounts/{}/bundles"),
                 ("bundle", "/1.0/kb/bundles/{}"),
                 ("invoices", "/1.0/kb/accounts/{}/invoices"),
                 ("invoice", "/1.0/kb/invoices/{}"),
                 ("invoice_html", "/1.0/kb/invoices/{}/html"),
                 ("subscription", "/1.0/kb/subscriptions/{}"),
                 ("account_payments", "/1.0/kb/accounts/{}/payments"),
                 ("payment", "/1.0/kb/payments/{}"),
                 ("payment_methods", "/1.0/kb/accounts/{}/paymentMethods"),
                 ("payment_method", "/1.0/kb/paymentMethods/{}"),
                 ("tags", "/1.0/kb/accounts/{}/tags")]


def _dispatch(args, base):
    read = {"tenant": args.tenant, "secret": args.secret}
    write = {**read, "created_by": args.created_by}
    if args.health:
        return show(_request(base, "/health", "GET", tenant=None))
    for flag, path in _FLAT_GETS:
        if getattr(args, flag):
            return show(_request(base, path, "GET", **read))
    for flag, template in _ONE_ARG_GETS:
        value = getattr(args, flag)
        if value:
            return show(_request(base, template.format(_quote(value[0])),
                                 "GET", **read))
    if args.accounts:
        suffix = (f"?externalKey={_quote(args.external_key)}"
                  if args.external_key else "")
        return show(_request(base, f"/1.0/kb/accounts{suffix}", "GET", **read))
    if args.create_account:
        return show(_request(base, "/1.0/kb/accounts", "POST", _body(args),
                             **write))
    if args.update_account:
        return show(_request(base, f"/1.0/kb/accounts/"
                                   f"{_quote(args.update_account[0])}", "PUT",
                             _body(args), **write))
    if args.commit_invoice:
        return show(_request(base, f"/1.0/kb/invoices/"
                                   f"{_quote(args.commit_invoice[0])}"
                                   f"/commitInvoice", "PUT", {}, **write))
    if args.charge:
        return show(_request(base, f"/1.0/kb/invoices/charges/"
                                   f"{_quote(args.charge[0])}", "POST",
                             _body(args), **write))
    if args.subscribe:
        return show(_request(base, "/1.0/kb/subscriptions", "POST",
                             _body(args), **write))
    if args.change_plan:
        subscription_id, plan = args.change_plan
        return show(_request(base, f"/1.0/kb/subscriptions/"
                                   f"{_quote(subscription_id)}", "PUT",
                             {"planName": plan}, **write))
    if args.cancel:
        query = []
        if args.entitlement_policy:
            query.append(f"entitlementPolicy={_quote(args.entitlement_policy)}")
        if args.billing_policy:
            query.append(f"billingPolicy={_quote(args.billing_policy)}")
        suffix = ("?" + "&".join(query)) if query else ""
        return show(_request(base, f"/1.0/kb/subscriptions/"
                                   f"{_quote(args.cancel[0])}{suffix}",
                             "DELETE", **write))
    if args.pay:
        body = {**_body(args)}
        if args.amount is not None:
            body["amount"] = args.amount
        return show(_request(base, f"/1.0/kb/accounts/{_quote(args.pay[0])}"
                                   f"/payments", "POST", body, **write))
    if args.refund:
        body = {**_body(args)}
        if args.amount is not None:
            body["amount"] = args.amount
        return show(_request(base, f"/1.0/kb/payments/"
                                   f"{_quote(args.refund[0])}/refunds", "POST",
                             body, **write))
    if args.add_payment_method:
        suffix = "?isDefault=true" if args.default else ""
        return show(_request(base, f"/1.0/kb/accounts/"
                                   f"{_quote(args.add_payment_method[0])}"
                                   f"/paymentMethods{suffix}", "POST",
                             _body(args), **write))
    if args.add_tags:
        return show(_request(base, f"/1.0/kb/accounts/"
                                   f"{_quote(args.add_tags[0])}/tags", "POST",
                             args.tag, **write))
    if args.remove_tags:
        suffix = f"?tagDef={_quote(','.join(args.tag))}" if args.tag else ""
        return show(_request(base, f"/1.0/kb/accounts/"
                                   f"{_quote(args.remove_tags[0])}/tags"
                                   f"{suffix}", "DELETE", **write))
    print("No endpoint flag provided. Use -h to list available endpoints.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
