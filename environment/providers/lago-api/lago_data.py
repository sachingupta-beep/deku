"""Data access module for the Lago mock service.

Lago is **usage-based billing**, and that makes it a different animal from the
in-house payments service next door. Nothing here charges a card. Instead:

* **You ingest events, not charges.** A usage event names a
  `external_subscription_id`, a billable-metric `code` and some `properties`.
  What it costs is not decided at ingestion --- it is *computed later* by
  aggregating the events in the period and running the plan's charges over the
  result.
* **The aggregation type decides what "how much" means.** `sum_agg` adds a
  property up, `max_agg` takes the peak, `unique_count_agg` counts distinct
  values, `count_agg` counts the events themselves. The same events under a
  different metric give a different number.
* **The charge model decides what that number costs**, and the five models
  disagree wildly on the same units. `graduated` bills each tier at its own
  rate; `volume` finds the one tier the whole quantity falls in and bills all
  of it there; `package` sells blocks; `percentage` takes basis points of a
  monetary metric; `standard` is a flat per-unit rate.
* **`current_usage` exists before any invoice does.** It is the running cost of
  the open period, recomputed on every read --- which is the endpoint people
  actually integrate against.

Identity is dual throughout: a `lago_id` the service owns and an `external_id`
the caller owns, and every read accepts the external one. Responses are
wrapped (`{"customer": …}`, `{"customers": […], "meta": {…}}`) because Lago's
are.

**Money is integer-only.** Amounts are cents; per-unit rates are *millicents*
(1 cent = 1000 millicents) so a rate like EUR 0.002 per API call is exact. Lago
itself uses decimal strings; millicents keep the arithmetic exact without
floats, and every computed total is rounded half-up to whole cents once, at the
end.

Mutations are held in process memory and reset on restart.
"""

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("lago-api")
_API = "lago-api"

LAGO_VERSION = "1.17.0"
API_VERSION = "v1"
MILLICENTS_PER_CENT = 1000

AGGREGATION_TYPES = ("count_agg", "sum_agg", "max_agg", "unique_count_agg",
                     "latest_agg")
CHARGE_MODELS = ("standard", "graduated", "package", "percentage", "volume")
INTERVALS = ("weekly", "monthly", "quarterly", "yearly")
BILLING_TIMES = ("calendar", "anniversary")


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


def _json_column(row, column):
    """Charge properties and event payloads ride as JSON in one cell.

    Keeping them in a single column is what lets a CSV overlay shadow the seed
    without the loader needing to know their shape.
    """
    raw = opt_str(row, column, default="")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _coerce_metrics(rows):
    return [{**_strip_ctx(r), "recurring": _flag(r, "recurring")} for r in rows]


def _coerce_plans(rows):
    return [{**_strip_ctx(r),
             "amount_cents": opt_int(r, "amount_cents", default=0),
             "trial_period_days": opt_int(r, "trial_period_days", default=0),
             "pay_in_advance": _flag(r, "pay_in_advance"),
             "bill_charges_monthly": _flag(r, "bill_charges_monthly")}
            for r in rows]


def _coerce_charges(rows):
    return [{**_strip_ctx(r), "properties": _json_column(r, "properties"),
             "pay_in_advance": _flag(r, "pay_in_advance"),
             "invoiceable": _flag(r, "invoiceable"),
             "min_amount_cents": opt_int(r, "min_amount_cents", default=0)}
            for r in rows]


def _coerce_events(rows):
    return [{**_strip_ctx(r), "properties": _json_column(r, "properties")}
            for r in rows]


def _coerce_invoices(rows):
    return [{**_strip_ctx(r),
             "sequential_id": opt_int(r, "sequential_id", default=0),
             "coupons_amount_cents": opt_int(r, "coupons_amount_cents",
                                             default=0),
             "credit_notes_amount_cents": opt_int(r, "credit_notes_amount_cents",
                                                  default=0),
             "prepaid_credit_amount_cents": opt_int(
                 r, "prepaid_credit_amount_cents", default=0),
             "taxes_rate_bps": opt_int(r, "taxes_rate_bps", default=0)}
            for r in rows]


def _coerce_fees(rows):
    return [{**_strip_ctx(r), "units": opt_int(r, "units", default=0),
             "amount_cents": opt_int(r, "amount_cents", default=0)}
            for r in rows]


def _coerce_credit_notes(rows):
    return [{**_strip_ctx(r),
             "credit_amount_cents": opt_int(r, "credit_amount_cents",
                                            default=0),
             "refund_amount_cents": opt_int(r, "refund_amount_cents",
                                            default=0),
             "balance_amount_cents": opt_int(r, "balance_amount_cents",
                                             default=0)} for r in rows]


def _coerce_wallets(rows):
    return [{**_strip_ctx(r),
             "rate_amount_cents": opt_int(r, "rate_amount_cents", default=0),
             "credits_balance": opt_int(r, "credits_balance", default=0),
             "balance_cents": opt_int(r, "balance_cents", default=0),
             "consumed_credits": opt_int(r, "consumed_credits", default=0)}
            for r in rows]


_store.register("billable_metrics", primary_key="code",
                initial_loader=lambda: _coerce_metrics(
                    _load("billable_metrics.json", "billable_metrics")))
_store.register("plans", primary_key="code",
                initial_loader=lambda: _coerce_plans(
                    _load("plans.json", "plans")))
# A charge is one metric on one plan, so neither key is unique on its own.
_store.register("charges", primary_key="_pk",
                initial_loader=lambda: _coerce_charges(
                    _load("charges.json", "charges")))
_store.register("customers", primary_key="external_id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("customers.json", "customers")])
_store.register("subscriptions", primary_key="external_id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("subscriptions.json",
                                              "subscriptions")])
# `transaction_id` is the caller's own key, and it is what makes ingestion
# idempotent --- Lago rejects a repeat rather than double-billing.
_store.register("events", primary_key="transaction_id",
                initial_loader=lambda: _coerce_events(
                    _load("events.json", "events")))
_store.register("invoices", primary_key="lago_id",
                initial_loader=lambda: _coerce_invoices(
                    _load("invoices.json", "invoices")))
_store.register("invoice_fees", primary_key="_pk",
                initial_loader=lambda: _coerce_fees(
                    _load("invoice_fees.json", "invoice_fees")))
_store.register("credit_notes", primary_key="lago_id",
                initial_loader=lambda: _coerce_credit_notes(
                    _load("credit_notes.json", "credit_notes")))
_store.register("wallets", primary_key="lago_id",
                initial_loader=lambda: _coerce_wallets(
                    _load("wallets.json", "wallets")))


def _events():
    return _store.table("events").rows()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lago_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# Errors --- Lago's envelope
# ---------------------------------------------------------------------------

def _error(status, code, message, details=None):
    return {"error": message, "code": status, "message": message,
            "err_code": code, "details": details}


def _not_found(kind, identifier):
    return _error(404, "not_found",
                  f"{kind} not found: {identifier}", {kind: ["not_found"]})


def _unprocessable(field, problem, message):
    """422 with a per-field detail map, which is what Lago returns."""
    return _error(422, "unprocessable_entity", message, {field: [problem]})


# ---------------------------------------------------------------------------
# Aggregation: what "how much" means
# ---------------------------------------------------------------------------

def _numeric(value):
    """Usage properties arrive as JSON; only whole units are billable here."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value).strip())
    except ValueError:
        return 0


def aggregate(metric, events):
    """Reduce a period's events to the single number the charge is applied to."""
    kind = metric["aggregation_type"]
    field = metric["field_name"]
    if kind == "count_agg":
        return len(events)
    values = [e["properties"].get(field) for e in events
              if field in e["properties"]]
    if kind == "sum_agg":
        return sum(_numeric(v) for v in values)
    if kind == "max_agg":
        return max((_numeric(v) for v in values), default=0)
    if kind == "unique_count_agg":
        return len({str(v) for v in values})
    if kind == "latest_agg":
        latest = sorted(events, key=lambda e: e["timestamp"])
        return _numeric(latest[-1]["properties"].get(field)) if latest else 0
    return 0


# ---------------------------------------------------------------------------
# The charge models: what that number costs
# ---------------------------------------------------------------------------

def _to_cents(millicents):
    """One half-up rounding, at the end, so tiers do not each lose a fraction."""
    return (millicents + MILLICENTS_PER_CENT // 2) // MILLICENTS_PER_CENT


def _standard(units, properties):
    rate = properties.get("per_unit_amount_millicents", 0)
    return _to_cents(units * rate), [
        {"model": "standard", "units": units,
         "per_unit_amount_millicents": rate}]


def _package(units, properties):
    free = properties.get("free_units", 0)
    size = max(1, properties.get("package_size", 1))
    amount = properties.get("amount_cents", 0)
    billable = max(0, units - free)
    packages = math.ceil(billable / size) if billable else 0
    return packages * amount, [
        {"model": "package", "units": units, "free_units": free,
         "billable_units": billable, "package_size": size,
         "packages": packages, "amount_cents": amount}]


def _graduated(units, properties):
    """Each tier bills its own slice --- the classic staircase."""
    total_millicents = 0
    total_cents = 0
    breakdown = []
    for tier in properties.get("graduated_ranges", []):
        lower = tier.get("from_value", 0)
        upper = tier.get("to_value")
        if units < lower:
            break
        top = units if upper is None else min(units, upper)
        # A tier that starts at 0 counts its lower bound; every later tier
        # starts one unit above the previous tier's ceiling.
        in_tier = top - lower + 1 if lower > 0 else top - lower
        in_tier = max(0, in_tier)
        tier_millicents = in_tier * tier.get("per_unit_amount_millicents", 0)
        flat = tier.get("flat_amount_cents", 0) if in_tier else 0
        total_millicents += tier_millicents
        total_cents += flat
        breakdown.append({"from_value": lower, "to_value": upper,
                          "units": in_tier,
                          "per_unit_amount_millicents":
                              tier.get("per_unit_amount_millicents", 0),
                          "flat_amount_cents": flat,
                          "amount_cents": _to_cents(tier_millicents) + flat})
    return _to_cents(total_millicents) + total_cents, breakdown


def _volume(units, properties):
    """The whole quantity falls into one tier and is billed entirely there."""
    for tier in properties.get("volume_ranges", []):
        lower = tier.get("from_value", 0)
        upper = tier.get("to_value")
        if units >= lower and (upper is None or units <= upper):
            rate = tier.get("per_unit_amount_millicents", 0)
            flat = tier.get("flat_amount_cents", 0)
            return _to_cents(units * rate) + flat, [
                {"model": "volume", "from_value": lower, "to_value": upper,
                 "units": units, "per_unit_amount_millicents": rate,
                 "flat_amount_cents": flat}]
    return 0, []


def _percentage(units, properties, event_count):
    """Basis points of a monetary metric, plus a fixed amount per event."""
    free = properties.get("free_units", 0)
    rate_bps = properties.get("rate_bps", 0)
    fixed = properties.get("fixed_amount_cents_per_event", 0)
    billable = max(0, units - free)
    variable = (billable * rate_bps + 5000) // 10000
    return variable + fixed * event_count, [
        {"model": "percentage", "units": units, "free_units": free,
         "billable_units": billable, "rate_bps": rate_bps,
         "variable_amount_cents": variable,
         "fixed_amount_cents_per_event": fixed, "events": event_count,
         "fixed_amount_cents": fixed * event_count}]


def apply_charge(charge, units, event_count):
    model = charge["charge_model"]
    properties = charge["properties"]
    if model == "standard":
        return _standard(units, properties)
    if model == "package":
        return _package(units, properties)
    if model == "graduated":
        return _graduated(units, properties)
    if model == "volume":
        return _volume(units, properties)
    if model == "percentage":
        return _percentage(units, properties, event_count)
    return 0, []


# ---------------------------------------------------------------------------
# Envelopes
# ---------------------------------------------------------------------------

def _page(rows, page, per_page, key):
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 20), 100))
    total = len(rows)
    pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    return {key: rows[start:start + per_page],
            "meta": {"current_page": page, "next_page": page + 1
                     if page < pages else None,
                     "prev_page": page - 1 if page > 1 else None,
                     "total_pages": pages, "total_count": total}}


# ---------------------------------------------------------------------------
# Billable metrics
# ---------------------------------------------------------------------------

def metric_representation(metric):
    return {"lago_id": metric["lago_id"], "name": metric["name"],
            "code": metric["code"], "description": metric["description"],
            "aggregation_type": metric["aggregation_type"],
            "field_name": metric["field_name"],
            "recurring": metric["recurring"],
            "created_at": metric["created_at"]}


def list_billable_metrics(page=1, per_page=20):
    rows = sorted(_store.table("billable_metrics").rows(),
                  key=lambda m: m["created_at"])
    return _page([metric_representation(m) for m in rows], page, per_page,
                 "billable_metrics")


def get_billable_metric(code):
    metric = _store.table("billable_metrics").get(code)
    if not metric:
        return _not_found("billable_metric", code)
    return {"billable_metric": metric_representation(metric)}


def create_billable_metric(payload):
    payload = (payload or {}).get("billable_metric") or payload or {}
    code = payload.get("code")
    if not code:
        return _unprocessable("code", "value_is_mandatory",
                              "code is required")
    if _store.table("billable_metrics").get(code):
        return _unprocessable("code", "value_already_exist",
                              f"A billable metric with code {code!r} already "
                              f"exists")
    aggregation = payload.get("aggregation_type")
    if aggregation not in AGGREGATION_TYPES:
        return _unprocessable("aggregation_type", "value_is_invalid",
                              f"aggregation_type must be one of "
                              f"{', '.join(AGGREGATION_TYPES)}")
    field = payload.get("field_name", "")
    if aggregation != "count_agg" and not field:
        return _unprocessable("field_name", "value_is_mandatory",
                              f"{aggregation} needs a field_name to aggregate")
    metric = {"code": code, "lago_id": _lago_id("bm"),
              "name": payload.get("name", code),
              "description": payload.get("description", ""),
              "aggregation_type": aggregation, "field_name": field,
              "recurring": bool(payload.get("recurring", False)),
              "created_at": _now()}
    _store_insert("billable_metrics", metric)
    return {"__status__": 201,
            "billable_metric": metric_representation(metric)}


# ---------------------------------------------------------------------------
# Plans and their charges
# ---------------------------------------------------------------------------

def _charges_for(plan_code):
    return sorted((c for c in _store.table("charges").rows()
                   if c["plan_code"] == plan_code),
                  key=lambda c: c["billable_metric_code"])


def charge_representation(charge):
    return {"lago_id": charge["lago_id"],
            "billable_metric_code": charge["billable_metric_code"],
            "charge_model": charge["charge_model"],
            "pay_in_advance": charge["pay_in_advance"],
            "invoiceable": charge["invoiceable"],
            "min_amount_cents": charge["min_amount_cents"],
            "properties": charge["properties"]}


def plan_representation(plan):
    charges = _charges_for(plan["code"])
    return {"lago_id": plan["lago_id"], "name": plan["name"],
            "code": plan["code"], "description": plan["description"],
            "interval": plan["interval"],
            "amount_cents": plan["amount_cents"],
            "amount_currency": plan["amount_currency"],
            "pay_in_advance": plan["pay_in_advance"],
            "trial_period_days": plan["trial_period_days"],
            "bill_charges_monthly": plan["bill_charges_monthly"],
            "charges": [charge_representation(c) for c in charges],
            "active_subscriptions_count": len(
                [s for s in _store.table("subscriptions").rows()
                 if s["plan_code"] == plan["code"] and s["status"] == "active"]),
            "created_at": plan["created_at"]}


def list_plans(page=1, per_page=20):
    rows = sorted(_store.table("plans").rows(), key=lambda p: p["created_at"])
    return _page([plan_representation(p) for p in rows], page, per_page, "plans")


def get_plan(code):
    plan = _store.table("plans").get(code)
    if not plan:
        return _not_found("plan", code)
    return {"plan": plan_representation(plan)}


def create_plan(payload):
    payload = (payload or {}).get("plan") or payload or {}
    code = payload.get("code")
    if not code:
        return _unprocessable("code", "value_is_mandatory", "code is required")
    if _store.table("plans").get(code):
        return _unprocessable("code", "value_already_exist",
                              f"A plan with code {code!r} already exists")
    interval = payload.get("interval")
    if interval not in INTERVALS:
        return _unprocessable("interval", "value_is_invalid",
                              f"interval must be one of {', '.join(INTERVALS)}")
    amount = payload.get("amount_cents", 0)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        return _unprocessable("amount_cents", "value_is_invalid",
                              "amount_cents must be a whole number of cents")
    charges = payload.get("charges") or []
    for index, charge in enumerate(charges):
        failure = _validate_charge(charge, index)
        if failure:
            return failure
    plan = {"code": code, "lago_id": _lago_id("pl"),
            "name": payload.get("name", code),
            "description": payload.get("description", ""),
            "interval": interval, "amount_cents": amount,
            "amount_currency": payload.get("amount_currency", "EUR"),
            "pay_in_advance": bool(payload.get("pay_in_advance", False)),
            "trial_period_days": payload.get("trial_period_days", 0),
            "bill_charges_monthly": bool(
                payload.get("bill_charges_monthly", False)),
            "created_at": _now()}
    _store_insert("plans", plan)
    for charge in charges:
        metric_code = charge["billable_metric_code"]
        _store_insert("charges", {
            "_pk": f"{code}#{metric_code}", "lago_id": _lago_id("chr"),
            "plan_code": code, "billable_metric_code": metric_code,
            "charge_model": charge["charge_model"],
            "pay_in_advance": bool(charge.get("pay_in_advance", False)),
            "invoiceable": bool(charge.get("invoiceable", True)),
            "min_amount_cents": charge.get("min_amount_cents", 0),
            "properties": charge.get("properties") or {}})
    return {"__status__": 201, "plan": plan_representation(plan)}


def _validate_charge(charge, index):
    metric_code = charge.get("billable_metric_code")
    if not metric_code:
        return _unprocessable(f"charges[{index}].billable_metric_code",
                              "value_is_mandatory",
                              "each charge needs a billable_metric_code")
    if not _store.table("billable_metrics").get(metric_code):
        return _unprocessable(f"charges[{index}].billable_metric_code",
                              "billable_metric_not_found",
                              f"No billable metric with code {metric_code!r}")
    model = charge.get("charge_model")
    if model not in CHARGE_MODELS:
        return _unprocessable(f"charges[{index}].charge_model",
                              "value_is_invalid",
                              f"charge_model must be one of "
                              f"{', '.join(CHARGE_MODELS)}")
    properties = charge.get("properties") or {}
    required = {"graduated": "graduated_ranges", "volume": "volume_ranges",
                "package": "package_size",
                "standard": "per_unit_amount_millicents",
                "percentage": "rate_bps"}[model]
    if required not in properties:
        return _unprocessable(f"charges[{index}].properties",
                              "value_is_mandatory",
                              f"a {model} charge needs {required} in properties")
    return None


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

def customer_representation(customer):
    subscriptions = [s for s in _store.table("subscriptions").rows()
                     if s["external_customer_id"] == customer["external_id"]]
    return {"lago_id": customer["lago_id"],
            "external_id": customer["external_id"], "name": customer["name"],
            "email": customer["email"], "currency": customer["currency"],
            "country": customer["country"],
            "tax_identification_number": customer["tax_identification_number"],
            "address_line1": customer["address_line1"],
            "city": customer["city"], "zipcode": customer["zipcode"],
            "timezone": customer["timezone"],
            "payment_provider": customer["payment_provider"],
            "active_subscriptions_count": len(
                [s for s in subscriptions if s["status"] == "active"]),
            "created_at": customer["created_at"]}


def list_customers(page=1, per_page=20):
    rows = sorted(_store.table("customers").rows(),
                  key=lambda c: c["created_at"])
    return _page([customer_representation(c) for c in rows], page, per_page,
                 "customers")


def get_customer(external_id):
    customer = _store.table("customers").get(external_id)
    if not customer:
        return _not_found("customer", external_id)
    return {"customer": customer_representation(customer)}


def create_customer(payload):
    """Lago upserts on `external_id`, so this is create-or-update."""
    payload = (payload or {}).get("customer") or payload or {}
    external_id = payload.get("external_id")
    if not external_id:
        return _unprocessable("external_id", "value_is_mandatory",
                              "external_id is required")
    email = payload.get("email", "")
    if email and "@" not in email:
        return _unprocessable("email", "value_is_invalid",
                              f"{email!r} is not an email address")
    existing = _store.table("customers").get(external_id)
    customer = {
        "external_id": external_id,
        "lago_id": existing["lago_id"] if existing else _lago_id("cus"),
        "name": payload.get("name", existing["name"] if existing else ""),
        "email": email or (existing["email"] if existing else ""),
        "currency": payload.get("currency",
                                existing["currency"] if existing else "EUR"),
        "country": payload.get("country",
                               existing["country"] if existing else ""),
        "tax_identification_number": payload.get(
            "tax_identification_number",
            existing["tax_identification_number"] if existing else ""),
        "address_line1": payload.get(
            "address_line1", existing["address_line1"] if existing else ""),
        "city": payload.get("city", existing["city"] if existing else ""),
        "zipcode": payload.get("zipcode",
                               existing["zipcode"] if existing else ""),
        "timezone": payload.get("timezone",
                                existing["timezone"] if existing else "UTC"),
        "payment_provider": payload.get(
            "payment_provider",
            existing["payment_provider"] if existing else ""),
        "created_at": existing["created_at"] if existing else _now(),
    }
    _store_insert("customers", customer)
    return {"__status__": 200 if existing else 201,
            "customer": customer_representation(customer),
            "upserted": bool(existing)}


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

def subscription_representation(subscription):
    plan = _store.table("plans").get(subscription["plan_code"])
    return {"lago_id": subscription["lago_id"],
            "external_id": subscription["external_id"],
            "external_customer_id": subscription["external_customer_id"],
            "name": subscription["name"], "plan_code": subscription["plan_code"],
            "plan_interval": plan["interval"] if plan else "",
            "status": subscription["status"],
            "billing_time": subscription["billing_time"],
            "subscription_at": subscription["subscription_at"],
            "started_at": subscription["started_at"],
            "terminated_at": subscription["terminated_at"],
            "current_period_from": subscription["current_period_from"],
            "current_period_to": subscription["current_period_to"]}


def list_subscriptions(external_customer_id=None, status=None, page=1,
                       per_page=20):
    rows = sorted(_store.table("subscriptions").rows(),
                  key=lambda s: s["subscription_at"])
    if external_customer_id:
        if not _store.table("customers").get(external_customer_id):
            return _not_found("customer", external_customer_id)
        rows = [s for s in rows
                if s["external_customer_id"] == external_customer_id]
    if status:
        rows = [s for s in rows if s["status"] == status]
    return _page([subscription_representation(s) for s in rows], page,
                 per_page, "subscriptions")


def get_subscription(external_id):
    subscription = _store.table("subscriptions").get(external_id)
    if not subscription:
        return _not_found("subscription", external_id)
    return {"subscription": subscription_representation(subscription)}


def create_subscription(payload):
    payload = (payload or {}).get("subscription") or payload or {}
    external_id = payload.get("external_id")
    if not external_id:
        return _unprocessable("external_id", "value_is_mandatory",
                              "external_id is required")
    if _store.table("subscriptions").get(external_id):
        return _unprocessable("external_id", "value_already_exist",
                              f"A subscription with external_id "
                              f"{external_id!r} already exists")
    customer_id = payload.get("external_customer_id")
    if not _store.table("customers").get(customer_id or ""):
        return _not_found("customer", customer_id)
    plan_code = payload.get("plan_code")
    plan = _store.table("plans").get(plan_code or "")
    if not plan:
        return _not_found("plan", plan_code)
    billing_time = payload.get("billing_time", "calendar")
    if billing_time not in BILLING_TIMES:
        return _unprocessable("billing_time", "value_is_invalid",
                              f"billing_time must be one of "
                              f"{', '.join(BILLING_TIMES)}")
    customer = _store.table("customers").get(customer_id)
    if plan["amount_currency"] != customer["currency"]:
        # A plan carries its own currency, so a customer can only subscribe to
        # one priced in theirs --- otherwise the invoice would mix two.
        return _unprocessable("plan_code", "value_is_invalid",
                              f"Plan {plan_code} is priced in "
                              f"{plan['amount_currency']} but customer "
                              f"{customer_id} settles in "
                              f"{customer['currency']}")
    started = payload.get("subscription_at") or _now()
    subscription = {
        "external_id": external_id, "lago_id": _lago_id("sub"),
        "external_customer_id": customer_id, "plan_code": plan_code,
        "name": payload.get("name", plan["name"]), "status": "active",
        "billing_time": billing_time, "subscription_at": started,
        "started_at": started, "terminated_at": "",
        "current_period_from": payload.get("current_period_from", started),
        "current_period_to": payload.get("current_period_to", ""),
    }
    _store_insert("subscriptions", subscription)
    return {"__status__": 201,
            "subscription": subscription_representation(subscription)}


def terminate_subscription(external_id):
    subscription = _store.table("subscriptions").get(external_id)
    if not subscription:
        return _not_found("subscription", external_id)
    if subscription["status"] == "terminated":
        return _unprocessable("status", "value_is_invalid",
                              f"Subscription {external_id} is already "
                              f"terminated")
    updated = {**subscription, "status": "terminated",
               "terminated_at": _now()}
    _store_insert("subscriptions", updated)
    return {"subscription": subscription_representation(updated)}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def event_representation(event):
    return {"lago_id": event["lago_id"],
            "transaction_id": event["transaction_id"],
            "external_subscription_id": event["external_subscription_id"],
            "code": event["code"], "timestamp": event["timestamp"],
            "properties": event["properties"],
            "created_at": event["created_at"]}


def get_event(transaction_id):
    event = _store.table("events").get(transaction_id)
    if not event:
        return _not_found("event", transaction_id)
    return {"event": event_representation(event)}


def list_events(external_subscription_id=None, code=None, page=1, per_page=20):
    rows = sorted(_events(), key=lambda e: e["timestamp"], reverse=True)
    if external_subscription_id:
        rows = [e for e in rows
                if e["external_subscription_id"] == external_subscription_id]
    if code:
        rows = [e for e in rows if e["code"] == code]
    return _page([event_representation(e) for e in rows], page, per_page,
                 "events")


def _validate_event(entry):
    transaction_id = entry.get("transaction_id")
    if not transaction_id:
        return None, _unprocessable("transaction_id", "value_is_mandatory",
                                    "transaction_id is required")
    if _store.table("events").get(transaction_id):
        # Ingestion is idempotent on the caller's own key: a repeat is refused
        # rather than silently billed twice.
        return None, _unprocessable("transaction_id", "value_already_exist",
                                    f"transaction_id {transaction_id!r} has "
                                    f"already been ingested")
    subscription_id = entry.get("external_subscription_id")
    subscription = _store.table("subscriptions").get(subscription_id or "")
    if not subscription:
        return None, _not_found("subscription", subscription_id)
    if subscription["status"] != "active":
        return None, _unprocessable("external_subscription_id",
                                    "value_is_invalid",
                                    f"Subscription {subscription_id} is "
                                    f"{subscription['status']} and cannot "
                                    f"receive usage")
    code = entry.get("code")
    metric = _store.table("billable_metrics").get(code or "")
    if not metric:
        return None, _not_found("billable_metric", code)
    charge = _store.table("charges").get(
        f"{subscription['plan_code']}#{code}")
    if not charge:
        return None, _unprocessable("code", "value_is_invalid",
                                    f"Plan {subscription['plan_code']} has no "
                                    f"charge for metric {code!r}")
    properties = entry.get("properties") or {}
    if metric["field_name"] and metric["field_name"] not in properties:
        return None, _unprocessable("properties", "value_is_mandatory",
                                    f"{metric['aggregation_type']} on "
                                    f"{code!r} needs properties."
                                    f"{metric['field_name']}")
    return {"transaction_id": transaction_id, "lago_id": _lago_id("ev"),
            "external_subscription_id": subscription_id, "code": code,
            "timestamp": entry.get("timestamp") or _now(),
            "properties": properties, "invoice_id": "",
            "created_at": _now()}, None


def create_event(payload):
    entry = (payload or {}).get("event") or payload or {}
    event, failure = _validate_event(entry)
    if failure:
        return failure
    _store_insert("events", event)
    return {"__status__": 200, "event": event_representation(event)}


def create_events_batch(payload):
    """All or nothing: one bad entry rejects the batch, naming its index."""
    entries = (payload or {}).get("events") or []
    if not isinstance(entries, list) or not entries:
        return _unprocessable("events", "value_is_mandatory",
                              "events must be a non-empty array")
    if len(entries) > 100:
        return _unprocessable("events", "value_is_invalid",
                              "a batch may carry at most 100 events")
    prepared = []
    seen = set()
    for index, entry in enumerate(entries):
        transaction_id = (entry or {}).get("transaction_id")
        if transaction_id in seen:
            return _unprocessable(f"events[{index}].transaction_id",
                                  "value_already_exist",
                                  f"transaction_id {transaction_id!r} appears "
                                  f"twice in the same batch")
        seen.add(transaction_id)
        event, failure = _validate_event(entry or {})
        if failure:
            failure["details"] = {f"events[{index}]": failure["details"]}
            return failure
        prepared.append(event)
    for event in prepared:
        _store_insert("events", event)
    return {"__status__": 200,
            "events": [event_representation(e) for e in prepared]}


# ---------------------------------------------------------------------------
# Current usage --- the endpoint people integrate against
# ---------------------------------------------------------------------------

def _period_events(subscription, code=None):
    start = subscription["current_period_from"]
    end = subscription["current_period_to"]
    rows = [e for e in _events()
            if e["external_subscription_id"] == subscription["external_id"]]
    if start:
        rows = [e for e in rows if e["timestamp"] >= start]
    if end:
        rows = [e for e in rows if e["timestamp"] < end]
    if code:
        rows = [e for e in rows if e["code"] == code]
    return rows


def _usage_for(subscription):
    plan = _store.table("plans").get(subscription["plan_code"])
    charges = _charges_for(subscription["plan_code"])
    fees = []
    total = 0
    for charge in charges:
        metric = _store.table("billable_metrics").get(
            charge["billable_metric_code"])
        if not metric:
            continue
        events = _period_events(subscription, metric["code"])
        units = aggregate(metric, events)
        amount, breakdown = apply_charge(charge, units, len(events))
        if amount < charge["min_amount_cents"]:
            amount = charge["min_amount_cents"]
        total += amount
        fees.append({
            "billable_metric_code": metric["code"],
            "billable_metric_name": metric["name"],
            "aggregation_type": metric["aggregation_type"],
            "charge_model": charge["charge_model"],
            "events_count": len(events),
            "units": units,
            "amount_cents": amount,
            "amount_currency": plan["amount_currency"] if plan else "EUR",
            "breakdown": breakdown,
        })
    return plan, fees, total


def current_usage(external_customer_id, external_subscription_id):
    customer = _store.table("customers").get(external_customer_id)
    if not customer:
        return _not_found("customer", external_customer_id)
    if not external_subscription_id:
        return _unprocessable("external_subscription_id",
                              "value_is_mandatory",
                              "external_subscription_id is required")
    subscription = _store.table("subscriptions").get(external_subscription_id)
    if not subscription:
        return _not_found("subscription", external_subscription_id)
    if subscription["external_customer_id"] != external_customer_id:
        return _unprocessable("external_subscription_id", "value_is_invalid",
                              f"Subscription {external_subscription_id} "
                              f"belongs to "
                              f"{subscription['external_customer_id']}, not "
                              f"{external_customer_id}")
    if subscription["status"] != "active":
        return _unprocessable("external_subscription_id", "value_is_invalid",
                              f"Subscription {external_subscription_id} is "
                              f"{subscription['status']} and has no open "
                              f"period")
    plan, fees, total = _usage_for(subscription)
    return {"customer_usage": {
        "from_datetime": subscription["current_period_from"],
        "to_datetime": subscription["current_period_to"],
        "issuing_date": subscription["current_period_to"][:10],
        "currency": plan["amount_currency"] if plan else "EUR",
        "amount_cents": total,
        "taxes_amount_cents": 0,
        "total_amount_cents": total,
        "lago_invoice_id": None,
        "charges_usage": fees,
        "note": "recomputed from the events in the open period on every read; "
                "no invoice exists yet"}}


def estimate_fees(payload):
    """What would this usage cost, without ingesting anything?"""
    payload = (payload or {}).get("event") or payload or {}
    subscription_id = payload.get("external_subscription_id")
    subscription = _store.table("subscriptions").get(subscription_id or "")
    if not subscription:
        return _not_found("subscription", subscription_id)
    code = payload.get("code")
    metric = _store.table("billable_metrics").get(code or "")
    if not metric:
        return _not_found("billable_metric", code)
    charge = _store.table("charges").get(f"{subscription['plan_code']}#{code}")
    if not charge:
        return _unprocessable("code", "value_is_invalid",
                              f"Plan {subscription['plan_code']} has no charge "
                              f"for metric {code!r}")
    plan = _store.table("plans").get(subscription["plan_code"])
    existing = _period_events(subscription, code)
    hypothetical = {"properties": payload.get("properties") or {},
                    "timestamp": payload.get("timestamp") or _now()}
    before_units = aggregate(metric, existing)
    before_amount, _ = apply_charge(charge, before_units, len(existing))
    after_units = aggregate(metric, existing + [hypothetical])
    after_amount, breakdown = apply_charge(charge, after_units,
                                           len(existing) + 1)
    return {"fees": [{
        "lago_id": None, "billable_metric_code": code,
        "charge_model": charge["charge_model"],
        "units": after_units,
        "amount_cents": after_amount,
        "amount_currency": plan["amount_currency"] if plan else "EUR",
        "incremental_amount_cents": after_amount - before_amount,
        "breakdown": breakdown,
        "note": "estimate only; nothing was ingested"}]}


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

def _fees_for(invoice_id):
    return sorted((f for f in _store.table("invoice_fees").rows()
                   if f["invoice_id"] == invoice_id),
                  key=lambda f: (f["fee_type"] != "subscription",
                                 f["billable_metric_code"]))


def invoice_representation(invoice):
    fees = _fees_for(invoice["lago_id"])
    subtotal = sum(f["amount_cents"] for f in fees)
    discounted = max(0, subtotal - invoice["coupons_amount_cents"])
    taxes = (discounted * invoice["taxes_rate_bps"] + 5000) // 10000
    total = discounted + taxes
    due = max(0, total - invoice["credit_notes_amount_cents"]
              - invoice["prepaid_credit_amount_cents"])
    return {
        "lago_id": invoice["lago_id"], "number": invoice["number"],
        "sequential_id": invoice["sequential_id"],
        "external_customer_id": invoice["external_customer_id"],
        "external_subscription_id": invoice["external_subscription_id"],
        "invoice_type": invoice["invoice_type"], "status": invoice["status"],
        "payment_status": invoice["payment_status"],
        "currency": invoice["currency"],
        "issuing_date": invoice["issuing_date"],
        "payment_due_date": invoice["payment_due_date"],
        "fees_amount_cents": subtotal,
        "coupons_amount_cents": invoice["coupons_amount_cents"],
        "sub_total_excluding_taxes_cents": discounted,
        "taxes_rate_bps": invoice["taxes_rate_bps"],
        "taxes_amount_cents": taxes,
        "total_amount_cents": total,
        "credit_notes_amount_cents": invoice["credit_notes_amount_cents"],
        "prepaid_credit_amount_cents": invoice["prepaid_credit_amount_cents"],
        "total_due_amount_cents": due,
        "period_from": invoice["period_from"], "period_to": invoice["period_to"],
        "voided_at": invoice["voided_at"],
        "fees": [{"lago_id": f["lago_id"], "fee_type": f["fee_type"],
                  "billable_metric_code": f["billable_metric_code"],
                  "charge_model": f["charge_model"], "units": f["units"],
                  "amount_cents": f["amount_cents"],
                  "description": f["description"]} for f in fees],
        "created_at": invoice["created_at"],
    }


def list_invoices(external_customer_id=None, status=None, payment_status=None,
                  page=1, per_page=20):
    rows = sorted(_store.table("invoices").rows(),
                  key=lambda i: i["created_at"], reverse=True)
    if external_customer_id:
        rows = [i for i in rows
                if i["external_customer_id"] == external_customer_id]
    if status:
        if status not in ("draft", "finalized", "voided"):
            return _unprocessable("status", "value_is_invalid",
                                  "status must be draft, finalized or voided")
        rows = [i for i in rows if i["status"] == status]
    if payment_status:
        rows = [i for i in rows if i["payment_status"] == payment_status]
    return _page([invoice_representation(i) for i in rows], page, per_page,
                 "invoices")


def get_invoice(lago_id):
    invoice = _store.table("invoices").get(lago_id)
    if not invoice:
        return _not_found("invoice", lago_id)
    return {"invoice": invoice_representation(invoice)}


def update_invoice(lago_id, payload):
    invoice = _store.table("invoices").get(lago_id)
    if not invoice:
        return _not_found("invoice", lago_id)
    payload = (payload or {}).get("invoice") or payload or {}
    status = payload.get("payment_status")
    if status is None:
        return _unprocessable("payment_status", "value_is_mandatory",
                              "payment_status is required")
    if status not in ("pending", "succeeded", "failed"):
        return _unprocessable("payment_status", "value_is_invalid",
                              "payment_status must be pending, succeeded or "
                              "failed")
    if invoice["status"] == "draft":
        return _unprocessable("status", "value_is_invalid",
                              f"Invoice {lago_id} is a draft; finalize it "
                              f"before recording a payment")
    updated = {**invoice, "payment_status": status}
    _store_insert("invoices", updated)
    return {"invoice": invoice_representation(updated)}


def finalize_invoice(lago_id):
    invoice = _store.table("invoices").get(lago_id)
    if not invoice:
        return _not_found("invoice", lago_id)
    if invoice["status"] != "draft":
        return _unprocessable("status", "value_is_invalid",
                              f"Only a draft can be finalized; invoice "
                              f"{lago_id} is {invoice['status']}")
    # A draft carries a placeholder number; finalizing assigns the real one,
    # ORB-{year}-{sequential}-{attempt}.
    number = (f"ORB-{invoice['issuing_date'][:4]}-"
              f"{invoice['sequential_id']:04d}-001")
    updated = {**invoice, "status": "finalized", "number": number}
    _store_insert("invoices", updated)
    return {"invoice": invoice_representation(updated)}


def void_invoice(lago_id):
    invoice = _store.table("invoices").get(lago_id)
    if not invoice:
        return _not_found("invoice", lago_id)
    if invoice["status"] != "finalized":
        return _unprocessable("status", "value_is_invalid",
                              f"Only a finalized invoice can be voided; "
                              f"invoice {lago_id} is {invoice['status']}")
    if invoice["payment_status"] == "succeeded":
        return _unprocessable("payment_status", "value_is_invalid",
                              f"Invoice {lago_id} is paid; issue a credit note "
                              f"instead of voiding it")
    updated = {**invoice, "status": "voided", "voided_at": _now()}
    _store_insert("invoices", updated)
    return {"invoice": invoice_representation(updated)}


def refresh_invoice(lago_id):
    """Recompute a draft's fees from the usage as it stands right now."""
    invoice = _store.table("invoices").get(lago_id)
    if not invoice:
        return _not_found("invoice", lago_id)
    if invoice["status"] != "draft":
        return _unprocessable("status", "value_is_invalid",
                              f"Only a draft can be refreshed; invoice "
                              f"{lago_id} is {invoice['status']}")
    subscription = _store.table("subscriptions").get(
        invoice["external_subscription_id"])
    if not subscription:
        return _not_found("subscription", invoice["external_subscription_id"])
    plan, fees, _total = _usage_for(subscription)
    _store.table("invoice_fees").delete_where(
        lambda f, _id=lago_id: f["invoice_id"] == _id)
    if plan:
        _store_insert("invoice_fees", {
            "_pk": f"{lago_id}#subscription", "lago_id": _lago_id("fee"),
            "invoice_id": lago_id, "fee_type": "subscription",
            "billable_metric_code": "", "charge_model": "", "units": 1,
            "amount_cents": plan["amount_cents"],
            "description": f"{plan['name']}, {invoice['period_from'][:10]} to "
                           f"{invoice['period_to'][:10]}"})
    for fee in fees:
        _store_insert("invoice_fees", {
            "_pk": f"{lago_id}#{fee['billable_metric_code']}",
            "lago_id": _lago_id("fee"), "invoice_id": lago_id,
            "fee_type": "charge",
            "billable_metric_code": fee["billable_metric_code"],
            "charge_model": fee["charge_model"], "units": fee["units"],
            "amount_cents": fee["amount_cents"],
            "description": f"{fee['billable_metric_name']}, "
                           f"{fee['charge_model']}"})
    return {"invoice": invoice_representation(
        _store.table("invoices").get(lago_id))}


# ---------------------------------------------------------------------------
# Credit notes and wallets
# ---------------------------------------------------------------------------

_CREDIT_NOTE_REASONS = ("duplicated_charge", "product_unsatisfactory",
                        "order_change", "order_cancellation",
                        "fraudulent_charge", "other")


def list_credit_notes(external_customer_id=None, page=1, per_page=20):
    rows = sorted(_store.table("credit_notes").rows(),
                  key=lambda c: c["created_at"], reverse=True)
    if external_customer_id:
        rows = [c for c in rows
                if c["external_customer_id"] == external_customer_id]
    return _page(rows, page, per_page, "credit_notes")


def get_credit_note(lago_id):
    note = _store.table("credit_notes").get(lago_id)
    if not note:
        return _not_found("credit_note", lago_id)
    return {"credit_note": note}


def create_credit_note(payload):
    payload = (payload or {}).get("credit_note") or payload or {}
    invoice_id = payload.get("invoice_id")
    invoice = _store.table("invoices").get(invoice_id or "")
    if not invoice:
        return _not_found("invoice", invoice_id)
    if invoice["status"] != "finalized":
        return _unprocessable("invoice_id", "value_is_invalid",
                              f"A credit note needs a finalized invoice; "
                              f"{invoice_id} is {invoice['status']}")
    reason = payload.get("reason", "other")
    if reason not in _CREDIT_NOTE_REASONS:
        return _unprocessable("reason", "value_is_invalid",
                              f"reason must be one of "
                              f"{', '.join(_CREDIT_NOTE_REASONS)}")
    amount = payload.get("credit_amount_cents", 0)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return _unprocessable("credit_amount_cents", "value_is_invalid",
                              "credit_amount_cents must be a positive whole "
                              "number of cents")
    rendered = invoice_representation(invoice)
    already = invoice["credit_notes_amount_cents"]
    if already + amount > rendered["total_amount_cents"]:
        return _unprocessable(
            "credit_amount_cents", "value_is_invalid",
            f"Cannot credit {amount}; only "
            f"{rendered['total_amount_cents'] - already} remains creditable on "
            f"{invoice_id}")
    note_id = _lago_id("cn")
    sequence = len(_store.table("credit_notes").rows()) + 1
    note = {"lago_id": note_id,
            "number": f"{invoice['number']}-CN{sequence:02d}",
            "invoice_id": invoice_id,
            "external_customer_id": invoice["external_customer_id"],
            "reason": reason, "description": payload.get("description", ""),
            "credit_status": "available", "refund_status": "pending",
            "currency": invoice["currency"], "credit_amount_cents": amount,
            "refund_amount_cents": 0, "balance_amount_cents": amount,
            "created_at": _now()}
    _store_insert("credit_notes", note)
    _store_insert("invoices", {**invoice,
                               "credit_notes_amount_cents": already + amount})
    return {"__status__": 201, "credit_note": note}


def list_wallets(external_customer_id=None, page=1, per_page=20):
    rows = sorted(_store.table("wallets").rows(), key=lambda w: w["created_at"])
    if external_customer_id:
        rows = [w for w in rows
                if w["external_customer_id"] == external_customer_id]
    return _page(rows, page, per_page, "wallets")


def get_wallet(lago_id):
    wallet = _store.table("wallets").get(lago_id)
    if not wallet:
        return _not_found("wallet", lago_id)
    return {"wallet": wallet}


def create_wallet(payload):
    payload = (payload or {}).get("wallet") or payload or {}
    customer_id = payload.get("external_customer_id")
    customer = _store.table("customers").get(customer_id or "")
    if not customer:
        return _not_found("customer", customer_id)
    rate = payload.get("rate_amount_cents", 100)
    credits = payload.get("granted_credits", 0)
    if not isinstance(credits, int) or isinstance(credits, bool) \
            or credits <= 0:
        return _unprocessable("granted_credits", "value_is_invalid",
                              "granted_credits must be a positive whole number")
    wallet = {"lago_id": _lago_id("wal"), "external_customer_id": customer_id,
              "name": payload.get("name", f"{customer['name']} credits"),
              "status": "active", "currency": customer["currency"],
              "rate_amount_cents": rate, "credits_balance": credits,
              "balance_cents": credits * rate, "consumed_credits": 0,
              "expiration_at": payload.get("expiration_at", ""),
              "created_at": _now()}
    _store_insert("wallets", wallet)
    return {"__status__": 201, "wallet": wallet}


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def gross_revenue(currency=None):
    buckets = {}
    for invoice in _store.table("invoices").rows():
        if invoice["status"] != "finalized":
            continue
        if currency and invoice["currency"] != currency:
            continue
        month = invoice["issuing_date"][:7]
        rendered = invoice_representation(invoice)
        key = (month, invoice["currency"])
        buckets[key] = buckets.get(key, 0) + rendered["total_amount_cents"]
    return {"gross_revenues": [
        {"month": month, "currency": code, "amount_cents": amount}
        for (month, code), amount in sorted(buckets.items())]}


def mrr(currency=None):
    """Monthly recurring revenue from active subscriptions' plan fees."""
    buckets = {}
    per_interval = {"weekly": 4, "monthly": 1, "quarterly": 3, "yearly": 12}
    for subscription in _store.table("subscriptions").rows():
        if subscription["status"] != "active":
            continue
        plan = _store.table("plans").get(subscription["plan_code"])
        if not plan:
            continue
        if currency and plan["amount_currency"] != currency:
            continue
        divisor = per_interval.get(plan["interval"], 1)
        monthly = plan["amount_cents"] // divisor
        buckets[plan["amount_currency"]] = buckets.get(
            plan["amount_currency"], 0) + monthly
    return {"mrrs": [{"currency": code, "amount_cents": amount}
                     for code, amount in sorted(buckets.items())],
            "note": "plan fees only; usage charges are not recurring revenue"}


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def service_info():
    return {"version": LAGO_VERSION, "api_version": API_VERSION,
            "aggregation_types": list(AGGREGATION_TYPES),
            "charge_models": list(CHARGE_MODELS),
            "billable_metrics": len(_store.table("billable_metrics").rows()),
            "plans": len(_store.table("plans").rows()),
            "customers": len(_store.table("customers").rows()),
            "active_subscriptions": len(
                [s for s in _store.table("subscriptions").rows()
                 if s["status"] == "active"]),
            "events": len(_events()),
            "money_note": "amounts are integer cents; per-unit rates are "
                          "millicents (1 cent = 1000) so sub-cent rates stay "
                          "exact, and totals round half-up to cents once"}


_store.eager_load()
