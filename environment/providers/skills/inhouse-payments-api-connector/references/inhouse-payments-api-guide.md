# Orbit Payments API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$INHOUSE_PAYMENTS_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `INHOUSE_PAYMENTS_API_URL` | Base URL for all requests |

```bash
export AMELIA='cus_amelia_3f7e1b0c'
export ACME='cus_acme_5b07d21f'
export HELENA='cus_helena_9f14c73e'
export DMITRI='cus_dmitri_2d47b9e0'
export SEATS='pay_5b07d21f8c64'          # authorized, capturable
export SANDBOX_AUTH='pay_4a8f2c1d3e65'   # authorized, capture will fail
export THREEDS='pay_9f14c73e0b2a'        # requires_confirmation
export EGRESS='pay_2d47b9e01f5c'         # partially refunded
export DISPUTED='pay_c8e05a1976b3'       # USD, open dispute
export USD_DISPUTE='dp_6b19d5ec8f30'
export EUR_DISPUTE='dp_9e21b7304c15'
```

## Rule one: every write carries an Idempotency-Key

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments" \
  -H 'Content-Type: application/json' \
  -d '{"customer": "'$AMELIA'", "amount_minor": 5000, "currency": "EUR"}'
# 400 idempotency_key_required
```

| Request | Result |
|---------|--------|
| no key | **400** `idempotency_key_required` |
| fresh key | the write happens |
| same key, **same body** | the original response, plus `idempotent_replay: true` |
| same key, **different body** | **409** `idempotency_key_reuse` |

Only successes are recorded, so a declined card can be retried with the same
key once the cardholder has fixed the problem.

## Rule two: the ledger is the source of truth

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/ledger/trial_balance"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/balance"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/ledger/entries?source=pay_3f7e1b0c2d54"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/ledger/entries?account=processing_fees"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/ledger/entries?currency=USD"
```

Accounts: `gateway_clearing`, `merchant_revenue`, `processing_fees`,
`disputed_funds`, `bank_settlement`. Anything else is a 400 listing them.

| Movement | Legs |
|----------|------|
| capture *A* | DR `gateway_clearing` · CR `merchant_revenue` |
| fee *F* | DR `processing_fees` · CR `gateway_clearing` |
| refund *R* | DR `merchant_revenue` · CR `gateway_clearing` |
| dispute opened | DR `disputed_funds` · CR `gateway_clearing` |
| dispute won | DR `gateway_clearing` · CR `disputed_funds` |
| dispute lost | DR `merchant_revenue` · CR `disputed_funds`, plus the fee |
| payout *P* | DR `bank_settlement` · CR `gateway_clearing` |

`available_minor` in `/v1/balance` **is** the `gateway_clearing` balance,
computed at read time. Pay out 50000 and it falls by exactly 50000.

## Customers and cards

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/customers"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/customers?status=delinquent"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/customers/$AMELIA"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/payment_methods?customer=$ACME"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/payment_methods/pm_visa_0002"

curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/customers" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: cust-001' \
  -d '{"name": "Rohit Bansal", "email": "rohit.bansal@orbit-labs.com",
       "currency": "EUR", "country": "ES"}'
```

A customer settles in **exactly one** currency, and that is enforced on every
charge.

## Charging

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: charge-001' \
  -d '{"customer": "'$AMELIA'", "payment_method": "pm_visa_4242",
       "amount_minor": 5000, "currency": "EUR",
       "description": "Scheduled export add-on",
       "statement_descriptor": "ORBIT LABS EXPORT"}'
```

Omit `payment_method` to use the customer's default. The outcome depends on the
card:

| Method | Outcome |
|--------|---------|
| `pm_visa_4242` `pm_mc_5555` `pm_visa_1881` `pm_visa_0259` | `authorized` |
| `pm_visa_0002` | **402** `insufficient_funds` |
| `pm_visa_0119` | **402** `expired_card` |
| `pm_visa_3220` | `requires_confirmation`, confirm succeeds |
| `pm_visa_3221` | `requires_confirmation`, confirm **fails** |
| `pm_amex_0005` | `authorized`, capture refused later |

A **402** carries the payment it created under `resource`. Charging
`$DMITRI` is refused with `customer_delinquent` before the card is considered.

Other refusals: `currency_mismatch` (customer settles elsewhere),
`currency_unsupported` (not EUR/GBP/USD), `amount_too_small`, `amount_invalid`,
`payment_method_mismatch` (someone else's card).

## The state machine

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/payments?status=authorized"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/payments/$SEATS"
```

Every payment carries `next_actions`:

| Status | Actions |
|--------|---------|
| `requires_confirmation` | confirm, cancel |
| `authorized` | capture, cancel |
| `partially_captured` | capture, cancel, refund |
| `captured` · `partially_refunded` | refund |
| `refunded` · `failed` · `canceled` | *(terminal)* |

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments/$THREEDS/confirm" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: conf-001' -d '{}'

curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments/$SEATS/capture" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: cap-001' \
  -d '{"amount_minor": 20000}'

# omit the amount to capture whatever remains
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments/$SEATS/capture" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: cap-002' -d '{}'

curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payments/$SANDBOX_AUTH/cancel" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: cancel-001' -d '{}'
```

A refused capture (`pm_amex_0005`) leaves the authorization **open** — read the
payment back and it is still `authorized`, so it can be retried or cancelled.
Cancelling reports `released_minor`.

An illegal transition is a 409 naming what is available; over-capture is a 400
naming what remains.

## Refunds

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/refunds" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: ref-001' \
  -d '{"payment": "'$EGRESS'", "amount_minor": 5000, "reason": "duplicate"}'

curl -s "$INHOUSE_PAYMENTS_API_URL/v1/refunds?payment=$EGRESS"
```

Reasons: `requested_by_customer`, `duplicate`, `fraudulent`,
`product_unacceptable`. Omit `amount_minor` to refund everything still
refundable. Over-refunding is a 400 naming the remainder; refunding a failed or
canceled payment is a 409.

**A payment with an open dispute cannot be refunded** — the funds are already
withheld. Close the dispute first.

## Disputes

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/disputes"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/disputes/$USD_DISPUTE"

curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/disputes/$USD_DISPUTE/evidence" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: ev-001' \
  -d '{"evidence": "Delivery signed for on 2026-05-02, tracking OL-4417."}'

curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/disputes/$USD_DISPUTE/close" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: cl-001' \
  -d '{"resolution": "won"}'
```

`$USD_DISPUTE` has a live evidence window; `$EUR_DISPUTE`'s has closed, so its
evidence is a 409 `evidence_window_closed`. Evidence moves a dispute to
`under_review` and cannot be resubmitted. `resolution` must be `won` or `lost`:
**won** returns the withheld funds, **lost** realises the chargeback plus a
1500-minor network fee — both as balanced ledger postings.

## Payouts

```bash
curl -s -X POST "$INHOUSE_PAYMENTS_API_URL/v1/payouts" \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: po-001' \
  -d '{"currency": "EUR", "amount_minor": 50000}'

curl -s "$INHOUSE_PAYMENTS_API_URL/v1/payouts"
```

Omit `amount_minor` to pay out the whole available balance. Below
`payout_minimum_minor` (1000) is `amount_too_small`; beyond the balance is
`insufficient_balance`, naming the figure.

## Events

```bash
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/events?limit=10"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/events?object=$SEATS"
curl -s "$INHOUSE_PAYMENTS_API_URL/v1/events?type=payment.captured"
```

Every mutation appends one, newest first.

## Errors

| Type | HTTP | Examples |
|------|------|----------|
| `idempotency_error` | 400 / 409 | missing key; key reused with a different body |
| `invalid_request_error` | 400 | `amount_too_large`, `amount_too_small`, `currency_mismatch`, `currency_unsupported`, `reason_invalid`, `status_unknown`, `account_unknown`, `insufficient_balance`, `resolution_invalid`, `parameter_missing` |
| `card_error` | **402** | `insufficient_funds`, `expired_card`, `authentication_failed`, `processor_declined`, `customer_delinquent` |
| `state_error` | 409 | `payment_state_invalid`, `payment_terminal`, `payment_disputed`, `dispute_not_open`, `dispute_closed`, `evidence_window_closed` |
| `not_found_error` | 404 | any unknown id |

Every envelope carries `type`, `code`, `message` and usually `param`; a
`card_error` also carries the payment under `resource`.
