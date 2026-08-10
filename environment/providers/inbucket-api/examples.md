# Inbucket Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$INBUCKET_API_URL`; responses are verbatim (long lists elided
with `…`).

## The naming policy

These six requests read the **same mailbox**:

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/Amelia.Ortega@orbit-labs.com"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega%2Bbilling@orbit-labs.com"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/AMELIA.ORTEGA@acme-partner.example"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/AMELIA.ORTEGA"
curl -s --get --data-urlencode 'x=' \
  "$INBUCKET_API_URL/api/v1/mailbox/Amelia%20Ortega%20%3Camelia.ortega%40orbit-labs.com%3E"
```

Three addresses, two domains, one mailbox — because the mailbox is the local
part, lowercased, with the `+subaddress` cut off. `/status` reports the policy
that decides it:

```bash
curl -s "$INBUCKET_API_URL/status"
```
```json
{"version": "3.1.0", "build-date": "2026-02-11T08:41:03Z",
 "smtp-listener": "0.0.0.0:2500", "pop3-listener": "0.0.0.0:1100",
 "web-listener": "0.0.0.0:9000", "storage": "memory",
 "mailbox-naming": "local", "case-sensitive": false, "strip-subaddress": true,
 "mailbox-message-cap": 5, "retention-period": "72h",
 "monitor-visible": true, "messages": 10, "mailboxes-with-mail": 6}
```

## Listing a mailbox

Headers only — no bodies, no attachments, oldest first:

```json
[
  {"mailbox": "amelia.ortega", "id": "20260526T101733-0003",
   "from": "Noor Aziz <noor.aziz@orbit-labs.com>",
   "to": ["AMELIA.ORTEGA@acme-partner.example"],
   "subject": "Partner sandbox credentials", "date": "2026-05-26T10:17:33Z",
   "posix-millis": 1779790653000, "size": 533, "seen": true},
  {"mailbox": "amelia.ortega", "id": "20260527T143055-0002", "…": "…"},
  {"mailbox": "amelia.ortega", "id": "20260528T091412-0001", "…": "…"}
]
```

Note `posix-millis` and the arrival ordering. MailHog and Mailpit list newest
first; Inbucket does not.

## Every mailbox exists

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/nobody"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/who.ever@nowhere.example"
```
```json
[]
[]
```

`200`, both times. There is no mailbox to create, so there is none to be
missing — which is why the 404s in this API are all about *messages*, never
mailboxes.

## Reading one message

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega/20260528T091412-0001"
```
```json
{
  "mailbox": "amelia.ortega",
  "id": "20260528T091412-0001",
  "from": "Orbit Labs Billing <billing@orbit-labs.com>",
  "to": ["Amelia Ortega <Amelia.Ortega@orbit-labs.com>"],
  "subject": "Your Orbit Labs order ORD-2026-4417 is confirmed",
  "date": "2026-05-28T09:14:12Z",
  "posix-millis": 1779959652000,
  "size": 1322,
  "seen": false,
  "header": {
    "Date": ["Thu, 28 May 2026 09:14:12 +0000"],
    "From": ["Orbit Labs Billing <billing@orbit-labs.com>"],
    "To": ["Amelia Ortega <Amelia.Ortega@orbit-labs.com>"],
    "Subject": ["Your Orbit Labs order ORD-2026-4417 is confirmed"],
    "Message-ID": ["<20260528T091412-0001@inbucket.example>"],
    "Delivered-To": ["Amelia.Ortega@orbit-labs.com"],
    "MIME-Version": ["1.0"],
    "Content-Type": ["multipart/mixed; boundary=\"==_inbucket_20260528T091412-0001\""]
  },
  "body": {"text": "Hi Amelia,\n\nThanks for your order. …", "html": "<html>…"},
  "attachments": [
    {"filename": "receipt-ORD-2026-4417.pdf",
     "content-type": "application/pdf",
     "download-link": "/api/v1/mailbox/amelia.ortega/20260528T091412-0001/attach/0/receipt-ORD-2026-4417.pdf",
     "view-link": "/api/v1/mailbox/amelia.ortega/20260528T091412-0001/attach/0/receipt-ORD-2026-4417.pdf",
     "md5": "4ccc175219d79ab9f36dd3a111e10c26", "size": 90}
  ]
}
```

The `Delivered-To` header keeps the address as it was written, even though the
mailbox that address resolved to has been normalised.

## The same message in two mailboxes

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/oncall/20260526T142208-0006"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/helena.park/20260526T142208-0007"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/oncall/20260526T142208-0007"
```

Same subject, same body, different ids — and the third is a **404**, because
helena's copy does not live in `oncall`:

```json
{"error": "message 20260526T142208-0007 not found in mailbox oncall"}
```

Marking one seen leaves the other alone:

```bash
curl -s -X PATCH "$INBUCKET_API_URL/api/v1/mailbox/oncall/20260526T142208-0006" \
  -H 'Content-Type: application/json' -d '{"seen": true}'
```
```json
{"mailbox": "oncall", "id": "20260526T142208-0006", "seen": true}
```

Refusals:

```json
{"error": "seen must be a boolean"}
{"error": "seen is required and must be a boolean"}
```

## Attachments

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega/20260527T143055-0002/attach/0/invoice-INV-2026-0417.csv"
```
```
bGluZSxkZXNjcmlwdGlvbixxdHksdW5pdCxhbW91bnQNCjEsT3JiaXQgTGFicyBUZWFtIHBsYW4g…
```

The filename in the path is part of the identity and is checked:

```json
{"error": "attachment 0 of 20260527T143055-0002 is 'invoice-INV-2026-0417.csv', not 'nope.csv'"}
{"error": "message 20260527T143055-0002 has 1 attachment(s); 3 is out of range"}
{"error": "attachment index must be an integer"}
```

## Delivering

```bash
curl -s -X POST "$INBUCKET_API_URL/api/v1/mailbox/Jonas.Pereira%2Bci@orbit-labs.com" \
  -H 'Content-Type: application/json' \
  -d '{"from": "ci@orbit-labs.com", "subject": "Nightly build 4417",
       "text": "All suites green."}'
```
```json
{"mailbox": "jonas.pereira", "id": "20260806T094539-0011",
 "addressedTo": "Jonas.Pereira+ci@orbit-labs.com", "evicted": [],
 "note": "not an Inbucket endpoint; it stands in for the SMTP delivery a mock cannot accept"}
```

`201`, and the response says exactly where the address resolved to — which is
the shortest way to see the policy work. Refusals:

```json
{"error": "from is required"}
{"error": "from is not a valid address: 'not-an-address'"}
{"error": "'broken@' is neither a mailbox name nor a valid address"}
```

## The per-mailbox cap

Six deliveries into a fresh mailbox capped at five:

```json
{"mailbox": "loadtest", "id": "…-0014", "evicted": [], "…": "…"}
{"mailbox": "loadtest", "id": "…-0015", "evicted": [], "…": "…"}
{"mailbox": "loadtest", "id": "…-0016", "evicted": [], "…": "…"}
{"mailbox": "loadtest", "id": "…-0017", "evicted": [], "…": "…"}
{"mailbox": "loadtest", "id": "…-0018", "evicted": [], "…": "…"}
{"mailbox": "loadtest", "id": "…-0019", "evicted": ["…-0014"], "…": "…"}
```

The mailbox then holds five, starting at `burst 2`. Inbucket defaults to 500;
this instance is set to 5 so the eviction is actually reachable.

## Deleting and purging

```bash
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/billing/20260523T111020-0009"
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/loadtest"
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/loadtest"
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/never-used"
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/oncall%2Bpager@orbit-labs.com"
```
```json
{"mailbox": "billing", "id": "20260523T111020-0009", "deleted": true}
{"mailbox": "loadtest", "purged": 5}
{"mailbox": "loadtest", "purged": 0}
{"mailbox": "never-used", "purged": 0}
{"mailbox": "oncall", "purged": 2}
```

Purging an already-empty or never-used mailbox reports `0` rather than failing —
consistent with every mailbox existing. The last one goes through the naming
policy like everything else. Deleting a message twice **is** a 404:

```json
{"error": "message 20260523T111020-0009 not found in mailbox billing"}
```

Purging `oncall` leaves helena's copy of the incident untouched:

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/helena.park"
```
```json
[{"mailbox": "helena.park", "id": "20260526T142208-0007",
  "subject": "[Orbit Status] Investigating elevated API latency (INC-4417)",
  "…": "…"}]
```

## The monitor, and the counters

The monitor is the only view that crosses mailboxes:

```bash
curl -s "$INBUCKET_API_URL/api/v1/monitor/messages?limit=3"
```
```json
{"messages": [{"mailbox": "amelia.ortega", "id": "20260528T091412-0001", "…": "…"},
              {"mailbox": "jonas.pereira", "id": "20260527T164155-0004", "…": "…"},
              {"mailbox": "amelia.ortega", "id": "20260527T143055-0002", "…": "…"}],
 "note": "the real /api/v1/monitor/messages endpoint is a server-sent-event stream; the mock returns a snapshot of the most recent deliveries instead"}
```

```bash
curl -s "$INBUCKET_API_URL/debug/vars"
```
```json
{"smtpConnectsTotal": 46, "smtpConnectsCurrent": 0, "smtpReceivedTotal": 15,
 "smtpErrorsTotal": 2, "smtpWarnsTotal": 5, "retentionDeletesTotal": 5,
 "retentionPeriodMinutes": 4320, "retainedHits": 128, "retainedCurrent": 10,
 "retainedSize": 6105, "uptimeSeconds": 84213}
```
