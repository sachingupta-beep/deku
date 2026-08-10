# Lago Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$LAGO_API_URL`; responses are verbatim (long lists elided with
`…`).

```bash
export ORBIT='cust_orbit_labs'    ; export GROWTH='sub_orbit_growth'
export ACME='cust_acme'           ; export STARTER='sub_acme_starter'
export NORTHWIND='cust_northwind' ; export SCALE='sub_northwind_scale'
export DRAFT='inv_5b07d21f8c64f002'
export PAID='inv_3f7e1b0c2d54f001'
```

## The plan is the price list

```bash
curl -s "$LAGO_API_URL/api/v1/plans/orbit_growth"
```
```json
{"plan": {
  "lago_id": "pl_5b07d21f8c642e07", "code": "orbit_growth",
  "name": "Orbit Growth", "interval": "monthly",
  "amount_cents": 9900, "amount_currency": "EUR",
  "charges": [
    {"billable_metric_code": "active_seats", "charge_model": "standard",
     "properties": {"per_unit_amount_millicents": 1200000}},
    {"billable_metric_code": "api_calls", "charge_model": "graduated",
     "properties": {"graduated_ranges": [
       {"from_value": 0, "to_value": 50000, "per_unit_amount_millicents": 0, "flat_amount_cents": 0},
       {"from_value": 50001, "to_value": 200000, "per_unit_amount_millicents": 200, "flat_amount_cents": 0},
       {"from_value": 200001, "to_value": null, "per_unit_amount_millicents": 120, "flat_amount_cents": 0}]}},
    {"billable_metric_code": "data_egress_gb", "charge_model": "volume",
     "properties": {"volume_ranges": [ … ]}}],
  "active_subscriptions_count": 1, "created_at": "2025-10-02T10:06:18Z"}}
```

Rates are **millicents** — 200 mc is €0.002 per API call, exact and integral.

## `current_usage`: the whole service in one response

```bash
curl -s "$LAGO_API_URL/api/v1/customers/$ORBIT/current_usage?external_subscription_id=$GROWTH"
```
```json
{
  "customer_usage": {
    "from_datetime": "2026-05-01T00:00:00Z",
    "to_datetime": "2026-06-01T00:00:00Z",
    "issuing_date": "2026-06-01",
    "currency": "EUR",
    "amount_cents": 78320,
    "total_amount_cents": 78320,
    "lago_invoice_id": null,
    "charges_usage": [
      {"billable_metric_code": "active_seats", "aggregation_type": "max_agg",
       "charge_model": "standard", "events_count": 3, "units": 24,
       "amount_cents": 28800,
       "breakdown": [{"model": "standard", "units": 24,
                      "per_unit_amount_millicents": 1200000}]},
      {"billable_metric_code": "api_calls", "aggregation_type": "sum_agg",
       "charge_model": "graduated", "events_count": 3, "units": 320000,
       "amount_cents": 44400,
       "breakdown": [
         {"from_value": 0, "to_value": 50000, "units": 50000, "amount_cents": 0},
         {"from_value": 50001, "to_value": 200000, "units": 150000,
          "per_unit_amount_millicents": 200, "amount_cents": 30000},
         {"from_value": 200001, "to_value": null, "units": 120000,
          "per_unit_amount_millicents": 120, "amount_cents": 14400}]},
      {"billable_metric_code": "data_egress_gb", "aggregation_type": "sum_agg",
       "charge_model": "volume", "events_count": 2, "units": 420,
       "amount_cents": 5120,
       "breakdown": [{"model": "volume", "from_value": 101, "to_value": 1000,
                      "units": 420, "per_unit_amount_millicents": 11000,
                      "flat_amount_cents": 500}]}],
    "note": "recomputed from the events in the open period on every read; no invoice exists yet"
  }
}
```

Three events became 320 000 units by `sum_agg`; three seat readings became 24 by
`max_agg`. Every charge shows its own `breakdown`, so the number is auditable
rather than asserted.

The other two subscriptions exercise the remaining models:

```bash
curl -s "$LAGO_API_URL/api/v1/customers/$ACME/current_usage?external_subscription_id=$STARTER"
```
```json
{"charges_usage": [
  {"billable_metric_code": "api_calls", "charge_model": "package",
   "units": 34000, "amount_cents": 1500,
   "breakdown": [{"model": "package", "free_units": 10000,
                  "billable_units": 24000, "package_size": 10000,
                  "packages": 3, "amount_cents": 500}]},
  {"billable_metric_code": "support_tickets", "aggregation_type": "count_agg",
   "charge_model": "standard", "events_count": 4, "units": 4,
   "amount_cents": 6000}], "…": "…"}
```

```bash
curl -s "$LAGO_API_URL/api/v1/customers/$NORTHWIND/current_usage?external_subscription_id=$SCALE"
```
```json
{"currency": "USD", "amount_cents": 32850, "charges_usage": [
  {"billable_metric_code": "payment_volume_cents", "charge_model": "percentage",
   "units": 1250000, "amount_cents": 18850,
   "breakdown": [{"model": "percentage", "rate_bps": 150,
                  "variable_amount_cents": 18750,
                  "fixed_amount_cents_per_event": 50, "events": 2,
                  "fixed_amount_cents": 100}]},
  {"billable_metric_code": "unique_users", "aggregation_type": "unique_count_agg",
   "events_count": 3, "units": 2, "amount_cents": 500}], "…": "…"}
```

Three `unique_users` events, **two** units — one user appears twice.

## Ingesting usage

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/events" \
  -H 'Content-Type: application/json' \
  -d '{"event": {"transaction_id": "run-growth-api-2026-05-30",
                 "external_subscription_id": "'$GROWTH'",
                 "code": "api_calls", "timestamp": "2026-05-30T12:00:00Z",
                 "properties": {"count": 80000, "region": "eu-west"}}}'
```
```json
{"event": {"lago_id": "ev_f6bcaefa89ac41e9",
           "transaction_id": "run-growth-api-2026-05-30",
           "external_subscription_id": "sub_orbit_growth", "code": "api_calls",
           "timestamp": "2026-05-30T12:00:00Z",
           "properties": {"count": 80000, "region": "eu-west"},
           "created_at": "…"}}
```

Re-reading the usage: **78 320 → 87 920** cents. The extra 80 000 calls landed
entirely in the third tier at 120 mc.

Send the same `transaction_id` again:

```json
{"status": 422, "error": "transaction_id 'run-growth-api-2026-05-30' has already been ingested",
 "code": "unprocessable_entity",
 "error_details": {"transaction_id": ["value_already_exist"]}}
```

Three more ingestions and the aggregations show their character:

| Ingested | Effect |
|----------|--------|
| `{"seats": 19}` — below the peak | **nothing**; `max_agg` already had 24 |
| `{"user_id": "u_priya"}` — seen before | **nothing**; already counted |
| `{"user_id": "u_helena"}` — new | scale 32 850 → **33 100** |
| 500 000 calls dated `2026-06-14` | **nothing**; outside the open period |

## Batches are all or nothing

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/events/batch" \
  -H 'Content-Type: application/json' \
  -d '{"events": [{"transaction_id": "run-batch-good", "external_subscription_id": "'$STARTER'", "code": "support_tickets", "properties": {}},
                  {"transaction_id": "run-batch-bad", "external_subscription_id": "sub_nope", "code": "support_tickets", "properties": {}}]}'
```
```json
{"status": 404, "error": "subscription not found: sub_nope", "code": "not_found",
 "error_details": {"events[1]": {"subscription": ["not_found"]}}}
```

```bash
curl -s "$LAGO_API_URL/api/v1/events/run-batch-good"
```
```json
{"status": 404, "error": "event not found: run-batch-good", "code": "not_found",
 "error_details": {"event": ["not_found"]}}
```

Entry 0 was valid and still did not land. A duplicate *inside* one batch is
caught too:

```json
{"status": 422, "error": "transaction_id 'run-batch-dup' appears twice in the same batch",
 "error_details": {"events[1].transaction_id": ["value_already_exist"]}}
```

## `estimate_fees`: volume's cliff, priced without storing anything

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/events/estimate_fees" \
  -H 'Content-Type: application/json' \
  -d '{"event": {"external_subscription_id": "'$GROWTH'",
                 "code": "data_egress_gb", "properties": {"gb": 700}}}'
```
```json
{"fees": [{"lago_id": null, "billable_metric_code": "data_egress_gb",
           "charge_model": "volume", "units": 1120, "amount_cents": 10960,
           "amount_currency": "EUR", "incremental_amount_cents": 5840,
           "breakdown": [{"model": "volume", "from_value": 1001,
                          "to_value": null, "units": 1120,
                          "per_unit_amount_millicents": 8000,
                          "flat_amount_cents": 2000}],
           "note": "estimate only; nothing was ingested"}]}
```

420 + 700 = 1 120 crosses the tier-2 ceiling, so **all** of it re-prices at
€0.08 — the charge goes 5 120 → 10 960, an increment of 5 840 rather than the
7 700 the old rate implied. That is `volume`; `graduated` would have charged
only the new slice.

## Invoices: two axes, both enforced

```bash
curl -s "$LAGO_API_URL/api/v1/invoices/$PAID"
```
```json
{"invoice": {"lago_id": "inv_3f7e1b0c2d54f001", "number": "ORB-2026-0004-001",
  "status": "finalized", "payment_status": "succeeded", "currency": "EUR",
  "fees_amount_cents": 81688, "coupons_amount_cents": 0,
  "sub_total_excluding_taxes_cents": 81688, "taxes_rate_bps": 2100,
  "taxes_amount_cents": 17155, "total_amount_cents": 98843,
  "credit_notes_amount_cents": 4500, "total_due_amount_cents": 94343,
  "fees": [
    {"fee_type": "subscription", "units": 1, "amount_cents": 9900,
     "description": "Orbit Growth, 2026-04-01 to 2026-05-01"},
    {"fee_type": "charge", "billable_metric_code": "active_seats",
     "charge_model": "standard", "units": 22, "amount_cents": 26400}, "…"],
  "…": "…"}}
```

The draft refuses everything until it is finalized:

```json
{"status": 422, "error": "Invoice inv_5b07d21f8c64f002 is a draft; finalize it before recording a payment"}
{"status": 422, "error": "Only a finalized invoice can be voided; invoice inv_5b07d21f8c64f002 is draft"}
{"status": 422, "error": "A credit note needs a finalized invoice; inv_5b07d21f8c64f002 is draft"}
```

`refresh` rebuilds a draft's fees from the usage as it stands right now — after
the collection's own events, its fee total moves from 3 900 to 13 400 cents.
Finalizing assigns the real number:

```json
{"invoice": {"number": "ORB-2026-0018-001", "status": "finalized", "…": "…"}}
```

And once paid, it can only be credited:

```json
{"status": 422, "error": "Invoice inv_5b07d21f8c64f002 is paid; issue a credit note instead of voiding it"}
```

## Credit notes

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/credit_notes" \
  -H 'Content-Type: application/json' \
  -d '{"credit_note": {"invoice_id": "'$PAID'", "reason": "order_change",
                       "credit_amount_cents": 2000,
                       "description": "Seats over-counted for the last week of April"}}'
```
```json
{"credit_note": {"lago_id": "cn_2a63d0805f304fa5",
                 "number": "ORB-2026-0004-001-CN02",
                 "reason": "order_change", "credit_status": "available",
                 "credit_amount_cents": 2000, "balance_amount_cents": 2000,
                 "…": "…"}}
```

The invoice's `total_due_amount_cents` drops by exactly that. Over-crediting is
refused with the figure:

```json
{"status": 422, "error": "Cannot credit 9999999; only 92103 remains creditable on inv_3f7e1b0c2d54f001"}
```

## Upsert, and the id you own

```bash
curl -s -X POST "$LAGO_API_URL/api/v1/customers" \
  -H 'Content-Type: application/json' \
  -d '{"customer": {"external_id": "cust_helios", "name": "Helios Robotics AG", "city": "Munich"}}'
```

Returns **200** with `"upserted": true` and the *same* `lago_id` the customer
already had — Lago keys on your `external_id`, and unspecified fields are left
alone.

## Analytics

```bash
curl -s "$LAGO_API_URL/api/v1/analytics/gross_revenue"
curl -s "$LAGO_API_URL/api/v1/analytics/mrr"
```
```json
{"gross_revenues": [{"month": "2026-05", "currency": "EUR", "amount_cents": 115085},
                    {"month": "2026-05", "currency": "USD", "amount_cents": 22100}]}
{"mrrs": [{"currency": "EUR", "amount_cents": 12800},
          {"currency": "USD", "amount_cents": 8250}],
 "note": "plan fees only; usage charges are not recurring revenue"}
```

MRR divides each plan by its interval — the yearly USD plan contributes
99 000 / 12 = 8 250 a month.
