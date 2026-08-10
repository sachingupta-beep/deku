"""FastAPI server wrapping inhouse_payments_data module as REST endpoints.

The Orbit Labs in-house payments service. Three things about the wiring are
worth reading before the routes:

* **Every POST takes an `Idempotency-Key` header, and refuses without one.**
  That is stricter than most hosted APIs and deliberate: an in-house ledger
  that double-charges is worse than a rejected request.
* **Errors are a typed envelope**, not a bare string:
  `{"error": {"type", "code", "message", "param"}}`. A declined card is
  **402** and carries the payment it created under `resource`, so the caller
  can follow it up.
* **`/v1/ledger/*` is a first-class part of the API**, not an admin extra. The
  balance is derived from those entries at read time rather than stored beside
  them, which is the whole point of building the ledger yourself.
"""

from fastapi import Body, FastAPI, Header, Query, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional

import inhouse_payments_data as payments_data
try:
    from tracking_middleware import install_tracker
    from admin_plane import install_admin_plane
except ModuleNotFoundError as _shared_plane_err:  # standalone run without the shared module on sys.path
    import logging as _logging
    _logging.error("SHARED PLANE MISSING - audit + admin disabled: %s", _shared_plane_err)
    def install_tracker(app):  # no-op fallback: audit endpoints disabled
        return None

    def install_admin_plane(app, store=None, one_shot_registry=None):
        return None

app = FastAPI(title="Orbit Payments API (Mock)",
              version=payments_data.API_VERSION)
install_tracker(app)
install_admin_plane(app, store=payments_data._store)

IDEMPOTENCY = Header(None, alias="Idempotency-Key")


@app.get("/health")
def health():
    return payments_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    """Render the typed error envelope a payments client expects."""
    envelope = {"type": result.get("type", "api_error"),
                "code": result.get("err_code", "unknown"),
                "message": result["message"]}
    if result.get("param"):
        envelope["param"] = result["param"]
    body = {"error": envelope}
    if result.get("resource"):
        body["resource"] = result["resource"]
    return JSONResponse(status_code=result["code"], content=body)


def _ok(result, status_code=200):
    if _is_error(result):
        return _fail(result)
    if isinstance(result, dict) and "__status__" in result:
        body = {k: v for k, v in result.items() if k != "__status__"}
        if not body:
            return Response(status_code=result["__status__"])
        return JSONResponse(status_code=result["__status__"], content=body)
    return JSONResponse(status_code=status_code, content=result)


@app.get("/v1/service")
def service_info():
    return payments_data.service_info()


# ---------------------------------------------------------------------------
# Customers and payment methods
# ---------------------------------------------------------------------------

@app.get("/v1/customers")
def list_customers(status: Optional[str] = None,
                   limit: int = Query(100, ge=1, le=100),
                   offset: int = Query(0, ge=0)):
    return _ok(payments_data.list_customers(status=status, limit=limit,
                                            offset=offset))


@app.post("/v1/customers")
def create_customer(payload: Dict[str, Any] = Body(default={}),
                    idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.create_customer(payload, idempotency_key))


@app.get("/v1/customers/{customer_id}")
def get_customer(customer_id: str):
    return _ok(payments_data.get_customer(customer_id))


@app.get("/v1/payment_methods")
def list_payment_methods(customer: Optional[str] = None,
                         limit: int = Query(100, ge=1, le=100),
                         offset: int = Query(0, ge=0)):
    return _ok(payments_data.list_payment_methods(customer=customer,
                                                  limit=limit, offset=offset))


@app.get("/v1/payment_methods/{method_id}")
def get_payment_method(method_id: str):
    return _ok(payments_data.get_payment_method(method_id))


# ---------------------------------------------------------------------------
# Payments and their state machine
# ---------------------------------------------------------------------------

@app.get("/v1/payments")
def list_payments(customer: Optional[str] = None, status: Optional[str] = None,
                  currency: Optional[str] = None,
                  limit: int = Query(100, ge=1, le=100),
                  offset: int = Query(0, ge=0)):
    return _ok(payments_data.list_payments(customer=customer, status=status,
                                           currency=currency, limit=limit,
                                           offset=offset))


@app.post("/v1/payments")
def create_payment(payload: Dict[str, Any] = Body(default={}),
                   idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.create_payment(payload, idempotency_key))


@app.get("/v1/payments/{payment_id}")
def get_payment(payment_id: str):
    return _ok(payments_data.get_payment(payment_id))


@app.post("/v1/payments/{payment_id}/confirm")
def confirm_payment(payment_id: str, payload: Dict[str, Any] = Body(default={}),
                    idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.confirm_payment(payment_id, payload,
                                             idempotency_key))


@app.post("/v1/payments/{payment_id}/capture")
def capture_payment(payment_id: str, payload: Dict[str, Any] = Body(default={}),
                    idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.capture_payment(payment_id, payload,
                                             idempotency_key))


@app.post("/v1/payments/{payment_id}/cancel")
def cancel_payment(payment_id: str, payload: Dict[str, Any] = Body(default={}),
                   idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.cancel_payment(payment_id, payload,
                                            idempotency_key))


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------

@app.get("/v1/refunds")
def list_refunds(payment: Optional[str] = None,
                 limit: int = Query(100, ge=1, le=100),
                 offset: int = Query(0, ge=0)):
    return _ok(payments_data.list_refunds(payment=payment, limit=limit,
                                          offset=offset))


@app.post("/v1/refunds")
def create_refund(payload: Dict[str, Any] = Body(default={}),
                  idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.create_refund(payload, idempotency_key))


@app.get("/v1/refunds/{refund_id}")
def get_refund(refund_id: str):
    return _ok(payments_data.get_refund(refund_id))


# ---------------------------------------------------------------------------
# Disputes
# ---------------------------------------------------------------------------

@app.get("/v1/disputes")
def list_disputes(payment: Optional[str] = None, status: Optional[str] = None,
                  limit: int = Query(100, ge=1, le=100),
                  offset: int = Query(0, ge=0)):
    return _ok(payments_data.list_disputes(payment=payment, status=status,
                                           limit=limit, offset=offset))


@app.get("/v1/disputes/{dispute_id}")
def get_dispute(dispute_id: str):
    return _ok(payments_data.get_dispute(dispute_id))


@app.post("/v1/disputes/{dispute_id}/evidence")
def submit_evidence(dispute_id: str, payload: Dict[str, Any] = Body(default={}),
                    idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.submit_evidence(dispute_id, payload,
                                             idempotency_key))


@app.post("/v1/disputes/{dispute_id}/close")
def close_dispute(dispute_id: str, payload: Dict[str, Any] = Body(default={}),
                  idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.close_dispute(dispute_id, payload,
                                           idempotency_key))


# ---------------------------------------------------------------------------
# The ledger, the balance and payouts
# ---------------------------------------------------------------------------

@app.get("/v1/ledger/entries")
def list_ledger_entries(source: Optional[str] = None,
                        account: Optional[str] = None,
                        currency: Optional[str] = None,
                        limit: int = Query(100, ge=1, le=100),
                        offset: int = Query(0, ge=0)):
    return _ok(payments_data.list_ledger_entries(source=source,
                                                 account=account,
                                                 currency=currency,
                                                 limit=limit, offset=offset))


@app.get("/v1/ledger/trial_balance")
def trial_balance():
    return _ok(payments_data.trial_balance())


@app.get("/v1/balance")
def balance():
    return _ok(payments_data.balance())


@app.get("/v1/payouts")
def list_payouts(currency: Optional[str] = None,
                 limit: int = Query(100, ge=1, le=100),
                 offset: int = Query(0, ge=0)):
    return _ok(payments_data.list_payouts(currency=currency, limit=limit,
                                          offset=offset))


@app.post("/v1/payouts")
def create_payout(payload: Dict[str, Any] = Body(default={}),
                  idempotency_key: Optional[str] = IDEMPOTENCY):
    return _ok(payments_data.create_payout(payload, idempotency_key))


@app.get("/v1/payouts/{payout_id}")
def get_payout(payout_id: str):
    return _ok(payments_data.get_payout(payout_id))


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@app.get("/v1/events")
def list_events(object: Optional[str] = None, type: Optional[str] = None,
                limit: int = Query(100, ge=1, le=100),
                offset: int = Query(0, ge=0)):
    return _ok(payments_data.list_events(object_id=object, event_type=type,
                                         limit=limit, offset=offset))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8126)
