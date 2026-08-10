# Inbucket API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$INBUCKET_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `INBUCKET_API_URL` | Base URL for all requests |

## The one thing to understand first

Inbucket has **no global inbox**. There is no endpoint that lists all captured
mail, and none that lists the mailboxes. Every read names a mailbox, and the
mailbox name is **computed from the address**:

```
local part  ->  lowercased  ->  +subaddress stripped
```

So all of these read the same mailbox:

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/Amelia.Ortega@orbit-labs.com"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega%2Bbilling@orbit-labs.com"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/AMELIA.ORTEGA@acme-partner.example"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/AMELIA.ORTEGA"
```

Three addresses, two domains, one mailbox. The policy applies to **every** route
that takes a `{name}` — read, patch, delete and purge included. Percent-encode
the `+` as `%2B`, or the query parser will read it as a space.

## Service state

```bash
curl -s "$INBUCKET_API_URL/health"
curl -s "$INBUCKET_API_URL/status"
curl -s "$INBUCKET_API_URL/debug/vars"
```

`/status` reports the policy that decides the mailbox — `mailbox-naming`,
`case-sensitive`, `strip-subaddress` — plus `mailbox-message-cap`.
`/debug/vars` is the expvar counter set: `smtpReceivedTotal`,
`retentionDeletesTotal`, `retainedCurrent`, `retainedSize`.

## Listing a mailbox

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/jonas.pereira"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/oncall"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/helena.park"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/billing"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/support"
```

Headers only — no bodies, no attachments — and **oldest first**, which is
arrival order. MailHog and Mailpit list newest first; Inbucket does not.

Each entry carries `mailbox`, `id`, `from`, `to`, `subject`, `date`,
`posix-millis`, `size` and `seen`. The hyphenated keys are Inbucket's.

**An unknown mailbox is `200 []`, never a 404:**

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/nobody"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/who.ever@nowhere.example"
```

There is nothing to create, so there is nothing to be missing.

## Reading one message

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega/20260528T091412-0001"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega/20260528T091412-0001/source"
```

The read adds `header` (every header as a map of lists), `body` (`text` and
`html`) and `attachments`. `Delivered-To` keeps the address as it was written,
even though the mailbox it resolved to is normalised.

A message id is only valid **inside its own mailbox** — reading a real id
through the wrong mailbox is a 404, not a redirect.

## One message, two mailboxes

The seeded incident notice went to two recipients, so Inbucket stored two
copies:

| Mailbox | Id |
|---------|-----|
| `oncall` | `20260526T142208-0006` |
| `helena.park` | `20260526T142208-0007` |

Same subject, same body, independent `seen` flags. Marking one seen leaves the
other alone, and purging one mailbox leaves the other's copy standing.

## Attachments

```bash
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega/20260528T091412-0001/attach/0/receipt-ORD-2026-4417.pdf"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega/20260527T143055-0002/attach/0/invoice-INV-2026-0417.csv"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/support/20260522T083045-0010/attach/0/export-error.png"
```

The **filename is part of the path and is checked** — asking for index 0 under
the wrong name is a 404 reporting what the file is really called. An index out
of range is 404 naming the count, a non-numeric index is 400, and a message
with no attachments is 404.

| File | Type | Size | MD5 |
|------|------|------|-----|
| `receipt-ORD-2026-4417.pdf` | `application/pdf` | 90 | `4ccc175219d79ab9f36dd3a111e10c26` |
| `invoice-INV-2026-0417.csv` | `text/csv` | 156 | `ff85013f7b19cd169282f88a32906b59` |
| `export-error.png` | `image/png` | 70 | `2cd8bde463f5d82aae0f0cec061d6b8f` |

## Read state

```bash
curl -s -X PATCH "$INBUCKET_API_URL/api/v1/mailbox/oncall/20260526T142208-0006" \
  -H 'Content-Type: application/json' -d '{"seen": true}'
```

`{"seen": true|false}` is the only mutation on a message. A missing `seen` and a
non-boolean `seen` are each 400; patching through the wrong mailbox is 404.

## Delivering

```bash
curl -s -X POST "$INBUCKET_API_URL/api/v1/mailbox/deploys" \
  -H 'Content-Type: application/json' \
  -d '{"from": "Orbit Sync Bot <sync-bot@orbit-labs.com>",
       "subject": "Deploy 2026.05.29-1 succeeded",
       "text": "production: SUCCEEDED in 6m41s"}'

curl -s -X POST "$INBUCKET_API_URL/api/v1/mailbox/Jonas.Pereira%2Bci@orbit-labs.com" \
  -H 'Content-Type: application/json' \
  -d '{"from": "ci@orbit-labs.com", "to": ["jonas.pereira@orbit-labs.com"],
       "cc": ["rohit.bansal@orbit-labs.com"], "subject": "Nightly build 4417",
       "text": "All suites green.", "html": "<p>All suites green.</p>"}'
```

Answers **201** with the mailbox the address resolved to — the shortest way to
watch the policy work. Not an Inbucket endpoint: it stands in for the SMTP
delivery a mock cannot accept, and the response says so.

Refusals: a missing `from`, a malformed `from`, and a `{name}` that is a
half-written address (`broken@`) — each 400.

Ids are the arrival timestamp plus a sequence, so a delivered id differs per
run. Verify a delivery by listing the mailbox rather than by quoting the id.

## The per-mailbox cap

Once a mailbox exceeds `mailbox-message-cap`, the oldest message is dropped and
the delivery response names it in `evicted`. Inbucket defaults to 500; this
instance is configured to **5**, so six deliveries into a fresh mailbox leave
five and report the eviction.

## Deleting and purging

```bash
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/billing/20260523T111020-0009"
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/loadtest"
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/oncall%2Bpager@orbit-labs.com"
```

Deletion is **per-mailbox**; nothing empties the server. Purging reports the
count, and purging an empty or never-used mailbox reports `0` rather than
failing — consistent with every mailbox existing. Deleting a message twice **is**
a 404.

## The monitor

```bash
curl -s "$INBUCKET_API_URL/api/v1/monitor/messages?limit=5"
curl -s "$INBUCKET_API_URL/api/v1/monitor/mailbox/amelia.ortega"
```

The only view that crosses mailboxes, and the only way to discover what has
arrived without knowing the address. The real endpoints are server-sent-event
streams; the mock returns a snapshot, and the response says so.

## Errors

| HTTP | When |
|------|------|
| 400 | a non-numeric attachment index, a missing or non-boolean `seen`, a delivery with no `from` or a malformed `from`, a `{name}` that is a half-written address |
| 404 | an unknown message id, a real id read through the wrong mailbox, an attachment index out of range, an attachment filename that does not match, a message with no attachments |

There is no 404 on the mailbox routes themselves — every mailbox exists.
