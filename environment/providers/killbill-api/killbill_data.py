"""Data access module for the Kill Bill mock service.

Kill Bill is the enterprise end of this fleet --- a Java, multi-tenant
subscription platform --- and five of its habits are modelled rather than
smoothed away:

* **Every request carries its tenant in headers.** `X-Killbill-ApiKey` and
  `X-Killbill-ApiSecret` decide which data even exists; an account in one
  tenant is invisible from the other, and a missing or wrong pair is a 401.
  Writes additionally need `X-Killbill-CreatedBy`, because every change is
  audited against a person.
* **Creates answer 201 with a `Location` header and no body.** You are expected
  to follow the header, or look the object up by the `externalKey` you chose.
  Updates and cancellations answer 204. Nothing is echoed back.
* **Entitlement and billing are two different timelines.** A subscription has a
  `startDate` (when the customer got access) and a `billingStartDate` (when
  money starts), and cancelling takes an `entitlementPolicy` *and* a
  `billingPolicy` --- you can stop the service today and stop charging at the
  end of the term, or the reverse.
* **A payment is a container of transactions.** `AUTHORIZE`, `CAPTURE`,
  `PURCHASE`, `REFUND`, `VOID`, each with its own status, so a failed attempt
  and its retry both live on the same payment.
* **Control tags change what the system does.** `AUTO_PAY_OFF` stops payment
  attempts, `OVERDUE_ENFORCEMENT_OFF` keeps an account out of the dunning
  ladder. They are data, and they are enforced.

Amounts are integers in the currency's minor unit throughout.

Mutations are held in process memory and reset on restart.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("killbill-api")
_API = "killbill-api"

KILLBILL_VERSION = "0.24.10"
API_PREFIX = "/1.0/kb"

ENTITLEMENT_POLICIES = ("IMMEDIATE", "END_OF_TERM")
BILLING_POLICIES = ("IMMEDIATE", "END_OF_TERM", "START_OF_TERM")
CONTROL_TAGS = ("AUTO_PAY_OFF", "AUTO_INVOICING_OFF", "OVERDUE_ENFORCEMENT_OFF",
                "WRITTEN_OFF", "MANUAL_PAY", "TEST")


def _store_insert(_table, _row):
    """Persist a newly-created row into the shared store (drift/injection-safe).

    Synthesizes the table's registered primary key from the row's ``id`` field
    when the row doesn't already carry it, so creates work regardless of whether
    the table was registered with primary_key="id" or a domain-specific key.
    """
    _t = _store.table(_table)
    if _t.primary_key not in _row and "id" in _row:
        _row = {**_row, _t.primary_key: _row["id"]}
    return _t.upsert(_row)


def _load(filename, table):
    return read_seed_with_ctx(DATA_DIR / filename, _API, table)


def _strip_ctx(r):
    return {k: v for k, v in r.items() if not k.startswith("__")}


def _flag(row, column, default="0"):
    return opt_str(row, column, default=default) == "1"


def _load_json(filename):
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _ints(row, *columns):
    return {column: opt_int(row, column, default=0) for column in columns}


def _coerce_accounts(rows):
    return [{**_strip_ctx(r),
             **_ints(r, "billCycleDayLocal", "accountBalance", "accountCBA"),
             "isPaymentDelegatedToParent": _flag(r,
                                                 "isPaymentDelegatedToParent")}
            for r in rows]


def _coerce_invoices(rows):
    return [{**_strip_ctx(r), **_ints(r, "amount", "creditAdj", "refundAdj"),
             "isParentInvoice": _flag(r, "isParentInvoice")} for r in rows]


def _coerce_items(rows):
    return [{**_strip_ctx(r), **_ints(r, "amount")} for r in rows]


def _coerce_methods(rows):
    return [{**_strip_ctx(r), "isDefault": _flag(r, "isDefault")}
            for r in rows]


def _coerce_payments(rows):
    return [{**_strip_ctx(r), **_ints(r, "authAmount", "capturedAmount",
                                      "purchasedAmount", "refundedAmount")}
            for r in rows]


def _coerce_transactions(rows):
    return [{**_strip_ctx(r), **_ints(r, "amount")} for r in rows]


_store.register("tenants", primary_key="apiKey",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("tenants.json", "tenants")])
_store.register("accounts", primary_key="accountId",
                initial_loader=lambda: _coerce_accounts(
                    _load("accounts.json", "accounts")))
_store.register("bundles", primary_key="bundleId",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("bundles.json", "bundles")])
_store.register("subscriptions", primary_key="subscriptionId",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("subscriptions.json",
                                              "subscriptions")])
_store.register("invoices", primary_key="invoiceId",
                initial_loader=lambda: _coerce_invoices(
                    _load("invoices.json", "invoices")))
_store.register("invoice_items", primary_key="invoiceItemId",
                initial_loader=lambda: _coerce_items(
                    _load("invoice_items.json", "invoice_items")))
_store.register("payment_methods", primary_key="paymentMethodId",
                initial_loader=lambda: _coerce_methods(
                    _load("payment_methods.json", "payment_methods")))
_store.register("payments", primary_key="paymentId",
                initial_loader=lambda: _coerce_payments(
                    _load("payments.json", "payments")))
_store.register("payment_transactions", primary_key="transactionId",
                initial_loader=lambda: _coerce_transactions(
                    _load("payment_transactions.json", "payment_transactions")))
_store.register("tags", primary_key="tagId",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("tags.json", "tags")])
_store.register_document("catalog",
                         initial_loader=lambda: _load_json("catalog.json"))


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _uuid():
    return str(uuid.uuid4())


def _catalog():
    return _store.document("catalog").get()


# ---------------------------------------------------------------------------
# Errors --- Kill Bill's body shape: a class name, a numeric code, a message
# ---------------------------------------------------------------------------

ERROR_CODES = {
    "ACCOUNT_DOES_NOT_EXIST_FOR_ID": 1000,
    "ACCOUNT_ALREADY_EXISTS_FOR_KEY": 1001,
    "ACCOUNT_INVALID_CURRENCY": 1002,
    "SUB_GET_NO_SUCH_SUBSCRIPTION": 1500,
    "SUB_CANCEL_BAD_STATE": 1501,
    "SUB_CHANGE_INVALID_PLAN": 1502,
    "SUB_INVALID_POLICY": 1503,
    "BUNDLE_DOES_NOT_EXIST": 1600,
    "INVOICE_NOT_FOUND": 2000,
    "INVOICE_INVALID_STATUS": 2001,
    "INVOICE_INVALID_AMOUNT": 2002,
    "PAYMENT_NO_SUCH_PAYMENT": 3000,
    "PAYMENT_NO_DEFAULT_PAYMENT_METHOD": 3001,
    "PAYMENT_AMOUNT_INVALID": 3002,
    "PAYMENT_AUTO_PAY_OFF": 3003,
    "PAYMENT_PLUGIN_FAILURE": 3004,
    "PAYMENT_DECLINED": 3005,
    "PAYMENT_NO_SUCH_METHOD": 3006,
    "SECURITY_INVALID_CREDENTIALS": 4000,
    "SECURITY_MISSING_CREATED_BY": 4001,
    "CAT_NO_SUCH_PLAN": 5000,
    "TAG_DOES_NOT_EXIST": 6000,
}


def _error(status, code_name, message):
    return {"error": message, "code": status, "message": message,
            "kbCode": ERROR_CODES.get(code_name, 0),
            "className": f"org.killbill.billing.{code_name.split('_')[0].lower()}"
                         f".api.BillingExceptionBase"}


def _not_found(code_name, message):
    return _error(404, code_name, message)


# ---------------------------------------------------------------------------
# Tenancy --- the header pair decides which data exists at all
# ---------------------------------------------------------------------------

def resolve_tenant(api_key, api_secret):
    """Kill Bill partitions everything by tenant, and the tenant is a header."""
    if not api_key or not api_secret:
        return None, _error(401, "SECURITY_INVALID_CREDENTIALS",
                            "X-Killbill-ApiKey and X-Killbill-ApiSecret are "
                            "required on every request")
    tenant = _store.table("tenants").get(api_key)
    if not tenant or tenant["apiSecret"] != api_secret:
        return None, _error(401, "SECURITY_INVALID_CREDENTIALS",
                            "Invalid tenant credentials")
    return tenant, None


def require_created_by(created_by):
    """Every write is audited against a person, so the header is mandatory."""
    if not created_by:
        return _error(400, "SECURITY_MISSING_CREATED_BY",
                      "X-Killbill-CreatedBy is required on any request that "
                      "changes state")
    return None


def _scoped(table, tenant):
    return [r for r in _store.table(table).rows()
            if r["tenantId"] == tenant["tenantId"]]


def _get_scoped(table, key, tenant):
    row = _store.table(table).get(key)
    if not row or row["tenantId"] != tenant["tenantId"]:
        return None
    return row


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def account_representation(account):
    return {
        "accountId": account["accountId"],
        "externalKey": account["externalKey"], "name": account["name"],
        "email": account["email"], "currency": account["currency"],
        "country": account["country"], "timeZone": account["timeZone"],
        "billCycleDayLocal": account["billCycleDayLocal"],
        "accountBalance": account["accountBalance"],
        "accountCBA": account["accountCBA"],
        "paymentMethodId": account["paymentMethodId"] or None,
        "isPaymentDelegatedToParent": account["isPaymentDelegatedToParent"],
        "parentAccountId": account["parentAccountId"] or None,
        "referenceTime": account["referenceTime"],
    }


def list_accounts(tenant, external_key=None, offset=0, limit=100):
    rows = sorted(_scoped("accounts", tenant), key=lambda a: a["referenceTime"])
    if external_key:
        rows = [a for a in rows if a["externalKey"] == external_key]
    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or 100), 100))
    return [account_representation(a) for a in rows[offset:offset + limit]]


def get_account(tenant, account_id):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    return account_representation(account)


def create_account(tenant, payload, created_by):
    payload = payload or {}
    external_key = payload.get("externalKey")
    if not external_key:
        return _error(400, "ACCOUNT_ALREADY_EXISTS_FOR_KEY",
                      "externalKey is required")
    if any(a["externalKey"] == external_key
           for a in _scoped("accounts", tenant)):
        return _error(409, "ACCOUNT_ALREADY_EXISTS_FOR_KEY",
                      f"Account already exists for key {external_key}")
    currency = payload.get("currency", "EUR")
    if currency not in _catalog()["currencies"]:
        return _error(400, "ACCOUNT_INVALID_CURRENCY",
                      f"Invalid currency {currency}; the catalog supports "
                      f"{', '.join(_catalog()['currencies'])}")
    account_id = _uuid()
    _store_insert("accounts", {
        "accountId": account_id, "tenantId": tenant["tenantId"],
        "externalKey": external_key, "name": payload.get("name", ""),
        "email": payload.get("email", ""), "currency": currency,
        "country": payload.get("country", ""),
        "timeZone": payload.get("timeZone", "UTC"),
        "billCycleDayLocal": payload.get("billCycleDayLocal", 0),
        "accountBalance": 0, "accountCBA": 0, "paymentMethodId": "",
        "isPaymentDelegatedToParent": False, "parentAccountId": "",
        "referenceTime": _now()})
    # Kill Bill answers a create with the Location of the new resource and an
    # empty body; the caller follows the header or looks it up by externalKey.
    return {"__created__": f"{API_PREFIX}/accounts/{account_id}"}


def update_account(tenant, account_id, payload, created_by):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    payload = payload or {}
    updatable = ("name", "email", "country", "timeZone", "billCycleDayLocal")
    unknown = [k for k in payload if k not in updatable]
    if unknown:
        return _error(400, "ACCOUNT_INVALID_CURRENCY",
                      f"{', '.join(sorted(unknown))} cannot be updated; "
                      f"updatable fields are {', '.join(updatable)}")
    _store_insert("accounts", {**account,
                               **{k: payload[k] for k in payload}})
    return {"__status__": 204}


def account_timeline(tenant, account_id):
    """One read that stitches the whole account together, as Kill Bill does."""
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    bundles = [b for b in _scoped("bundles", tenant)
               if b["accountId"] == account_id]
    return {
        "account": account_representation(account),
        "bundles": [bundle_representation(tenant, b) for b in bundles],
        "invoices": [invoice_representation(tenant, i, with_items=False)
                     for i in _scoped("invoices", tenant)
                     if i["accountId"] == account_id],
        "payments": [payment_representation(tenant, p)
                     for p in _scoped("payments", tenant)
                     if p["accountId"] == account_id],
    }


def overdue_state(tenant, account_id):
    """Derived from the balance and the control tags, not stored."""
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    tags = {t["tagDefinitionName"] for t in _scoped("tags", tenant)
            if t["objectId"] == account_id}
    if "OVERDUE_ENFORCEMENT_OFF" in tags:
        return {"name": "CLEAR", "externalMessage": "Overdue enforcement is "
                                                    "switched off for this "
                                                    "account",
                "daysBetweenPaymentRetries": [], "isDisableEntitlementAndChangesBlocked": False,
                "isBlockChanges": False, "isClearState": True}
    if account["accountBalance"] <= 0:
        return {"name": "CLEAR", "externalMessage": "Account is current",
                "daysBetweenPaymentRetries": [], "isDisableEntitlementAndChangesBlocked": False,
                "isBlockChanges": False, "isClearState": True}
    return {"name": "OD1", "externalMessage": "Payment is overdue; entitlement "
                                              "remains active while we retry",
            "daysBetweenPaymentRetries": [3, 5, 8],
            "isDisableEntitlementAndChangesBlocked": False,
            "isBlockChanges": False, "isClearState": False}


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def get_catalog(tenant):
    return [_catalog()]


def available_base_plans(tenant):
    catalog = _catalog()
    base = {p["name"] for p in catalog["products"] if p["type"] == "BASE"}
    return [{"planName": plan["name"], "product": plan["product"],
             "productType": plan["productType"],
             "priceList": plan["priceList"],
             "billingPeriod": plan["billingPeriod"],
             "prices": plan["phases"][-1]["prices"]}
            for plan in catalog["plans"] if plan["product"] in base]


def _plan(plan_name):
    return next((p for p in _catalog()["plans"] if p["name"] == plan_name),
                None)


# ---------------------------------------------------------------------------
# Bundles and subscriptions
# ---------------------------------------------------------------------------

def subscription_representation(subscription):
    return {
        "accountId": subscription["accountId"],
        "bundleId": subscription["bundleId"],
        "subscriptionId": subscription["subscriptionId"],
        "externalKey": subscription["externalKey"],
        "productName": subscription["productName"],
        "productCategory": subscription["productCategory"],
        "planName": subscription["planName"],
        "priceList": subscription["priceList"],
        "billingPeriod": subscription["billingPeriod"],
        "phaseType": subscription["phaseType"],
        "state": subscription["state"],
        # Entitlement and billing are separate timelines, and Kill Bill keeps
        # both ends of each.
        "startDate": subscription["startDate"],
        "billingStartDate": subscription["billingStartDate"],
        "chargedThroughDate": subscription["chargedThroughDate"] or None,
        "cancelledDate": subscription["cancelledDate"] or None,
        "billingEndDate": subscription["billingEndDate"] or None,
    }


def bundle_representation(tenant, bundle):
    subscriptions = [s for s in _scoped("subscriptions", tenant)
                     if s["bundleId"] == bundle["bundleId"]]
    return {"accountId": bundle["accountId"], "bundleId": bundle["bundleId"],
            "externalKey": bundle["externalKey"],
            "subscriptions": [subscription_representation(s)
                              for s in subscriptions]}


def list_bundles(tenant, account_id):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    return [bundle_representation(tenant, b) for b in _scoped("bundles", tenant)
            if b["accountId"] == account_id]


def get_bundle(tenant, bundle_id):
    bundle = _get_scoped("bundles", bundle_id, tenant)
    if not bundle:
        return _not_found("BUNDLE_DOES_NOT_EXIST",
                          f"Bundle does not exist for id {bundle_id}")
    return bundle_representation(tenant, bundle)


def get_subscription(tenant, subscription_id):
    subscription = _get_scoped("subscriptions", subscription_id, tenant)
    if not subscription:
        return _not_found("SUB_GET_NO_SUCH_SUBSCRIPTION",
                          f"Subscription does not exist for id "
                          f"{subscription_id}")
    return subscription_representation(subscription)


def create_subscription(tenant, payload, created_by):
    payload = payload or {}
    account_id = payload.get("accountId")
    account = _get_scoped("accounts", account_id or "", tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    plan_name = payload.get("planName")
    plan = _plan(plan_name or "")
    if not plan:
        return _not_found("CAT_NO_SUCH_PLAN",
                          f"No such plan {plan_name} in the OrbitLabs catalog")
    bundle_key = payload.get("externalKey") or f"{account['externalKey']}-bundle"
    bundle = next((b for b in _scoped("bundles", tenant)
                   if b["externalKey"] == bundle_key), None)
    if plan["productType"] == "ADD_ON":
        if not bundle:
            return _error(400, "SUB_CHANGE_INVALID_PLAN",
                          f"An ADD_ON needs an existing bundle; no bundle has "
                          f"externalKey {bundle_key}")
        base = next((s for s in _scoped("subscriptions", tenant)
                     if s["bundleId"] == bundle["bundleId"]
                     and s["productCategory"] == "BASE"
                     and s["state"] == "ACTIVE"), None)
        if not base:
            return _error(400, "SUB_CHANGE_INVALID_PLAN",
                          f"Bundle {bundle_key} has no active BASE "
                          f"subscription to attach an ADD_ON to")
        allowed = next((p["available"] for p in _catalog()["products"]
                        if p["name"] == base["productName"]), [])
        if plan["product"] not in allowed:
            return _error(400, "SUB_CHANGE_INVALID_PLAN",
                          f"{base['productName']} does not offer "
                          f"{plan['product']}; it offers "
                          f"{', '.join(allowed) or 'nothing'}")
    if not bundle:
        bundle = {"bundleId": _uuid(), "tenantId": tenant["tenantId"],
                  "accountId": account_id, "externalKey": bundle_key,
                  "created": _now()}
        _store_insert("bundles", bundle)
    subscription_id = _uuid()
    entitlement_date = payload.get("entitlementDate") or _today()
    billing_date = payload.get("billingDate") or entitlement_date
    trial = next((p for p in plan["phases"] if p["type"] == "TRIAL"), None)
    _store_insert("subscriptions", {
        "subscriptionId": subscription_id, "tenantId": tenant["tenantId"],
        "bundleId": bundle["bundleId"], "accountId": account_id,
        "externalKey": bundle_key, "productName": plan["product"],
        "productCategory": plan["productType"], "planName": plan_name,
        "priceList": plan["priceList"], "billingPeriod": plan["billingPeriod"],
        "phaseType": "TRIAL" if trial else "EVERGREEN", "state": "ACTIVE",
        "startDate": entitlement_date, "billingStartDate": billing_date,
        "chargedThroughDate": "", "cancelledDate": "", "billingEndDate": ""})
    return {"__created__": f"{API_PREFIX}/subscriptions/{subscription_id}"}


def change_plan(tenant, subscription_id, payload, created_by):
    subscription = _get_scoped("subscriptions", subscription_id, tenant)
    if not subscription:
        return _not_found("SUB_GET_NO_SUCH_SUBSCRIPTION",
                          f"Subscription does not exist for id "
                          f"{subscription_id}")
    if subscription["state"] != "ACTIVE":
        return _error(400, "SUB_CANCEL_BAD_STATE",
                      f"Subscription {subscription_id} is "
                      f"{subscription['state']} and cannot change plan")
    plan_name = (payload or {}).get("planName")
    plan = _plan(plan_name or "")
    if not plan:
        return _not_found("CAT_NO_SUCH_PLAN",
                          f"No such plan {plan_name} in the OrbitLabs catalog")
    if plan["productType"] != subscription["productCategory"]:
        return _error(400, "SUB_CHANGE_INVALID_PLAN",
                      f"Cannot change a {subscription['productCategory']} "
                      f"subscription to a {plan['productType']} plan")
    _store_insert("subscriptions", {
        **subscription, "planName": plan_name, "productName": plan["product"],
        "billingPeriod": plan["billingPeriod"], "phaseType": "EVERGREEN"})
    return {"__status__": 204}


def cancel_subscription(tenant, subscription_id, entitlement_policy,
                        billing_policy, created_by):
    """Two policies, because entitlement and billing are two timelines."""
    subscription = _get_scoped("subscriptions", subscription_id, tenant)
    if not subscription:
        return _not_found("SUB_GET_NO_SUCH_SUBSCRIPTION",
                          f"Subscription does not exist for id "
                          f"{subscription_id}")
    if subscription["state"] == "CANCELLED":
        return _error(400, "SUB_CANCEL_BAD_STATE",
                      f"Subscription {subscription_id} is already cancelled")
    entitlement_policy = entitlement_policy or "END_OF_TERM"
    billing_policy = billing_policy or "END_OF_TERM"
    if entitlement_policy not in ENTITLEMENT_POLICIES:
        return _error(400, "SUB_INVALID_POLICY",
                      f"entitlementPolicy must be one of "
                      f"{', '.join(ENTITLEMENT_POLICIES)}")
    if billing_policy not in BILLING_POLICIES:
        return _error(400, "SUB_INVALID_POLICY",
                      f"billingPolicy must be one of "
                      f"{', '.join(BILLING_POLICIES)}")
    charged_through = subscription["chargedThroughDate"] or _today()
    cancelled_on = _today() if entitlement_policy == "IMMEDIATE" \
        else charged_through
    billing_end = _today() if billing_policy == "IMMEDIATE" else (
        subscription["billingStartDate"] if billing_policy == "START_OF_TERM"
        else charged_through)
    _store_insert("subscriptions", {
        **subscription, "state": "CANCELLED", "cancelledDate": cancelled_on,
        "billingEndDate": billing_end})
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

def _items_for(tenant, invoice_id):
    return [i for i in _scoped("invoice_items", tenant)
            if i["invoiceId"] == invoice_id]


def invoice_representation(tenant, invoice, with_items=True):
    items = _items_for(tenant, invoice["invoiceId"])
    paid = sum(t["amount"] for t in _scoped("payment_transactions", tenant)
               if t["status"] == "SUCCESS"
               and t["transactionType"] in ("PURCHASE", "CAPTURE")
               and _payment_of(tenant, t) == invoice["accountId"])
    body = {
        "invoiceId": invoice["invoiceId"],
        "accountId": invoice["accountId"],
        "invoiceNumber": invoice["invoiceNumber"] or None,
        "currency": invoice["currency"], "status": invoice["status"],
        "invoiceDate": invoice["invoiceDate"],
        "targetDate": invoice["targetDate"],
        "amount": invoice["amount"],
        "creditAdj": invoice["creditAdj"], "refundAdj": invoice["refundAdj"],
        "balance": max(0, invoice["amount"] - invoice["creditAdj"]
                       - min(paid, invoice["amount"])),
        "isParentInvoice": invoice["isParentInvoice"],
    }
    if with_items:
        body["items"] = [{
            "invoiceItemId": i["invoiceItemId"], "invoiceId": i["invoiceId"],
            "accountId": i["accountId"],
            "subscriptionId": i["subscriptionId"] or None,
            "itemType": i["itemType"], "description": i["description"],
            "planName": i["planName"] or None,
            "phaseName": i["phaseName"] or None,
            "startDate": i["startDate"], "endDate": i["endDate"] or None,
            "amount": i["amount"], "currency": i["currency"]} for i in items]
    return body


def _payment_of(tenant, transaction):
    payment = _store.table("payments").get(transaction["paymentId"])
    return payment["accountId"] if payment else ""


def list_account_invoices(tenant, account_id):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    rows = sorted((i for i in _scoped("invoices", tenant)
                   if i["accountId"] == account_id),
                  key=lambda i: i["invoiceDate"], reverse=True)
    return [invoice_representation(tenant, i, with_items=False) for i in rows]


def get_invoice(tenant, invoice_id):
    invoice = _get_scoped("invoices", invoice_id, tenant)
    if not invoice:
        return _not_found("INVOICE_NOT_FOUND",
                          f"Invoice does not exist for id {invoice_id}")
    return invoice_representation(tenant, invoice)


def get_invoice_html(tenant, invoice_id):
    invoice = _get_scoped("invoices", invoice_id, tenant)
    if not invoice:
        return _not_found("INVOICE_NOT_FOUND",
                          f"Invoice does not exist for id {invoice_id}")
    rendered = invoice_representation(tenant, invoice)
    rows = "".join(
        f"<tr><td>{i['description']}</td><td>{i['itemType']}</td>"
        f"<td>{i['amount']}</td></tr>" for i in rendered["items"])
    html = (f"<html><body><h1>Invoice "
            f"{rendered['invoiceNumber'] or 'DRAFT'}</h1>"
            f"<p>{rendered['invoiceDate']} &middot; {rendered['currency']}</p>"
            f"<table>{rows}</table>"
            f"<p>Balance: {rendered['balance']}</p></body></html>")
    return {"__raw__": html, "__content_type__": "text/html"}


def commit_invoice(tenant, invoice_id, created_by):
    invoice = _get_scoped("invoices", invoice_id, tenant)
    if not invoice:
        return _not_found("INVOICE_NOT_FOUND",
                          f"Invoice does not exist for id {invoice_id}")
    if invoice["status"] != "DRAFT":
        return _error(400, "INVOICE_INVALID_STATUS",
                      f"Only a DRAFT invoice can be committed; invoice "
                      f"{invoice_id} is {invoice['status']}")
    number = str(max((int(i["invoiceNumber"]) for i in _scoped("invoices",
                                                               tenant)
                      if i["invoiceNumber"]), default=1000) + 1)
    _store_insert("invoices", {**invoice, "status": "COMMITTED",
                               "invoiceNumber": number})
    account = _store.table("accounts").get(invoice["accountId"])
    if account:
        _store_insert("accounts", {
            **account,
            "accountBalance": account["accountBalance"] + invoice["amount"]})
    return {"__status__": 204}


def create_external_charge(tenant, account_id, payload, created_by):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    payload = payload or {}
    amount = payload.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return _error(400, "INVOICE_INVALID_AMOUNT",
                      "amount must be a positive whole number of minor units")
    currency = payload.get("currency", account["currency"])
    if currency != account["currency"]:
        return _error(400, "ACCOUNT_INVALID_CURRENCY",
                      f"Account {account_id} is billed in "
                      f"{account['currency']}, not {currency}")
    invoice_id = _uuid()
    _store_insert("invoices", {
        "invoiceId": invoice_id, "tenantId": tenant["tenantId"],
        "accountId": account_id, "invoiceNumber": "", "currency": currency,
        "status": "DRAFT", "invoiceDate": _today(), "targetDate": _today(),
        "amount": amount, "creditAdj": 0, "refundAdj": 0,
        "isParentInvoice": False})
    _store_insert("invoice_items", {
        "invoiceItemId": _uuid(), "invoiceId": invoice_id,
        "tenantId": tenant["tenantId"], "accountId": account_id,
        "subscriptionId": "", "itemType": "EXTERNAL_CHARGE",
        "description": payload.get("description", "External charge"),
        "planName": "", "phaseName": "", "startDate": _today(), "endDate": "",
        "amount": amount, "currency": currency})
    return {"__created__": f"{API_PREFIX}/invoices/{invoice_id}"}


# ---------------------------------------------------------------------------
# Payment methods and payments
# ---------------------------------------------------------------------------

def payment_method_representation(method):
    return {"paymentMethodId": method["paymentMethodId"],
            "accountId": method["accountId"],
            "externalKey": method["externalKey"],
            "isDefault": method["isDefault"],
            "pluginName": method["pluginName"],
            "pluginInfo": {"type": method["pluginType"],
                           "brand": method["pluginBrand"] or None,
                           "last4": method["pluginLast4"] or None,
                           "expiry": method["pluginExpiry"] or None}}


def list_payment_methods(tenant, account_id):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    return [payment_method_representation(m)
            for m in _scoped("payment_methods", tenant)
            if m["accountId"] == account_id]


def get_payment_method(tenant, payment_method_id):
    method = _get_scoped("payment_methods", payment_method_id, tenant)
    if not method:
        return _not_found("PAYMENT_NO_SUCH_METHOD",
                          f"Payment method does not exist for id "
                          f"{payment_method_id}")
    return payment_method_representation(method)


def create_payment_method(tenant, account_id, payload, created_by,
                          is_default=False):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    payload = payload or {}
    external_key = payload.get("externalKey")
    if not external_key:
        return _error(400, "PAYMENT_NO_SUCH_METHOD", "externalKey is required")
    plugin_info = payload.get("pluginInfo") or {}
    method_id = _uuid()
    _store_insert("payment_methods", {
        "paymentMethodId": method_id, "tenantId": tenant["tenantId"],
        "accountId": account_id, "externalKey": external_key,
        "isDefault": bool(is_default),
        "pluginName": payload.get("pluginName", "__EXTERNAL_PAYMENT__"),
        "pluginType": plugin_info.get("type", "card"),
        "pluginBrand": plugin_info.get("brand", ""),
        "pluginLast4": plugin_info.get("last4", ""),
        "pluginExpiry": plugin_info.get("expiry", ""),
        "behaviour": plugin_info.get("behaviour", "ok")})
    if is_default:
        _store_insert("accounts", {**account, "paymentMethodId": method_id})
        for other in _scoped("payment_methods", tenant):
            if other["accountId"] == account_id \
                    and other["paymentMethodId"] != method_id \
                    and other["isDefault"]:
                _store_insert("payment_methods", {**other, "isDefault": False})
    return {"__created__": f"{API_PREFIX}/paymentMethods/{method_id}"}


def _transactions_for(tenant, payment_id):
    return sorted((t for t in _scoped("payment_transactions", tenant)
                   if t["paymentId"] == payment_id),
                  key=lambda t: t["effectiveDate"])


def payment_representation(tenant, payment):
    return {
        "accountId": payment["accountId"], "paymentId": payment["paymentId"],
        "paymentNumber": payment["paymentNumber"],
        "paymentExternalKey": payment["externalKey"],
        "paymentMethodId": payment["paymentMethodId"],
        "authAmount": payment["authAmount"],
        "capturedAmount": payment["capturedAmount"],
        "purchasedAmount": payment["purchasedAmount"],
        "refundedAmount": payment["refundedAmount"],
        "currency": payment["currency"],
        # A payment is a container: the attempt, its retry and any refund all
        # hang off the same payment id.
        "transactions": [{
            "transactionId": t["transactionId"], "paymentId": t["paymentId"],
            "transactionExternalKey": t["transactionExternalKey"],
            "transactionType": t["transactionType"], "status": t["status"],
            "amount": t["amount"], "currency": t["currency"],
            "gatewayErrorCode": t["gatewayErrorCode"] or None,
            "gatewayErrorMsg": t["gatewayErrorMsg"] or None,
            "effectiveDate": t["effectiveDate"]}
            for t in _transactions_for(tenant, payment["paymentId"])],
    }


def list_payments(tenant, offset=0, limit=100):
    rows = sorted(_scoped("payments", tenant), key=lambda p: p["created"],
                  reverse=True)
    offset = max(0, int(offset or 0))
    limit = max(1, min(int(limit or 100), 100))
    return [payment_representation(tenant, p)
            for p in rows[offset:offset + limit]]


def list_account_payments(tenant, account_id):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    return [payment_representation(tenant, p)
            for p in _scoped("payments", tenant)
            if p["accountId"] == account_id]


def get_payment(tenant, payment_id):
    payment = _get_scoped("payments", payment_id, tenant)
    if not payment:
        return _not_found("PAYMENT_NO_SUCH_PAYMENT",
                          f"Payment does not exist for id {payment_id}")
    return payment_representation(tenant, payment)


_BEHAVIOUR_RESULT = {
    "ok": ("SUCCESS", "", ""),
    "pending": ("PENDING", "", ""),
    "declines": ("PAYMENT_FAILURE", "insufficient_funds",
                 "The card issuer declined the charge"),
    "plugin_error": ("PLUGIN_FAILURE", "plugin_timeout",
                     "The payment plugin did not respond in time"),
}


def create_payment(tenant, account_id, payload, created_by):
    """Take a payment, subject to the account's control tags and the plugin."""
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    tags = {t["tagDefinitionName"] for t in _scoped("tags", tenant)
            if t["objectId"] == account_id}
    if "AUTO_PAY_OFF" in tags:
        # A control tag is data that changes what the system does.
        return _error(400, "PAYMENT_AUTO_PAY_OFF",
                      f"Account {account_id} carries AUTO_PAY_OFF; remove the "
                      f"tag before taking a payment")
    payload = payload or {}
    method_id = payload.get("paymentMethodId") or account["paymentMethodId"]
    method = _get_scoped("payment_methods", method_id or "", tenant)
    if not method:
        return _error(400, "PAYMENT_NO_DEFAULT_PAYMENT_METHOD",
                      f"Account {account_id} has no usable payment method")
    amount = payload.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return _error(400, "PAYMENT_AMOUNT_INVALID",
                      "amount must be a positive whole number of minor units")
    transaction_type = payload.get("transactionType", "PURCHASE")
    if transaction_type not in ("PURCHASE", "AUTHORIZE"):
        return _error(400, "PAYMENT_AMOUNT_INVALID",
                      "transactionType must be PURCHASE or AUTHORIZE")
    status, error_code, error_message = _BEHAVIOUR_RESULT.get(
        method["behaviour"], _BEHAVIOUR_RESULT["ok"])
    payment_id = _uuid()
    number = str(max((int(p["paymentNumber"]) for p in _scoped("payments",
                                                               tenant)),
                     default=800) + 1)
    external_key = payload.get("paymentExternalKey") or f"pay-{number}"
    _store_insert("payments", {
        "paymentId": payment_id, "tenantId": tenant["tenantId"],
        "accountId": account_id, "paymentMethodId": method_id,
        "paymentNumber": number, "externalKey": external_key,
        "currency": account["currency"],
        "authAmount": amount if transaction_type == "AUTHORIZE"
                      and status == "SUCCESS" else 0,
        "capturedAmount": 0,
        "purchasedAmount": amount if transaction_type == "PURCHASE"
                           and status == "SUCCESS" else 0,
        "refundedAmount": 0, "created": _now()})
    _store_insert("payment_transactions", {
        "transactionId": _uuid(), "paymentId": payment_id,
        "tenantId": tenant["tenantId"],
        "transactionExternalKey": payload.get("transactionExternalKey")
                                  or f"{external_key}-1",
        "transactionType": transaction_type, "status": status,
        "amount": amount, "currency": account["currency"],
        "gatewayErrorCode": error_code, "gatewayErrorMsg": error_message,
        "effectiveDate": _now()})
    if status == "SUCCESS":
        _store_insert("accounts", {
            **account,
            "accountBalance": max(0, account["accountBalance"] - amount)})
        return {"__created__": f"{API_PREFIX}/payments/{payment_id}"}
    if status == "PENDING":
        # An asynchronous plugin still gets a resource; the transaction says so.
        return {"__created__": f"{API_PREFIX}/payments/{payment_id}"}
    if status == "PLUGIN_FAILURE":
        return _error(400, "PAYMENT_PLUGIN_FAILURE",
                      f"{error_message} (payment {payment_id} was recorded "
                      f"with a PLUGIN_FAILURE transaction)")
    return _error(402, "PAYMENT_DECLINED",
                  f"{error_message} (payment {payment_id} was recorded with a "
                  f"PAYMENT_FAILURE transaction)")


def refund_payment(tenant, payment_id, payload, created_by):
    payment = _get_scoped("payments", payment_id, tenant)
    if not payment:
        return _not_found("PAYMENT_NO_SUCH_PAYMENT",
                          f"Payment does not exist for id {payment_id}")
    settled = payment["purchasedAmount"] + payment["capturedAmount"]
    refundable = settled - payment["refundedAmount"]
    payload = payload or {}
    amount = payload.get("amount", refundable)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return _error(400, "PAYMENT_AMOUNT_INVALID",
                      "amount must be a positive whole number of minor units")
    if amount > refundable:
        return _error(400, "PAYMENT_AMOUNT_INVALID",
                      f"Cannot refund {amount}; only {refundable} "
                      f"{payment['currency']} of payment {payment_id} is "
                      f"refundable")
    _store_insert("payments", {
        **payment, "refundedAmount": payment["refundedAmount"] + amount})
    _store_insert("payment_transactions", {
        "transactionId": _uuid(), "paymentId": payment_id,
        "tenantId": tenant["tenantId"],
        "transactionExternalKey": payload.get("transactionExternalKey")
                                  or f"{payment['externalKey']}-refund",
        "transactionType": "REFUND", "status": "SUCCESS", "amount": amount,
        "currency": payment["currency"], "gatewayErrorCode": "",
        "gatewayErrorMsg": "", "effectiveDate": _now()})
    return {"__created__": f"{API_PREFIX}/payments/{payment_id}"}


# ---------------------------------------------------------------------------
# Tags --- data that changes behaviour
# ---------------------------------------------------------------------------

def list_account_tags(tenant, account_id):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    return [{"tagId": t["tagId"], "objectId": t["objectId"],
             "objectType": t["objectType"],
             "tagDefinitionName": t["tagDefinitionName"],
             "isControlTag": t["tagDefinitionName"] in CONTROL_TAGS}
            for t in _scoped("tags", tenant) if t["objectId"] == account_id]


def add_account_tags(tenant, account_id, names, created_by):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    if not names:
        return _error(400, "TAG_DOES_NOT_EXIST",
                      "at least one tag definition name is required")
    unknown = [n for n in names if n not in CONTROL_TAGS]
    if unknown:
        return _error(400, "TAG_DOES_NOT_EXIST",
                      f"Unknown tag definition(s) {', '.join(unknown)}; the "
                      f"control tags are {', '.join(CONTROL_TAGS)}")
    existing = {t["tagDefinitionName"] for t in _scoped("tags", tenant)
                if t["objectId"] == account_id}
    for name in names:
        if name in existing:
            continue
        _store_insert("tags", {
            "tagId": _uuid(), "tenantId": tenant["tenantId"],
            "objectId": account_id, "objectType": "ACCOUNT",
            "tagDefinitionName": name, "created": _now()})
    return {"__created__": f"{API_PREFIX}/accounts/{account_id}/tags"}


def remove_account_tags(tenant, account_id, names, created_by):
    account = _get_scoped("accounts", account_id, tenant)
    if not account:
        return _not_found("ACCOUNT_DOES_NOT_EXIST_FOR_ID",
                          f"Account does not exist for id {account_id}")
    if not names:
        return _error(400, "TAG_DOES_NOT_EXIST",
                      "at least one tag definition name is required")
    present = {t["tagDefinitionName"] for t in _scoped("tags", tenant)
               if t["objectId"] == account_id}
    missing = [n for n in names if n not in present]
    if missing:
        return _not_found("TAG_DOES_NOT_EXIST",
                          f"Account {account_id} does not carry "
                          f"{', '.join(missing)}")
    _store.table("tags").delete_where(
        lambda t: t["objectId"] == account_id
        and t["tenantId"] == tenant["tenantId"]
        and t["tagDefinitionName"] in names)
    return {"__status__": 204}


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def nodes_info():
    return [{"nodeName": "killbill-mock-0", "bootTime": "2026-08-01T00:00:00Z",
             "lastUpdatedDate": _now(), "kbVersion": KILLBILL_VERSION,
             "apiVersion": "3.0.0", "pluginApiVersion": "0.26",
             "commonVersion": "0.26.10", "platformVersion": "0.41.10",
             "pluginsInfo": [
                 {"pluginKey": "killbill-orbit-payments",
                  "pluginName": "killbill-orbit-payments",
                  "version": "1.4.2", "state": "RUNNING",
                  "type": "PAYMENT"},
                 {"pluginKey": "killbill-email-notifications",
                  "pluginName": "killbill-email-notifications",
                  "version": "0.6.1", "state": "RUNNING",
                  "type": "NOTIFICATION"}]}]


_store.eager_load()
