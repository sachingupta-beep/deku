# Orbit Payments Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$INHOUSE_PAYMENTS_API_URL`; responses are verbatim (long lists
elided with `…`).

```bash
export AMELIA='cus_amelia_3f7e1b0c'
export SEATS='pay_5b07d21f8c64'      # authorized, capturable
export SANDBOX_AUTH='pay_4a8f2c1d3e65'  # authorized, capture will fail
export EGRESS='pay_2d47b9e01f5c'     # partially refunded
export DISPUTED='pay_c8e05a1976b3'   # USD, has an open dispute
export USD_DISPUTE='dp_6b19d5ec8f30'
export EUR_DISPUTE='dp_9e21b7304c15'
```

## The books, before anything happens

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/ledger/trial_balance"
```
```json
{
  "object": "trial_balance",
  "as_of": "2026-08-06T11:24:19Z",
  "books": [
    {"currency": "EUR",
     "accounts": [
       {"account": "gateway_clearing", "debit_minor": 227700, "credit_minor": 17763, "net_minor": 209937},
       {"account": "processing_fees", "debit_minor": 3263, "credit_minor": 0, "net_minor": 3263},
       {"account": "disputed_funds", "debit_minor": 4500, "credit_minor": 0, "net_minor": 4500},
       {"account": "merchant_revenue", "debit_minor": 10000, "credit_minor": 227700, "net_minor": -217700}
     ],
     "total_debit_minor": 245463, "total_credit_minor": 245463, "balanced": true},
    {"currency": "USD", "…": "…", "balanced": true}
  ],
  "balanced": true
}
```

The balance is *derived* from those entries rather than stored beside them:

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/balance"
```
```json
{"object": "balance", "as_of": "…",
 "balances": [
   {"currency": "EUR", "available_minor": 209937,
    "pending_authorization_minor": 72000, "disputed_minor": 4500,
    "paid_out_minor": 0},
   {"currency": "USD", "available_minor": -755,
    "pending_authorization_minor": 0, "disputed_minor": 25000,
    "paid_out_minor": 0}],
 "note": "available_minor is the gateway_clearing account balance, computed from the ledger at read time"}
```

The USD balance is **negative** because the network pulled the disputed funds —
exactly what the ledger says.

## Idempotency is mandatory

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments" \
  -H 'Content-Type: application/json' \
  -d '{"customer": "'$AMELIA'", "amount_minor": 5000, "currency": "EUR"}'
```
```json
{"error": {"type": "idempotency_error", "code": "idempotency_key_required",
           "message": "Every write requires an Idempotency-Key header",
           "param": "Idempotency-Key"}}
```

With a key it goes through, and the **same key replays the same payment**:

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: run-charge-amelia-01' \
  -d '{"customer": "'$AMELIA'", "payment_method": "pm_visa_4242",
       "amount_minor": 5000, "currency": "EUR",
       "description": "Scheduled export add-on"}'
```
```json
{"object": "payment", "id": "pay_28de14806fc3", "status": "authorized",
 "amount_minor": 5000, "currency": "EUR", "capturable_minor": 5000,
 "next_actions": ["capture", "cancel"], "…": "…"}
```

Repeat it verbatim and the response carries `"idempotent_replay": true` with the
same id. Change the body and keep the key:

```json
{"error": {"type": "idempotency_error", "code": "idempotency_key_reuse",
           "message": "Idempotency-Key 'run-charge-amelia-01' was already used for a different request (POST /v1/payments)",
           "param": "Idempotency-Key"}}
```

## The card decides the outcome

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: run-charge-declined-01' \
  -d '{"customer": "cus_acme_5b07d21f", "payment_method": "pm_visa_0002",
       "amount_minor": 1000, "currency": "EUR"}'
```
```json
{"error": {"type": "card_error", "code": "insufficient_funds",
           "message": "The card was declined: the account does not have enough funds.",
           "param": "payment_method"},
 "resource": {"object": "payment", "id": "pay_f59af04f3771",
              "status": "failed", "failure_code": "insufficient_funds", "…": "…"}}
```

**402**, and the payment it created comes back under `resource` so the caller
can follow it up. A decline is not a completed write, so the *same key* may be
sent again — and declines again.

Other behaviours: `pm_visa_0119` → `expired_card`; `pm_visa_3220` →
`requires_confirmation` (confirm succeeds); `pm_visa_3221` → confirm **fails**
with `authentication_failed`; `pm_amex_0005` → authorizes, capture refused.
Charging the delinquent customer never reaches the card:

```json
{"error": {"type": "card_error", "code": "customer_delinquent",
           "message": "Customer cus_dmitri_2d47b9e0 is delinquent and cannot be charged"}}
```

## Partial capture, and the arithmetic that follows

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments/$SEATS/capture" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: run-capture-seats-01' \
  -d '{"amount_minor": 20000}'
```
```json
{"object": "payment", "id": "pay_5b07d21f8c64", "status": "partially_captured",
 "amount_minor": 48000, "captured_minor": 20000, "capturable_minor": 28000,
 "refundable_minor": 20000, "fee_minor": 305, "net_minor": 19695,
 "next_actions": ["capture", "cancel", "refund"], "…": "…"}
```

```json
{"error": {"code": "amount_too_large", "message": "Cannot capture 99999; only 28000 EUR remains authorized on pay_5b07d21f8c64", "param": "amount_minor"}}
```

Omitting the amount captures whatever remains, and the status becomes
`captured` with `next_actions: ["refund"]`. Capturing again:

```json
{"error": {"type": "state_error", "code": "payment_state_invalid",
           "message": "Cannot capture a payment that is captured; the available actions are refund",
           "param": "status"}}
```

## A capture the processor refuses

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments/$SANDBOX_AUTH/capture" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: run-capture-sandbox-01' -d '{}'
```
```json
{"error": {"type": "card_error", "code": "processor_declined",
           "message": "The processor refused the capture; the authorization remains open and may be retried or canceled",
           "param": "payment_method"},
 "resource": {"object": "payment", "status": "authorized", "…": "…"}}
```

The authorization survives — reading the payment back still shows `authorized`
— so it can be cancelled instead:

```json
{"object": "payment", "status": "canceled", "released_minor": 24000, "…": "…"}
```

## Refunds, and the dispute that blocks them

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/refunds" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: run-refund-egress-01' \
  -d '{"payment": "'$EGRESS'", "amount_minor": 5000, "reason": "duplicate"}'
```
```json
{"id": "re_da571b4335ef", "payment": "pay_2d47b9e01f5c", "amount_minor": 5000,
 "currency": "EUR", "reason": "duplicate", "status": "succeeded",
 "idempotency_key": "run-refund-egress-01", "created": "…"}
```

Refusals name the number or the list:

```json
{"error": {"code": "amount_too_large", "message": "Cannot refund 99999; only 15000 EUR of pay_2d47b9e01f5c remains refundable"}}
{"error": {"code": "reason_invalid", "message": "'vibes' is not a refund reason; expected one of requested_by_customer, duplicate, fraudulent, product_unacceptable"}}
{"error": {"type": "state_error", "code": "payment_terminal", "message": "Payment pay_7a63f04c9e21 is failed, which is terminal; no further action is possible"}}
```

And a disputed payment is held:

```json
{"error": {"type": "state_error", "code": "payment_disputed",
           "message": "Payment pay_c8e05a1976b3 has an open dispute (dp_6b19d5ec8f30); the funds are already withheld and cannot be refunded until it is closed",
           "param": "status"}}
```

## Disputes

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/disputes/$EUR_DISPUTE/evidence" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: run-evidence-late-01' \
  -d '{"evidence": "Signed delivery receipt attached."}'
```
```json
{"error": {"type": "state_error", "code": "evidence_window_closed",
           "message": "The evidence window for dp_9e21b7304c15 closed at 2026-06-05T23:59:59Z"}}
```

The USD dispute is still open, so its evidence lands and moves it to
`under_review`. Closing it as **won** returns the funds:

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/disputes/$USD_DISPUTE/close" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: run-close-usd-01' -d '{"resolution": "won"}'
```

Closing the EUR one as **lost** realises the chargeback and the network fee —
two balanced postings:

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/ledger/entries?source=$EUR_DISPUTE"
```
```json
{"object": "list", "data": [
  {"id": "le_0021", "account": "disputed_funds", "direction": "debit", "amount_minor": 4500, "memo": "Funds withdrawn for dispute dp_9e21b7304c15"},
  {"id": "le_0022", "account": "gateway_clearing", "direction": "credit", "amount_minor": 4500, "…": "…"},
  {"id": "le_00xx", "account": "merchant_revenue", "direction": "debit", "amount_minor": 4500, "memo": "Chargeback realised, dispute dp_9e21b7304c15 lost"},
  {"id": "le_00xx", "account": "disputed_funds", "direction": "credit", "amount_minor": 4500, "…": "…"},
  {"id": "le_00xx", "account": "processing_fees", "direction": "debit", "amount_minor": 1500, "memo": "Dispute fee for dp_9e21b7304c15"},
  {"id": "le_00xx", "account": "gateway_clearing", "direction": "credit", "amount_minor": 1500, "…": "…"}
], "total_count": 6, "has_more": false}
```

With the dispute closed, the same payment refunds cleanly.

## Payouts move the balance by exactly what they say

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payouts" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: run-payout-04' \
  -d '{"currency": "EUR", "amount_minor": 50000}'
```
```json
{"id": "po_b38e728bc9f2", "amount_minor": 50000, "currency": "EUR",
 "status": "in_transit", "destination": "ES91 2100 0418 4502 0005 1332",
 "arrival_date": "2026-08-08T11:29:04Z", "created": "…"}
```

Before: `available_minor: 250715`. After: `200715`, with
`paid_out_minor: 50000`. Refusals:

```json
{"error": {"code": "amount_too_small", "message": "The minimum payout in EUR is 1000 minor units"}}
{"error": {"code": "insufficient_balance", "message": "Cannot pay out 99999999; the available EUR balance is 250715"}}
```

And the books still balance:

```json
{"currency": "EUR", "total_debit_minor": 355185, "total_credit_minor": 355185, "balanced": true}
```

## The event log

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/events?type=payment.captured"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/events?object=$SEATS"
```
```json
{"object": "list", "url": "/v1/events", "data": [
  {"id": "evt_0021", "type": "payout.created", "object_type": "payout",
   "object": "po_b38e728bc9f2",
   "summary": "Paid out 50000 EUR, arriving 2026-08-08T11:29:04Z",
   "created": "…"},
  "…"
], "total_count": 21, "has_more": false}
```
