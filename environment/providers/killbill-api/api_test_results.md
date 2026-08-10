# Kill Bill Mock API — Test Results

Base URL: `http://localhost:8128` (in docker-compose: `http://killbill-api:8128`)

## Endpoints covered

| Method | Path                                              | Status          |
|--------|---------------------------------------------------|-----------------|
| GET    | /health                                           | 200             |
| GET    | /1.0/kb/nodesInfo                                 | 200/401         |
| GET    | /1.0/kb/catalog · /catalog/availableBasePlans     | 200/401         |
| GET    | /1.0/kb/accounts                                  | 200/401         |
| POST   | /1.0/kb/accounts                                  | 201/400/401/409 |
| GET    | /1.0/kb/accounts/{id}                             | 200/401/404     |
| PUT    | /1.0/kb/accounts/{id}                             | 204/400/404     |
| GET    | /1.0/kb/accounts/{id}/timeline · /overdueState    | 200/404         |
| GET    | /1.0/kb/accounts/{id}/bundles · /invoices · /payments | 200/404     |
| GET    | /1.0/kb/accounts/{id}/paymentMethods              | 200/404         |
| POST   | /1.0/kb/accounts/{id}/paymentMethods              | 201/400/404     |
| POST   | /1.0/kb/accounts/{id}/payments                    | 201/400/402/404 |
| GET    | /1.0/kb/accounts/{id}/tags                        | 200/404         |
| POST   | /1.0/kb/accounts/{id}/tags                        | 201/400/404     |
| DELETE | /1.0/kb/accounts/{id}/tags                        | 204/400/404     |
| GET    | /1.0/kb/bundles/{id}                              | 200/404         |
| POST   | /1.0/kb/subscriptions                             | 201/400/404     |
| GET    | /1.0/kb/subscriptions/{id}                        | 200/404         |
| PUT    | /1.0/kb/subscriptions/{id}                        | 204/400/404     |
| DELETE | /1.0/kb/subscriptions/{id}                        | 204/400/404     |
| POST   | /1.0/kb/invoices/charges/{accountId}              | 201/400/404     |
| GET    | /1.0/kb/invoices/{id} · /html                     | 200/404         |
| PUT    | /1.0/kb/invoices/{id}/commitInvoice               | 204/400/404     |
| GET    | /1.0/kb/payments · /payments/{id}                 | 200/404         |
| POST   | /1.0/kb/payments/{id}/refunds                     | 201/400/404     |
| GET    | /1.0/kb/paymentMethods/{id}                       | 200/404         |

Collection run: **PASS 52 / WARN 32 / FAIL 0 / SKIP 0** over 84 requests. Every
WARN is an intentional error-path request, labelled `(N expected)` in the
collection, and every label matches the status the harness observed.

## Tenancy is a header, and it partitions everything

| Request | Result |
|---------|--------|
| no `X-Killbill-ApiKey` / `ApiSecret` | **401** `SECURITY_INVALID_CREDENTIALS` (4000) |
| the right key, the wrong secret | **401** |
| a key that does not exist | **401** |
| `orbit-labs` listing accounts | its **three** |
| `acme-reseller` listing accounts | a different **one** |
| `acme-reseller` reading an orbit account by id | **404** — not 403 |
| `orbit-labs` reading the acme account by id | **404** |

The 404 rather than a 403 is the point: from the other tenant, the object does
not exist at all.

Writes need one more header. `POST /1.0/kb/accounts` **without**
`X-Killbill-CreatedBy` is a **400** `SECURITY_MISSING_CREATED_BY` (4001),
checked before the body is even looked at.

## Creates return 201 + Location, and nothing else

```
POST /1.0/kb/accounts        -> 201, Location: /1.0/kb/accounts/1f16811b-…
POST /1.0/kb/subscriptions   -> 201, Location: /1.0/kb/subscriptions/afa76746-…
POST /1.0/kb/invoices/charges/{id} -> 201, Location: /1.0/kb/invoices/c0a82a0d-…
PUT  /1.0/kb/accounts/{id}   -> 204, no body
DELETE /1.0/kb/subscriptions/{id} -> 204, no body
```

Nothing is echoed back. The collection creates an account and then finds it
again with `GET /1.0/kb/accounts?externalKey=orbit-rohit`, which is how a client
without access to the response header actually works.

## Entitlement and billing are two timelines

A subscription carries both ends of each:

| Subscription | `startDate` | `billingStartDate` | Note |
|--------------|-------------|--------------------|------|
| `s444a6fa…` | 2026-05-19 | **2026-06-02** | 14-day TRIAL: access first, money later |
| `s111f3c7…` | 2025-11-04 | 2025-11-04 | no trial phase |

Cancelling takes **two** policies, and the collection runs both directions:

| Cancellation | `cancelledDate` | `billingEndDate` |
|--------------|-----------------|------------------|
| `entitlementPolicy=IMMEDIATE&billingPolicy=END_OF_TERM` | today | the charged-through date |
| `entitlementPolicy=END_OF_TERM&billingPolicy=IMMEDIATE` | the charged-through date | today |

Both are read back afterwards, so the divergence is observed rather than
claimed. `entitlementPolicy` accepts `IMMEDIATE` or `END_OF_TERM`;
`billingPolicy` also accepts `START_OF_TERM`. Anything else is a 400 naming the
set, and cancelling twice is a 400.

## The catalog constrains what can be sold

Six products across `BASE`, `ADD_ON` and `STANDALONE`; six plans with `TRIAL`
and `EVERGREEN` phases and per-currency prices. Each base product declares what
add-ons it `available`s:

| Base | Offers |
|------|--------|
| `OrbitStarter` | `OrbitSupport` |
| `OrbitGrowth` | `OrbitSupport`, `OrbitEgressPack` |
| `OrbitScale` | `OrbitSupport`, `OrbitEgressPack` (with `OrbitSupport` included) |

So attaching `OrbitEgressPack` to an `OrbitStarter` bundle is a 400 that says
what the base *does* offer, an add-on with no bundle is a 400, an unknown plan
is a 404, and changing a `BASE` subscription to an `ADD_ON` plan is a 400.

## A payment is a container of transactions

| Payment | Holds |
|---------|-------|
| `p111f3c7…` | one `PURCHASE` / `SUCCESS` (a `REFUND` joins it during the run) |
| `p222e4d8…` | **two** `PURCHASE` / `PAYMENT_FAILURE` — the attempt and its retry |
| `p333f5e9…` | an `AUTHORIZE` / `SUCCESS` and a **partial** `CAPTURE` |

The collection refunds part of the settled payment and reads it back: the
refund is a new transaction on the **same** payment id, and `refundedAmount`
moves. Over-refunding is a 400 naming what remains; refunding a payment that
never settled is a 400.

## The plugin decides the outcome

| Method | Plugin | Behaviour | Result |
|--------|--------|-----------|--------|
| `amelia-visa-4242` | `killbill-orbit-payments` | ok | **201** + Location, `SUCCESS` |
| `acme-amex-0005` | `killbill-orbit-payments` | declines | **402**, `PAYMENT_FAILURE` (3005) |
| `northwind-ach` | `__EXTERNAL_PAYMENT__` | pending | **201** + Location, `PENDING` |
| `amelia-sepa-backup` | `killbill-orbit-payments` | plugin error | **400**, `PLUGIN_FAILURE` (3004) |

An asynchronous plugin still gets a resource — the transaction says `PENDING`,
which is the whole reason the payment/transaction split exists. An account with
no usable method is a 400 `PAYMENT_NO_DEFAULT_PAYMENT_METHOD` (3001), and the
collection fixes it by adding one with `?isDefault=true` and paying
successfully straight after.

## Control tags are enforced

The clearest sequence in the collection:

1. Read the acme account's tags → `AUTO_PAY_OFF` is there.
2. Take a payment → **400** `PAYMENT_AUTO_PAY_OFF` (3003). The card is never
   contacted.
3. Remove the tag → **204**.
4. Take the same payment → **402**, `insufficient_funds`. Now the card *was*
   contacted, and declined for its own reason.

`OVERDUE_ENFORCEMENT_OFF` does the same to dunning: Northwind owes 22 100 and
still reports `CLEAR`, while Acme owes 4 900 and reports `OD1` with a retry
schedule. Both states are derived at read time from the balance and the tags,
not stored.

Adding an unknown tag definition is a 400 listing the six control tags;
removing one the account never had is a 404.

## Invoices

`GET /1.0/kb/invoices/{id}` returns the items — `RECURRING`,
`EXTERNAL_CHARGE`, `CBA_ADJ` are all seeded — plus a computed `balance`.
`/html` renders the same invoice for a human.

`commitInvoice` moves the seeded **DRAFT** to `COMMITTED`, assigns the next
invoice number (`1043`) and adds the amount to the account balance. Committing
twice is a 400.

`POST /1.0/kb/invoices/charges/{accountId}` raises an external charge as a new
DRAFT invoice and answers 201 + Location. A charge in a currency the account is
not billed in is a 400; a missing or negative amount is a 400.

## Error codes

Kill Bill carries its own numeric code beside the HTTP status:

| HTTP | Code | Meaning |
|------|------|---------|
| 401 | 4000 | missing or invalid tenant credentials |
| 400 | 4001 | missing `X-Killbill-CreatedBy` |
| 404 | 1000 | account does not exist *in this tenant* |
| 409 | 1001 | account externalKey already taken |
| 400 | 1002 | invalid currency, or an immutable field |
| 404 | 1500 | no such subscription · 400 1501 bad state · 400 1502 invalid plan · 400 1503 invalid policy |
| 404 | 1600 | no such bundle · 5000 no such plan |
| 404 | 2000 | no such invoice · 400 2001 wrong status · 400 2002 bad amount |
| 404 | 3000 | no such payment · 400 3001 no method · 400 3002 bad amount |
| 400 | 3003 | `AUTO_PAY_OFF` · 400 3004 plugin failure · **402 3005 declined** |
| 400/404 | 6000 | unknown or absent tag definition |

## Seed data summary

- **Tenants** (2) with their own API key/secret pairs
- **Accounts** (4): three in `orbit-labs` (one with a balance owed, one with
  `OVERDUE_ENFORCEMENT_OFF`), one in `acme-reseller` with a credit balance and
  **no payment method**
- **Bundles** (4) · **Subscriptions** (6) covering `ACTIVE`, `TRIAL`,
  `CANCELLED`, `BASE` and `ADD_ON`
- **Invoices** (5, one **DRAFT**) with **9 items** across `RECURRING`,
  `EXTERNAL_CHARGE` and `CBA_ADJ`
- **Payment methods** (4) on four plugin behaviours · **Payments** (3) holding
  **5 transactions** · **Tags** (2)

The accounts are the same Orbit Labs, Acme, Northwind and Helios organisations
the rest of the fleet bills.

## Notes

- Paths live under `/1.0/kb`, version and namespace both in the URL.
- Amounts are integers in the currency's minor unit.
- The overdue state and the invoice balance are **derived at read time**, not
  stored.
- Mutations are held in process memory and reset on container restart.
