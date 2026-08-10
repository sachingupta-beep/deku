# Mailpit Mock API — Test Results

Base URL: `http://localhost:8122` (in docker-compose: `http://mailpit-api:8122`)

## Endpoints covered

| Method | Path                                                | Status      |
|--------|-----------------------------------------------------|-------------|
| GET    | /health                                             | 200         |
| GET    | /livez                                              | 200         |
| GET    | /readyz                                             | 200         |
| GET    | /api/v1/info                                        | 200         |
| GET    | /api/v1/webui                                       | 200         |
| GET    | /api/v1/messages                                    | 200         |
| PUT    | /api/v1/messages                                    | 200/400/404 |
| DELETE | /api/v1/messages                                    | 200/404     |
| GET    | /api/v1/search                                      | 200/400     |
| DELETE | /api/v1/search                                      | 200/400     |
| GET    | /api/v1/tags                                        | 200         |
| PUT    | /api/v1/tags                                        | 200/400/404 |
| PUT    | /api/v1/tags/{tag}                                  | 200/400/404 |
| DELETE | /api/v1/tags/{tag}                                  | 200/404     |
| GET    | /api/v1/message/{id}                                | 200/404     |
| GET    | /api/v1/message/{id}/raw                            | 200/404     |
| GET    | /api/v1/message/{id}/headers                        | 200/404     |
| GET    | /api/v1/message/{id}/part/{partId}                  | 200/404     |
| GET    | /api/v1/message/{id}/part/{partId}/thumbnail        | 200/400/404 |
| GET    | /api/v1/message/{id}/html-check                     | 200/400/404 |
| GET    | /api/v1/message/{id}/link-check                     | 200/404     |
| GET    | /api/v1/message/{id}/sa-check                       | 200/404     |
| POST   | /api/v1/message/{id}/release                        | 200/400/404 |
| POST   | /api/v1/send                                        | 200/400     |
| GET    | /api/v1/chaos                                       | 200         |
| PUT    | /api/v1/chaos                                       | 200/400     |

Collection run: **PASS 75 / WARN 37 / FAIL 0 / SKIP 0** over 112 requests. Every
WARN is an intentional error-path request, labelled `(N expected)` in the
collection, and every label matches the status the harness observed.

## The search query language

This is the headline difference from MailHog, which offers
`kind=from|to|containing` and nothing else.

| Form | Example | Matches |
|------|---------|---------|
| prefix | `from:billing` | the sender |
| | `to:` `cc:` `bcc:` `reply-to:` | that header alone |
| | `addressed:helena.park@orbit-labs.com` | from, to, cc **and** bcc |
| | `subject:invoice` · `message-id:20260522204517` | that field |
| | `tag:billing` | an exact tag |
| | `before:2026-05-28` · `after:2026-05-25` | the date bounds |
| flag | `is:read` `is:unread` `is:tagged` `is:untagged` | message state |
| | `has:attachment` | a non-inline attachment |
| phrase | `"elevated api latency"` | the phrase, across the body |
| bare | `INC-4417` | subject, bodies, addresses and tags |
| negation | `-tag:ops` · `!is:read` | the inverse |

Terms are ANDed. `GET` and `DELETE` share the parser, so
`DELETE /api/v1/search?query=tag:marketing` removes exactly what the same query
would have listed.

Errors name what was expected: an unknown prefix lists the valid ones, an
unknown `is:` value lists the valid flags, `before:`/`after:` reject anything
that is not `YYYY-MM-DD`, and an empty query is 400.

## Read state is real, and reading changes it

The collection proves the side effect rather than asserting it:

```
GET  /api/v1/search?query=is:unread        -> 4 of 9
GET  /api/v1/message/iAfZuC9x4Pq2wKvNhLmRtY
GET  /api/v1/search?query=is:unread        -> 3 of 9
```

`PUT /api/v1/messages` sets the flag in bulk; an empty `IDs` applies to every
message, which is Mailpit's behaviour and is exercised.

## Two shapes for one message

| | Gives |
|---|-------|
| `GET /api/v1/messages` | `Snippet`, `Attachments` as a **count**, plus inbox-wide `total`, `unread` and `tags` |
| `GET /api/v1/message/{id}` | `Text`, `HTML`, `ReturnPath`, the parsed `ListUnsubscribe`, and `Inline` / `Attachments` as **lists** |

Addresses are `{Name, Address}` objects in both.

## The three analyses

**`html-check`** scores the HTML against an eight-client matrix (Outlook on
Windows and macOS, Gmail on desktop and Android, Apple Mail on macOS and iOS,
Yahoo! Mail, Thunderbird). The partner welcome fails four tests — `display:
flex`, `gap`, `border-radius` and `linear-gradient()` — for a total of 75%
supported, 3.12% partial, 21.88% unsupported. The order confirmation trips
nothing and scores a clean 100%. A message with no HTML part is 400.

**`link-check`** reports what each link answered. Two of the newsletter's four
links fail: a `404` and a DNS failure, which Mailpit reports as `StatusCode 0`
with the resolver error as its status. `follow=true` resolves a redirect to its
target — the partner welcome's `301` becomes a `200` at
`/partners/getting-started` — so the same message answers differently under the
two settings.

**`sa-check`** returns SpamAssassin rule hits, highest score first, with the
total and an `IsSpam` verdict at the 5.0 threshold:

| Message | Score | Spam |
|---------|-------|------|
| promo blast | 6.839 | **yes** |
| bounce | 0.099 | no |
| order confirmation | -0.2 | no |
| May digest | -1.089 | no |
| anything with no rule hits | 0.0 | no |

## Chaos: error codes and percentages

Mailpit's chaos is a different design from MailHog's Jim, and the mock keeps the
difference. Each trigger carries an **SMTP error code** and a **whole
percentage**, not a behavioural float:

```json
{"Sender":         {"ErrorCode": 451, "Probability": 0},
 "Recipient":      {"ErrorCode": 451, "Probability": 0},
 "Authentication": {"ErrorCode": 535, "Probability": 0}}
```

Chaos bites on `POST /api/v1/send`, which is the mock's SMTP entry point. The
roll is seeded from the address, so the outcome is deterministic per address
rather than random:

| Address | Roll |
|---------|------|
| `priya.raman@orbit-labs.com` | 2 |
| `rohit.bansal@orbit-labs.com` | 16 |
| `jonas.pereira@orbit-labs.com` | 41 |
| `oncall@orbit-labs.com` | 44 |
| `dmitri.volkov@orbit-labs.com` | 53 |
| `amelia.ortega@orbit-labs.com` | 59 |
| `helena.park@orbit-labs.com` | 68 |
| `noor.aziz@orbit-labs.com` | 75 |

The collection arms `Recipient` at 50% and sends to priya (refused) and helena
(accepted) — the same setting, two outcomes — then arms `Sender` at 30% with a
`550` and sends from rohit (refused with 550) and noor (accepted).

The SMTP code is not an HTTP status, so it is returned in the body and the
request itself fails with 400:

```json
{"error": "chaos: sender rohit.bansal@orbit-labs.com rejected",
 "smtpErrorCode": 550}
```

Validation is enforced: a probability outside `0..100`, a fractional
probability, an error code outside `400..599` and an unknown trigger are each
400 naming the offender.

## Release goes through the relay's rules

`POST /api/v1/message/{id}/release` takes `{"To": [...]}` and is checked against
the relay configuration reported by `/api/v1/webui`:

```
AllowedRecipients: @(orbit-labs\.com|acme-partner\.example)$
BlockedRecipients: ^(audit|no-reply)@
```

So `amelia.ortega@orbit-labs.com` releases, `audit@orbit-labs.com` is blocked,
and `someone@elsewhere.example` is not permitted — each 400 naming which rule
refused it.

## Sending

`POST /api/v1/send` creates a real message in the mailbox: it appears in the
list, is searchable, and carries whatever tags and attachments were posted. The
new id is derived from the sender, subject and recipients, so the same payload
always produces the same id.

## Verifying without an invented endpoint

Sends, releases and deletes are recorded in `RuntimeStats` on `/api/v1/info` —
`SMTPAccepted`, `SMTPAcceptedSize`, `SMTPRejected`, `MessagesDeleted` — which
is where Mailpit already reports them. Nothing needed to be added to the API to
make the mutations checkable.

## Seed data summary

- **Messages** (9): 4 unread, 5 read; 7 tagged, 2 untagged; 3 with attachments
  (PDF, CSV and an inline PNG); one with a `Bcc`, one with two `Cc`s, one with a
  `List-Unsubscribe` header
- **Attachments** (3), keyed `{messageId}#{partId}`
- **SpamAssassin rules** (18) across 4 messages
- **Links** (7) across 4 messages, including a `404`, a DNS failure and a `301`
- **HTML warnings** (7) across 3 messages
- **Chaos**: all three triggers seeded at 0% · **Relay**: enabled, with the
  allow and block rules above

The mail is the mail the rest of the fleet would have sent: the recovery code
`770412` matches the authentication services, `INC-4417` matches MailHog's
incident notice, and the bounce is addressed to the deactivated account.

## Notes

- Messages are listed newest-first.
- Deleting a message removes its attachments, rules, links and warnings with it.
- `DELETE /api/v1/messages` with an empty or absent `IDs` empties the mailbox.
- An inline image is not an attachment: it is excluded from the summary
  `Attachments` count and from `has:attachment`, and appears under `Inline` on
  the read.
- `thumbnail` refuses a non-image part with a 400 naming its content type.
- Mutations are held in process memory and reset on container restart.
