"""Data access module for the Orbit Labs in-house payments service.

This is not a clone of a hosted processor's API. It is the shape a team ends up
with when they build the ledger themselves, and four things follow from that:

* **Every movement of money is double-entry.** A capture, a fee, a refund, a
  dispute and a payout each post balanced legs to `gateway_clearing`,
  `merchant_revenue`, `processing_fees`, `disputed_funds` and
  `bank_settlement`. `/v1/ledger/trial_balance` proves it: debits equal credits
  per currency, always, and the available balance is *derived* from the ledger
  rather than stored beside it.
* **Idempotency keys are mandatory on every write.** A POST without
  `Idempotency-Key` is refused. Replaying a key returns the original response
  with `idempotent_replay: true`; reusing one with a different body is a 409.
  That is the discipline an in-house system needs and a vendor SDK usually
  hides.
* **Payments are a state machine, and it is enforced.** Illegal transitions are
  refused with the actions that *are* available named in the error, and partial
  captures and partial refunds carry running totals so over-capture and
  over-refund are arithmetic, not guesswork.
* **The card decides the outcome.** Each stored payment method carries a
  `behaviour`, so declines, step-up authentication and capture-time failures are
  reproducible rather than random.

Amounts are integers in the currency's minor unit and every amount travels with
its currency; there is no float anywhere in this module.

Mutations are held in process memory and reset on restart.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent

import sys as _sys
_sys.path.insert(0, str(DATA_DIR.parent))
from _mutable_store import (
    read_seed_with_ctx, get_store, opt_int, opt_str)

_store = get_store("inhouse-payments-api")
_API = "inhouse-payments-api"

API_VERSION = "2026-04-01"
SERVICE_NAME = "orbit-payments"

DEBIT_ACCOUNTS = ("gateway_clearing", "processing_fees", "disputed_funds",
                  "bank_settlement")
CREDIT_ACCOUNTS = ("merchant_revenue",)
ACCOUNTS = DEBIT_ACCOUNTS + CREDIT_ACCOUNTS


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


def _load_json(filename):
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _ints(row, *columns):
    return {column: opt_int(row, column, default=0) for column in columns}


def _coerce_payments(rows):
    return [{**_strip_ctx(r),
             **_ints(r, "amount_minor", "captured_minor", "refunded_minor",
                     "fee_minor")} for r in rows]


def _coerce_refunds(rows):
    return [{**_strip_ctx(r), **_ints(r, "amount_minor")} for r in rows]


def _coerce_disputes(rows):
    return [{**_strip_ctx(r), **_ints(r, "amount_minor")} for r in rows]


def _coerce_entries(rows):
    return [{**_strip_ctx(r), **_ints(r, "amount_minor")} for r in rows]


_store.register("customers", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("customers.json", "customers")])
_store.register("payment_methods", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("payment_methods.json",
                                              "payment_methods")])
_store.register("payments", primary_key="id",
                initial_loader=lambda: _coerce_payments(
                    _load("payments.json", "payments")))
_store.register("refunds", primary_key="id",
                initial_loader=lambda: _coerce_refunds(
                    _load("refunds.json", "refunds")))
_store.register("disputes", primary_key="id",
                initial_loader=lambda: _coerce_disputes(
                    _load("disputes.json", "disputes")))
_store.register("ledger_entries", primary_key="id",
                initial_loader=lambda: _coerce_entries(
                    _load("ledger_entries.json", "ledger_entries")))
_store.register("events", primary_key="id",
                initial_loader=lambda: [_strip_ctx(r) for r in
                                        _load("events.json", "events")])
_store.register("payouts", primary_key="id", initial_loader=lambda: [])
# Idempotency records are written at runtime only; a replay must survive for the
# life of the process, which is exactly as long as the rest of the store.
_store.register("idempotency", primary_key="key", initial_loader=lambda: [])
_store.register_document("pricing",
                         initial_loader=lambda: _load_json("pricing.json"))


def _payments():
    return _store.table("payments").rows()


def _pricing():
    return _store.document("pricing").get()


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sequence(table, prefix, width=4):
    """Ids are prefixed and sequential, which is what a home-grown system does."""
    used = [r["id"] for r in _store.table(table).rows()
            if r["id"].startswith(prefix)]
    return f"{prefix}{len(used) + 1:0{width}d}"


def _token(prefix, seed):
    """A stable id derived from the request, so a replay produces the same one."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{prefix}{digest[:12]}"


# ---------------------------------------------------------------------------
# Errors --- a typed envelope, as a payments API needs
# ---------------------------------------------------------------------------

def _error(status, error_type, code, message, param=None, resource=None):
    """`resource` carries the object the call was about, when there is one.

    A declined charge still creates a payment, and a caller needs its id to
    follow up --- so the error envelope carries it rather than throwing it away.
    """
    return {"error": message, "code": status, "message": message,
            "type": error_type, "err_code": code, "param": param,
            "resource": resource}


def _invalid(code, message, param=None):
    return _error(400, "invalid_request_error", code, message, param)


def _missing(kind, identifier):
    return _error(404, "not_found_error", "resource_missing",
                  f"No such {kind}: {identifier}", "id")


def _card_error(code, message, resource=None):
    """A declined card is 402 Payment Required --- the request was well formed."""
    return _error(402, "card_error", code, message, "payment_method", resource)


def _state_error(code, message):
    return _error(409, "state_error", code, message, "status")


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def _fingerprint(endpoint, payload):
    body = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{endpoint}|{body}".encode("utf-8")).hexdigest()


def idempotency_check(endpoint, key, payload):
    """Return a replay, a conflict, or None to say "go ahead".

    Every write needs a key. This is deliberately stricter than most hosted
    APIs, which treat the header as optional: an in-house ledger that double
    charges is a much worse problem than a rejected request.
    """
    if not key:
        return _error(400, "idempotency_error", "idempotency_key_required",
                      "Every write requires an Idempotency-Key header",
                      "Idempotency-Key")
    record = _store.table("idempotency").get(key)
    if not record:
        return None
    fingerprint = _fingerprint(endpoint, payload)
    if record["fingerprint"] != fingerprint:
        return _error(409, "idempotency_error", "idempotency_key_reuse",
                      f"Idempotency-Key {key!r} was already used for a "
                      f"different request ({record['endpoint']})",
                      "Idempotency-Key")
    return {"__status__": record["status_code"],
            **record["response"], "idempotent_replay": True}


def _remember(endpoint, key, payload, result):
    """Store a successful response so the same key replays it verbatim.

    Only successes are recorded. A declined card is not a completed write, so
    the same key may be presented again once the cardholder has fixed whatever
    was wrong --- which is what a caller retrying a decline actually wants.
    """
    if not key or "error" in result:
        return result
    body = {k: v for k, v in result.items() if k != "__status__"}
    _store_insert("idempotency", {
        "key": key, "endpoint": endpoint,
        "fingerprint": _fingerprint(endpoint, payload),
        "status_code": result.get("__status__", 200), "response": body,
        "created": _now()})
    return result


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

def _fee_for(amount_minor, currency):
    """Integer arithmetic only --- half-up, never a float."""
    schedule = _pricing()["fees"]
    rule = schedule.get(currency, schedule["default"])
    percent = (amount_minor * rule["percent_bps"] + 5000) // 10000
    return percent + rule["fixed_minor"]


def _check_amount(amount_minor, currency):
    pricing = _pricing()
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        return _invalid("amount_invalid",
                        "amount_minor must be a whole number of minor units",
                        "amount_minor")
    if amount_minor <= 0:
        return _invalid("amount_invalid", "amount_minor must be positive",
                        "amount_minor")
    if currency not in pricing["supported_currencies"]:
        return _invalid("currency_unsupported",
                        f"{currency!r} is not supported; this account settles "
                        f"in {', '.join(pricing['supported_currencies'])}",
                        "currency")
    minimum = pricing["minimum_charge_minor"].get(currency, 0)
    if amount_minor < minimum:
        return _invalid("amount_too_small",
                        f"The minimum charge in {currency} is {minimum} minor "
                        f"units", "amount_minor")
    return None


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------

def _post(legs, currency, source_type, source, memo, stamp=None):
    """Write a balanced set of ledger entries, or refuse to write any.

    The balance assertion is not decoration: it is the invariant the whole
    service is built around, and a caller that gets the legs wrong should fail
    loudly here rather than leave the books crooked.
    """
    debits = sum(a for account, direction, a in legs if direction == "debit")
    credits = sum(a for account, direction, a in legs if direction == "credit")
    if debits != credits:
        raise AssertionError(
            f"unbalanced ledger posting for {source}: {debits} != {credits}")
    stamp = stamp or _now()
    written = []
    for account, direction, amount in legs:
        entry = {"id": _sequence("ledger_entries", "le_"), "account": account,
                 "direction": direction, "amount_minor": amount,
                 "currency": currency, "source_type": source_type,
                 "source": source, "memo": memo, "created": stamp}
        _store_insert("ledger_entries", entry)
        written.append(entry)
    return written


def _account_balance(account, currency):
    total = 0
    for entry in _store.table("ledger_entries").rows():
        if entry["account"] != account or entry["currency"] != currency:
            continue
        total += entry["amount_minor"] if entry["direction"] == "debit" \
            else -entry["amount_minor"]
    return total


def _currencies():
    seen = {e["currency"] for e in _store.table("ledger_entries").rows()}
    return sorted(seen or {"EUR"})


def list_ledger_entries(source=None, account=None, currency=None, limit=100,
                        offset=0):
    rows = sorted(_store.table("ledger_entries").rows(), key=lambda e: e["id"])
    if source:
        rows = [e for e in rows if e["source"] == source]
    if account:
        if account not in ACCOUNTS:
            return _invalid("account_unknown",
                            f"{account!r} is not a ledger account; expected one "
                            f"of {', '.join(ACCOUNTS)}", "account")
        rows = [e for e in rows if e["account"] == account]
    if currency:
        rows = [e for e in rows if e["currency"] == currency]
    return _page(rows, limit, offset, "/v1/ledger/entries")


def trial_balance():
    """Debits and credits per account and currency; the totals must agree."""
    books = []
    for currency in _currencies():
        accounts = []
        debits = credits = 0
        for account in ACCOUNTS:
            account_debits = sum(
                e["amount_minor"] for e in _store.table("ledger_entries").rows()
                if e["account"] == account and e["currency"] == currency
                and e["direction"] == "debit")
            account_credits = sum(
                e["amount_minor"] for e in _store.table("ledger_entries").rows()
                if e["account"] == account and e["currency"] == currency
                and e["direction"] == "credit")
            if not account_debits and not account_credits:
                continue
            accounts.append({"account": account, "debit_minor": account_debits,
                             "credit_minor": account_credits,
                             "net_minor": account_debits - account_credits})
            debits += account_debits
            credits += account_credits
        books.append({"currency": currency, "accounts": accounts,
                      "total_debit_minor": debits,
                      "total_credit_minor": credits,
                      "balanced": debits == credits})
    return {"object": "trial_balance", "as_of": _now(), "books": books,
            "balanced": all(b["balanced"] for b in books)}


def balance():
    """Available funds are *derived* from the ledger, never stored beside it."""
    available = []
    for currency in _currencies():
        pending = sum(p["amount_minor"] - p["captured_minor"]
                      for p in _payments()
                      if p["currency"] == currency
                      and p["status"] in ("authorized", "partially_captured"))
        available.append({
            "currency": currency,
            "available_minor": _account_balance("gateway_clearing", currency),
            "pending_authorization_minor": pending,
            "disputed_minor": _account_balance("disputed_funds", currency),
            "paid_out_minor": _account_balance("bank_settlement", currency),
        })
    return {"object": "balance", "as_of": _now(), "balances": available,
            "note": "available_minor is the gateway_clearing account balance, "
                    "computed from the ledger at read time"}


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def _emit(event_type, object_type, object_id, summary):
    event = {"id": _sequence("events", "evt_"), "type": event_type,
             "object_type": object_type, "object": object_id,
             "summary": summary, "created": _now()}
    _store_insert("events", event)
    return event


def list_events(object_id=None, event_type=None, limit=100, offset=0):
    rows = sorted(_store.table("events").rows(), key=lambda e: e["created"],
                  reverse=True)
    if object_id:
        rows = [e for e in rows if e["object"] == object_id]
    if event_type:
        rows = [e for e in rows if e["type"] == event_type]
    return _page(rows, limit, offset, "/v1/events")


# ---------------------------------------------------------------------------
# List envelope
# ---------------------------------------------------------------------------

def _page(rows, limit, offset, url):
    limit = max(1, min(int(limit or 100), 100))
    offset = max(0, int(offset or 0))
    window = rows[offset:offset + limit]
    return {"object": "list", "url": url, "data": window,
            "total_count": len(rows),
            "has_more": offset + len(window) < len(rows)}


# ---------------------------------------------------------------------------
# Customers and payment methods
# ---------------------------------------------------------------------------

def list_customers(status=None, limit=100, offset=0):
    rows = sorted(_store.table("customers").rows(), key=lambda c: c["created"])
    if status:
        rows = [c for c in rows if c["status"] == status]
    return _page(rows, limit, offset, "/v1/customers")


def get_customer(customer_id):
    customer = _store.table("customers").get(customer_id)
    if not customer:
        return _missing("customer", customer_id)
    return customer


def create_customer(payload, idempotency_key):
    payload = payload or {}
    guard = idempotency_check("POST /v1/customers", idempotency_key, payload)
    if guard is not None:
        return guard
    name = payload.get("name")
    email = payload.get("email")
    if not name:
        return _invalid("parameter_missing", "name is required", "name")
    if not email or "@" not in email:
        return _invalid("parameter_invalid", "a valid email is required",
                        "email")
    currency = payload.get("currency", "EUR")
    if currency not in _pricing()["supported_currencies"]:
        return _invalid("currency_unsupported",
                        f"{currency!r} is not supported", "currency")
    customer = {"id": _token("cus_", f"{email}|{name}"), "name": name,
                "email": email, "currency": currency, "status": "active",
                "country": payload.get("country", ""),
                "tax_id": payload.get("tax_id", ""),
                "default_payment_method": "", "created": _now()}
    _store_insert("customers", customer)
    _emit("customer.created", "customer", customer["id"],
          f"Created customer {name}")
    return _remember("POST /v1/customers", idempotency_key, payload,
                     {"__status__": 201, **customer})


def list_payment_methods(customer=None, limit=100, offset=0):
    rows = sorted(_store.table("payment_methods").rows(),
                  key=lambda m: m["created"])
    if customer:
        if not _store.table("customers").get(customer):
            return _missing("customer", customer)
        rows = [m for m in rows if m["customer"] == customer]
    return _page(rows, limit, offset, "/v1/payment_methods")


def get_payment_method(method_id):
    method = _store.table("payment_methods").get(method_id)
    if not method:
        return _missing("payment_method", method_id)
    return method


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

_NEXT_ACTIONS = {
    "requires_confirmation": ("confirm", "cancel"),
    "authorized": ("capture", "cancel"),
    "partially_captured": ("capture", "cancel", "refund"),
    "captured": ("refund",),
    "partially_refunded": ("refund",),
    "refunded": (),
    "failed": (),
    "canceled": (),
}

_DECLINES = {
    "decline_insufficient_funds": ("insufficient_funds",
                                   "The card was declined: the account does "
                                   "not have enough funds."),
    "decline_expired_card": ("expired_card",
                             "The card has expired and cannot be charged."),
}


def payment_representation(payment):
    refunds = [r["id"] for r in _store.table("refunds").rows()
               if r["payment"] == payment["id"]]
    disputes = [d["id"] for d in _store.table("disputes").rows()
                if d["payment"] == payment["id"]]
    return {
        "object": "payment",
        "id": payment["id"],
        "customer": payment["customer"],
        "payment_method": payment["payment_method"],
        "amount_minor": payment["amount_minor"],
        "currency": payment["currency"],
        "status": payment["status"],
        "captured_minor": payment["captured_minor"],
        "refunded_minor": payment["refunded_minor"],
        "capturable_minor": max(0, payment["amount_minor"]
                                - payment["captured_minor"])
                            if payment["status"] in ("authorized",
                                                     "partially_captured")
                            else 0,
        "refundable_minor": max(0, payment["captured_minor"]
                                - payment["refunded_minor"]),
        "fee_minor": payment["fee_minor"],
        "net_minor": payment["captured_minor"] - payment["refunded_minor"]
                     - payment["fee_minor"],
        "description": payment["description"],
        "statement_descriptor": payment["statement_descriptor"],
        "failure_code": payment["failure_code"],
        "failure_message": payment["failure_message"],
        "next_actions": list(_NEXT_ACTIONS.get(payment["status"], ())),
        "refunds": refunds,
        "disputes": disputes,
        "created": payment["created"],
        "authorized_at": payment["authorized_at"],
        "captured_at": payment["captured_at"],
    }


def list_payments(customer=None, status=None, currency=None, limit=100,
                  offset=0):
    rows = sorted(_payments(), key=lambda p: p["created"], reverse=True)
    if customer:
        if not _store.table("customers").get(customer):
            return _missing("customer", customer)
        rows = [p for p in rows if p["customer"] == customer]
    if status:
        if status not in _NEXT_ACTIONS:
            return _invalid("status_unknown",
                            f"{status!r} is not a payment status; expected one "
                            f"of {', '.join(sorted(_NEXT_ACTIONS))}", "status")
        rows = [p for p in rows if p["status"] == status]
    if currency:
        rows = [p for p in rows if p["currency"] == currency]
    return _page([payment_representation(p) for p in rows], limit, offset,
                 "/v1/payments")


def get_payment(payment_id):
    payment = _store.table("payments").get(payment_id)
    if not payment:
        return _missing("payment", payment_id)
    return payment_representation(payment)


def _guard(payment, action):
    allowed = _NEXT_ACTIONS.get(payment["status"], ())
    if action in allowed:
        return None
    if not allowed:
        return _state_error(
            "payment_terminal",
            f"Payment {payment['id']} is {payment['status']}, which is "
            f"terminal; no further action is possible")
    return _state_error(
        "payment_state_invalid",
        f"Cannot {action} a payment that is {payment['status']}; the available "
        f"actions are {', '.join(allowed)}")


def create_payment(payload, idempotency_key):
    payload = payload or {}
    guard = idempotency_check("POST /v1/payments", idempotency_key, payload)
    if guard is not None:
        return guard
    customer_id = payload.get("customer")
    customer = _store.table("customers").get(customer_id or "")
    if not customer:
        return _missing("customer", customer_id)
    method_id = payload.get("payment_method") \
        or customer["default_payment_method"]
    method = _store.table("payment_methods").get(method_id or "")
    if not method:
        return _missing("payment_method", method_id)
    if method["customer"] != customer["id"]:
        return _invalid("payment_method_mismatch",
                        f"Payment method {method['id']} belongs to "
                        f"{method['customer']}, not {customer['id']}",
                        "payment_method")
    amount = payload.get("amount_minor")
    currency = payload.get("currency", customer["currency"])
    invalid = _check_amount(amount, currency)
    if invalid:
        return invalid
    if currency != customer["currency"]:
        return _invalid("currency_mismatch",
                        f"Customer {customer['id']} settles in "
                        f"{customer['currency']}, not {currency}", "currency")
    if customer["status"] == "delinquent":
        return _card_error("customer_delinquent",
                           f"Customer {customer['id']} is delinquent and "
                           f"cannot be charged")
    payment_id = _token("pay_", f"{idempotency_key}|{customer['id']}|{amount}")
    stamp = _now()
    payment = {
        "id": payment_id, "customer": customer["id"],
        "payment_method": method["id"], "amount_minor": amount,
        "currency": currency, "status": "requires_confirmation",
        "captured_minor": 0, "refunded_minor": 0, "fee_minor": 0,
        "description": payload.get("description", ""),
        "statement_descriptor": payload.get("statement_descriptor",
                                            "ORBIT LABS"),
        "failure_code": "", "failure_message": "",
        "idempotency_key": idempotency_key, "created": stamp,
        "authorized_at": "", "captured_at": "",
    }
    behaviour = method["behaviour"]
    if behaviour in _DECLINES:
        code, message = _DECLINES[behaviour]
        payment.update({"status": "failed", "failure_code": code,
                        "failure_message": message})
        _store_insert("payments", payment)
        _emit("payment.failed", "payment", payment_id, f"Declined: {code}")
        return _card_error(code, message, payment_representation(payment))
    if behaviour in ("requires_confirmation", "confirmation_fails"):
        _store_insert("payments", payment)
        _emit("payment.requires_confirmation", "payment", payment_id,
              "Issuer requested step-up authentication")
    else:
        payment.update({"status": "authorized", "authorized_at": stamp})
        _store_insert("payments", payment)
        _emit("payment.authorized", "payment", payment_id,
              f"Authorized {amount} {currency}, awaiting capture")
    return _remember("POST /v1/payments", idempotency_key, payload,
                     {"__status__": 201,
                      **payment_representation(
                          _store.table("payments").get(payment_id))})


def confirm_payment(payment_id, payload, idempotency_key):
    payload = payload or {}
    endpoint = f"POST /v1/payments/{payment_id}/confirm"
    guard = idempotency_check(endpoint, idempotency_key, payload)
    if guard is not None:
        return guard
    payment = _store.table("payments").get(payment_id)
    if not payment:
        return _missing("payment", payment_id)
    blocked = _guard(payment, "confirm")
    if blocked:
        return blocked
    method = _store.table("payment_methods").get(payment["payment_method"])
    stamp = _now()
    if method and method["behaviour"] == "confirmation_fails":
        updated = {**payment, "status": "failed",
                   "failure_code": "authentication_failed",
                   "failure_message": "The cardholder failed step-up "
                                      "authentication."}
        _store_insert("payments", updated)
        _emit("payment.failed", "payment", payment_id,
              "Declined: authentication_failed")
        return _card_error("authentication_failed",
                           updated["failure_message"],
                           payment_representation(updated))
    updated = {**payment, "status": "authorized", "authorized_at": stamp}
    _store_insert("payments", updated)
    _emit("payment.authorized", "payment", payment_id,
          f"Authenticated and authorized {payment['amount_minor']} "
          f"{payment['currency']}")
    return _remember(endpoint, idempotency_key, payload,
                     payment_representation(updated))


def capture_payment(payment_id, payload, idempotency_key):
    payload = payload or {}
    endpoint = f"POST /v1/payments/{payment_id}/capture"
    guard = idempotency_check(endpoint, idempotency_key, payload)
    if guard is not None:
        return guard
    payment = _store.table("payments").get(payment_id)
    if not payment:
        return _missing("payment", payment_id)
    blocked = _guard(payment, "capture")
    if blocked:
        return blocked
    outstanding = payment["amount_minor"] - payment["captured_minor"]
    amount = payload.get("amount_minor", outstanding)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return _invalid("amount_invalid",
                        "amount_minor must be a positive whole number",
                        "amount_minor")
    if amount > outstanding:
        return _invalid("amount_too_large",
                        f"Cannot capture {amount}; only {outstanding} "
                        f"{payment['currency']} remains authorized on "
                        f"{payment_id}", "amount_minor")
    method = _store.table("payment_methods").get(payment["payment_method"])
    if method and method["behaviour"] == "capture_fails":
        _emit("payment.capture_failed", "payment", payment_id,
              "Processor refused the capture")
        return _card_error("processor_declined",
                           "The processor refused the capture; the "
                           "authorization remains open and may be retried or "
                           "canceled",
                           payment_representation(payment))
    stamp = _now()
    captured = payment["captured_minor"] + amount
    fee = _fee_for(amount, payment["currency"])
    status = "captured" if captured >= payment["amount_minor"] \
        else "partially_captured"
    updated = {**payment, "captured_minor": captured, "status": status,
               "fee_minor": payment["fee_minor"] + fee, "captured_at": stamp}
    _store_insert("payments", updated)
    _post([("gateway_clearing", "debit", amount),
           ("merchant_revenue", "credit", amount)],
          payment["currency"], "payment", payment_id,
          f"Capture of {payment_id}", stamp)
    _post([("processing_fees", "debit", fee),
           ("gateway_clearing", "credit", fee)],
          payment["currency"], "payment", payment_id,
          f"Processing fee for {payment_id}", stamp)
    _emit("payment.captured", "payment", payment_id,
          f"Captured {amount} {payment['currency']} from {payment['customer']}")
    return _remember(endpoint, idempotency_key, payload,
                     payment_representation(updated))


def cancel_payment(payment_id, payload, idempotency_key):
    payload = payload or {}
    endpoint = f"POST /v1/payments/{payment_id}/cancel"
    guard = idempotency_check(endpoint, idempotency_key, payload)
    if guard is not None:
        return guard
    payment = _store.table("payments").get(payment_id)
    if not payment:
        return _missing("payment", payment_id)
    blocked = _guard(payment, "cancel")
    if blocked:
        return blocked
    released = payment["amount_minor"] - payment["captured_minor"]
    updated = {**payment, "status": "canceled"}
    _store_insert("payments", updated)
    _emit("payment.canceled", "payment", payment_id,
          f"Released {released} {payment['currency']} without capture")
    return _remember(endpoint, idempotency_key, payload,
                     {**payment_representation(updated),
                      "released_minor": released})


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

_REFUND_REASONS = ("requested_by_customer", "duplicate", "fraudulent",
                   "product_unacceptable")


def list_refunds(payment=None, limit=100, offset=0):
    rows = sorted(_store.table("refunds").rows(), key=lambda r: r["created"],
                  reverse=True)
    if payment:
        rows = [r for r in rows if r["payment"] == payment]
    return _page(rows, limit, offset, "/v1/refunds")


def get_refund(refund_id):
    refund = _store.table("refunds").get(refund_id)
    if not refund:
        return _missing("refund", refund_id)
    return refund


def create_refund(payload, idempotency_key):
    payload = payload or {}
    guard = idempotency_check("POST /v1/refunds", idempotency_key, payload)
    if guard is not None:
        return guard
    payment_id = payload.get("payment")
    payment = _store.table("payments").get(payment_id or "")
    if not payment:
        return _missing("payment", payment_id)
    blocked = _guard(payment, "refund")
    if blocked:
        return blocked
    open_dispute = next((d for d in _store.table("disputes").rows()
                         if d["payment"] == payment_id
                         and d["status"] in ("needs_response",
                                             "under_review")), None)
    if open_dispute:
        # Refunding a disputed payment would move the same funds twice: the
        # network has already pulled them.
        return _state_error(
            "payment_disputed",
            f"Payment {payment_id} has an open dispute ({open_dispute['id']}); "
            f"the funds are already withheld and cannot be refunded until it "
            f"is closed")
    refundable = payment["captured_minor"] - payment["refunded_minor"]
    amount = payload.get("amount_minor", refundable)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return _invalid("amount_invalid",
                        "amount_minor must be a positive whole number",
                        "amount_minor")
    if amount > refundable:
        return _invalid("amount_too_large",
                        f"Cannot refund {amount}; only {refundable} "
                        f"{payment['currency']} of {payment_id} remains "
                        f"refundable", "amount_minor")
    reason = payload.get("reason", "requested_by_customer")
    if reason not in _REFUND_REASONS:
        return _invalid("reason_invalid",
                        f"{reason!r} is not a refund reason; expected one of "
                        f"{', '.join(_REFUND_REASONS)}", "reason")
    stamp = _now()
    refund_id = _token("re_", f"{idempotency_key}|{payment_id}|{amount}")
    refund = {"id": refund_id, "payment": payment_id, "amount_minor": amount,
              "currency": payment["currency"], "reason": reason,
              "status": "succeeded", "failure_reason": "",
              "idempotency_key": idempotency_key, "created": stamp}
    _store_insert("refunds", refund)
    refunded = payment["refunded_minor"] + amount
    status = "refunded" if refunded >= payment["captured_minor"] \
        else "partially_refunded"
    _store_insert("payments", {**payment, "refunded_minor": refunded,
                               "status": status})
    _post([("merchant_revenue", "debit", amount),
           ("gateway_clearing", "credit", amount)],
          payment["currency"], "refund", refund_id,
          f"Refund {refund_id} of {payment_id}", stamp)
    _emit("refund.succeeded", "refund", refund_id,
          f"Refunded {amount} {payment['currency']} of {payment_id}")
    return _remember("POST /v1/refunds", idempotency_key, payload,
                     {"__status__": 201, **refund})


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------

_DISPUTE_OPEN = ("needs_response", "under_review")


def list_disputes(payment=None, status=None, limit=100, offset=0):
    rows = sorted(_store.table("disputes").rows(), key=lambda d: d["created"],
                  reverse=True)
    if payment:
        rows = [d for d in rows if d["payment"] == payment]
    if status:
        rows = [d for d in rows if d["status"] == status]
    return _page(rows, limit, offset, "/v1/disputes")


def get_dispute(dispute_id):
    dispute = _store.table("disputes").get(dispute_id)
    if not dispute:
        return _missing("dispute", dispute_id)
    return dispute


def submit_evidence(dispute_id, payload, idempotency_key):
    payload = payload or {}
    endpoint = f"POST /v1/disputes/{dispute_id}/evidence"
    guard = idempotency_check(endpoint, idempotency_key, payload)
    if guard is not None:
        return guard
    dispute = _store.table("disputes").get(dispute_id)
    if not dispute:
        return _missing("dispute", dispute_id)
    if dispute["status"] != "needs_response":
        return _state_error("dispute_not_open",
                            f"Dispute {dispute_id} is {dispute['status']}; "
                            f"evidence can only be submitted while it needs a "
                            f"response")
    evidence = payload.get("evidence")
    if not evidence or not str(evidence).strip():
        return _invalid("parameter_missing",
                        "evidence is required and must not be empty",
                        "evidence")
    stamp = _now()
    if stamp > dispute["evidence_due_by"]:
        return _state_error("evidence_window_closed",
                            f"The evidence window for {dispute_id} closed at "
                            f"{dispute['evidence_due_by']}")
    updated = {**dispute, "status": "under_review", "evidence": evidence,
               "evidence_submitted_at": stamp}
    _store_insert("disputes", updated)
    _emit("dispute.evidence_submitted", "dispute", dispute_id,
          f"Evidence submitted for {dispute_id}")
    return _remember(endpoint, idempotency_key, payload, updated)


def close_dispute(dispute_id, payload, idempotency_key):
    """Resolve a dispute, returning or keeping the withheld funds."""
    payload = payload or {}
    endpoint = f"POST /v1/disputes/{dispute_id}/close"
    guard = idempotency_check(endpoint, idempotency_key, payload)
    if guard is not None:
        return guard
    dispute = _store.table("disputes").get(dispute_id)
    if not dispute:
        return _missing("dispute", dispute_id)
    if dispute["status"] not in _DISPUTE_OPEN:
        return _state_error("dispute_closed",
                            f"Dispute {dispute_id} is already "
                            f"{dispute['status']}")
    resolution = payload.get("resolution")
    if resolution not in ("won", "lost"):
        return _invalid("resolution_invalid",
                        "resolution must be 'won' or 'lost'", "resolution")
    stamp = _now()
    amount = dispute["amount_minor"]
    if resolution == "won":
        # The network returns the funds it withheld when the dispute opened.
        _post([("gateway_clearing", "debit", amount),
               ("disputed_funds", "credit", amount)],
              dispute["currency"], "dispute", dispute_id,
              f"Funds returned, dispute {dispute_id} won", stamp)
    else:
        # The loss is realised against revenue, plus the network's fee.
        fee = _pricing()["dispute_fee_minor"].get(dispute["currency"], 0)
        _post([("merchant_revenue", "debit", amount),
               ("disputed_funds", "credit", amount)],
              dispute["currency"], "dispute", dispute_id,
              f"Chargeback realised, dispute {dispute_id} lost", stamp)
        _post([("processing_fees", "debit", fee),
               ("gateway_clearing", "credit", fee)],
              dispute["currency"], "dispute", dispute_id,
              f"Dispute fee for {dispute_id}", stamp)
    updated = {**dispute, "status": resolution, "resolution": resolution}
    _store_insert("disputes", updated)
    _emit(f"dispute.{resolution}", "dispute", dispute_id,
          f"Dispute {dispute_id} closed as {resolution}")
    return _remember(endpoint, idempotency_key, payload, updated)


# ---------------------------------------------------------------------------
# Payouts
# ---------------------------------------------------------------------------

def list_payouts(currency=None, limit=100, offset=0):
    rows = sorted(_store.table("payouts").rows(), key=lambda p: p["created"],
                  reverse=True)
    if currency:
        rows = [p for p in rows if p["currency"] == currency]
    return _page(rows, limit, offset, "/v1/payouts")


def get_payout(payout_id):
    payout = _store.table("payouts").get(payout_id)
    if not payout:
        return _missing("payout", payout_id)
    return payout


def create_payout(payload, idempotency_key):
    payload = payload or {}
    guard = idempotency_check("POST /v1/payouts", idempotency_key, payload)
    if guard is not None:
        return guard
    currency = payload.get("currency", "EUR")
    pricing = _pricing()
    if currency not in pricing["supported_currencies"]:
        return _invalid("currency_unsupported",
                        f"{currency!r} is not supported", "currency")
    available = _account_balance("gateway_clearing", currency)
    amount = payload.get("amount_minor", available)
    if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return _invalid("amount_invalid",
                        "amount_minor must be a positive whole number",
                        "amount_minor")
    minimum = pricing["payout_minimum_minor"].get(currency, 0)
    if amount < minimum:
        return _invalid("amount_too_small",
                        f"The minimum payout in {currency} is {minimum} minor "
                        f"units", "amount_minor")
    if amount > available:
        return _invalid("insufficient_balance",
                        f"Cannot pay out {amount}; the available {currency} "
                        f"balance is {available}", "amount_minor")
    stamp = _now()
    payout_id = _token("po_", f"{idempotency_key}|{currency}|{amount}")
    arrival = (datetime.now(timezone.utc) + timedelta(days=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    payout = {"id": payout_id, "amount_minor": amount, "currency": currency,
              "status": "in_transit", "destination": payload.get(
                  "destination", "ES91 2100 0418 4502 0005 1332"),
              "statement_descriptor": payload.get("statement_descriptor",
                                                  "ORBIT LABS PAYOUT"),
              "arrival_date": arrival,
              "idempotency_key": idempotency_key, "created": stamp}
    _store_insert("payouts", payout)
    _post([("bank_settlement", "debit", amount),
           ("gateway_clearing", "credit", amount)],
          currency, "payout", payout_id, f"Payout {payout_id}", stamp)
    _emit("payout.created", "payout", payout_id,
          f"Paid out {amount} {currency}, arriving {arrival}")
    return _remember("POST /v1/payouts", idempotency_key, payload,
                     {"__status__": 201, **payout})


# ---------------------------------------------------------------------------
# Service state
# ---------------------------------------------------------------------------

def health():
    return {"status": "ok"}


def service_info():
    return {"service": SERVICE_NAME, "api_version": API_VERSION,
            "supported_currencies": _pricing()["supported_currencies"],
            "fees": _pricing()["fees"],
            "payout_schedule": _pricing()["payout_schedule"],
            "ledger_accounts": list(ACCOUNTS),
            "payments": len(_payments()),
            "idempotency_keys_seen": len(_store.table("idempotency").rows())}


_store.eager_load()
