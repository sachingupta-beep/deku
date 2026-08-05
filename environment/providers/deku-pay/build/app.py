"""deku-pay: in-house, adversarial payment sidecar for the Deku benchmark (PLAN.md 3.3.1).

State is in-memory and consistent for the lifetime of one container / one trial.
The verifier interrogates this service directly, so it must behave like a real
payment provider -- not a mock that hardcodes expected values.

Endpoints
---------
  GET  /health                  liveness probe (no auth)
  POST /v1/charges              create a charge; Idempotency-Key header honoured
  GET  /v1/charges              list charges (limit query param)
  GET  /v1/charges/{id}         retrieve a single charge
  POST /v1/webhooks             register a webhook endpoint URL
  GET  /v1/webhooks             list registered endpoints
  DELETE /v1/webhooks/{id}      remove a registered endpoint
  GET  /v1/refunds              list refunds (filter by ?charge=<id>)
  POST /v1/refunds              create a refund

Settlement is asynchronous: charges start as 'pending' and transition after
DEKU_SETTLE_DELAY seconds, then a webhook is delivered to every registered URL.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets
import time

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Configuration — read from env; compose sets these; fallbacks for local dev
# ---------------------------------------------------------------------------

SECRET_KEY      = os.environ.get("PAYMENTS_SECRET_KEY",      "sk_local_deku")
PUBLISHABLE_KEY = os.environ.get("PAYMENTS_PUBLISHABLE_KEY", "pk_local_deku")
WEBHOOK_SECRET  = os.environ.get("PAYMENTS_WEBHOOK_SECRET",  "wh_local_deku")
SETTLE_DELAY    = float(os.environ.get("DEKU_SETTLE_DELAY",  "2"))

# Deterministic card tokens — matches instruction.md "Deterministic test instruments"
CARD_BEHAVIORS: dict[str, dict] = {
    "tok_visa_ok":            {"outcome": "succeeded", "flake": False},
    "tok_visa_decline":       {"outcome": "failed",    "flake": False},
    "tok_visa_webhook_flake": {"outcome": "succeeded", "flake": True},
}

# ---------------------------------------------------------------------------
# In-memory state (thread-safe enough: uvicorn default worker is single-threaded)
# ---------------------------------------------------------------------------

_charges:    dict[str, dict] = {}   # charge_id -> charge object
_idem_map:   dict[str, str]  = {}   # idempotency_key -> charge_id
_webhooks:   dict[str, dict] = {}   # endpoint_id -> endpoint object
_refunds:    dict[str, dict] = {}   # refund_id -> refund object

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="deku-pay", version="1.0.0")


# ---------------------------------------------------------------------------
# Auth dependency — Bearer token checked against PAYMENTS_SECRET_KEY
# ---------------------------------------------------------------------------

async def _auth(request: Request) -> None:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    if header[len("Bearer "):] != SECRET_KEY:
        raise HTTPException(status_code=401, detail="invalid secret key")


# ---------------------------------------------------------------------------
# HMAC signing — used for webhook delivery
# ---------------------------------------------------------------------------

def _sign(body: bytes) -> str:
    """HMAC-SHA256 of raw body with PAYMENTS_WEBHOOK_SECRET, returned as hex."""
    return hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Async settlement + webhook delivery
# ---------------------------------------------------------------------------

async def _deliver_once(url: str, body: bytes, sig: str) -> None:
    headers = {"Content-Type": "application/json", "Deku-Signature": sig}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, content=body, headers=headers)
    except Exception:
        pass  # at-least-once: failures are the receiver's problem


async def _deliver_event(event: dict, flake: bool) -> None:
    """POST the event to every registered endpoint. flake=True → deliver twice."""
    import json as _json
    body = _json.dumps(event, separators=(",", ":")).encode()
    sig = _sign(body)
    for endpoint in list(_webhooks.values()):
        await _deliver_once(endpoint["url"], body, sig)
        if flake:
            await asyncio.sleep(0.5)   # small gap between the two deliveries
            await _deliver_once(endpoint["url"], body, sig)


async def _settle(charge_id: str, outcome: str, flake: bool) -> None:
    """Background task: wait SETTLE_DELAY, flip status, deliver webhook."""
    await asyncio.sleep(SETTLE_DELAY)
    if charge_id not in _charges:
        return
    charge = _charges[charge_id]
    charge["status"] = outcome
    charge["updated_at"] = int(time.time())

    event_type = "charge.succeeded" if outcome == "succeeded" else "charge.failed"
    event = {
        "id": f"evt_{secrets.token_hex(8)}",
        "type": event_type,
        "created": int(time.time()),
        "data": {
            "object": {
                "id": charge_id,
                "amount": charge["amount"],
                "currency": charge["currency"],
                "status": outcome,
                "metadata": charge.get("metadata") or {},
            }
        },
    }
    await _deliver_event(event, flake)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/charges", dependencies=[Depends(_auth)])
async def create_charge(request: Request) -> JSONResponse:
    body = await request.json()

    amount   = body.get("amount")
    currency = str(body.get("currency", "usd")).lower()
    source   = body.get("source")
    email    = body.get("customer_email", "")
    metadata = body.get("metadata") or {}

    if amount is None or not source:
        raise HTTPException(status_code=400, detail="amount and source are required")

    # Idempotency — header is case-folded by Starlette to lowercase
    idem_key = request.headers.get("idempotency-key")
    if idem_key and idem_key in _idem_map:
        return JSONResponse(content=_charges[_idem_map[idem_key]], status_code=200)

    behavior = CARD_BEHAVIORS.get(source)
    if behavior is None:
        raise HTTPException(status_code=400, detail=f"unknown card token: {source!r}")

    charge_id = f"ch_{secrets.token_hex(12)}"
    now = int(time.time())
    charge = {
        "id":             charge_id,
        "amount":         int(amount),
        "currency":       currency,
        "status":         "pending",
        "source":         source,
        "customer_email": email,
        "metadata":       metadata,
        "created_at":     now,
        "updated_at":     now,
    }
    _charges[charge_id] = charge
    if idem_key:
        _idem_map[idem_key] = charge_id

    # Fire and forget — settlement runs independently of the HTTP response
    asyncio.create_task(_settle(charge_id, behavior["outcome"], behavior["flake"]))

    return JSONResponse(content=charge, status_code=201)


@app.get("/v1/charges", dependencies=[Depends(_auth)])
def list_charges(limit: int = Query(default=100, ge=1, le=1000)) -> dict:
    data = sorted(_charges.values(), key=lambda c: c["created_at"], reverse=True)
    return {"data": data[:limit], "count": len(data)}


@app.get("/v1/charges/{charge_id}", dependencies=[Depends(_auth)])
def get_charge(charge_id: str) -> dict:
    charge = _charges.get(charge_id)
    if not charge:
        raise HTTPException(status_code=404, detail=f"charge {charge_id!r} not found")
    return charge


@app.post("/v1/webhooks", dependencies=[Depends(_auth)])
async def register_webhook(request: Request) -> JSONResponse:
    body = await request.json()
    url = body.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    events = body.get("events", ["charge.succeeded", "charge.failed", "charge.refunded"])
    endpoint_id = f"we_{secrets.token_hex(8)}"
    endpoint = {"id": endpoint_id, "url": url, "events": events, "created_at": int(time.time())}
    _webhooks[endpoint_id] = endpoint
    return JSONResponse(content=endpoint, status_code=201)


@app.get("/v1/webhooks", dependencies=[Depends(_auth)])
def list_webhooks() -> dict:
    return {"data": list(_webhooks.values())}


@app.delete("/v1/webhooks/{endpoint_id}", dependencies=[Depends(_auth)])
def delete_webhook(endpoint_id: str) -> JSONResponse:
    if endpoint_id not in _webhooks:
        raise HTTPException(status_code=404, detail="webhook endpoint not found")
    del _webhooks[endpoint_id]
    return JSONResponse(content={"deleted": True}, status_code=200)


@app.get("/v1/refunds", dependencies=[Depends(_auth)])
def list_refunds(charge: str | None = Query(default=None)) -> dict:
    data = list(_refunds.values())
    if charge:
        data = [r for r in data if r.get("charge_id") == charge]
    return {"data": data}


@app.post("/v1/refunds", dependencies=[Depends(_auth)])
async def create_refund(request: Request) -> JSONResponse:
    body = await request.json()
    charge_id = body.get("charge_id") or body.get("charge")
    if not charge_id:
        raise HTTPException(status_code=400, detail="charge_id is required")
    charge = _charges.get(charge_id)
    if not charge:
        raise HTTPException(status_code=404, detail="charge not found")
    if charge["status"] != "succeeded":
        raise HTTPException(status_code=400, detail="only succeeded charges can be refunded")

    amount = body.get("amount", charge["amount"])
    refund_id = f"re_{secrets.token_hex(8)}"
    now = int(time.time())
    refund = {
        "id":         refund_id,
        "charge_id":  charge_id,
        "amount":     int(amount),
        "currency":   charge["currency"],
        "status":     "succeeded",
        "created_at": now,
    }
    _refunds[refund_id] = refund
    charge["status"] = "refunded"
    charge["updated_at"] = now

    event = {
        "id":      f"evt_{secrets.token_hex(8)}",
        "type":    "charge.refunded",
        "created": now,
        "data":    {
            "object": {
                "id":       charge_id,
                "amount":   charge["amount"],
                "currency": charge["currency"],
                "status":   "refunded",
                "metadata": charge.get("metadata") or {},
                "refund":   refund,
            }
        },
    }
    asyncio.create_task(_deliver_event(event, flake=False))
    return JSONResponse(content=refund, status_code=201)
