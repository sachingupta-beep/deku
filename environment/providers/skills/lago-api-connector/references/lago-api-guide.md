# Lago API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$LAGO_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `LAGO_API_URL` | Base URL for all requests |

```bash
export ORBIT='cust_orbit_labs'    ; export GROWTH='sub_orbit_growth'
export ACME='cust_acme'           ; export STARTER='sub_acme_starter'
export NORTHWIND='cust_northwind' ; export SCALE='sub_northwind_scale'
export HELIOS='cust_helios'       ; export LEGACY='sub_acme_legacy'
export DRAFT='inv_5b07d21f8c64f002'
export PAID='inv_3f7e1b0c2d54f001'
export FAILED='inv_9f14c73e0b2af003'
```

## The mental model

Nothing here charges anyone. Usage goes in as **events**; cost comes out of
**aggregation × charge model**, computed at read time:

```
events  ──aggregation──▶  units  ──charge model──▶  cents
```

## The catalogue

```bash
curl -s "$LAGO_API_URL/api/v1/service"
curl -s "$LAGO_API_URL/api/v1/billable_metrics"
curl -s "$LAGO_API_URL/api/v1/billable_metrics/active_seats"
curl -s "$LAGO_API_URL/api/v1/plans"
curl -s "$LAGO_API_URL/api/v1/plans/orbit_growth"
```

| Metric | Aggregation | Meaning |
|--------|-------------|---------|
| `api_calls` | `sum_agg` on `count` | adds the property up |
| `data_egress_gb` | `sum_agg` on `gb` | adds the property up |
| `active_seats` | `max_agg` on `seats` | takes the **peak**, so a lower reading changes nothing |
| `unique_users` | `unique_count_agg` on `user_id` | counts **distinct** values |
| `support_tickets` | `count_agg` | counts the events themselves |
| `payment_volume_cents` | `sum_agg` on `amount_cents` | adds the property up |

| Plan | Currency | Charge models in play |
|------|----------|----------------------|
| `orbit_starter` | EUR | **package**, standard |
| `orbit_growth` | EUR | **graduated**, **volume**, standard |
| `orbit_scale` | **USD** | graduated, standard, **percentage** |

## Reading the open period

```bash
curl -s "$LAGO_API_URL/api/v1/customers/$ORBIT/current_usage?external_subscription_id=$GROWTH"
curl -s "$LAGO_API_URL/api/v1/customers/$ACME/current_usage?external_subscription_id=$STARTER"
curl -s "$LAGO_API_URL/api/v1/customers/$NORTHWIND/current_usage?external_subscription_id=$SCALE"
```

Each charge comes back with its own `breakdown`, so the number is auditable.
Seeded totals: growth **78 320 c**, starter **7 500 c**, scale **32 850 c**.

Refusals: no `external_subscription_id` (422), a subscription belonging to
another customer (422), a terminated subscription (422), an unknown customer
(404).

## The charge models, in one table

| Model | Rule |
|-------|------|
| `standard` | `units × per_unit_amount_millicents` |
| `package` | `ceil((units − free_units) / package_size) × amount_cents` |
| `graduated` | each tier bills **its own slice** at its own rate, plus any flat |
| `volume` | the **whole** quantity falls in one tier and is billed entirely there |
| `percentage` | `units × rate_bps / 10000`, plus `fixed_amount_cents_per_event × events` |

`graduated` versus `volume` is the distinction worth internalising: under
`graduated`, crossing a tier only re-prices the new slice; under `volume`, it
re-prices **everything**.

## Recording usage

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/events" \
  -H 'Content-Type: application/json' \
  -d '{"event": {"transaction_id": "job-2026-08-06-001",
                 "external_subscription_id": "'$GROWTH'",
                 "code": "api_calls", "timestamp": "2026-05-30T12:00:00Z",
                 "properties": {"count": 80000, "region": "eu-west"}}}'
```

**The timestamp matters.** `current_usage` reads the subscription's declared
`current_period_from`/`current_period_to`; an event outside that window is
stored but does not count. The seeded periods are May 2026, so pass an explicit
timestamp inside them.

**`transaction_id` is yours and makes ingestion idempotent** — a repeat is a
422 `value_already_exist`, never a second charge.

Other refusals: no `transaction_id` (422), missing the property the aggregation
needs (422, naming it), a metric the plan does not charge (422), a terminated
subscription (422), an unknown subscription or metric (404).

```bash
curl -s "$LAGO_API_URL/api/v1/events?external_subscription_id=$GROWTH&code=active_seats"
curl -s "$LAGO_API_URL/api/v1/events/evt_growth_seats_2026_05_18"
```

## Batches are atomic

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/events/batch" \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"transaction_id": "b1", "external_subscription_id": "'$STARTER'", "code": "support_tickets", "timestamp": "2026-05-30T09:00:00Z", "properties": {}},
                  {"transaction_id": "b2", "external_subscription_id": "'$STARTER'", "code": "support_tickets", "timestamp": "2026-05-31T09:00:00Z", "properties": {}}]}'
```

One bad entry rejects the whole batch, named by index (`events[1]`), and **none
of it lands** — including the entries that were fine. A `transaction_id`
repeated inside a single batch is caught too. Maximum 100 per batch; an empty
array is 422.

## Pricing without recording

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/events/estimate_fees" \
  -H 'Content-Type: application/json' \
  -d '{"event": {"external_subscription_id": "'$GROWTH'",
                 "code": "data_egress_gb", "properties": {"gb": 700}}}'
```

Returns the charge as it *would* stand plus `incremental_amount_cents`, and
stores nothing. On the seeded data this is the clearest demonstration of
`volume`: 420 + 700 = 1 120 crosses into the cheapest tier, so all of it
re-prices and the charge goes 5 120 → 10 960.

## Invoices

```bash
curl -s "$LAGO_API_URL/api/v1/invoices?status=draft"
curl -s "$LAGO_API_URL/api/v1/invoices?payment_status=failed"
curl -s "$LAGO_API_URL/api/v1/invoices/$PAID"

curl -s -X POST "$LAGO_API_URL/api/v1/invoices/$DRAFT/refresh"
curl -s -X POST "$LAGO_API_URL/api/v1/invoices/$DRAFT/finalize"
curl -s -X PUT  "$LAGO_API_URL/api/v1/invoices/$DRAFT" \
  -H 'Content-Type: application/json' \
  -d '{"invoice": {"payment_status": "succeeded"}}'
curl -s -X POST "$LAGO_API_URL/api/v1/invoices/$FAILED/void"
```

Two independent axes — `status` (draft → finalized → voided) and
`payment_status` (pending / succeeded / failed) — and the machine is enforced:

| Attempt | Result |
|---------|--------|
| pay a draft | 422, finalize first |
| void a draft | 422, only a finalized invoice can be voided |
| refresh a finalized invoice | 422, only a draft can be refreshed |
| finalize twice | 422 |
| void a **paid** invoice | 422, issue a credit note instead |

`refresh` rebuilds the draft's fees from the usage as it stands right now, which
is how a draft catches up with events ingested since it was opened. Finalizing
replaces the placeholder number with the real one.

## Credit notes and wallets

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/credit_notes" \
  -H 'Content-Type: application/json' \
  -d '{"credit_note": {"invoice_id": "'$PAID'", "reason": "order_change",
                       "credit_amount_cents": 2000,
                       "description": "Seats over-counted"}}'

curl -s -X POST "$LAGO_API_URL/api/v1/wallets" \
  -H 'Content-Type: application/json' \
  -d '{"wallet": {"external_customer_id": "'$HELIOS'", "granted_credits": 500,
                  "rate_amount_cents": 100}}'
```

Reasons: `duplicated_charge`, `product_unsatisfactory`, `order_change`,
`order_cancellation`, `fraudulent_charge`, `other`. A credit note needs a
**finalized** invoice, and over-crediting is refused with the remaining figure.

## Catalogue and customer writes

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/billable_metrics" \
  -H 'Content-Type: application/json' \
  -d '{"billable_metric": {"code": "storage_gb", "name": "Storage",
                           "aggregation_type": "max_agg", "field_name": "gb"}}'

curl -s -X POST "$LAGO_API_URL/api/v1/plans" \
  -H 'Content-Type: application/json' \
  -d '{"plan": {"code": "orbit_archive", "interval": "monthly",
                "amount_cents": 1900, "amount_currency": "EUR",
                "charges": [{"billable_metric_code": "storage_gb",
                             "charge_model": "standard",
                             "properties": {"per_unit_amount_millicents": 3000}}]}}'

curl -s -X POST "$LAGO_API_URL/api/v1/customers" \
  -H 'Content-Type: application/json' \
  -d '{"customer": {"external_id": "cust_helios", "name": "Helios Robotics AG"}}'

curl -s -X POST "$LAGO_API_URL/api/v1/subscriptions" \
  -H 'Content-Type: application/json' \
  -d '{"subscription": {"external_id": "sub_helios_archive",
                        "external_customer_id": "'$HELIOS'",
                        "plan_code": "orbit_archive",
                        "current_period_from": "2026-05-01T00:00:00Z",
                        "current_period_to": "2026-06-01T00:00:00Z"}}'

curl -s -X DELETE "$LAGO_API_URL/api/v1/subscriptions/sub_helios_archive"
```

`POST /api/v1/customers` **upserts** on `external_id` — the `lago_id` survives
and unspecified fields are left alone, so it answers **200** rather than 201.

Each charge model demands its own property: `graduated_ranges`,
`volume_ranges`, `package_size`, `per_unit_amount_millicents`, `rate_bps`.
Missing it is a 422 naming both the charge index and what is needed.

**A plan carries its own currency**, so subscribing a EUR customer to
`orbit_scale` (USD) is a 422.

## Analytics

```bash
curl -s "$LAGO_API_URL/api/v1/analytics/gross_revenue"
curl -s "$LAGO_API_URL/api/v1/analytics/mrr?currency=EUR"
```

Gross revenue buckets finalized invoices by month and currency. MRR divides
each active plan by its interval and counts **plan fees only** — usage is not
recurring revenue.

## Errors

| HTTP | When |
|------|------|
| 422 | any validation failure, with `error_details` naming the field: a repeated `transaction_id`, a missing aggregation property, a metric the plan does not charge, a terminated subscription, a currency mismatch, a bad charge model or missing charge property, an invalid invoice transition, over-crediting |
| 404 | an unknown customer, subscription, plan, metric, event, invoice, credit note or wallet |
