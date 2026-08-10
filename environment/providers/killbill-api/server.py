"""FastAPI server wrapping killbill_data module as REST endpoints.

Kill Bill's wiring is Java/JAX-RS and this keeps it:

* **The tenant is in the headers.** `X-Killbill-ApiKey` and
  `X-Killbill-ApiSecret` are resolved on every request before anything else;
  data in one tenant is simply not visible from the other. Writes also need
  `X-Killbill-CreatedBy`.
* **Creates answer 201 with a `Location` header and an empty body.** Updates
  and cancellations answer 204. Nothing is echoed back, so a caller either
  follows the header or looks the object up by the `externalKey` it chose.
* Paths live under `/1.0/kb`, version and namespace both in the URL.
"""

from fastapi import Body, FastAPI, Header, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Any, Dict, List, Optional

import killbill_data
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

app = FastAPI(title="Kill Bill API (Mock)",
              version=killbill_data.KILLBILL_VERSION)
install_tracker(app)
install_admin_plane(app, store=killbill_data._store)

API_KEY = Header(None, alias="X-Killbill-ApiKey")
API_SECRET = Header(None, alias="X-Killbill-ApiSecret")
CREATED_BY = Header(None, alias="X-Killbill-CreatedBy")


@app.get("/health")
def health():
    return killbill_data.health()


def _is_error(result):
    return isinstance(result, dict) and "error" in result


def _fail(result):
    """Kill Bill's error body: a class name, its own numeric code, a message."""
    return JSONResponse(status_code=result["code"],
                        content={"className": result["className"],
                                 "code": result["kbCode"],
                                 "message": result["message"]})


def _ok(result, status_code=200):
    """Render a data-module result.

    `__created__` is the JAX-RS shape: **201, a `Location` header, no body**.
    `__status__` covers the 204s.
    """
    if _is_error(result):
        return _fail(result)
    if isinstance(result, dict) and "__created__" in result:
        return Response(status_code=201,
                        headers={"Location": result["__created__"]})
    if isinstance(result, dict) and "__raw__" in result:
        return HTMLResponse(result["__raw__"])
    if isinstance(result, dict) and "__status__" in result:
        return Response(status_code=result["__status__"])
    return JSONResponse(status_code=status_code, content=result)


def _tenant(api_key, api_secret):
    return killbill_data.resolve_tenant(api_key, api_secret)


def _writable(api_key, api_secret, created_by):
    """Resolve the tenant and insist on an audit identity, in that order."""
    tenant, failure = _tenant(api_key, api_secret)
    if failure:
        return None, failure
    missing = killbill_data.require_created_by(created_by)
    if missing:
        return None, missing
    return tenant, None


# ---------------------------------------------------------------------------
# Service state and catalog
# ---------------------------------------------------------------------------

@app.get("/1.0/kb/nodesInfo")
def nodes_info(x_killbill_api_key: Optional[str] = API_KEY,
               x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.nodes_info())


@app.get("/1.0/kb/catalog")
def get_catalog(x_killbill_api_key: Optional[str] = API_KEY,
                x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.get_catalog(tenant))


@app.get("/1.0/kb/catalog/availableBasePlans")
def available_base_plans(x_killbill_api_key: Optional[str] = API_KEY,
                         x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.available_base_plans(tenant))


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

@app.get("/1.0/kb/accounts")
def list_accounts(externalKey: Optional[str] = None,
                  offset: int = Query(0, ge=0),
                  limit: int = Query(100, ge=1, le=100),
                  x_killbill_api_key: Optional[str] = API_KEY,
                  x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.list_accounts(
        tenant, external_key=externalKey, offset=offset, limit=limit))


@app.post("/1.0/kb/accounts")
def create_account(payload: Dict[str, Any] = Body(default={}),
                   x_killbill_api_key: Optional[str] = API_KEY,
                   x_killbill_api_secret: Optional[str] = API_SECRET,
                   x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.create_account(
        tenant, payload, x_killbill_created_by))


@app.get("/1.0/kb/accounts/{account_id}")
def get_account(account_id: str,
                x_killbill_api_key: Optional[str] = API_KEY,
                x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.get_account(tenant, account_id))


@app.put("/1.0/kb/accounts/{account_id}")
def update_account(account_id: str, payload: Dict[str, Any] = Body(default={}),
                   x_killbill_api_key: Optional[str] = API_KEY,
                   x_killbill_api_secret: Optional[str] = API_SECRET,
                   x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.update_account(
        tenant, account_id, payload, x_killbill_created_by))


@app.get("/1.0/kb/accounts/{account_id}/timeline")
def account_timeline(account_id: str,
                     x_killbill_api_key: Optional[str] = API_KEY,
                     x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.account_timeline(tenant, account_id))


@app.get("/1.0/kb/accounts/{account_id}/overdueState")
def overdue_state(account_id: str,
                  x_killbill_api_key: Optional[str] = API_KEY,
                  x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.overdue_state(tenant, account_id))


@app.get("/1.0/kb/accounts/{account_id}/bundles")
def list_bundles(account_id: str,
                 x_killbill_api_key: Optional[str] = API_KEY,
                 x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.list_bundles(tenant, account_id))


@app.get("/1.0/kb/accounts/{account_id}/invoices")
def list_account_invoices(account_id: str,
                          x_killbill_api_key: Optional[str] = API_KEY,
                          x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.list_account_invoices(tenant,
                                                              account_id))


@app.get("/1.0/kb/accounts/{account_id}/payments")
def list_account_payments(account_id: str,
                          x_killbill_api_key: Optional[str] = API_KEY,
                          x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.list_account_payments(tenant,
                                                              account_id))


@app.post("/1.0/kb/accounts/{account_id}/payments")
def create_payment(account_id: str, payload: Dict[str, Any] = Body(default={}),
                   x_killbill_api_key: Optional[str] = API_KEY,
                   x_killbill_api_secret: Optional[str] = API_SECRET,
                   x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.create_payment(
        tenant, account_id, payload, x_killbill_created_by))


@app.get("/1.0/kb/accounts/{account_id}/paymentMethods")
def list_payment_methods(account_id: str,
                         x_killbill_api_key: Optional[str] = API_KEY,
                         x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.list_payment_methods(tenant,
                                                             account_id))


@app.post("/1.0/kb/accounts/{account_id}/paymentMethods")
def create_payment_method(account_id: str, isDefault: bool = False,
                          payload: Dict[str, Any] = Body(default={}),
                          x_killbill_api_key: Optional[str] = API_KEY,
                          x_killbill_api_secret: Optional[str] = API_SECRET,
                          x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.create_payment_method(
        tenant, account_id, payload, x_killbill_created_by,
        is_default=isDefault))


@app.get("/1.0/kb/accounts/{account_id}/tags")
def list_account_tags(account_id: str,
                      x_killbill_api_key: Optional[str] = API_KEY,
                      x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.list_account_tags(tenant, account_id))


@app.post("/1.0/kb/accounts/{account_id}/tags")
def add_account_tags(account_id: str, payload: List[str] = Body(default=[]),
                     x_killbill_api_key: Optional[str] = API_KEY,
                     x_killbill_api_secret: Optional[str] = API_SECRET,
                     x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.add_account_tags(
        tenant, account_id, payload, x_killbill_created_by))


@app.delete("/1.0/kb/accounts/{account_id}/tags")
def remove_account_tags(account_id: str, tagDef: Optional[str] = None,
                        x_killbill_api_key: Optional[str] = API_KEY,
                        x_killbill_api_secret: Optional[str] = API_SECRET,
                        x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    names = [n for n in (tagDef or "").split(",") if n]
    return _ok(failure or killbill_data.remove_account_tags(
        tenant, account_id, names, x_killbill_created_by))


# ---------------------------------------------------------------------------
# Bundles and subscriptions
# ---------------------------------------------------------------------------

@app.get("/1.0/kb/bundles/{bundle_id}")
def get_bundle(bundle_id: str,
               x_killbill_api_key: Optional[str] = API_KEY,
               x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.get_bundle(tenant, bundle_id))


@app.post("/1.0/kb/subscriptions")
def create_subscription(payload: Dict[str, Any] = Body(default={}),
                        x_killbill_api_key: Optional[str] = API_KEY,
                        x_killbill_api_secret: Optional[str] = API_SECRET,
                        x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.create_subscription(
        tenant, payload, x_killbill_created_by))


@app.get("/1.0/kb/subscriptions/{subscription_id}")
def get_subscription(subscription_id: str,
                     x_killbill_api_key: Optional[str] = API_KEY,
                     x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.get_subscription(tenant,
                                                         subscription_id))


@app.put("/1.0/kb/subscriptions/{subscription_id}")
def change_plan(subscription_id: str, payload: Dict[str, Any] = Body(default={}),
                x_killbill_api_key: Optional[str] = API_KEY,
                x_killbill_api_secret: Optional[str] = API_SECRET,
                x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.change_plan(
        tenant, subscription_id, payload, x_killbill_created_by))


@app.delete("/1.0/kb/subscriptions/{subscription_id}")
def cancel_subscription(subscription_id: str,
                        entitlementPolicy: Optional[str] = None,
                        billingPolicy: Optional[str] = None,
                        x_killbill_api_key: Optional[str] = API_KEY,
                        x_killbill_api_secret: Optional[str] = API_SECRET,
                        x_killbill_created_by: Optional[str] = CREATED_BY):
    """Two policies, because entitlement and billing are two timelines."""
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.cancel_subscription(
        tenant, subscription_id, entitlementPolicy, billingPolicy,
        x_killbill_created_by))


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

@app.post("/1.0/kb/invoices/charges/{account_id}")
def create_external_charge(account_id: str,
                           payload: Dict[str, Any] = Body(default={}),
                           x_killbill_api_key: Optional[str] = API_KEY,
                           x_killbill_api_secret: Optional[str] = API_SECRET,
                           x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.create_external_charge(
        tenant, account_id, payload, x_killbill_created_by))


@app.get("/1.0/kb/invoices/{invoice_id}")
def get_invoice(invoice_id: str,
                x_killbill_api_key: Optional[str] = API_KEY,
                x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.get_invoice(tenant, invoice_id))


@app.get("/1.0/kb/invoices/{invoice_id}/html")
def get_invoice_html(invoice_id: str,
                     x_killbill_api_key: Optional[str] = API_KEY,
                     x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.get_invoice_html(tenant, invoice_id))


@app.put("/1.0/kb/invoices/{invoice_id}/commitInvoice")
def commit_invoice(invoice_id: str,
                   x_killbill_api_key: Optional[str] = API_KEY,
                   x_killbill_api_secret: Optional[str] = API_SECRET,
                   x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.commit_invoice(
        tenant, invoice_id, x_killbill_created_by))


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@app.get("/1.0/kb/payments")
def list_payments(offset: int = Query(0, ge=0),
                  limit: int = Query(100, ge=1, le=100),
                  x_killbill_api_key: Optional[str] = API_KEY,
                  x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.list_payments(tenant, offset=offset,
                                                      limit=limit))


@app.get("/1.0/kb/payments/{payment_id}")
def get_payment(payment_id: str,
                x_killbill_api_key: Optional[str] = API_KEY,
                x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.get_payment(tenant, payment_id))


@app.post("/1.0/kb/payments/{payment_id}/refunds")
def refund_payment(payment_id: str, payload: Dict[str, Any] = Body(default={}),
                   x_killbill_api_key: Optional[str] = API_KEY,
                   x_killbill_api_secret: Optional[str] = API_SECRET,
                   x_killbill_created_by: Optional[str] = CREATED_BY):
    tenant, failure = _writable(x_killbill_api_key, x_killbill_api_secret,
                                x_killbill_created_by)
    return _ok(failure or killbill_data.refund_payment(
        tenant, payment_id, payload, x_killbill_created_by))


@app.get("/1.0/kb/paymentMethods/{payment_method_id}")
def get_payment_method(payment_method_id: str,
                       x_killbill_api_key: Optional[str] = API_KEY,
                       x_killbill_api_secret: Optional[str] = API_SECRET):
    tenant, failure = _tenant(x_killbill_api_key, x_killbill_api_secret)
    return _ok(failure or killbill_data.get_payment_method(tenant,
                                                           payment_method_id))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8128)
