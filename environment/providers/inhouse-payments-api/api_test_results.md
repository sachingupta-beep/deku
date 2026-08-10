# Orbit Payments Mock API — Test Results

Base URL: `http://localhost:8126` (in docker-compose:
`http://inhouse-payments-api:8126`)

## Endpoints covered

| Method | Path                                     | Status          |
|--------|------------------------------------------|-----------------|
| GET    | /health                                  | 200             |
| GET    | /v1/service                              | 200             |
| GET    | /v1/customers                            | 200             |
| POST   | /v1/customers                            | 201/400/409     |
| GET    | /v1/customers/{id}                       | 200/404         |
| GET    | /v1/payment_methods                      | 200/404         |
| GET    | /v1/payment_methods/{id}                 | 200/404         |
| GET    | /v1/payments                             | 200/400/404     |
| POST   | /v1/payments                             | 201/400/402/404/409 |
| GET    | /v1/payments/{id}                        | 200/404         |
| POST   | /v1/payments/{id}/confirm                | 200/400/402/404/409 |
| POST   | /v1/payments/{id}/capture                | 200/400/402/404/409 |
| POST   | /v1/payments/{id}/cancel                 | 200/400/404/409 |
| GET    | /v1/refunds                              | 200             |
| POST   | /v1/refunds                              | 201/400/404/409 |
| GET    | /v1/refunds/{id}                         | 200/404         |
| GET    | /v1/disputes                             | 200             |
| GET    | /v1/disputes/{id}                        | 200/404         |
| POST   | /v1/disputes/{id}/evidence               | 200/400/404/409 |
| POST   | /v1/disputes/{id}/close                  | 200/400/404/409 |
| GET    | /v1/ledger/entries                       | 200/400         |
| GET    | /v1/ledger/trial_balance                 | 200             |
| GET    | /v1/balance                              | 200             |
| GET    | /v1/payouts                              | 200             |
| POST   | /v1/payouts                              | 201/400/409     |
| GET    | /v1/payouts/{id}                         | 200/404         |
| GET    | /v1/events                               | 200             |

Collection run: **PASS 52 / WARN 42 / FAIL 0 / SKIP 0** over 94 requests. Every
WARN is an intentional error-path request, labelled `(N expected)` in the
collection, and every label matches the status the harness observed.

## The invariant: the books balance, always

Every money movement posts balanced legs, and a posting whose debits and
credits disagree is refused before anything is written. The collection asks for
the trial balance **before** any mutation and **after** all of them, and both
report `"balanced": true`:

| Movement | Legs |
|----------|------|
| capture *A* | DR `gateway_clearing` *A* · CR `merchant_revenue` *A* |
| fee *F* | DR `processing_fees` *F* · CR `gateway_clearing` *F* |
| refund *R* | DR `merchant_revenue` *R* · CR `gateway_clearing` *R* |
| dispute opened *D* | DR `disputed_funds` *D* · CR `gateway_clearing` *D* |
| dispute **won** | DR `gateway_clearing` *D* · CR `disputed_funds` *D* |
| dispute **lost** | DR `merchant_revenue` *D* · CR `disputed_funds` *D*, plus the network fee |
| payout *P* | DR `bank_settlement` *P* · CR `gateway_clearing` *P* |

`/v1/balance` is **derived** from those entries at read time — `available_minor`
*is* the `gateway_clearing` balance — rather than being a counter kept
alongside them. The collection proves the link by paying out 50000 and showing
the available balance fall by exactly that.

## Idempotency is mandatory, not optional

| Request | Result |
|---------|--------|
| POST with no `Idempotency-Key` | **400** `idempotency_key_required` |
| POST with a fresh key | 201, the payment created |
| the **same key, same body** | 201, the **same payment id**, `idempotent_replay: true` |
| the same key, a **different body** | **409** `idempotency_key_reuse` |

Only successes are recorded. The collection charges a declining card twice with
the same key and gets a 402 both times — a decline is not a completed write, so
the caller may retry once the cardholder has fixed the problem.

## The state machine is enforced

| Status | Available actions |
|--------|-------------------|
| `requires_confirmation` | confirm, cancel |
| `authorized` | capture, cancel |
| `partially_captured` | capture, cancel, refund |
| `captured` | refund |
| `partially_refunded` | refund |
| `refunded`, `failed`, `canceled` | *(terminal)* |

Every payment carries its own `next_actions`, and an illegal transition is a
409 that names them:

```json
{"error": {"type": "state_error", "code": "payment_state_invalid",
           "message": "Cannot capture a payment that is captured; the available actions are refund",
           "param": "status"}}
```

Partial amounts are tracked, so the errors are arithmetic:

```json
{"error": {"code": "amount_too_large", "message": "Cannot capture 99999; only 28000 EUR remains authorized on pay_5b07d21f8c64", "param": "amount_minor"}}
{"error": {"code": "amount_too_large", "message": "Cannot refund 99999; only 15000 EUR of pay_2d47b9e01f5c remains refundable", "param": "amount_minor"}}
```

The collection captures 20000 of a 48000 authorization, reads back
`capturable_minor: 28000`, then captures the rest by **omitting** the amount.

## The card decides the outcome

| Method | Outcome |
|--------|---------|
| `pm_visa_4242`, `pm_mc_5555`, `pm_visa_1881`, `pm_visa_0259` | authorize cleanly |
| `pm_visa_0002` | **402** `insufficient_funds` at authorize |
| `pm_visa_0119` | **402** `expired_card` at authorize |
| `pm_visa_3220` | `requires_confirmation`, then confirm succeeds |
| `pm_visa_3221` | `requires_confirmation`, then confirm **fails** |
| `pm_amex_0005` | authorizes, then the **capture** is refused |

A refused capture leaves the authorization open — the collection reads the
payment back to show it is still `authorized`, then cancels it instead.

Dmitri is a `delinquent` customer, refused before the card is considered at all.

## Disputes hold the funds

A dispute withdraws the money when it opens, which is why a disputed payment
**cannot** be refunded:

```json
{"error": {"type": "state_error", "code": "payment_disputed",
           "message": "Payment pay_c8e05a1976b3 has an open dispute (dp_6b19d5ec8f30); the funds are already withheld and cannot be refunded until it is closed"}}
```

Two disputes are seeded on purpose:

| Dispute | Window | Exercises |
|---------|--------|-----------|
| `dp_6b19d5ec8f30` (USD 25000) | open until 2027-06-10 | evidence submitted, then closed **won** — the funds come back |
| `dp_9e21b7304c15` (EUR 4500) | closed on 2026-06-05 | `evidence_window_closed`, then closed **lost** — the chargeback and the 1500 network fee are realised |

After the USD dispute closes, the same payment refunds cleanly — the collection
runs that refund immediately afterwards to show the block lifting.

## Money handling

Amounts are integers in the currency's minor unit and always travel with their
currency; there is no float in the module and fees use integer half-up
arithmetic:

| Currency | Fee | 193200 minor |
|----------|-----|--------------|
| EUR | 1.40% + 25 | 2730 |
| GBP | 1.50% + 20 | — |
| USD | 2.90% + 30 | — |

A customer settles in exactly one currency, so charging Amelia in USD is a
`currency_mismatch`; `JPY` is `currency_unsupported`; below `minimum_charge_minor`
is `amount_too_small`; a negative amount is `amount_invalid`.

## Seed data summary

- **Customers** (5): four active across ES/IE/DE/US, one **delinquent**; one
  settles in **USD**
- **Payment methods** (10) across eight behaviours
- **Payments** (9): captured, authorized ×2, requires_confirmation,
  partially_refunded, failed, canceled — in both currencies
- **Refunds** (1) · **Disputes** (2) · **Ledger entries** (22), balanced in
  both currencies · **Events** (7) · **Payouts** (0, created by the run)

The amounts tie to the rest of the fleet: 1932.00 EUR is the invoice total the
mail services carry, and `INV-2026-0417` / `ORD-2026-4417` are the same
documents.

## Notes

- Ids are prefixed and derived from the request, so the same idempotency key
  produces the same id: `pay_`, `re_`, `dp_`, `po_`, `cus_`, `le_`, `evt_`.
- A declined card is **402 Payment Required** — the request was well formed —
  and the envelope carries the payment under `resource`.
- `/v1/events` is appended to by every mutation and filterable by `object` and
  `type`.
- Mutations are held in process memory and reset on container restart.
