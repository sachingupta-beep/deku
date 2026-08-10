"""FastAPI server wrapping lago_data module as REST endpoints.

Lago is usage-based billing, so the shape of this API is the shape of that
problem:

* **Nothing here charges anyone.** `POST /api/v1/events` ingests usage; what it
  costs is computed later by aggregating the period's events and running the
  plan's charges over the result.
* **`/customers/{id}/current_usage` is the endpoint people integrate against.**
  It recomputes the open period's cost on every read, before any invoice
  exists.
* **Identity is dual.** A `lago_id` the service owns, an `external_id` the
  caller owns; every path takes the external one, except invoices, credit notes
  and wallets, which only ever had a `lago_id`.
* **Responses are wrapped** --- `{"customer": …}` for one,
  `{"customers": […], "meta": {…}}` for many --- because Lago's are, and errors
  carry a per-field `details` map.
"""

from fastapi import Body, FastAPI, Query, Response
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional

import lago_data
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

app = FastAPI(title="Lago API (Mock)", version=lago_data.LAGO_VERSION)
install_tracker(app)
install_admin_plane(app, store=lago_data._store)


@app.get("/health")
def health():
    return lago_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    """Lago's error envelope: a status, a code, and a per-field detail map."""
    body = {"status": result["code"], "error": result["message"],
            "code": result.get("err_code", "error")}
    if result.get("details"):
        body["error_details"] = result["details"]
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


@app.get("/api/v1/service")
def service_info():
    return lago_data.service_info()


# ---------------------------------------------------------------------------
# Billable metrics: what is measured
# ---------------------------------------------------------------------------

@app.get("/api/v1/billable_metrics")
def list_billable_metrics(page: int = Query(1, ge=1),
                          per_page: int = Query(20, ge=1, le=100)):
    return _ok(lago_data.list_billable_metrics(page=page, per_page=per_page))


@app.post("/api/v1/billable_metrics")
def create_billable_metric(payload: Dict[str, Any] = Body(default={})):
    return _ok(lago_data.create_billable_metric(payload))


@app.get("/api/v1/billable_metrics/{code}")
def get_billable_metric(code: str):
    return _ok(lago_data.get_billable_metric(code))


# ---------------------------------------------------------------------------
# Plans: how it is priced
# ---------------------------------------------------------------------------

@app.get("/api/v1/plans")
def list_plans(page: int = Query(1, ge=1),
               per_page: int = Query(20, ge=1, le=100)):
    return _ok(lago_data.list_plans(page=page, per_page=per_page))


@app.post("/api/v1/plans")
def create_plan(payload: Dict[str, Any] = Body(default={})):
    return _ok(lago_data.create_plan(payload))


@app.get("/api/v1/plans/{code}")
def get_plan(code: str):
    return _ok(lago_data.get_plan(code))


# ---------------------------------------------------------------------------
# Customers and their open usage
# ---------------------------------------------------------------------------

@app.get("/api/v1/customers")
def list_customers(page: int = Query(1, ge=1),
                   per_page: int = Query(20, ge=1, le=100)):
    return _ok(lago_data.list_customers(page=page, per_page=per_page))


@app.post("/api/v1/customers")
def create_customer(payload: Dict[str, Any] = Body(default={})):
    """Lago upserts on `external_id`, so this creates or updates."""
    return _ok(lago_data.create_customer(payload))


@app.get("/api/v1/customers/{external_id}")
def get_customer(external_id: str):
    return _ok(lago_data.get_customer(external_id))


@app.get("/api/v1/customers/{external_id}/current_usage")
def current_usage(external_id: str,
                  external_subscription_id: Optional[str] = None):
    return _ok(lago_data.current_usage(external_id, external_subscription_id))


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

@app.get("/api/v1/subscriptions")
def list_subscriptions(external_customer_id: Optional[str] = None,
                       status: Optional[str] = None,
                       page: int = Query(1, ge=1),
                       per_page: int = Query(20, ge=1, le=100)):
    return _ok(lago_data.list_subscriptions(
        external_customer_id=external_customer_id, status=status, page=page,
        per_page=per_page))


@app.post("/api/v1/subscriptions")
def create_subscription(payload: Dict[str, Any] = Body(default={})):
    return _ok(lago_data.create_subscription(payload))


@app.get("/api/v1/subscriptions/{external_id}")
def get_subscription(external_id: str):
    return _ok(lago_data.get_subscription(external_id))


@app.delete("/api/v1/subscriptions/{external_id}")
def terminate_subscription(external_id: str):
    return _ok(lago_data.terminate_subscription(external_id))


# ---------------------------------------------------------------------------
# Events: usage in, cost later
#
# The literal `batch` and `estimate_fees` paths are declared before
# `/events/{transaction_id}`, which would otherwise swallow them.
# ---------------------------------------------------------------------------

@app.post("/api/v1/events/batch")
def create_events_batch(payload: Dict[str, Any] = Body(default={})):
    return _ok(lago_data.create_events_batch(payload))


@app.post("/api/v1/events/estimate_fees")
def estimate_fees(payload: Dict[str, Any] = Body(default={})):
    """What would this usage cost? Nothing is ingested."""
    return _ok(lago_data.estimate_fees(payload))


@app.get("/api/v1/events")
def list_events(external_subscription_id: Optional[str] = None,
                code: Optional[str] = None, page: int = Query(1, ge=1),
                per_page: int = Query(20, ge=1, le=100)):
    return _ok(lago_data.list_events(
        external_subscription_id=external_subscription_id, code=code,
        page=page, per_page=per_page))


@app.post("/api/v1/events")
def create_event(payload: Dict[str, Any] = Body(default={})):
    return _ok(lago_data.create_event(payload))


@app.get("/api/v1/events/{transaction_id}")
def get_event(transaction_id: str):
    return _ok(lago_data.get_event(transaction_id))


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

@app.get("/api/v1/invoices")
def list_invoices(external_customer_id: Optional[str] = None,
                  status: Optional[str] = None,
                  payment_status: Optional[str] = None,
                  page: int = Query(1, ge=1),
                  per_page: int = Query(20, ge=1, le=100)):
    return _ok(lago_data.list_invoices(
        external_customer_id=external_customer_id, status=status,
        payment_status=payment_status, page=page, per_page=per_page))


@app.get("/api/v1/invoices/{lago_id}")
def get_invoice(lago_id: str):
    return _ok(lago_data.get_invoice(lago_id))


@app.put("/api/v1/invoices/{lago_id}")
def update_invoice(lago_id: str, payload: Dict[str, Any] = Body(default={})):
    return _ok(lago_data.update_invoice(lago_id, payload))


@app.post("/api/v1/invoices/{lago_id}/refresh")
def refresh_invoice(lago_id: str):
    return _ok(lago_data.refresh_invoice(lago_id))


@app.post("/api/v1/invoices/{lago_id}/finalize")
def finalize_invoice(lago_id: str):
    return _ok(lago_data.finalize_invoice(lago_id))


@app.post("/api/v1/invoices/{lago_id}/void")
def void_invoice(lago_id: str):
    return _ok(lago_data.void_invoice(lago_id))


# ---------------------------------------------------------------------------
# Credit notes and wallets
# ---------------------------------------------------------------------------

@app.get("/api/v1/credit_notes")
def list_credit_notes(external_customer_id: Optional[str] = None,
                      page: int = Query(1, ge=1),
                      per_page: int = Query(20, ge=1, le=100)):
    return _ok(lago_data.list_credit_notes(
        external_customer_id=external_customer_id, page=page,
        per_page=per_page))


@app.post("/api/v1/credit_notes")
def create_credit_note(payload: Dict[str, Any] = Body(default={})):
    return _ok(lago_data.create_credit_note(payload))


@app.get("/api/v1/credit_notes/{lago_id}")
def get_credit_note(lago_id: str):
    return _ok(lago_data.get_credit_note(lago_id))


@app.get("/api/v1/wallets")
def list_wallets(external_customer_id: Optional[str] = None,
                 page: int = Query(1, ge=1),
                 per_page: int = Query(20, ge=1, le=100)):
    return _ok(lago_data.list_wallets(
        external_customer_id=external_customer_id, page=page,
        per_page=per_page))


@app.post("/api/v1/wallets")
def create_wallet(payload: Dict[str, Any] = Body(default={})):
    return _ok(lago_data.create_wallet(payload))


@app.get("/api/v1/wallets/{lago_id}")
def get_wallet(lago_id: str):
    return _ok(lago_data.get_wallet(lago_id))


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@app.get("/api/v1/analytics/gross_revenue")
def gross_revenue(currency: Optional[str] = None):
    return _ok(lago_data.gross_revenue(currency=currency))


@app.get("/api/v1/analytics/mrr")
def mrr(currency: Optional[str] = None):
    return _ok(lago_data.mrr(currency=currency))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8127)
