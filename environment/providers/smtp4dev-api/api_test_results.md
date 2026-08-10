# smtp4dev Mock API — Test Results

Base URL: `http://localhost:8124` (in docker-compose: `http://smtp4dev-api:8124`)

## Endpoints covered

| Method | Path                                            | Status      |
|--------|-------------------------------------------------|-------------|
| GET    | /health                                         | 200         |
| GET    | /api/Version                                    | 200         |
| GET    | /api/Server                                     | 200         |
| POST   | /api/Server                                     | 200/400     |
| GET    | /api/Mailboxes                                  | 200         |
| GET    | /api/Messages                                   | 200/400/404 |
| POST   | /api/Messages                                   | 201/400     |
| DELETE | /api/Messages/*                                 | 200/404     |
| POST   | /api/Messages/markAllRead                       | 200/404     |
| GET    | /api/Messages/{id}                              | 200/404     |
| DELETE | /api/Messages/{id}                              | 200/404     |
| GET    | /api/Messages/{id}/source                       | 200/404     |
| GET    | /api/Messages/{id}/html                         | 200/404     |
| GET    | /api/Messages/{id}/plaintext                    | 200/404     |
| GET    | /api/Messages/{id}/part/{partId}/content        | 200/400/404 |
| GET    | /api/Messages/{id}/part/{partId}/source         | 200/404     |
| POST   | /api/Messages/{id}/markRead                     | 200/404     |
| POST   | /api/Messages/{id}/relay                        | 200/400/404 |
| GET    | /api/Sessions                                   | 200/400     |
| DELETE | /api/Sessions/*                                 | 200         |
| GET    | /api/Sessions/{id}                              | 200/404     |
| DELETE | /api/Sessions/{id}                              | 200/404     |
| GET    | /api/Sessions/{id}/log                          | 200/404     |

Collection run: **PASS 68 / WARN 28 / FAIL 0 / SKIP 0** over 96 requests. Every
WARN is an intentional error-path request, labelled `(N expected)` in the
collection, and every label matches the status the harness observed.

## Pages, not offsets

Every list is a `PagedResult`:

```json
{"results": [ … ], "firstRowOnPage": 4, "lastRowOnPage": 6, "currentPage": 2,
 "pageCount": 3, "pageSize": 3, "rowCount": 8}
```

`page` is **1-based**. A page past the end returns an empty `results` with
`firstRowOnPage: 0`, not a 404. Sorting is `sortColumn` + `sortIsDescending`:

| Resource | Sortable columns |
|----------|------------------|
| messages | `receivedDate`, `from`, `to`, `subject`, `attachmentCount`, `isUnread`, `mailbox` |
| sessions | `startDate`, `endDate`, `clientAddress`, `numberOfMessages`, `terminatedWithError` |

Anything else is a 400 that lists the ones that work:

```json
{"error": "sortColumn 'banana' is not sortable; expected one of attachmentCount, from, isUnread, mailbox, receivedDate, subject, to"}
```

`searchTerms` matches across the sender, recipients, Cc, subject and both
bodies, and composes with `mailboxName`.

## Sessions are peers of messages, not a view of them

A session is the SMTP conversation, kept with its transcript. Two of the seven
seeded sessions produced **no message at all**:

| Session | `sessionErrorType` | What happened |
|---------|--------------------|---------------|
| `7e30825b…` | `UnexpectedException` | three failed `AUTH LOGIN` attempts, then `421 4.7.0 Too many failed authentication attempts` |
| `8f41936c…` | `ClientDisconnected` | both `RCPT TO` got `550 5.1.1`, client closed the connection before `DATA` |

The transcripts are real conversations — `220`/`EHLO`/`STARTTLS`/`AUTH`/`MAIL
FROM`/`RCPT TO`/`DATA`/`250`/`QUIT` — and are readable whole at
`/api/Sessions/{id}/log`.

The collection ends by deleting **every message** and then listing sessions:
they are all still there, now reporting `numberOfMessages: 0`. That is the
clearest proof the two are separate stores.

## Mailboxes route, they do not derive

| Mailbox | Rule | Claims |
|---------|------|--------|
| `Billing` | `billing@orbit-labs.com`, `invoices@orbit-labs.com`, `finance@*` | invoices and payouts |
| `Alerts` | `oncall@orbit-labs.com`, `alerts@*`, `sre@*` | monitoring and incidents |
| `Default` | `*` | everything nothing else claimed |

`Default` is checked **last** regardless of seed order, so it never steals a
message from a named mailbox. The collection delivers three messages to prove
the routing: `sre@orbit-labs.com` → `Alerts`, `finance@orbit-labs.com` →
`Billing`, `priya.raman@acme-partner.example` → `Default`.

Filtering by a mailbox that does not exist is a 404, which is a deliberate
contrast with Inbucket, where every mailbox exists.

## MIME parts are a tree

The order confirmation is three levels deep:

```
1        multipart/mixed
1.1      multipart/alternative
1.1.1    text/plain
1.1.2    text/html
1.2      application/pdf   receipt-ORD-2026-4417.pdf
```

Each node carries `childParts`, `headers`, `size`, `isAttachment`, `fileName`
and `warnings`. Three distinguishable errors:

```json
{"error": "Part '1' is a multipart/mixed container and has no content of its own"}
{"error": "Message has no part '9.9'; it has 1, 1.1, 1.1.1, 1.1.2, 1.2"}
{"error": "Message not found"}
```

`/part/{id}/source` renders the subtree with its own boundary, so asking for
`1.1` returns the `multipart/alternative` block complete with both leaves.

`/html` and `/plaintext` pull one body out; a text-only message 404s on `/html`
and an HTML-only message 404s on `/plaintext`.

## Two error fields that are not the same thing

| Field | Means |
|-------|-------|
| `mimeParseError` | smtp4dev could not parse what arrived — the nightly archive has an unclosed boundary, and its attachment part carries two `warnings` |
| `relayError` | the relay attempt failed — the ingest-lag alert has `451 4.7.1 Greylisted, try again in 300 seconds` |

Both are seeded so a client can tell them apart.

## The server settings are writable, and take effect immediately

`POST /api/Server` accepts a partial object and validates every key:

```json
{"error": "'banana' is not a server setting"}
{"error": "portNumber must be a whole number between 1 and 65535"}
{"error": "allowRemoteConnections must be a boolean"}
{"error": "relayOptions.tlsMode must be one of None, StartTls, ImplicitTls, StartTlsWhenAvailable"}
{"error": "'relayOptions.smtpUser' is not a relay setting"}
```

The collection uses it three ways:

1. **Relay on/off.** Turning `relayOptions.isEnabled` off makes the next relay a
   400 naming the setting to change; turning it back on with a new port and TLS
   mode restores it.
2. **Retention on messages.** Lowering `numberOfMessagesToKeep` to 4 trims the
   store immediately and reports `"trimmed": {"messages": N, "sessions": 0}` —
   only the four newest survive.
3. **Retention on sessions.** Lowering `numberOfSessionsToKeep` to 3 does the
   same to the conversations.

That immediacy is the point: in smtp4dev the Settings dialog empties your list
in front of you.

## Relay

`POST /api/Messages/{id}/relay` uses the message's own recipients unless
`overrideRecipientAddresses` is supplied. Refusals: relay disabled, a malformed
address, a non-array override, and a message with no recipients — each 400. The
message's `isRelayed` flips to `true` and any previous `relayError` is cleared,
so the outcome is readable back.

## Seed data summary

- **Messages** (8) across 3 mailboxes: `Default` 4, `Billing` 2, `Alerts` 2 —
  four unread, one already relayed, one with a failed relay, one with a MIME
  parse error
- **Parts** (18), keyed `{messageId}#{partId}` — one tree three levels deep,
  two two-level trees, five single-part messages
- **Sessions** (7), two of which produced **no message**
- **Mailboxes** (3) with their recipient rules
- **Server settings**: relay enabled to `smtp.orbit-labs.com:587` over StartTls,
  retention 100/100

The mail matches the rest of the fleet: the recovery code `770412` is the
authentication services', and `INC-4417` is the incident MailHog, Mailpit and
Inbucket also captured.

## Notes

- Messages default to newest-first (`receivedDate`, descending).
- The delete-everything routes really are spelled `DELETE /api/Messages/*` and
  `DELETE /api/Sessions/*` — the literal star is smtp4dev's. They are declared
  before `/{id}` in the router so an id pattern cannot swallow them.
- `DELETE /api/Messages/*` takes an optional `mailboxName` to empty one mailbox.
- Delivered ids and session ids are UUIDs generated per call, so they differ
  per run; the collection verifies a delivery by its response and by listing,
  not by quoting the id back.
- Mutations are held in process memory and reset on container restart.
