# Kill Bill Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$KILLBILL_API_URL`; responses are verbatim (long lists elided
with `…`).

```bash
export KB_ORBIT=(-H 'X-Killbill-ApiKey: orbit-labs'
                 -H 'X-Killbill-ApiSecret: orbit-labs-secret-9f14c73e')
export AMELIA='a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54'
export ACME='b2e4d8ea-5c3f-4d7b-8e96-4a8f2c1d3e65'
export NORTHWIND='c3f5e9fb-6d40-4e8c-9fa7-5b903d2e4f76'
export BASE_SUB='s111f3c7-d94b-4e6a-8d85-3f7e1b0c2d54'
export DRAFT_INV='i444a6fa-0c7e-4f9d-80b8-6ca14e3f5087'
export SETTLED='p111f3c7-d94b-4e6a-8d85-3f7e1b0c2d54'
```

## The tenant is the header, and it partitions everything

```bash
curl -s "$KILLBILL_API_URL/1.0/kb/accounts"
```
```json
{"className": "org.killbill.billing.security.api.BillingExceptionBase",
 "code": 4000,
 "message": "X-Killbill-ApiKey and X-Killbill-ApiSecret are required on every request"}
```

With the right pair, `orbit-labs` sees three accounts and `acme-reseller` sees
one — and each other's are simply **not there**:

```bash
curl -s -H 'X-Killbill-ApiKey: acme-reseller' \
        -H 'X-Killbill-ApiSecret: acme-reseller-secret-5b07d21f' \
        "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA"
```
```json
{"className": "org.killbill.billing.account.api.BillingExceptionBase",
 "code": 1000,
 "message": "Account does not exist for id a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54"}
```

**404, not 403.** From the other tenant the object does not exist.

Writes need one more header:

```json
{"className": "org.killbill.billing.security.api.BillingExceptionBase",
 "code": 4001,
 "message": "X-Killbill-CreatedBy is required on any request that changes state"}
```

## Creates answer 201 with a Location and no body

```bash
curl -si -X POST "$KILLBILL_API_URL/1.0/kb/accounts" \
  -H 'Content-Type: application/json' "${KB_ORBIT[@]}" \
  -H 'X-Killbill-CreatedBy: collection-run' \
  -d '{"externalKey": "orbit-rohit", "name": "Rohit Bansal",
       "email": "rohit.bansal@orbit-labs.com", "currency": "EUR",
       "country": "ES", "billCycleDayLocal": 7}'
```
```
HTTP/1.1 201 Created
location: /1.0/kb/accounts/1f16811b-f4a2-40bb-bfdc-f4462b419bae
content-length: 0
```

No body at all. Find it again by the key you chose:

```bash
curl -s "${KB_ORBIT[@]}" \
  "$KILLBILL_API_URL/1.0/kb/accounts?externalKey=orbit-rohit"
```
```json
[{"accountId": "1f16811b-f4a2-40bb-bfdc-f4462b419bae",
  "externalKey": "orbit-rohit", "name": "Rohit Bansal",
  "email": "rohit.bansal@orbit-labs.com", "currency": "EUR", "country": "ES",
  "timeZone": "UTC", "billCycleDayLocal": 7, "accountBalance": 0,
  "accountCBA": 0, "paymentMethodId": null,
  "isPaymentDelegatedToParent": false, "parentAccountId": null,
  "referenceTime": "…"}]
```

Updates answer **204** with no body; the same key twice is a **409**; an
unsupported currency is a 400 naming the ones the catalog prices.

## Entitlement and billing are two timelines

```bash
curl -s "${KB_ORBIT[@]}" \
  "$KILLBILL_API_URL/1.0/kb/subscriptions/s444a6fa-0c7e-4f9d-80b8-6ca14e3f5087"
```
```json
{"subscriptionId": "s444a6fa-0c7e-4f9d-80b8-6ca14e3f5087",
 "productName": "OrbitStarter", "productCategory": "BASE",
 "planName": "orbit-starter-monthly", "billingPeriod": "MONTHLY",
 "phaseType": "TRIAL", "state": "ACTIVE",
 "startDate": "2026-05-19",
 "billingStartDate": "2026-06-02",
 "chargedThroughDate": null, "cancelledDate": null, "billingEndDate": null}
```

Access on the 19th, money on the 2nd — a 14-day trial, expressed as two dates
rather than a flag.

Cancelling takes **two** policies:

```bash
curl -s -X DELETE "${KB_ORBIT[@]}" -H 'X-Killbill-CreatedBy: collection-run' \
  "$KILLBILL_API_URL/1.0/kb/subscriptions/$BASE_SUB?entitlementPolicy=IMMEDIATE&billingPolicy=END_OF_TERM"
```
```
HTTP/1.1 204 No Content
```

```json
{"state": "CANCELLED",
 "cancelledDate": "2026-08-06",
 "chargedThroughDate": "2026-06-04",
 "billingEndDate": "2026-06-04"}
```

Access stopped today; billing runs to the charged-through date. Reverse the
policies on the add-on and you get the mirror image. An unknown policy is
refused:

```json
{"code": 1503, "message": "entitlementPolicy must be one of IMMEDIATE, END_OF_TERM"}
```

## The catalog constrains what can be sold

```bash
curl -s "${KB_ORBIT[@]}" "$KILLBILL_API_URL/1.0/kb/catalog/availableBasePlans"
```
```json
[{"planName": "orbit-starter-monthly", "product": "OrbitStarter",
  "productType": "BASE", "priceList": "DEFAULT", "billingPeriod": "MONTHLY",
  "prices": [{"currency": "EUR", "value": 29.0},
             {"currency": "USD", "value": 34.0}]}, "…"]
```

Adding an add-on the base does not offer:

```json
{"className": "org.killbill.billing.sub.api.BillingExceptionBase", "code": 1502,
 "message": "OrbitStarter does not offer OrbitEgressPack; it offers OrbitSupport"}
```

## A payment is a container of transactions

```bash
curl -s "${KB_ORBIT[@]}" \
  "$KILLBILL_API_URL/1.0/kb/payments/p222e4d8-ea5c-4f7b-8e96-4a8f2c1d3e65"
```
```json
{"paymentId": "p222e4d8-ea5c-4f7b-8e96-4a8f2c1d3e65", "paymentNumber": "802",
 "paymentExternalKey": "orbit-acme-2026-06",
 "authAmount": 0, "capturedAmount": 0, "purchasedAmount": 0,
 "refundedAmount": 0, "currency": "EUR",
 "transactions": [
   {"transactionExternalKey": "orbit-acme-2026-06-purchase-1",
    "transactionType": "PURCHASE", "status": "PAYMENT_FAILURE",
    "amount": 4900, "gatewayErrorCode": "insufficient_funds",
    "gatewayErrorMsg": "The card issuer declined the charge",
    "effectiveDate": "2026-06-02T02:10:06Z"},
   {"transactionExternalKey": "orbit-acme-2026-06-purchase-2",
    "transactionType": "PURCHASE", "status": "PAYMENT_FAILURE",
    "amount": 4900, "gatewayErrorCode": "insufficient_funds", "…": "…"}]}
```

The attempt and its retry, on one payment. Refunding the settled payment adds a
`REFUND` transaction to the *same* container and moves `refundedAmount`.

## The plugin decides the outcome

```bash
curl -si -X POST "${KB_ORBIT[@]}" -H 'Content-Type: application/json' \
  -H 'X-Killbill-CreatedBy: collection-run' \
  -d '{"amount": 5000, "paymentExternalKey": "run-amelia-topup"}' \
  "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA/payments"
# 201, Location: /1.0/kb/payments/2ed2031d-…
```

```json
{"code": 3005, "message": "The card issuer declined the charge (payment c2d9ad01-… was recorded with a PAYMENT_FAILURE transaction)"}
{"code": 3004, "message": "The payment plugin did not respond in time (payment a8932061-… was recorded with a PLUGIN_FAILURE transaction)"}
```

A decline is **402**; a plugin timeout is **400**. The `__EXTERNAL_PAYMENT__`
plugin answers **201** with a `PENDING` transaction — asynchronous, but the
resource exists.

## Control tags are enforced

```bash
curl -s "${KB_ORBIT[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$ACME/tags"
```
```json
[{"tagId": "…", "objectId": "b2e4d8ea-…", "objectType": "ACCOUNT",
  "tagDefinitionName": "AUTO_PAY_OFF", "isControlTag": true}]
```

Take a payment and the card is never contacted:

```json
{"code": 3003,
 "message": "Account b2e4d8ea-… carries AUTO_PAY_OFF; remove the tag before taking a payment"}
```

Remove it (**204**) and the *same* request now reaches the card and declines
for its own reason — a 402 rather than a 400. That difference is the whole
point of the tag.

```bash
curl -s "${KB_ORBIT[@]}" \
  "$KILLBILL_API_URL/1.0/kb/accounts/$NORTHWIND/overdueState"
curl -s "${KB_ORBIT[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$ACME/overdueState"
```
```json
{"name": "CLEAR", "externalMessage": "Overdue enforcement is switched off for this account", "isClearState": true}
{"name": "OD1", "externalMessage": "Payment is overdue; entitlement remains active while we retry", "daysBetweenPaymentRetries": [3, 5, 8], "isClearState": false}
```

Northwind owes 22 100 and is still `CLEAR`, because it carries
`OVERDUE_ENFORCEMENT_OFF`. Both states are computed at read time.

## Invoices

```bash
curl -s "${KB_ORBIT[@]}" \
  "$KILLBILL_API_URL/1.0/kb/invoices/i111f3c7-d94b-4e6a-8d85-3f7e1b0c2d54"
```
```json
{"invoiceId": "i111f3c7-…", "invoiceNumber": "1041", "currency": "EUR",
 "status": "COMMITTED", "invoiceDate": "2026-05-04", "amount": 14800,
 "creditAdj": 0, "refundAdj": 0, "balance": 0,
 "items": [
   {"itemType": "RECURRING", "description": "orbit-growth-monthly",
    "planName": "orbit-growth-monthly", "subscriptionId": "s111f3c7-…",
    "startDate": "2026-05-04", "endDate": "2026-06-04", "amount": 9900},
   {"itemType": "RECURRING", "description": "orbit-support-monthly",
    "amount": 4900, "…": "…"}]}
```

Committing the draft assigns the next number and moves the account balance:

```bash
curl -s -X PUT "${KB_ORBIT[@]}" -H 'X-Killbill-CreatedBy: collection-run' \
  "$KILLBILL_API_URL/1.0/kb/invoices/$DRAFT_INV/commitInvoice"   # 204
```
```json
{"invoiceNumber": "1043", "status": "COMMITTED", "amount": 14800, "…": "…"}
```

Committing again is a 400 `INVOICE_INVALID_STATUS` (2001). An external charge
answers 201 + Location and lands as a new DRAFT invoice.

## The whole account in one read

```bash
curl -s "${KB_ORBIT[@]}" "$KILLBILL_API_URL/1.0/kb/accounts/$AMELIA/timeline"
```
```json
{"account": {"accountId": "a1f3c7d9-…", "externalKey": "orbit-amelia", "…": "…"},
 "bundles": [{"bundleId": "bd11f3c7-…", "externalKey": "orbit-amelia-growth",
              "subscriptions": [{"productCategory": "BASE", "…": "…"},
                                {"productCategory": "ADD_ON", "…": "…"}]}],
 "invoices": [{"invoiceNumber": "1041", "…": "…"}, "…"],
 "payments": [{"paymentNumber": "801", "…": "…"}]}
```
