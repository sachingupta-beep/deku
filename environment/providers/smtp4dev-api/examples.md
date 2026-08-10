# smtp4dev Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$SMTP4DEV_API_URL`; responses are verbatim (long lists elided
with `…`).

```bash
export ORDER='a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54'   # PDF, 3-level part tree
export INVOICE='b2e4d8ea-5c3f-4d7b-8e96-4a8f2c1d3e65' # CSV
export RESET='d4a6fa0c-7e51-4f9d-80b8-6ca14e3f5087'   # text only
export WELCOME='e5b70b1d-8f62-40ae-91c9-7db25f406198' # html only, relayed
export ALERT='f6c81c2e-9073-41bf-a2da-8ec360517209'   # relay failed
export ARCHIVE='07d92d3f-a184-42c0-b3eb-9f047162831a' # MIME parse error
export AUTHFAIL='7e30825b-6fc5-43a4-b172-b049e5f60718'  # session, 0 messages
export REJECTED='8f41936c-70d6-44b5-8283-c15af6071829'  # session, 0 messages
```

## Pages, not offsets

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages?page=2&pageSize=3"
```
```json
{
  "results": [ … three summaries … ],
  "firstRowOnPage": 4,
  "lastRowOnPage": 6,
  "currentPage": 2,
  "pageCount": 3,
  "pageSize": 3,
  "rowCount": 8
}
```

A summary carries the state, not the content:

```json
{"id": "a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54", "mailbox": "Default",
 "from": "billing@orbit-labs.com", "to": ["amelia.ortega@orbit-labs.com"],
 "receivedDate": "2026-05-28T09:14:12.804Z",
 "subject": "Your Orbit Labs order ORD-2026-4417 is confirmed",
 "attachmentCount": 1, "isUnread": true, "isRelayed": false,
 "deliveredTo": "amelia.ortega@orbit-labs.com", "hasMimeParseError": false}
```

Sorting names its own vocabulary:

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages?sortColumn=attachmentCount&sortIsDescending=true"
curl -s "$SMTP4DEV_API_URL/api/Messages?sortColumn=banana"
```
```json
{"error": "sortColumn 'banana' is not sortable; expected one of attachmentCount, from, isUnread, mailbox, receivedDate, subject, to"}
```

## Mailboxes are routing rules

```bash
curl -s "$SMTP4DEV_API_URL/api/Mailboxes"
```
```json
[
  {"name": "Alerts",
   "recipients": ["oncall@orbit-labs.com", "alerts@*", "sre@*"],
   "description": "Monitoring and incident traffic", "messageCount": 2},
  {"name": "Billing",
   "recipients": ["billing@orbit-labs.com", "invoices@orbit-labs.com", "finance@*"],
   "description": "Invoices, payouts and statements", "messageCount": 2},
  {"name": "Default", "recipients": ["*"],
   "description": "Catch-all: anything no other mailbox claims", "messageCount": 4}
]
```

`Default` is checked last, so it never steals a message a named mailbox claims.
Filtering by a mailbox that does not exist **is** an error here:

```json
{"error": "Mailbox 'Nope' does not exist"}
```

## MIME parts are a tree

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER"
```
```json
{
  "id": "a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54",
  "mailbox": "Default",
  "from": "billing@orbit-labs.com",
  "to": ["amelia.ortega@orbit-labs.com"],
  "cc": [], "bcc": [],
  "deliveredTo": "amelia.ortega@orbit-labs.com",
  "receivedDate": "2026-05-28T09:14:12.804Z",
  "subject": "Your Orbit Labs order ORD-2026-4417 is confirmed",
  "isUnread": true, "isRelayed": false,
  "relayError": "", "mimeParseError": "",
  "secureConnection": true,
  "sessionId": "3a9c4e17-2b81-4f60-9d3e-7c05a1b2c3d4",
  "attachmentCount": 1,
  "headers": [{"name": "Date", "value": "Thu, 28 May 2026 09:14:12 +0000"},
              {"name": "From", "value": "billing@orbit-labs.com"}, "…"],
  "parts": [
    {"id": "1", "name": "multipart/mixed", "contentType": "multipart/mixed",
     "isAttachment": false, "size": 0, "warnings": [],
     "childParts": [
       {"id": "1.1", "name": "multipart/alternative", "childParts": [
          {"id": "1.1.1", "name": "text/plain", "size": 146, "childParts": []},
          {"id": "1.1.2", "name": "text/html", "size": 137, "childParts": []}
       ]},
       {"id": "1.2", "name": "receipt-ORD-2026-4417.pdf",
        "contentType": "application/pdf", "isAttachment": true,
        "fileName": "receipt-ORD-2026-4417.pdf", "size": 120,
        "childParts": []}
     ]}
  ]
}
```

Headers are a **list of name/value pairs**, not a map — smtp4dev's shape.

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/part/1.2/content"   # the PDF
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/part/1.1/source"    # the subtree
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/part/1/content"     # 400
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/part/9.9/content"   # 404
```
```json
{"error": "Part '1' is a multipart/mixed container and has no content of its own"}
{"error": "Message has no part '9.9'; it has 1, 1.1, 1.1.1, 1.1.2, 1.2"}
```

`/part/1.1/source` renders the subtree with its own boundary:

```
Content-Type: multipart/alternative; boundary="==_orbit_a1f3c7d9_1_1"

--==_orbit_a1f3c7d9_1_1
Content-Type: text/plain; charset=utf-8

Hi Amelia,
…
--==_orbit_a1f3c7d9_1_1
Content-Type: text/html; charset=utf-8

<html><body><h1>Order confirmed</h1>…</body></html>
--==_orbit_a1f3c7d9_1_1--
```

## Two different kinds of failure

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages/$ARCHIVE"   # could not be parsed
curl -s "$SMTP4DEV_API_URL/api/Messages/$ALERT"     # could not be relayed
```
```json
{"mimeParseError": "Boundary '==_orbit_legacy' declared in Content-Type was never closed; the final part was truncated at end of stream.", "relayError": "", "…": "…"}
{"mimeParseError": "", "relayError": "451 4.7.1 Greylisted, try again in 300 seconds", "…": "…"}
```

The archive's attachment part carries its own warnings:

```json
{"id": "1.2", "name": "archive-2026-05-23.tar.gz",
 "warnings": ["Part was truncated at end of stream",
              "Decoded length does not match the declared Content-Length"], "…": "…"}
```

## Sessions: the conversation, not the mail

```bash
curl -s "$SMTP4DEV_API_URL/api/Sessions?sortColumn=numberOfMessages&sortIsDescending=false"
curl -s "$SMTP4DEV_API_URL/api/Sessions/$AUTHFAIL"
```
```json
{"id": "7e30825b-6fc5-43a4-b172-b049e5f60718",
 "clientAddress": "198.51.100.77", "clientName": "unknown",
 "startDate": "2026-05-26T03:11:04.512Z",
 "endDate": "2026-05-26T03:11:06.980Z",
 "numberOfMessages": 0,
 "terminatedWithError": true,
 "sessionErrorType": "UnexpectedException",
 "sessionError": "Authentication failed for user 'admin' after 3 attempts",
 "secureConnection": false, "authenticatedUser": "",
 "log": "S: 220 smtp4dev.orbit-labs.local smtp4dev ready\nC: EHLO unknown\n…"}
```

```bash
curl -s "$SMTP4DEV_API_URL/api/Sessions/$REJECTED/log"
```
```
S: 220 smtp4dev.orbit-labs.local smtp4dev ready
C: EHLO relay.partner.example
S: 250-smtp4dev.orbit-labs.local
S: 250 8BITMIME
C: MAIL FROM:<bulk@relay.partner.example>
S: 250 OK
C: RCPT TO:<dmitri.volkov@orbit-labs.com>
S: 550 5.1.1 Recipient address rejected: user unknown
C: RCPT TO:<postmaster@orbit-labs.com>
S: 550 5.1.1 Recipient address rejected: user unknown
<connection closed by client>
```

Neither session produced a message, and both are still first-class records.

## Relay

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Messages/$RESET/relay" \
  -H 'Content-Type: application/json' \
  -d '{"overrideRecipientAddresses": ["qa@orbit-labs.com"]}'
```
```json
{"id": "d4a6fa0c-7e51-4f9d-80b8-6ca14e3f5087", "relayed": true,
 "recipients": ["qa@orbit-labs.com"], "via": "smtp.orbit-labs.com:587",
 "tlsMode": "StartTls",
 "note": "no mail is actually relayed by the mock; isRelayed is set on the message so the outcome is readable back"}
```

Turn relay off through the settings and the next attempt says exactly what to
change:

```json
{"error": "Relay is not enabled; set relayOptions.isEnabled through POST /api/Server first"}
{"error": "'not-an-address' is not a valid recipient address"}
{"error": "overrideRecipientAddresses must be an array"}
```

## The settings dialog, over HTTP

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Server" \
  -H 'Content-Type: application/json' \
  -d '{"hostName": "smtp4dev.qa.local", "portNumber": 2526,
       "relayOptions": {"smtpPort": 2587, "tlsMode": "ImplicitTls"}}'
```

Returns the whole settings object as it now stands, plus what the change
trimmed. Validation names the offender:

```json
{"error": "'banana' is not a server setting"}
{"error": "portNumber must be a whole number between 1 and 65535"}
{"error": "relayOptions.tlsMode must be one of None, StartTls, ImplicitTls, StartTlsWhenAvailable"}
```

**Retention trims on the spot** — this is the behaviour worth knowing:

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Server" \
  -H 'Content-Type: application/json' -d '{"numberOfMessagesToKeep": 4}'
curl -s "$SMTP4DEV_API_URL/api/Messages?pageSize=20"
```

The response includes `"trimmed": {"messages": 7, "sessions": 0}`, and the list
that follows holds exactly four — the newest. Lowering
`numberOfSessionsToKeep` does the same to the conversations.

## Delivering

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Messages" \
  -H 'Content-Type: application/json' \
  -d '{"from": "monitoring@orbit-labs.com", "to": ["sre@orbit-labs.com"],
       "subject": "Disk pressure on node-7", "text": "node-7 root at 91%."}'
```
```json
{"id": "dbab41fb-f69d-4ad5-9af8-e5112f5336b9", "mailbox": "Alerts",
 "sessionId": "81f7ac19-875f-4679-b0cc-d203a67a9bda",
 "trimmed": {"messages": 0, "sessions": 0},
 "note": "not an smtp4dev endpoint; it stands in for the SMTP delivery a mock cannot accept"}
```

`201`, with the mailbox the recipient routed to — `sre@orbit-labs.com` matches
`Alerts`'s `sre@*` rule. The delivery also opens a session with a matching
transcript, so it shows up under `/api/Sessions` too.

Refusals: `{"error": "from is required"}`,
`{"error": "at least one to recipient is required"}`, and
`{"error": "'not-an-address' is not a valid recipient address"}`.

## Deleting, and what survives

```bash
curl -s -X DELETE "$SMTP4DEV_API_URL/api/Messages/$ORDER"
curl -s -X DELETE "$SMTP4DEV_API_URL/api/Messages/*?mailboxName=Billing"
curl -s -X DELETE "$SMTP4DEV_API_URL/api/Messages/*"
curl -s "$SMTP4DEV_API_URL/api/Sessions"
```
```json
{"id": "a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54", "deleted": true}
{"mailbox": "Billing", "deleted": 1}
{"mailbox": "*", "deleted": 3}
{"results": [{"id": "…", "numberOfMessages": 0, "…": "…"}, "…"], "rowCount": 3}
```

The literal `*` is smtp4dev's spelling. And the last response is the point: with
every message gone, the **sessions are all still there**, now reporting
`numberOfMessages: 0`. They are separate stores, and only
`DELETE /api/Sessions/*` clears them.
