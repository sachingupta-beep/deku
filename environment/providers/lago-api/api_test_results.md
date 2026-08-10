# Lago Mock API — Test Results

Base URL: `http://localhost:8127` (in docker-compose: `http://lago-api:8127`)

## Endpoints covered

| Method | Path                                              | Status      |
|--------|---------------------------------------------------|-------------|
| GET    | /health · /api/v1/service                         | 200         |
| GET    | /api/v1/billable_metrics                          | 200         |
| POST   | /api/v1/billable_metrics                          | 201/422     |
| GET    | /api/v1/billable_metrics/{code}                   | 200/404     |
| GET    | /api/v1/plans                                     | 200         |
| POST   | /api/v1/plans                                     | 201/422     |
| GET    | /api/v1/plans/{code}                              | 200/404     |
| GET    | /api/v1/customers                                 | 200         |
| POST   | /api/v1/customers                                 | 200/201/422 |
| GET    | /api/v1/customers/{external_id}                   | 200/404     |
| GET    | /api/v1/customers/{external_id}/current_usage     | 200/404/422 |
| GET    | /api/v1/subscriptions                             | 200/404     |
| POST   | /api/v1/subscriptions                             | 201/404/422 |
| GET    | /api/v1/subscriptions/{external_id}               | 200/404     |
| DELETE | /api/v1/subscriptions/{external_id}               | 200/404/422 |
| GET    | /api/v1/events                                    | 200         |
| POST   | /api/v1/events                                    | 200/404/422 |
| POST   | /api/v1/events/batch                              | 200/404/422 |
| POST   | /api/v1/events/estimate_fees                      | 200/404/422 |
| GET    | /api/v1/events/{transaction_id}                   | 200/404     |
| GET    | /api/v1/invoices                                  | 200/422     |
| GET    | /api/v1/invoices/{lago_id}                        | 200/404     |
| PUT    | /api/v1/invoices/{lago_id}                        | 200/404/422 |
| POST   | /api/v1/invoices/{lago_id}/refresh · /finalize · /void | 200/404/422 |
| GET    | /api/v1/credit_notes · /{lago_id}                 | 200/404     |
| POST   | /api/v1/credit_notes                              | 201/404/422 |
| GET    | /api/v1/wallets · /{lago_id}                      | 200/404     |
| POST   | /api/v1/wallets                                   | 201/404/422 |
| GET    | /api/v1/analytics/gross_revenue · /mrr            | 200         |

Collection run: **PASS 61 / WARN 48 / FAIL 0 / SKIP 0** over 109 requests.
Every WARN is an intentional error-path request, labelled `(N expected)` in the
collection, and every label matches the status the harness observed.

## The arithmetic, checked

The five charge models on the seeded events. Rates are millicents (1 cent =
1000); every total rounds half-up to cents once, at the end.

### graduated — each tier bills its own slice

`orbit_growth · api_calls`, 320 000 units from three events:

| Tier | Units in tier | Rate | Amount |
|------|---------------|------|--------|
| 0 – 50 000 | 50 000 | 0 | 0 |
| 50 001 – 200 000 | 150 000 | 200 mc | 30 000 c |
| 200 001 – ∞ | 120 000 | 120 mc | 14 400 c |
| | | | **44 400 c** |

### volume — the whole quantity falls in one tier

`orbit_growth · data_egress_gb`, 420 units → tier 2 (101–1000):
`420 × 11 000 mc = 4 620 c` plus a `500 c` flat = **5 120 c**.

### standard — a flat per-unit rate over an aggregate

`orbit_growth · active_seats`, `max_agg` peak of 24:
`24 × 1 200 000 mc` = **28 800 c**.

Growth total: `44 400 + 5 120 + 28 800` = **78 320 c**.

### package — blocks, with a free allowance

`orbit_starter · api_calls`, 34 000 units: `34 000 − 10 000 = 24 000` billable,
`ceil(24 000 / 10 000) = 3` packages × `500 c` = **1 500 c**.
Plus `support_tickets` (`count_agg`, 4 events) at `1 500 000 mc` = 6 000 c.
Starter total: **7 500 c**.

### percentage — basis points plus a per-event fixed amount

`orbit_scale · payment_volume_cents`, 1 250 000 units over 2 events:
`1 250 000 × 150 bps = 18 750 c` plus `2 × 50 c` = **18 850 c**.
Plus graduated api_calls (13 500 c) and `unique_count_agg` users
(2 × 250 000 mc = 500 c). Scale total: **32 850 c**.

## The aggregations, proved rather than asserted

The collection ingests and re-reads, so each aggregation's behaviour is visible:

| Ingested | Effect |
|----------|--------|
| 80 000 more API calls | growth 78 320 → **87 920 c** — the third tier absorbed them at 120 mc |
| a seat reading of **19**, below the peak of 24 | **no change** — `max_agg` already had 24 |
| a **repeat** user `u_priya` | **no change** — `unique_count_agg` already counted them |
| a **new** user `u_helena` | scale 32 850 → **33 100 c**, one more user at 250 000 mc |
| 500 000 calls dated **outside** the open period | **no change** — the period window excludes it |

## `estimate_fees`: volume's cliff, without ingesting anything

Adding 700 GB to the existing 420 pushes the total to 1 120 and past the
tier-2 ceiling, so **all 1 120 GB re-price in tier 3**:

```json
{"units": 1120, "charge_model": "volume", "amount_cents": 10960,
 "incremental_amount_cents": 5840,
 "breakdown": [{"model": "volume", "from_value": 1001, "to_value": null,
                "per_unit_amount_millicents": 8000, "flat_amount_cents": 2000}],
 "note": "estimate only; nothing was ingested"}
```

The charge goes from 5 120 c to 10 960 c — an increment of 5 840 c, not the
7 700 c the old rate would have implied. That cliff is exactly why the endpoint
exists, and nothing is stored.

## Ingestion is idempotent, and batches are atomic

| Request | Result |
|---------|--------|
| a fresh `transaction_id` | 200, ingested |
| the **same** `transaction_id` | **422** `value_already_exist` |
| a batch with the same id **twice inside it** | **422**, naming `events[1].transaction_id` |
| a batch where entry 1 is bad | **404**, naming `events[1]` — and entry 0 **is not applied** |

The collection reads back the good half of the rejected batch and gets a 404,
which is what makes "all or nothing" a fact rather than a claim.

## Invoices have two independent axes

`status`: draft → finalized → voided. `payment_status`: pending / succeeded /
failed. The collection walks the whole machine:

| Attempt | Result |
|---------|--------|
| pay a **draft** | 422 — finalize it first |
| void a **draft** | 422 — only a finalized invoice can be voided |
| credit-note a **draft** | 422 — a credit note needs a finalized invoice |
| **refresh** the draft | recomputes its fees from the usage as it stands |
| **finalize** it | assigns the real number, `ORB-2026-0018-001` |
| finalize / refresh again | 422 both ways |
| pay it | succeeds |
| void a **paid** invoice | 422 — issue a credit note instead |
| void the **payment-failed** one | succeeds |

`refresh` is the one that matters: it rebuilds the draft's fees from the events
in the open period, so the draft moved from 3 900 c of fees to 13 400 c once
the collection's own events had landed.

## Errors

Validation is **422** with a per-field map, and a missing resource is **404**:

```json
{"status": 422, "error": "sum_agg on 'data_egress_gb' needs properties.gb",
 "code": "unprocessable_entity",
 "error_details": {"properties": ["value_is_mandatory"]}}

{"status": 404, "error": "subscription not found: sub_nope",
 "code": "not_found", "error_details": {"subscription": ["not_found"]}}
```

Others worth knowing: metering a metric the plan does not charge, metering a
terminated subscription, subscribing to a plan priced in the wrong currency, a
`sum_agg` metric defined without a `field_name`, a graduated charge with no
tiers, and reading `current_usage` for someone else's subscription.

## Seed data summary

- **Billable metrics** (6) across `sum_agg`, `max_agg`, `unique_count_agg` and
  `count_agg`
- **Plans** (3) whose charges cover **all five** charge models; `orbit_scale`
  is priced in **USD**
- **Customers** (4), one with no subscription · **Subscriptions** (4), one
  **terminated**
- **Events** (20) across three subscriptions, all inside their open periods
- **Invoices** (3): draft, paid, payment-failed, with **8 fee lines** ·
  **Credit note** (1) · **Wallet** (1)

The amounts tie to the rest of the fleet: `ORB-2026-0004-001` is the invoice
the mail services carry, and the customers are the same Orbit Labs, Acme and
Northwind accounts.

## Notes

- `current_usage` reads the subscription's declared
  `current_period_from`/`current_period_to`, so the seeded May events are the
  open period regardless of the wall clock, and an event outside it is ignored.
- `POST /api/v1/customers` **upserts** on `external_id` — the collection
  changes a name and shows the `lago_id` survive.
- `/api/v1/analytics/mrr` divides each plan's amount by its interval and counts
  plan fees only; usage is not recurring revenue.
- Mutations are held in process memory and reset on container restart.
