# inhouse-payments-api

The Orbit Labs in-house payments service — **not** a clone of a hosted
processor. It is the shape a team ends up with when they build the ledger
themselves, and that difference is the point of the service.

Run it as its own container (build context is the environment root):
```
docker compose up -d inhouse-payments-api
curl http://localhost:8126/health
curl http://localhost:8126/v1/ledger/trial_balance
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir inhouse-payments-api --port 8126
```

Four things follow from owning the ledger:

- **Every movement of money is double-entry.** A capture, a fee, a refund, a
  dispute and a payout each post *balanced* legs across `gateway_clearing`,
  `merchant_revenue`, `processing_fees`, `disputed_funds` and
  `bank_settlement`. `/v1/ledger/trial_balance` proves it — debits equal
  credits per currency, after every mutation — and `/v1/balance` is **derived**
  from those entries at read time rather than stored beside them. A posting
  whose legs do not balance is refused before anything is written.
- **Idempotency keys are mandatory on every write.** A POST without
  `Idempotency-Key` is a 400. Replaying a key returns the original response
  with `idempotent_replay: true`; reusing one with a different body is a 409.
  Only *successes* are recorded, so a declined card can be retried with the
  same key once the cardholder has fixed whatever was wrong.
- **Payments are a state machine, and it is enforced.** An illegal transition is
  a 409 that names the actions which *are* available
  (`Cannot capture a payment that is captured; the available actions are
  refund`). Partial captures and partial refunds carry running totals, so
  over-capture and over-refund are arithmetic rather than guesswork.
- **The card decides the outcome.** Each stored payment method carries a
  `behaviour`, so declines, step-up authentication and capture-time failures are
  reproducible rather than random.

Amounts are integers in the currency's minor unit and always travel with their
currency; there is no float anywhere in the module. Errors are a typed envelope
— `{"error": {"type", "code", "message", "param"}}` — and a declined card is
**402** carrying the payment it created under `resource`, so the caller can
follow it up.

## The test cards

| Method | Customer | Behaviour |
|--------|----------|-----------|
| `pm_visa_4242`, `pm_mc_5555` | Amelia | authorize and capture cleanly |
| `pm_visa_1881` | Acme | clean; the seeded partial-capture subject |
| `pm_visa_0002` | Acme | declines with `insufficient_funds` |
| `pm_amex_0005` | Acme | authorizes, then the **capture** fails |
| `pm_visa_3220` | Helena | needs step-up authentication, then succeeds |
| `pm_visa_0119` | Helena | declines with `expired_card` |
| `pm_visa_3221` | Dmitri | needs step-up, then **fails** it |
| `pm_visa_0259` | Priya | clean, in USD |

Dmitri is `delinquent`, which is refused before the card is even considered.

## The seeded books

Nine payments spanning every status, one refund, and two disputes — one with a
live evidence window, one whose window has closed. The opening trial balance
carries 22 entries and balances in both EUR and USD.

Both currencies are seeded on purpose: a customer settles in exactly one, so
charging Amelia in USD is a `currency_mismatch`, and the fee schedule differs
(EUR 1.40% + 25, USD 2.90% + 30).

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`inhouse_payments_api_postman_collection.json` for the runnable collection.
