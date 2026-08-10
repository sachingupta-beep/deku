---
name: lago-api-connector
description: >
  Lago API (Mock) mock HTTP API. Base URL is provided via the
  `LAGO_API_URL` environment variable. 29 endpoint(s) across GET, POST, PUT, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Lago API (Mock)

Mock of Lago, open-source **usage-based billing**. **All requests go to the base
URL in `$LAGO_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `LAGO_API_URL` | Base URL for all requests (e.g. `http://lago-api:8127`) |

## Four things to know first

**Nothing here charges anyone.** You `POST /api/v1/events` to record usage;
what it costs is computed later from the plan's charges.

**Aggregation decides "how much", the charge model decides "what it costs".**
`sum_agg` adds a property up, `max_agg` takes the peak, `unique_count_agg`
counts distinct values, `count_agg` counts events. Then `graduated`, `volume`,
`package`, `percentage` or `standard` prices it.

**`current_usage` exists before any invoice does** and is recomputed on every
read — it is the endpoint to integrate against.

**Ingestion is idempotent on your own `transaction_id`**; a batch is
all-or-nothing.

## Seeded catalogue

| Metric | Aggregation |
|--------|-------------|
| `api_calls` | `sum_agg` on `count` |
| `data_egress_gb` | `sum_agg` on `gb` |
| `active_seats` | `max_agg` on `seats` |
| `unique_users` | `unique_count_agg` on `user_id` |
| `support_tickets` | `count_agg` |
| `payment_volume_cents` | `sum_agg` on `amount_cents` |

| Plan | Currency | Charges |
|------|----------|---------|
| `orbit_starter` | EUR | api_calls **package**, support_tickets **standard** |
| `orbit_growth` | EUR | api_calls **graduated**, data_egress_gb **volume**, active_seats **standard** |
| `orbit_scale` | **USD** | api_calls graduated, unique_users standard, payment_volume_cents **percentage** |

| Customer | Subscription |
|----------|--------------|
| `cust_orbit_labs` | `sub_orbit_growth` |
| `cust_acme` | `sub_acme_starter`, `sub_acme_legacy` (**terminated**) |
| `cust_northwind` | `sub_northwind_scale` (USD) |
| `cust_helios` | *(none)* |

Invoices: `inv_3f7e1b0c2d54f001` (paid), `inv_5b07d21f8c64f002` (**draft**),
`inv_9f14c73e0b2af003` (payment failed).

## Endpoints

| Method | Path |
|--------|------|
| GET | `/health` · `/api/v1/service` |
| GET/POST | `/api/v1/billable_metrics`; GET `/{code}` |
| GET/POST | `/api/v1/plans`; GET `/{code}` |
| GET/POST | `/api/v1/customers`; GET `/{external_id}` · `/{external_id}/current_usage` |
| GET/POST | `/api/v1/subscriptions`; GET/DELETE `/{external_id}` |
| GET/POST | `/api/v1/events`; POST `/batch` · `/estimate_fees`; GET `/{transaction_id}` |
| GET | `/api/v1/invoices`; GET/PUT `/{lago_id}`; POST `/{lago_id}/refresh` · `/finalize` · `/void` |
| GET/POST | `/api/v1/credit_notes`; GET `/{lago_id}` |
| GET/POST | `/api/v1/wallets`; GET `/{lago_id}` |
| GET | `/api/v1/analytics/gross_revenue` · `/mrr` |

## Usage

```bash
# what is this subscription costing right now?
curl -s "$LAGO_API_URL/api/v1/customers/cust_orbit_labs/current_usage?external_subscription_id=sub_orbit_growth"

# record usage
curl -s -X POST "$LAGO_API_URL/api/v1/events" \
  -H 'Content-Type: application/json' \
  -d '{"event": {"transaction_id": "job-2026-08-06-001",
                 "external_subscription_id": "sub_orbit_growth",
                 "code": "api_calls", "timestamp": "2026-05-30T12:00:00Z",
                 "properties": {"count": 80000}}}'

# what would this cost, without recording it?
curl -s -X POST "$LAGO_API_URL/api/v1/events/estimate_fees" \
  -H 'Content-Type: application/json' \
  -d '{"event": {"external_subscription_id": "sub_orbit_growth",
                 "code": "data_egress_gb", "properties": {"gb": 700}}}'

# the invoice machine
curl -s -X POST "$LAGO_API_URL/api/v1/invoices/inv_5b07d21f8c64f002/refresh"
curl -s -X POST "$LAGO_API_URL/api/v1/invoices/inv_5b07d21f8c64f002/finalize"
```

**Events must fall inside the subscription's declared period** —
`current_period_from`/`current_period_to` on the subscription — or they will not
show in `current_usage`. Pass an explicit `timestamp`; the seeded periods are
May 2026.

**Money**: amounts are integer **cents**; per-unit rates are **millicents**
(1 cent = 1000), so €0.002 per call is `200`. Totals round half-up once.

**Identity is dual**: `external_id` for customers, subscriptions and events;
`lago_id` for invoices, credit notes and wallets.

**Errors are 422 with a per-field map** (`error_details`), or 404 for a missing
resource. Notable refusals: a repeated `transaction_id`, a metric the plan does
not charge, a terminated subscription, a plan priced in the wrong currency, a
draft invoice asked to record a payment, and a paid invoice asked to be voided.

The audit log of every call the agent makes is available at
`$LAGO_API_URL/audit/requests` (used for grading).
