# deku-pay API Reference

`deku-pay` is the in-house payment provider for this benchmark. It behaves like a
real payment service: charges are created via API, settle asynchronously, and
settlement events are delivered via webhook. The verifier queries it directly, so
your integration must be genuine — no mocks, no `setTimeout` fakes.

---

## Base URL

```
PAYMENTS_API_URL   (environment variable, e.g. http://deku-pay:8080)
```

Read the base URL from the environment. Never hardcode it.

---

## Authentication

Every endpoint except `GET /health` requires:

```
Authorization: Bearer <PAYMENTS_SECRET_KEY>
```

`PAYMENTS_SECRET_KEY` is the server-side secret. Use it only in backend code.
`PAYMENTS_PUBLISHABLE_KEY` is the client-side key; it is not used by any API
endpoint but you may expose it to the browser if needed.

---

## Card Tokens

These are the **only** values accepted in the `source` field of `POST /v1/charges`.
Any other value returns `400`.

| Token                  | Outcome                                               |
|------------------------|-------------------------------------------------------|
| `tok_visa_ok`          | Charge settles `succeeded` after a short delay        |
| `tok_visa_decline`     | Charge settles `failed` (declined)                    |
| `tok_visa_webhook_flake` | Charge settles `succeeded`; webhook delivered **twice** |

---

## Endpoints

### `GET /health`

Liveness probe. No auth required.

**Response 200**
```json
{"status": "ok"}
```

---

### `POST /v1/charges`

Create a charge. The charge starts in `pending` status and transitions
asynchronously to `succeeded` or `failed`.

**Request headers**

| Header            | Required | Description                                                   |
|-------------------|----------|---------------------------------------------------------------|
| `Authorization`   | yes      | `Bearer <PAYMENTS_SECRET_KEY>`                                |
| `Idempotency-Key` | recommended | Unique per attempt. Replay returns the original charge instead of creating a duplicate. Derive from subscription ID. |

**Request body (JSON)**

```json
{
  "amount":         1000,
  "currency":       "usd",
  "source":         "tok_visa_ok",
  "customer_email": "reader@example.com",
  "metadata": {
    "subscription_id": "42",
    "creator_id":      "7"
  }
}
```

| Field            | Type    | Description                                            |
|------------------|---------|--------------------------------------------------------|
| `amount`         | integer | Amount in minor units (cents). `$10.00` = `1000`.     |
| `currency`       | string  | ISO 4217 lowercase. Use `"usd"`.                      |
| `source`         | string  | Card token. See table above.                           |
| `customer_email` | string  | Reader's email address.                                |
| `metadata`       | object  | Arbitrary key-value pairs. Use to tag subscription/creator IDs. |

**Response 201** — charge created (still `pending`)

```json
{
  "id":             "ch_a1b2c3d4e5f6a1b2c3d4e5f6",
  "amount":         1000,
  "currency":       "usd",
  "status":         "pending",
  "source":         "tok_visa_ok",
  "customer_email": "reader@example.com",
  "metadata":       {"subscription_id": "42", "creator_id": "7"},
  "created_at":     1700000000,
  "updated_at":     1700000000
}
```

**Response 200** — idempotent replay (same `Idempotency-Key` seen before)
Returns the original charge object unchanged.

**Response 400** — missing required fields or unknown card token.

---

### `GET /v1/charges`

List all charges, newest first.

**Query params**

| Param   | Default | Description          |
|---------|---------|----------------------|
| `limit` | 100     | Max results (≤ 1000) |

**Response 200**

```json
{
  "data":  [<Charge>, ...],
  "count": 42
}
```

---

### `GET /v1/charges/{id}`

Retrieve a single charge by ID. Poll this to observe status transitions.

**Response 200** — Charge object (same shape as POST response)

**Response 404** — charge not found

---

### `POST /v1/webhooks`

Register a URL to receive settlement events. Call this during your app's
startup, before creating any charges, so deliveries are not missed.

**Request body**

```json
{
  "url":    "http://main:4173/api/webhooks/payments",
  "events": ["charge.succeeded", "charge.failed", "charge.refunded"]
}
```

| Field    | Description                                                     |
|----------|-----------------------------------------------------------------|
| `url`    | Absolute URL the provider will POST events to.                  |
| `events` | Event types to subscribe to. Omit to receive all three.        |

**Response 201**

```json
{
  "id":         "we_a1b2c3d4e5f6a1b2",
  "url":        "http://main:4173/api/webhooks/payments",
  "events":     ["charge.succeeded", "charge.failed", "charge.refunded"],
  "created_at": 1700000000
}
```

---

### `GET /v1/webhooks`

List registered webhook endpoints.

**Response 200**

```json
{"data": [<WebhookEndpoint>, ...]}
```

---

### `DELETE /v1/webhooks/{id}`

Remove a webhook endpoint.

**Response 200**

```json
{"deleted": true}
```

---

### `GET /v1/refunds`

List refunds. Filter by charge with `?charge=<charge_id>`.

**Response 200**

```json
{"data": [<Refund>, ...]}
```

---

### `POST /v1/refunds`

Create a refund on a `succeeded` charge.

**Request body**

```json
{
  "charge_id": "ch_...",
  "amount":    1000
}
```

`amount` defaults to the full charge amount if omitted.

**Response 201** — Refund object

**Response 400** — charge not in `succeeded` status

**Response 404** — charge not found

---

## Webhook Delivery

When a charge settles, deku-pay POSTs to every registered URL:

```
POST <your-webhook-url>
Content-Type: application/json
Deku-Signature: <hex-string>
```

**Signature verification** (REQUIRED — reject any event with a bad signature):

```python
import hashlib, hmac

def verify(body: bytes, header: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)
```

`secret` = `PAYMENTS_WEBHOOK_SECRET` environment variable.
`body` = the raw request body bytes **before** JSON parsing.
`header` = the value of the `Deku-Signature` request header.

**Event body**

```json
{
  "id":      "evt_a1b2c3d4e5f6a1b2",
  "type":    "charge.succeeded",
  "created": 1700000000,
  "data": {
    "object": {
      "id":       "ch_...",
      "amount":   1000,
      "currency": "usd",
      "status":   "succeeded",
      "metadata": {"subscription_id": "42", "creator_id": "7"}
    }
  }
}
```

**Event types**

| Type               | When                                                |
|--------------------|-----------------------------------------------------|
| `charge.succeeded` | Charge settled successfully — activate subscription |
| `charge.failed`    | Charge declined — cancel subscription               |
| `charge.refunded`  | Charge refunded                                     |

**Delivery guarantees**

- Delivery is **at-least-once**. The same event may arrive more than once.
  Handle every event **idempotently** — a duplicate `charge.succeeded` must not
  double-grant access or double-count revenue.
- For `tok_visa_webhook_flake`, the same `charge.succeeded` event is delivered
  **exactly twice** to test your duplicate handling.
- Respond `200` to acknowledge. Non-200 responses may cause retries.

---

## Amounts and Currency

All amounts are **integer minor units** (cents). `$10.00` = `1000`, never `10.0`
or `"10.00"`. Currency is lowercase ISO 4217: `"usd"`.

---

## Status Transitions

```
pending  -->  succeeded   (tok_visa_ok, tok_visa_webhook_flake)
pending  -->  failed      (tok_visa_decline)
succeeded --> refunded    (via POST /v1/refunds)
```

Do **not** assume the POST /v1/charges response is already `succeeded`. Always
wait for the webhook or poll `GET /v1/charges/{id}`.
