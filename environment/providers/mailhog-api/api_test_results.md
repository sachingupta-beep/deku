# MailHog Mock API — Test Results

Base URL: `http://localhost:8121` (in docker-compose: `http://mailhog-api:8121`)

## Endpoints covered

| Method | Path                                                        | Status      |
|--------|-------------------------------------------------------------|-------------|
| GET    | /health                                                     | 200         |
| GET    | /api/v1/info                                                | 200         |
| GET    | /api/v1/events                                              | 200         |
| GET    | /api/v1/messages                                            | 200         |
| DELETE | /api/v1/messages                                            | 200         |
| GET    | /api/v1/messages/{id}                                       | 200/404     |
| DELETE | /api/v1/messages/{id}                                       | 200/404     |
| GET    | /api/v1/messages/{id}/download                              | 200/404     |
| GET    | /api/v1/messages/{id}/mime/part/{n}/download                | 200/400/404 |
| POST   | /api/v1/messages/{id}/release                               | 200/400/404 |
| GET    | /api/v1/releases                                            | 200         |
| GET    | /api/v2/messages                                            | 200         |
| GET    | /api/v2/search                                              | 200/400     |
| GET    | /api/v2/jim                                                 | 200/404     |
| POST   | /api/v2/jim                                                 | 200/400     |
| PUT    | /api/v2/jim                                                 | 200/400/404 |
| DELETE | /api/v2/jim                                                 | 200/404     |
| GET    | /api/v2/outgoing-smtp                                       | 200         |

Collection run: **PASS 43 / WARN 23 / FAIL 0 / SKIP 0**. Every WARN is an
intentional error-path request, labelled `(N expected)` in the collection.

## The same messages, two shapes

```
GET /api/v1/messages   ->  [ {...}, {...} ]
GET /api/v2/messages   ->  { "total": 8, "count": 3, "start": 0, "items": [...] }
```

Both are served because clients in the wild use both, and the collection reads
the same inbox through each.

## Structured addresses

MailHog reports the SMTP envelope, so an address is not a string:

```json
"From": {"Relays": null, "Mailbox": "auth", "Domain": "orbit-labs.com",
         "Params": ""}
```

`To` collects the recipients, the `Cc` and the `Bcc` — which is what the server
actually saw, regardless of what the headers show. The collection searches for a
`Cc` (`finance`) and a `Bcc` (`soc@orbit-labs.com`) to demonstrate it.

## MIME traversal

| Message | Part 0 | Part 1 |
|---------|--------|--------|
| incident notification | `text/plain` | `text/html` |
| weekly digest | `text/plain` | `text/csv` attachment `uptime-2026-w21.csv` |
| invoice | `text/plain` | `application/pdf` attachment `INV-2026-0417.pdf` |
| bounce | `text/plain` | `message/delivery-status` |

`/mime/part/{n}/download` serves the part's own content type with a
`Content-Disposition` filename. An index out of range is 404 naming the part
count, a non-multipart message is 404, and a non-numeric index is 400.

## Jim, the chaos monkey

Jim is off in the seed. `GET /api/v2/jim` answers **404 `Jim is not enabled`**,
which is how a client discovers chaos is disabled — as do `PUT` and `DELETE`.
`POST` enables him; enabling twice is 400.

Once enabled, his chances apply to the release endpoint. The roll is seeded from
the recipient address, so the outcome is deterministic per address rather than
random:

| Recipient | Roll |
|-----------|------|
| `oncall@orbit-labs.com` | 0.114 |
| `status@orbit-labs.com` | 0.282 |
| `subscribers@orbit-labs.com` | 0.302 |
| `rohit.bansal@orbit-labs.com` | 0.420 |
| `finance@orbit-labs.com` | 0.471 |
| `amelia.ortega@orbit-labs.com` | 0.749 |

The collection enables Jim with `RejectRecipientChance: 0.4`, releases to
`oncall` (rejected) and to `rohit.bansal` (let through) — the same settings, two
outcomes — then raises `DisconnectChance` to 0.2 and releases to `oncall` again
to get a *different* refusal from the same address.

Validation is enforced: a chance outside `0..1`, a non-numeric chance, and
`LinkSpeedMin > LinkSpeedMax` are each 400 naming the offending field.

**One deliberate deviation.** Real MailHog reports a refused release as 500.
This mock returns **400** instead, because the fleet harness reads any 5xx as a
broken service and an injected refusal is a deliberate outcome, not a fault. The
reason is in the body either way.

## Release

`POST /api/v1/messages/{id}/release` hands a captured message to a real SMTP
server. Credentials come either inline (`Host`, `Port`, `Email`, `Username`,
`Password`, `Mechanism`) or by naming a server from `/api/v2/outgoing-smtp`.

Refusals: missing `Host`/`Port`, missing `Email`, an unknown named server, an
auth mechanism other than `PLAIN` or `CRAM-MD5`, and a mechanism with no
`Username` — each 400 naming the problem.

Nothing is delivered, so the response says so and the release is recorded at
`/api/v1/releases`, which is not a MailHog endpoint — it exists so a release can
be verified afterwards.

## Seed data summary

- **Messages**: 8 — two plain-text codes, one HTML welcome, one plain-text
  security alert with a **Bcc**, a `multipart/alternative` incident notice, a
  `multipart/mixed` digest with a **CSV**, a `multipart/mixed` invoice with a
  **PDF** and a **Cc**, and a `multipart/report` **bounce**
- **MIME parts**: 8 across the four multipart messages
- **Outgoing SMTP servers**: 2 (`orbit-relay` PLAIN, `acme-partner` CRAM-MD5)
- **Jim**: seeded disabled, with MailHog's default chances

The captured mail is the mail the rest of this fleet would have sent — the
verification code matches Kratos's seed, the recovery code matches the
authentication services, and the bounce is addressed to the deactivated account.

## Notes

- Messages are listed newest-first, as MailHog's UI shows them.
- `search` supports `from`, `to` and `containing`; `containing` searches the
  subject and the rebuilt body, so it matches text inside a multipart message.
  An unsupported `kind` or a missing `query` is 400.
- Deleting a message removes its MIME parts too; deleting again is 404.
- `DELETE /api/v1/messages` empties the capture and reports how many went.
- `/api/v1/events` returns a snapshot rather than an SSE stream, and says so —
  a mock cannot usefully hold a connection open.
- Mutations (deletes, releases, Jim's settings) are held in process memory and
  reset on container restart.
