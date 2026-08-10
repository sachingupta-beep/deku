# Kill Bill API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$KILLBILL_API_URL`.** Responses are deterministic fixtures.

## Credentials come first

Every request needs a tenant; every **write** needs an audit identity as well.

```bash
KB=(-H 'X-Killbill-ApiKey: orbit-labs'
    -H 'X-Killbill-ApiSecret: orbit-labs-secret-9f14c73e')
WRITE=("${KB[@]}" -H 'X-Killbill-CreatedBy: agent'
       -H 'Content-Type: application/json')

ACME_KB=(-H 'X-Killbill-ApiKey: acme-reseller'
         -H 'X-Killbill-ApiSecret: acme-reseller-secret-5b07d21f')

export AMELIA='a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54'
export ACME='b2e4d8ea-5c3f-4d7b-8e96-4a8f2c1d3e65'
export NORTHWIND='c3f5e9fb-6d40-4e8c-9fa7-5b903d2e4f76'
export HELIOS='d4a6fa0c-7e51-4f9d-80b8-6ca14e3f5087'
export BUNDLE='bd11f3c7-d94b-4e6a-8d85-3f7e1b0c2d54'
export BASE_SUB='s111f3c7-d94b-4e6a-8d85-3f7e1b0c2d54'
export ADDON_SUB='s222e4d8-ea5c-4f7b-8e96-4a8f2c1d3e65'
export TRIAL_SUB='s444a6fa-0c7e-4f9d-80b8-6ca14e3f5087'
export PAID_INV='i111f3c7-d94b-4e6a-8d85-3f7e1b0c2d54'
export DRAFT_INV='i444a6fa-0c7e-4f9d-80b8-6ca14e3f5087'
export SETTLED='p111f3c7-d94b-4e6a-8d85-3f7e1b0c2d54'
export FAILED='p222e4d8-ea5c-4f7b-8e96-4a8f2c1d3e65'
```

Missing or wrong credentials are **401** (`code` 4000). A write without
`X-Killbill-CreatedBy` is **400** (`code` 4001), checked before the body.

**Tenancy partitions everything.** `orbit-labs` sees three accounts,
`acme-reseller` sees one, and each other's are **404** — not 403. From the
other tenant, the object does not exist.

## Service and catalog

```bash
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/nodesInfo"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/catalog"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/catalog/availableBasePlans"
```

Six products across `BASE`, `ADD_ON` and `STANDALONE`; six plans with `TRIAL`
and `EVERGREEN` phases. Each base product declares its add-ons:

| Base | Offers |
|------|--------|
| `OrbitStarter` | `OrbitSupport` |
| `OrbitGrowth` | `OrbitSupport`, `OrbitEgressPack` |
| `OrbitScale` | `OrbitSupport`, `OrbitEgressPack` |

## Accounts

```bash
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts?externalKey=orbit-acme"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA/timeline"
```

Creating answers **201 with a `Location` header and no body**:

```bash
curl -si -X POST "${WRITE[@]}" \
  -d '{"externalKey": "orbit-rohit", "name": "Rohit Bansal",
       "email": "rohit.bansal@orbit-labs.com", "currency": "EUR",
       "country": "ES", "timeZone": "Europe/Madrid", "billCycleDayLocal": 7}' \
  "$KILLBILL_API_URL/1.0/kb/accounts"
# 201, location: /1.0/kb/accounts/1f16811b-…

curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts?externalKey=orbit-rohit"
```

Follow the header, or look it up by the key you chose. Updating answers
**204**:

```bash
curl -s -X PUT "${WRITE[@]}" -d '{"email": "amelia@orbit-labs.com"}' \
  "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA"
```

Only `name`, `email`, `country`, `timeZone` and `billCycleDayLocal` are
updatable — `currency` is a 400. A duplicate `externalKey` is a **409**, an
unsupported currency a 400.

## Subscriptions: two timelines

```bash
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA/bundles"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/bundles/$BUNDLE"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/subscriptions/$TRIAL_SUB"
```

A subscription carries `startDate` (access) **and** `billingStartDate` (money),
plus `chargedThroughDate`, `cancelledDate` and `billingEndDate`. The trial
subscription starts on 2026-05-19 and bills from 2026-06-02.

```bash
# a BASE subscription opens its own bundle
curl -si -X POST "${WRITE[@]}" \
  -d '{"accountId": "'$NORTHWIND'", "externalKey": "orbit-northwind-sandbox",
       "planName": "orbit-starter-monthly",
       "entitlementDate": "2026-06-01", "billingDate": "2026-06-15"}' \
  "$KILLBILL_API_URL/1.0/kb/subscriptions"

# an ADD_ON joins an existing bundle, if the base offers it
curl -si -X POST "${WRITE[@]}" \
  -d '{"accountId": "'$AMELIA'", "externalKey": "orbit-amelia-growth",
       "planName": "orbit-egress-monthly"}' \
  "$KILLBILL_API_URL/1.0/kb/subscriptions"

# change plan (204)
curl -s -X PUT "${WRITE[@]}" -d '{"planName": "orbit-scale-annual"}' \
  "$KILLBILL_API_URL/1.0/kb/subscriptions/$BASE_SUB"
```

Refusals: an add-on the base does not offer (400, naming what it does), an
add-on with no bundle (400), an unknown plan (404), a `BASE`→`ADD_ON` change
(400), changing a cancelled subscription (400).

**Cancelling takes two policies:**

```bash
# access stops today, billing runs to the end of the term
curl -s -X DELETE "${KB[@]}" -H 'X-Killbill-CreatedBy: agent' \
  "$KILLBILL_API_URL/1.0/kb/subscriptions/$BASE_SUB?entitlementPolicy=IMMEDIATE&billingPolicy=END_OF_TERM"

# the mirror image
curl -s -X DELETE "${KB[@]}" -H 'X-Killbill-CreatedBy: agent' \
  "$KILLBILL_API_URL/1.0/kb/subscriptions/$ADDON_SUB?entitlementPolicy=END_OF_TERM&billingPolicy=IMMEDIATE"
```

`entitlementPolicy`: `IMMEDIATE`, `END_OF_TERM`. `billingPolicy`: those plus
`START_OF_TERM`. Anything else is a 400 naming the set; cancelling twice is a
400. Read the subscription back to see `cancelledDate` and `billingEndDate`
diverge.

## Invoices

```bash
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA/invoices"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/invoices/$PAID_INV"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/invoices/$PAID_INV/html"

curl -s -X PUT "${KB[@]}" -H 'X-Killbill-CreatedBy: agent' \
  "$KILLBILL_API_URL/1.0/kb/invoices/$DRAFT_INV/commitInvoice"   # 204

curl -si -X POST "${WRITE[@]}" \
  -d '{"amount": 7500, "currency": "EUR",
       "description": "Onboarding workshop, half day"}' \
  "$KILLBILL_API_URL/1.0/kb/invoices/charges/$AMELIA"            # 201 + Location
```

Items come back typed: `RECURRING`, `EXTERNAL_CHARGE`, `CBA_ADJ`, and `balance`
is computed at read time. Committing assigns the next invoice number and adds
the amount to the account balance; committing twice is a 400. An external
charge in the wrong currency or with a missing amount is a 400.

## Payments: a container of transactions

```bash
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/payments"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/payments/$FAILED"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA/paymentMethods"
```

`$FAILED` holds **two** `PURCHASE`/`PAYMENT_FAILURE` transactions — the attempt
and its retry. `p333f5e9-fb6d-4e8c-9fa7-5b903d2e4f76` holds an `AUTHORIZE` and
a *partial* `CAPTURE`.

```bash
curl -si -X POST "${WRITE[@]}" \
  -d '{"amount": 5000, "transactionType": "PURCHASE",
       "paymentExternalKey": "agent-topup-1"}' \
  "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA/payments"

curl -si -X POST "${WRITE[@]}" \
  -d '{"amount": 4900, "transactionExternalKey": "agent-refund-1"}' \
  "$KILLBILL_API_URL/1.0/kb/payments/$SETTLED/refunds"
```

The refund becomes a `REFUND` transaction on the **same** payment id.

**The plugin decides the outcome:**

| Method | Result |
|--------|--------|
| `pm11f3c7…` visa | **201** + Location, `SUCCESS` |
| `pm22e4d8…` amex | **402** (3005), `PAYMENT_FAILURE` |
| `pm33f5e9…` ACH via `__EXTERNAL_PAYMENT__` | **201** + Location, `PENDING` |
| `pm44a6fa…` SEPA | **400** (3004), `PLUGIN_FAILURE` |

Other refusals: a zero or negative amount (400), an account with no usable
method (400, 3001), over-refunding (400, naming what remains), refunding a
payment that never settled (400).

Adding a method, optionally as the default:

```bash
curl -si -X POST "${ACME_KB[@]}" -H 'X-Killbill-CreatedBy: agent' \
  -H 'Content-Type: application/json' \
  -d '{"externalKey": "helios-sepa", "pluginName": "killbill-orbit-payments",
       "pluginInfo": {"type": "sepa_debit", "last4": "9931", "behaviour": "ok"}}' \
  "$KILLBILL_API_URL/1.0/kb/accounts/$HELIOS/paymentMethods?isDefault=true"
```

## Control tags change behaviour

```bash
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$ACME/tags"

curl -si -X POST "${WRITE[@]}" -d '["AUTO_PAY_OFF", "MANUAL_PAY"]' \
  "$KILLBILL_API_URL/1.0/kb/accounts/$ACME/tags"

curl -s -X DELETE "${KB[@]}" -H 'X-Killbill-CreatedBy: agent' \
  "$KILLBILL_API_URL/1.0/kb/accounts/$ACME/tags?tagDef=AUTO_PAY_OFF"
```

Control tags: `AUTO_PAY_OFF`, `AUTO_INVOICING_OFF`, `OVERDUE_ENFORCEMENT_OFF`,
`WRITTEN_OFF`, `MANUAL_PAY`, `TEST`. Anything else is a 400 listing them;
removing one the account never had is a 404.

With `AUTO_PAY_OFF` on, a payment is a **400** and the card is never contacted.
Remove it and the same request reaches the card — where it may decline with a
**402**. That difference is the tag doing its job.

```bash
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$NORTHWIND/overdueState"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$ACME/overdueState"
```

Northwind owes money but carries `OVERDUE_ENFORCEMENT_OFF`, so it is `CLEAR`;
Acme is `OD1` with a retry schedule. Both are derived at read time.

## Errors

Kill Bill carries its own numeric code beside the HTTP status:

| HTTP | Code | Meaning |
|------|------|---------|
| 401 | 4000 | missing or invalid tenant credentials |
| 400 | 4001 | missing `X-Killbill-CreatedBy` |
| 404 | 1000 | no such account **in this tenant** |
| 409 | 1001 | externalKey already taken |
| 400 | 1002 | invalid currency, or an immutable field |
| 404/400 | 1500-1503 | subscription: not found, bad state, invalid plan, invalid policy |
| 404 | 1600 / 5000 | no such bundle / no such plan |
| 404/400 | 2000-2002 | invoice: not found, wrong status, bad amount |
| 404/400 | 3000-3002 | payment: not found, no method, bad amount |
| 400 | 3003 / 3004 | `AUTO_PAY_OFF` / plugin failure |
| **402** | 3005 | the card declined |
| 400/404 | 6000 | unknown or absent tag definition |
