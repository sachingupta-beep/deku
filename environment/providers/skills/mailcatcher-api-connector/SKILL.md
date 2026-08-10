---
name: mailcatcher-api-connector
description: >
  MailCatcher API (Mock) mock HTTP API. Base URL is provided via the
  `MAILCATCHER_API_URL` environment variable. 14 endpoint(s) across GET, POST, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# MailCatcher API (Mock)

Mock of MailCatcher, a Ruby/Sinatra capture tool. **All requests go to the base
URL in `$MAILCATCHER_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MAILCATCHER_API_URL` | Base URL for all requests (e.g. `http://mailcatcher-api:8125`) |

## Five things to know first

**The whole API is `/messages`.** No search, no tags, no read state, no
mailboxes, no sessions, no settings. The minimalism is the identity.

**The format is a file extension.** `/messages/1.json`, `.html`, `.plain`,
`.source`, `.eml` — and each message's `formats` array says which will work.
Check it rather than guessing.

**Ids are plain integers** in arrival order, and they **start again at 1** after
`DELETE /messages`.

**Addresses are angle-bracketed** as the envelope wrote them; a null return path
is the literal `<>`.

**Attachments are addressed by Content-ID**, and `.html` rewrites `cid:` to
`/messages/{id}/parts/{cid}` so the HTML it serves is renderable.

## Seeded messages

| Id | `formats` | Notable |
|----|-----------|---------|
| 1 | source, html, plain | order, **PDF** `receipt-4417@orbit-labs.com` |
| 2 | source, plain | invoice, **CSV** `invoice-0417@orbit-labs.com` |
| 3 | source, html, plain | incident INC-4417, has a `Cc` |
| 4 | source, plain | password reset, code `770412` |
| 5 | source, **html** | welcome, inline `partner-hero@orbit-labs.com` |
| 6 | source, html, plain | digest, `orbit-logo@…` inline + `uptime-w21@…` |
| 7 | source, plain | deploy notice |
| 8 | source, plain | bounce, sender is `<>` |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/health` · `/info` |
| GET/POST/DELETE | `/messages` — list, deliver, clear |
| GET | `/messages/{id}.json` · `.html` · `.plain` · `.source` · `.eml` |
| GET | `/messages/{id}/parts/{cid}` |
| DELETE | `/messages/{id}` — **204, no body** |

## Usage

```bash
# list, then read
curl -s "$MAILCATCHER_API_URL/messages"
curl -s "$MAILCATCHER_API_URL/messages/1.json"

# the bodies, by extension
curl -s "$MAILCATCHER_API_URL/messages/1.plain"
curl -s "$MAILCATCHER_API_URL/messages/1.html"
curl -s "$MAILCATCHER_API_URL/messages/1.source"

# an inline image: the html points at this path
curl -s "$MAILCATCHER_API_URL/messages/5.html"
curl -s "$MAILCATCHER_API_URL/messages/5/parts/partner-hero@orbit-labs.com"

# deliver
curl -s -X POST "$MAILCATCHER_API_URL/messages" \
  -H 'Content-Type: application/json' \
  -d '{"sender": "monitoring@orbit-labs.com",
       "recipients": ["oncall@orbit-labs.com"],
       "subject": "Disk pressure", "plain": "node-7 at 91%."}'

# clear
curl -s -X DELETE "$MAILCATCHER_API_URL/messages"
```

Asking for a format a message does not offer is a **404 naming what it does**;
an extension the API does not know is a **400** doing the same. An unknown
message is a 404 whichever extension is used — the message is checked first.

An unknown cid 404s with the real ones listed, and a cid is scoped to its own
message: message 6 does not answer for message 1's cid.

`size` is a **string** and keys are snake_case, because Ruby serialised them
that way.

One endpoint is marked in its own response as a mock addition:
`POST /messages` stands in for the SMTP delivery a mock cannot accept.

The audit log of every call the agent makes is available at
`$MAILCATCHER_API_URL/audit/requests` (used for grading).
