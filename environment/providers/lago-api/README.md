# lago-api

Mock of Lago, open-source **usage-based billing** — a different animal from the
in-house payments service next door.

Run it as its own container (build context is the environment root):
```
docker compose up -d lago-api
curl http://localhost:8127/health
curl "http://localhost:8127/api/v1/customers/cust_orbit_labs/current_usage?external_subscription_id=sub_orbit_growth"
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir lago-api --port 8127
```

**Nothing here charges anyone.** That is the whole difference:

- **You ingest events, not charges.** A usage event names a subscription, a
  billable-metric `code` and some `properties`. What it costs is not decided at
  ingestion — it is computed later by aggregating the period's events and
  running the plan's charges over the result.
- **The aggregation type decides what "how much" means.** `sum_agg` adds a
  property up, `max_agg` takes the peak, `unique_count_agg` counts distinct
  values, `count_agg` counts the events themselves. The collection proves it:
  a *lower* seat reading leaves a `max_agg` charge untouched, and a *repeat*
  user leaves a `unique_count_agg` charge untouched, while a new one moves it.
- **The charge model decides what that number costs**, and the five models
  disagree wildly on the same units.
- **`current_usage` exists before any invoice does**, and is recomputed on
  every read. It is the endpoint people actually integrate against.

## The five charge models, on the seeded data

| Model | Plan · metric | Units | Cost |
|-------|---------------|-------|------|
| **graduated** | growth · api_calls | 320 000 | **444.00** — 50 000 free, then 150 000 @ €0.002, then 120 000 @ €0.0012 |
| **volume** | growth · data_egress_gb | 420 | **51.20** — the whole quantity in tier 2 @ €0.11 + €5 flat |
| **standard** | growth · active_seats | 24 (the peak) | **288.00** — €12 a seat |
| **package** | starter · api_calls | 34 000 | **15.00** — 10 000 free, then 3 blocks of 10 000 @ €5 |
| **percentage** | scale · payment_volume_cents | 1 250 000 | **188.50** — 150 bps + €0.50 an event |

`volume` versus `graduated` is the sharpest contrast, and
`/events/estimate_fees` shows it: adding 700 GB to the existing 420 pushes the
total past 1 000, so **all 1 120 GB re-price in the cheapest tier** — the charge
goes from €51.20 to €109.60, an increment of €58.40 rather than the €77 the
old rate would have implied.

## Other things that are Lago's

- **Ingestion is idempotent on your own `transaction_id`** — a repeat is
  refused, not double-billed — and a **batch is all-or-nothing**: one bad entry
  rejects the whole thing, named by index, and none of it lands.
- **Identity is dual**: a `lago_id` the service owns and an `external_id` you
  own. Customers, subscriptions and events are addressed by yours; invoices,
  credit notes and wallets only ever had a `lago_id`.
- **Responses are wrapped** (`{"customer": …}`, `{"customers": […], "meta":
  {…}}`) and errors carry a per-field `error_details` map, both because Lago's
  do. Validation failures are **422**, not 400.
- **A plan carries its own currency**, so a customer can only subscribe to one
  priced in theirs — `orbit_scale` is USD and only the USD customer is on it.
- **Invoices have two independent axes**: `status` (draft → finalized → voided)
  and `payment_status` (pending / succeeded / failed). A draft cannot record a
  payment, only a draft can be refreshed or finalized, only a finalized one can
  be voided, and a *paid* one must be credited instead.

## Money

Amounts are **integer cents**. Per-unit rates are **millicents** (1 cent =
1000) so a rate like €0.002 per API call is exact, and every total rounds
half-up to whole cents once, at the end. Lago itself uses decimal strings;
millicents keep the arithmetic exact without floats, and the choice is reported
in `/api/v1/service`.

## Seed data

Six billable metrics across four aggregation types; three plans covering all
five charge models; four customers (one with no subscription); four
subscriptions (one terminated); twenty usage events; three invoices (draft,
paid, payment-failed) with their fee breakdowns; a credit note and a prepaid
wallet.

See `api_test_results.md` for the endpoint matrix and the arithmetic,
`examples.md` for captured request/response pairs, and
`lago_api_postman_collection.json` for the runnable collection.
