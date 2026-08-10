# Mailpit API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$MAILPIT_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MAILPIT_API_URL` | Base URL for all requests |

Set the message ids once to follow the examples:

```bash
export ORDER='iAfZuC9x4Pq2wKvNhLmRtY'
export RESET='Rn7KdWpXsE3zQjBvUyTaHc'
export DIGEST='Lm4TgVhNpZxCwQdRsFuKb8'
export PROMO='Yb9PxJqWnMkTvRzHcAeDs2'
export INCIDENT='Ct5NrXbGmVpLdWyQzKfJh7'
export INVOICE='Da3ZkFpQwSxEvRtYuIoLm1'
export WELCOME='Ek6MbNcVxZaSdFgHjKlPq4'
export BOUNCE='Gp8WqErTyUiOpAsDfGhZx5'
export DEPLOY='Hs2JnBvCxZlKmQwErTyUi9'
```

## Service state

```bash
curl -s "$MAILPIT_API_URL/health"
curl -s "$MAILPIT_API_URL/livez"
curl -s "$MAILPIT_API_URL/readyz"
curl -s "$MAILPIT_API_URL/api/v1/info"
curl -s "$MAILPIT_API_URL/api/v1/webui"
```

`/api/v1/info` carries the message and unread counts, a tag histogram, and the
`RuntimeStats` counters that record sends, releases, refusals and deletes.
`/api/v1/webui` carries the relay configuration release is checked against.

## The list and the read are different shapes

```bash
curl -s "$MAILPIT_API_URL/api/v1/messages?start=0&limit=5"
curl -s "$MAILPIT_API_URL/api/v1/message/$ORDER"
```

| | Gives |
|---|-------|
| list | `Snippet`, `Attachments` as a **count**, plus `total`, `unread`, `tags` |
| read | `Text`, `HTML`, `ReturnPath`, parsed `ListUnsubscribe`, `Inline` and `Attachments` as **lists** |

Addresses are `{Name, Address}` in both. Messages come back newest first.

**Reading marks the message read.** That is a side effect, not a bug —
`is:unread` counts drop as you browse.

## Search

```bash
curl -s "$MAILPIT_API_URL/api/v1/search?query=is:unread"
curl -s "$MAILPIT_API_URL/api/v1/search?query=from:billing"
curl -s "$MAILPIT_API_URL/api/v1/search?query=to:finance"
curl -s "$MAILPIT_API_URL/api/v1/search?query=cc:helena.park@orbit-labs.com"
curl -s "$MAILPIT_API_URL/api/v1/search?query=bcc:audit@orbit-labs.com"
curl -s "$MAILPIT_API_URL/api/v1/search?query=addressed:helena.park@orbit-labs.com"
curl -s "$MAILPIT_API_URL/api/v1/search?query=subject:invoice"
curl -s "$MAILPIT_API_URL/api/v1/search?query=tag:billing"
curl -s "$MAILPIT_API_URL/api/v1/search?query=has:attachment"
curl -s "$MAILPIT_API_URL/api/v1/search?query=is:untagged"
curl -s "$MAILPIT_API_URL/api/v1/search?query=%22elevated+api+latency%22"
curl -s "$MAILPIT_API_URL/api/v1/search?query=after:2026-05-25+before:2026-05-28"
curl -s "$MAILPIT_API_URL/api/v1/search?query=orbit+-tag:ops"
curl -s "$MAILPIT_API_URL/api/v1/search?query=orbit&start=2&limit=2"
```

| Form | Terms |
|------|-------|
| prefixes | `from:` `to:` `cc:` `bcc:` `reply-to:` `addressed:` `subject:` `message-id:` `tag:` `before:` `after:` |
| flags | `is:read` `is:unread` `is:tagged` `is:untagged` `has:attachment` |
| other | `"quoted phrase"`, bare words (subject + bodies + addresses + tags), `-term` / `!term` |

`addressed:` spans from, to, cc and bcc at once. `has:attachment` ignores inline
images. Terms are ANDed. Results use the same envelope as the list, so `start`
and `limit` work.

Errors name what was expected: an unknown prefix, an unknown `is:`/`has:` value,
a `before:`/`after:` that is not `YYYY-MM-DD`, and an empty query are each 400.

## Reading the parts

```bash
curl -s "$MAILPIT_API_URL/api/v1/message/$RESET/raw"
curl -s "$MAILPIT_API_URL/api/v1/message/$INVOICE/headers"
curl -s "$MAILPIT_API_URL/api/v1/message/$INVOICE/part/2"      # CSV
curl -s "$MAILPIT_API_URL/api/v1/message/$ORDER/part/2"        # PDF
curl -s "$MAILPIT_API_URL/api/v1/message/$DIGEST/part/2"       # inline PNG
curl -s "$MAILPIT_API_URL/api/v1/message/$DIGEST/part/2/thumbnail"
```

`thumbnail` refuses a non-image part with a 400 naming its content type; an
absent part id is 404.

## The three analyses

```bash
curl -s "$MAILPIT_API_URL/api/v1/message/$WELCOME/html-check"
curl -s "$MAILPIT_API_URL/api/v1/message/$DIGEST/link-check"
curl -s "$MAILPIT_API_URL/api/v1/message/$WELCOME/link-check?follow=true"
curl -s "$MAILPIT_API_URL/api/v1/message/$PROMO/sa-check"
```

**html-check** scores the HTML against eight clients (Outlook on Windows and
macOS, Gmail on desktop and Android, Apple Mail on macOS and iOS, Yahoo! Mail,
Thunderbird). The welcome mail fails four tests — `display: flex`, `gap`,
`border-radius`, `linear-gradient()` — for 75% supported / 3.12% partial /
21.88% unsupported. The order confirmation is clean at 100%. A message with no
HTML part is **400**.

**link-check** reports what each link answered. A DNS failure has no HTTP status
and comes back as `StatusCode 0` with the resolver error. `follow=true` resolves
a redirect to its target, so the welcome mail's `301` becomes a `200`.

**sa-check** returns SpamAssassin rule hits, highest first, with a total and an
`IsSpam` verdict at 5.0:

| Message | Score | Spam |
|---------|-------|------|
| `$PROMO` | 6.839 | **yes** |
| `$BOUNCE` | 0.099 | no |
| `$ORDER` | -0.2 | no |
| `$DIGEST` | -1.089 | no |
| `$WELCOME` (no hits) | 0.0 | no |

## Read state and tags

```bash
curl -s -X PUT "$MAILPIT_API_URL/api/v1/messages" \
  -H 'Content-Type: application/json' \
  -d '{"IDs": ["'$INCIDENT'"], "Read": false}'
curl -s -X PUT "$MAILPIT_API_URL/api/v1/messages" \
  -H 'Content-Type: application/json' -d '{"IDs": [], "Read": true}'

curl -s "$MAILPIT_API_URL/api/v1/tags"
curl -s -X PUT "$MAILPIT_API_URL/api/v1/tags" \
  -H 'Content-Type: application/json' \
  -d '{"IDs": ["'$BOUNCE'"], "Tags": ["bounce", "ops"]}'
curl -s -X PUT "$MAILPIT_API_URL/api/v1/tags/receipt" \
  -H 'Content-Type: application/json' -d '{"Name": "receipts"}'
curl -s -X DELETE "$MAILPIT_API_URL/api/v1/tags/receipts"
```

An empty `IDs` on the read update applies to **every** message. Setting tags
replaces them and needs at least one id. Renaming a tag rewrites it everywhere
it appears; renaming or deleting one that does not exist is 404. Tags may
contain letters, digits, spaces, dashes, dots and underscores — anything else is
400.

## Sending

```bash
curl -s -X POST "$MAILPIT_API_URL/api/v1/send" \
  -H 'Content-Type: application/json' \
  -d '{"From": {"Email": "noor.aziz@orbit-labs.com", "Name": "Noor Aziz"},
       "To": [{"Email": "dmitri.volkov@orbit-labs.com"}],
       "Cc": [], "Bcc": [], "Subject": "Sandbox tenant is ready",
       "Text": "Your partner sandbox is live.",
       "HTML": "<p>Your partner sandbox is live.</p>",
       "Tags": ["partners"],
       "Attachments": [{"Filename": "keys.csv", "ContentType": "text/csv",
                        "Content": "a2V5LHZhbHVlCg=="}]}'
```

The reply is `{"ID": "..."}`, and the id is derived from the sender, subject and
recipients so the same payload always produces the same one. The message lands
in the mailbox and is searchable straight away.

Refusals: no `From.Email`, no `To`, a malformed address in any group, and an
invalid tag — each 400.

## Chaos

```bash
curl -s "$MAILPIT_API_URL/api/v1/chaos"
curl -s -X PUT "$MAILPIT_API_URL/api/v1/chaos" \
  -H 'Content-Type: application/json' \
  -d '{"Recipient": {"ErrorCode": 451, "Probability": 50}}'
curl -s -X PUT "$MAILPIT_API_URL/api/v1/chaos" \
  -H 'Content-Type: application/json' \
  -d '{"Sender": {"ErrorCode": 550, "Probability": 30},
       "Recipient": {"Probability": 0}}'
```

Three triggers — `Sender`, `Recipient`, `Authentication` — each with an **SMTP
error code** (`400..599`) and a **whole percentage** (`0..100`). Chaos bites on
`POST /api/v1/send`, and the roll is seeded from the address:

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

A refusal is HTTP **400** with the SMTP code in the body — the SMTP code is not
an HTTP status:

```json
{"error": "chaos: sender rohit.bansal@orbit-labs.com rejected",
 "smtpErrorCode": 550}
```

Validation: a probability outside `0..100`, a fractional probability, an error
code outside `400..599`, and an unknown trigger are each 400 naming the offender.

## Release

```bash
curl -s -X POST "$MAILPIT_API_URL/api/v1/message/$ORDER/release" \
  -H 'Content-Type: application/json' \
  -d '{"To": ["amelia.ortega@orbit-labs.com"]}'
```

Checked against the relay rules reported by `/api/v1/webui`:

```
AllowedRecipients: @(orbit-labs\.com|acme-partner\.example)$
BlockedRecipients: ^(audit|no-reply)@
```

So `audit@orbit-labs.com` is blocked and `someone@elsewhere.example` is not
permitted — each 400 naming which rule refused it. An empty `To` is 400; an
unknown message is 404.

## Deleting

```bash
curl -s -X DELETE "$MAILPIT_API_URL/api/v1/search?query=tag:marketing"
curl -s -X DELETE "$MAILPIT_API_URL/api/v1/messages" \
  -H 'Content-Type: application/json' -d '{"IDs": ["'$BOUNCE'"]}'
curl -s -X DELETE "$MAILPIT_API_URL/api/v1/messages" \
  -H 'Content-Type: application/json' -d '{}'
```

`DELETE /api/v1/search` removes exactly what the same query would have listed.
An empty or absent `IDs` empties the mailbox. Deleting a message takes its
attachments, rules, links and warnings with it; deleting an unknown id is 404.

## Verifying a mutation

There is no releases endpoint, and none was invented. Sends, releases, chaos
refusals and deletes all land in `RuntimeStats` on `/api/v1/info` —
`SMTPAccepted`, `SMTPAcceptedSize`, `SMTPRejected`, `MessagesDeleted` — which is
where Mailpit already reports them.

## Errors

| HTTP | When |
|------|------|
| 400 | unknown search prefix or flag, a bad date bound, an empty query, a non-boolean `Read`, a missing `Read`, `Tags` with no `IDs`, an invalid tag, a rename with no `Name`, html-check on a text-only message, thumbnail of a non-image part, a send with no sender/recipient or a malformed address, a chaos setting out of range or an unknown trigger, a chaos-injected refusal, a release with no recipients or one the relay rules refuse |
| 404 | unknown message id, unknown part id, unknown tag |
