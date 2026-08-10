# smtp4dev API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$SMTP4DEV_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SMTP4DEV_API_URL` | Base URL for all requests |

Set the ids once to follow the examples:

```bash
export ORDER='a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54'
export INVOICE='b2e4d8ea-5c3f-4d7b-8e96-4a8f2c1d3e65'
export INCIDENT='c3f5e9fb-6d40-4e8c-9fa7-5b903d2e4f76'
export RESET='d4a6fa0c-7e51-4f9d-80b8-6ca14e3f5087'
export WELCOME='e5b70b1d-8f62-40ae-91c9-7db25f406198'
export ALERT='f6c81c2e-9073-41bf-a2da-8ec360517209'
export ARCHIVE='07d92d3f-a184-42c0-b3eb-9f047162831a'
export PAYOUT='18ea3e40-b295-43d1-84fc-a0158273942b'
export SESSION='3a9c4e17-2b81-4f60-9d3e-7c05a1b2c3d4'
export AUTHFAIL='7e30825b-6fc5-43a4-b172-b049e5f60718'
export REJECTED='8f41936c-70d6-44b5-8283-c15af6071829'
```

## Service state

```bash
curl -s "$SMTP4DEV_API_URL/health"
curl -s "$SMTP4DEV_API_URL/api/Version"
curl -s "$SMTP4DEV_API_URL/api/Mailboxes"
curl -s "$SMTP4DEV_API_URL/api/Server"
```

## Listing: pages, not offsets

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages?page=1&pageSize=3"
curl -s "$SMTP4DEV_API_URL/api/Messages?page=2&pageSize=3"
curl -s "$SMTP4DEV_API_URL/api/Messages?page=9&pageSize=3"   # empty, not 404
```

Every list is a `PagedResult`:

```json
{"results": [ … ], "firstRowOnPage": 4, "lastRowOnPage": 6,
 "currentPage": 2, "pageCount": 3, "pageSize": 3, "rowCount": 8}
```

`page` is **1-based**. Filter and sort:

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages?mailboxName=Billing"
curl -s "$SMTP4DEV_API_URL/api/Messages?searchTerms=770412"
curl -s "$SMTP4DEV_API_URL/api/Messages?mailboxName=Billing&searchTerms=INV-2026-0417"
curl -s "$SMTP4DEV_API_URL/api/Messages?sortColumn=subject&sortIsDescending=false"
curl -s "$SMTP4DEV_API_URL/api/Messages?sortColumn=attachmentCount&sortIsDescending=true"
```

| Resource | Sortable columns |
|----------|------------------|
| messages | `receivedDate` (default), `from`, `to`, `subject`, `attachmentCount`, `isUnread`, `mailbox` |
| sessions | `startDate` (default), `endDate`, `clientAddress`, `numberOfMessages`, `terminatedWithError` |

Anything else is a 400 that lists the ones that work. `searchTerms` matches the
sender, recipients, Cc, subject and both bodies.

A mailbox that does not exist is a **404** — unlike Inbucket, where every
mailbox exists.

## Mailboxes route, they do not derive

```bash
curl -s "$SMTP4DEV_API_URL/api/Mailboxes"
```

| Mailbox | Rule |
|---------|------|
| `Billing` | `billing@orbit-labs.com`, `invoices@orbit-labs.com`, `finance@*` |
| `Alerts` | `oncall@orbit-labs.com`, `alerts@*`, `sre@*` |
| `Default` | `*` — checked **last**, so it never steals from a named mailbox |

## Reading a message

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER"
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/source"
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/html"
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/plaintext"
```

Headers come back as a **list of name/value pairs**, not a map. `/html` on a
text-only message is 404, and `/plaintext` on an HTML-only message is 404.

## The part tree

The order confirmation is three levels deep:

```
1        multipart/mixed
1.1      multipart/alternative
1.1.1    text/plain
1.1.2    text/html
1.2      application/pdf   receipt-ORD-2026-4417.pdf
```

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/part/1.1.1/content"
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/part/1.2/content"
curl -s "$SMTP4DEV_API_URL/api/Messages/$INVOICE/part/1.2/content"
curl -s "$SMTP4DEV_API_URL/api/Messages/$ORDER/part/1.1/source"
```

`/source` on a container renders the whole subtree with its boundary. Three
distinguishable errors: asking a container for content is **400**, an unknown
section number is **404 and lists the real ones**, and an unknown message is
**404**.

## Two different failures

```bash
curl -s "$SMTP4DEV_API_URL/api/Messages/$ARCHIVE"   # mimeParseError
curl -s "$SMTP4DEV_API_URL/api/Messages/$ALERT"     # relayError
```

`mimeParseError` means smtp4dev could not parse what arrived — the archive has
an unclosed boundary, and its attachment part carries two `warnings`.
`relayError` means the relay attempt failed — the alert has
`451 4.7.1 Greylisted`. They are separate fields and both are seeded.

## Sessions: the conversation, not the mail

```bash
curl -s "$SMTP4DEV_API_URL/api/Sessions?page=1&pageSize=4"
curl -s "$SMTP4DEV_API_URL/api/Sessions?sortColumn=numberOfMessages&sortIsDescending=false"
curl -s "$SMTP4DEV_API_URL/api/Sessions/$SESSION"
curl -s "$SMTP4DEV_API_URL/api/Sessions/$AUTHFAIL"
curl -s "$SMTP4DEV_API_URL/api/Sessions/$REJECTED/log"
```

Two seeded sessions produced **no message**:

| Session | `sessionErrorType` | What happened |
|---------|--------------------|---------------|
| `$AUTHFAIL` | `UnexpectedException` | three failed `AUTH LOGIN`, then `421` |
| `$REJECTED` | `ClientDisconnected` | both `RCPT TO` got `550`, client hung up |

The transcripts are real SMTP conversations. Deleting every message leaves every
session in place, reporting `numberOfMessages: 0` — they are separate stores.

## Read state

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Messages/$ORDER/markRead"
curl -s -X POST "$SMTP4DEV_API_URL/api/Messages/markAllRead?mailboxName=Alerts"
curl -s -X POST "$SMTP4DEV_API_URL/api/Messages/markAllRead"
```

Omitting `mailboxName` marks every message read. An unknown mailbox is 404.

## Relay

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Messages/$INVOICE/relay" \
  -H 'Content-Type: application/json' -d '{}'

curl -s -X POST "$SMTP4DEV_API_URL/api/Messages/$RESET/relay" \
  -H 'Content-Type: application/json' \
  -d '{"overrideRecipientAddresses": ["qa@orbit-labs.com", "rohit.bansal@orbit-labs.com"]}'
```

With no override it uses the message's own recipients. `isRelayed` flips to
`true` and any earlier `relayError` is cleared, so the outcome reads back.

Refusals, each 400: relay disabled in the settings, a malformed address, a
non-array `overrideRecipientAddresses`, and a message with no recipients at all.

## The settings dialog, over HTTP

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Server" \
  -H 'Content-Type: application/json' \
  -d '{"hostName": "smtp4dev.qa.local", "portNumber": 2526,
       "allowRemoteConnections": false,
       "relayOptions": {"isEnabled": true, "smtpPort": 2587,
                        "tlsMode": "ImplicitTls"}}'
```

Accepts a partial object and returns the whole settings as they now stand.
Writable: `portNumber`, `imapPortNumber`, `numberOfMessagesToKeep`,
`numberOfSessionsToKeep`, `hostName`, `secureConnectionMode`,
`credentialsValidationExpression`, the booleans, and under `relayOptions`
`isEnabled`, `smtpServer`, `smtpPort`, `tlsMode`, `login`, `password`,
`senderAddress`, `automaticEmails`, `automaticRelayExpression`.

TLS modes: `None`, `StartTls`, `ImplicitTls`, `StartTlsWhenAvailable`.

Validation names the offender — an unknown key, a port out of range, a
non-boolean, an invalid TLS mode, an unknown relay key.

**Retention trims immediately**, which is the behaviour to be careful with:

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Server" \
  -H 'Content-Type: application/json' -d '{"numberOfMessagesToKeep": 4}'
```

The response carries `"trimmed": {"messages": 7, "sessions": 0}` and only the
four newest messages remain. `numberOfSessionsToKeep` does the same to the
conversations.

## Delivering

```bash
curl -s -X POST "$SMTP4DEV_API_URL/api/Messages" \
  -H 'Content-Type: application/json' \
  -d '{"from": "monitoring@orbit-labs.com", "to": ["sre@orbit-labs.com"],
       "cc": [], "subject": "Disk pressure on node-7",
       "text": "node-7 root filesystem at 91%.",
       "html": "<p>node-7 root filesystem at 91%.</p>"}'
```

Answers **201** with the mailbox the first recipient routed to, and opens a
session with a matching transcript. Not an smtp4dev endpoint: it stands in for
the SMTP delivery a mock cannot accept, and the response says so.

Refusals: no `from`, a malformed `from`, no `to`, a malformed recipient — each
400.

## Deleting

```bash
curl -s -X DELETE "$SMTP4DEV_API_URL/api/Messages/$ORDER"
curl -s -X DELETE "$SMTP4DEV_API_URL/api/Messages/*?mailboxName=Billing"
curl -s -X DELETE "$SMTP4DEV_API_URL/api/Messages/*"
curl -s -X DELETE "$SMTP4DEV_API_URL/api/Sessions/$AUTHFAIL"
curl -s -X DELETE "$SMTP4DEV_API_URL/api/Sessions/*"
```

The literal `*` is smtp4dev's spelling, not a wildcard the shell should expand —
quote it. Deleting a message twice is 404; the same for a session.

## Errors

| HTTP | When |
|------|------|
| 400 | an unsortable `sortColumn`, asking a container part for content, a relay while relay is disabled, a malformed or non-array relay override, a message with no recipients, an unknown or invalid server setting, a delivery with no/malformed `from` or `to` |
| 404 | an unknown message or session, an unknown part section number, `/html` on a text-only message, `/plaintext` on an HTML-only message, a `mailboxName` that does not exist |
