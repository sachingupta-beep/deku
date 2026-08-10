---
name: inhouse-payments-api-connector
description: >
  Orbit Payments API (Mock) mock HTTP API. Base URL is provided via the
  `INHOUSE_PAYMENTS_API_URL` environment variable. 26 endpoint(s) across GET, POST.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Orbit Payments API (Mock)

Mock of the Orbit Labs **in-house** payments service — not a hosted-processor
clone. **All requests go to the base URL in `$INHOUSE_PAYMENTS_API_URL`.**
Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `INHOUSE_PAYMENTS_API_URL` | Base URL for all requests (e.g. `http://inhouse-payments-api:8126`) |

## Four things to know first

**Every write needs an `Idempotency-Key` header.** No key is a **400**. The
same key + same body replays the original response with
`idempotent_replay: true`. The same key + a different body is a **409**. Only
successes are recorded, so a declined card can be retried with the same key.

**The ledger is double-entry and it is the source of truth.**
`/v1/balance` is derived from `/v1/ledger/entries` at read time;
`/v1/ledger/trial_balance` proves debits equal credits per currency.

**Payments are an enforced state machine.** Every payment carries
`next_actions`; an illegal transition is a **409** that names them.

**The card decides the outcome.** Each `payment_method` has a `behaviour`.

## Test cards

| Method | Customer | Behaviour |
|--------|----------|-----------|
| `pm_visa_4242` · `pm_mc_5555` | `cus_amelia_3f7e1b0c` | clean |
| `pm_visa_1881` | `cus_acme_5b07d21f` | clean |
| `pm_visa_0002` | `cus_acme_5b07d21f` | **402** `insufficient_funds` |
| `pm_amex_0005` | `cus_acme_5b07d21f` | authorizes; **capture** refused |
| `pm_visa_3220` | `cus_helena_9f14c73e` | step-up, then succeeds |
| `pm_visa_0119` | `cus_helena_9f14c73e` | **402** `expired_card` |
| `pm_visa_3221` | `cus_dmitri_2d47b9e0` | step-up, then **fails** |
| `pm_visa_0259` | `cus_priya_c8e05a19` | clean, **USD** |

`cus_dmitri_2d47b9e0` is `delinquent` — refused before the card is considered.

## Seeded payments

| Id | State |
|----|-------|
| `pay_3f7e1b0c2d54` | captured, 193200 EUR |
| `pay_5b07d21f8c64` | **authorized** 48000 EUR — capture this one |
| `pay_4a8f2c1d3e65` | authorized 24000 EUR — its capture will be refused |
| `pay_9f14c73e0b2a` | **requires_confirmation** 12000 EUR |
| `pay_2d47b9e01f5c` | partially_refunded, 15000 EUR still refundable |
| `pay_0b2a4d6f8e13` | captured 4500 EUR, **disputed** |
| `pay_c8e05a1976b3` | captured 25000 **USD**, **disputed** |
| `pay_7a63f04c9e21` | failed · `pay_1c84f0654a7d` | canceled |

Disputes: `dp_6b19d5ec8f30` (USD, window open) and `dp_9e21b7304c15` (EUR,
window **closed**).

## Endpoints

| Method | Path |
|--------|------|
| GET | `/health` · `/v1/service` |
| GET/POST | `/v1/customers` · GET `/v1/customers/{id}` |
| GET | `/v1/payment_methods` · `/v1/payment_methods/{id}` |
| GET/POST | `/v1/payments` · GET `/v1/payments/{id}` |
| POST | `/v1/payments/{id}/confirm` · `/capture` · `/cancel` |
| GET/POST | `/v1/refunds` · GET `/v1/refunds/{id}` |
| GET | `/v1/disputes` · `/v1/disputes/{id}` |
| POST | `/v1/disputes/{id}/evidence` · `/close` |
| GET | `/v1/ledger/entries` · `/v1/ledger/trial_balance` · `/v1/balance` |
| GET/POST | `/v1/payouts` · GET `/v1/payouts/{id}` |
| GET | `/v1/events` |

## Usage

```bash
# every write carries a key
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: charge-2026-08-06-001' \
  -d '{"customer": "cus_amelia_3f7e1b0c", "payment_method": "pm_visa_4242",
       "amount_minor": 5000, "currency": "EUR"}'

# partial capture, then the rest
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments/pay_5b07d21f8c64/capture" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: cap-001' \
  -d '{"amount_minor": 20000}'

# the ledger behind a payment, and the proof it balances
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/ledger/entries?source=pay_3f7e1b0c2d54"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/ledger/trial_balance"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/balance"
```

**Amounts are integers in the currency's minor unit** and always travel with
their currency. A customer settles in exactly one currency. Fees: EUR 1.40% +
25, GBP 1.50% + 20, USD 2.90% + 30.

**Errors are typed**: `{"error": {"type", "code", "message", "param"}}`. Types
are `invalid_request_error` (400), `card_error` (**402**), `state_error` (409),
`idempotency_error` (400/409), `not_found_error` (404). A declined card carries
the payment it created under `resource`.

**A disputed payment cannot be refunded** — the funds are already withheld.
Close the dispute first.

The audit log of every call the agent makes is available at
`$INHOUSE_PAYMENTS_API_URL/audit/requests` (used for grading).
