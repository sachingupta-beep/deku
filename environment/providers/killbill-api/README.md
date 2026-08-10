# killbill-api

Mock of Kill Bill — the enterprise end of this fleet. A Java, multi-tenant
subscription platform, and it behaves like one.

Run it as its own container (build context is the environment root):
```
docker compose up -d killbill-api
curl http://localhost:8128/health
curl -H 'X-Killbill-ApiKey: orbit-labs' \
     -H 'X-Killbill-ApiSecret: orbit-labs-secret-9f14c73e' \
     http://localhost:8128/1.0/kb/accounts
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir killbill-api --port 8128
```

Five habits are modelled rather than smoothed away:

- **Every request carries its tenant in headers.** `X-Killbill-ApiKey` and
  `X-Killbill-ApiSecret` decide which data even exists: an account in
  `orbit-labs` is a **404** from `acme-reseller` and vice versa, and a missing
  or wrong pair is a **401**. Writes additionally need `X-Killbill-CreatedBy`,
  because every change is audited against a person — omit it and the request is
  refused before anything else is checked.
- **Creates answer 201 with a `Location` header and no body.** Updates and
  cancellations answer **204**. Nothing is echoed back, so a caller follows the
  header or looks the object up by the `externalKey` it chose — which is
  exactly what the collection does.
- **Entitlement and billing are two different timelines.** A subscription
  carries a `startDate` (when access begins) *and* a `billingStartDate` (when
  money does), and cancelling takes an `entitlementPolicy` **and** a
  `billingPolicy`. Cancel with `IMMEDIATE`/`END_OF_TERM` and access stops today
  while billing runs to the charged-through date; reverse them and you get the
  mirror image. The collection does both and reads the dates back.
- **A payment is a container of transactions.** `PURCHASE`, `AUTHORIZE`,
  `CAPTURE`, `REFUND` — each with its own status — so a failed attempt, its
  retry and a later refund all hang off one payment id. One seeded payment
  holds two `PAYMENT_FAILURE` attempts; another holds a successful `AUTHORIZE`
  and a *partial* `CAPTURE`.
- **Control tags are data that changes behaviour.** `AUTO_PAY_OFF` blocks a
  payment attempt outright; `OVERDUE_ENFORCEMENT_OFF` keeps an account off the
  dunning ladder even with a balance owed. The collection removes the tag and
  watches the same request get all the way to the card — where it declines for
  a different reason.

## Plugin routing decides the outcome

Payment methods name a plugin, and the plugin's behaviour decides what happens:

| Method | Plugin | Outcome |
|--------|--------|---------|
| `amelia-visa-4242` | `killbill-orbit-payments` | **201** + Location, `SUCCESS` |
| `acme-amex-0005` | `killbill-orbit-payments` | **402**, `PAYMENT_FAILURE` |
| `northwind-ach` | `__EXTERNAL_PAYMENT__` | **201** + Location, `PENDING` |
| `amelia-sepa-backup` | `killbill-orbit-payments` | **400**, `PLUGIN_FAILURE` |

## The catalog is a real catalog

Six products across `BASE`, `ADD_ON` and `STANDALONE`, six plans with `TRIAL`
and `EVERGREEN` phases, and an `available` list per base product — so
`OrbitStarter` does **not** offer `OrbitEgressPack`, and asking for it is a 400
that says what it does offer.

Errors carry Kill Bill's own numeric code beside the HTTP status:

```json
{"className": "org.killbill.billing.payment.api.BillingExceptionBase",
 "code": 3003,
 "message": "Account b2e4d8ea… carries AUTO_PAY_OFF; remove the tag before taking a payment"}
```

## Seed data

Two tenants; four accounts (three in `orbit-labs`, one in `acme-reseller`);
four bundles and six subscriptions covering `ACTIVE`, `TRIAL`, `CANCELLED`,
`BASE` and `ADD_ON`; five invoices (one **DRAFT**) with nine items across
`RECURRING`, `EXTERNAL_CHARGE` and `CBA_ADJ`; four payment methods on four
plugins; three payments holding five transactions; two control tags.

See `api_test_results.md` for the endpoint matrix and the behaviours,
`examples.md` for captured request/response pairs, and
`killbill_api_postman_collection.json` for the runnable collection.
