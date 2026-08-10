---
name: killbill-api-connector
description: >
  Kill Bill API (Mock) mock HTTP API. Base URL is provided via the
  `KILLBILL_API_URL` environment variable. 27 endpoint(s) across GET, POST, PUT, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Kill Bill API (Mock)

Mock of Kill Bill, a Java multi-tenant subscription platform. **All requests go
to the base URL in `$KILLBILL_API_URL`.** Responses are deterministic fixtures.

## Base URL and credentials

| Variable | Purpose |
|----------|---------|
| `KILLBILL_API_URL` | Base URL for all requests (e.g. `http://killbill-api:8128`) |

**Every request needs a tenant.** Two are seeded:

| `X-Killbill-ApiKey` | `X-Killbill-ApiSecret` |
|---------------------|------------------------|
| `orbit-labs` | `orbit-labs-secret-9f14c73e` |
| `acme-reseller` | `acme-reseller-secret-5b07d21f` |

**Every write also needs `X-Killbill-CreatedBy`** — any string identifying the
person. Without it the request is a 400 before anything else is checked.

## Five things to know first

**Tenancy partitions everything.** An account in one tenant is a **404** from
the other, not a 403. A missing or wrong credential pair is a 401.

**Creates answer 201 + `Location`, with no body.** Updates and cancellations
answer **204**. Follow the header, or look the object up by the `externalKey`
you chose.

**Entitlement and billing are two timelines.** `startDate` vs
`billingStartDate`, and cancelling takes an `entitlementPolicy` **and** a
`billingPolicy`.

**A payment is a container of transactions** — PURCHASE, AUTHORIZE, CAPTURE,
REFUND — so an attempt, its retry and a refund share one payment id.

**Control tags change behaviour.** `AUTO_PAY_OFF` blocks payments;
`OVERDUE_ENFORCEMENT_OFF` keeps an account off the dunning ladder.

## Seeded ids (tenant `orbit-labs`)

| Object | Id |
|--------|-----|
| Amelia (paying) | `a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54` |
| Acme (owes 4900, **AUTO_PAY_OFF**) | `b2e4d8ea-5c3f-4d7b-8e96-4a8f2c1d3e65` |
| Northwind (owes 22100, **OVERDUE_ENFORCEMENT_OFF**) | `c3f5e9fb-6d40-4e8c-9fa7-5b903d2e4f76` |
| growth bundle | `bd11f3c7-d94b-4e6a-8d85-3f7e1b0c2d54` |
| BASE sub · ADD_ON sub · CANCELLED sub | `s111f3c7…` · `s222e4d8…` · `s333f5e9…` |
| TRIAL sub (billing starts later) | `s444a6fa-0c7e-4f9d-80b8-6ca14e3f5087` |
| paid invoice · **DRAFT** invoice | `i111f3c7…` · `i444a6fa…` |
| settled payment · twice-failed payment | `p111f3c7…` · `p222e4d8…` |

Tenant `acme-reseller` holds Helios, `d4a6fa0c-7e51-4f9d-80b8-6ca14e3f5087` —
with **no payment method**, so charging it is a 400 until one is added.

## Endpoints

| Method | Path (all under `/1.0/kb`) |
|--------|-----------------------------|
| GET | `/nodesInfo` · `/catalog` · `/catalog/availableBasePlans` |
| GET/POST | `/accounts`; GET/PUT `/accounts/{id}` |
| GET | `/accounts/{id}/timeline` · `/overdueState` · `/bundles` · `/invoices` · `/payments` |
| GET/POST | `/accounts/{id}/paymentMethods` · `/accounts/{id}/payments` · `/accounts/{id}/tags` |
| DELETE | `/accounts/{id}/tags?tagDef=` |
| GET | `/bundles/{id}` |
| POST | `/subscriptions`; GET/PUT/DELETE `/subscriptions/{id}` |
| POST | `/invoices/charges/{accountId}`; GET `/invoices/{id}` · `/html`; PUT `/invoices/{id}/commitInvoice` |
| GET | `/payments` · `/payments/{id}`; POST `/payments/{id}/refunds` |
| GET | `/paymentMethods/{id}` |

## Usage

```bash
KB=(-H 'X-Killbill-ApiKey: orbit-labs'
    -H 'X-Killbill-ApiSecret: orbit-labs-secret-9f14c73e')
WRITE=("${KB[@]}" -H 'X-Killbill-CreatedBy: agent' -H 'Content-Type: application/json')

curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts"
curl -s "${KB[@]}" "$KILLBILL_API_URL/1.0/kb/accounts?externalKey=orbit-acme"

# create, then find it by your own key -- the response has no body
curl -si -X POST "${WRITE[@]}" \
  -d '{"externalKey": "orbit-new", "currency": "EUR"}' \
  "$KILLBILL_API_URL/1.0/kb/accounts"

# cancel access now, keep billing to the end of the term
curl -s -X DELETE "${KB[@]}" -H 'X-Killbill-CreatedBy: agent' \
  "$KILLBILL_API_URL/1.0/kb/subscriptions/s111f3c7-d94b-4e6a-8d85-3f7e1b0c2d54?entitlementPolicy=IMMEDIATE&billingPolicy=END_OF_TERM"

# take a payment
curl -s -X POST "${WRITE[@]}" -d '{"amount": 5000}' \
  "$KILLBILL_API_URL/1.0/kb/accounts/a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54/payments"
```

Payment outcome depends on the method's plugin: `amelia-visa-4242` →
**201 SUCCESS**, `acme-amex-0005` → **402 PAYMENT_FAILURE**, `northwind-ach` →
**201 PENDING**, `amelia-sepa-backup` (`pm44a6fa-0c7e-4f9d-80b8-6ca14e3f5087`)
→ **400 PLUGIN_FAILURE**.

Catalog constraints are real: `OrbitStarter` offers only `OrbitSupport`, so
attaching `OrbitEgressPack` to it is a 400 that says so.

Errors carry Kill Bill's own numeric code beside the HTTP status —
4000 credentials, 4001 missing created-by, 1000 no such account, 1502 invalid
plan, 3003 AUTO_PAY_OFF, 3005 declined, and so on.

The audit log of every call the agent makes is available at
`$KILLBILL_API_URL/audit/requests` (used for grading).
