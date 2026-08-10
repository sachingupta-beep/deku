---
name: mailpit-api-connector
description: >
  Mailpit API (Mock) mock HTTP API. Base URL is provided via the
  `MAILPIT_API_URL` environment variable. 23 endpoint(s) across GET, POST, PUT, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Mailpit API (Mock)

Mock of Mailpit, MailHog's successor. **All requests go to the base URL in
`$MAILPIT_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MAILPIT_API_URL` | Base URL for all requests (e.g. `http://mailpit-api:8122`) |

## Four things to know first

**Search is a query language, not a `kind` parameter.**
`query=from:billing is:unread -tag:receipt "order total"`. Terms are ANDed;
`-` or `!` negates.

**Reading a message marks it read.** `GET /api/v1/message/{id}` has that side
effect, so `is:unread` counts change as you browse.

**The paths are singular and plural on purpose.** `/api/v1/messages` is the
list; `/api/v1/message/{id}` is the read. They return different shapes of the
same message.

**Chaos is SMTP error codes and whole percentages** — not MailHog's behavioural
floats. It bites on `POST /api/v1/send`, and the roll is seeded from the
address.

## Query language

| Form | Terms |
|------|-------|
| prefixes | `from:` `to:` `cc:` `bcc:` `reply-to:` `addressed:` `subject:` `message-id:` `tag:` `before:` `after:` |
| flags | `is:read` `is:unread` `is:tagged` `is:untagged` `has:attachment` |
| other | `"quoted phrase"`, bare words, `-term` / `!term` |

`before:`/`after:` take `YYYY-MM-DD`. An unknown prefix or flag is a 400 that
lists the valid ones.

## Captured messages

| Id | Notable |
|----|---------|
| `iAfZuC9x4Pq2wKvNhLmRtY` | order confirmation, **PDF**, tagged `billing;receipt`, unread |
| `Rn7KdWpXsE3zQjBvUyTaHc` | password reset, recovery code `770412` |
| `Lm4TgVhNpZxCwQdRsFuKb8` | May digest, inline logo, **two failing links** |
| `Yb9PxJqWnMkTvRzHcAeDs2` | promo blast, **spam** (6.839), untagged |
| `Ct5NrXbGmVpLdWyQzKfJh7` | incident notice, two `Cc`, tagged `ops;incident` |
| `Da3ZkFpQwSxEvRtYuIoLm1` | invoice, **CSV**, has a hidden **`Bcc`** |
| `Ek6MbNcVxZaSdFgHjKlPq4` | partner welcome, **4 html-check failures**, a `301` |
| `Gp8WqErTyUiOpAsDfGhZx5` | bounce, empty return path, untagged |
| `Hs2JnBvCxZlKmQwErTyUi9` | deploy notice from the sync bot |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/health` · `/livez` · `/readyz` · `/api/v1/info` · `/api/v1/webui` |
| GET/PUT/DELETE | `/api/v1/messages` — list, set read, bulk delete |
| GET/DELETE | `/api/v1/search?query=` |
| GET/PUT | `/api/v1/tags` — list, set on IDs |
| PUT/DELETE | `/api/v1/tags/{tag}` — rename, delete |
| GET | `/api/v1/message/{id}` · `/raw` · `/headers` |
| GET | `/api/v1/message/{id}/part/{partId}` · `/thumbnail` |
| GET | `/api/v1/message/{id}/html-check` · `/link-check` · `/sa-check` |
| POST | `/api/v1/message/{id}/release` · `/api/v1/send` |
| GET/PUT | `/api/v1/chaos` |

## Usage

```bash
# find it, then read it
curl -s "$MAILPIT_API_URL/api/v1/search?query=is:unread+tag:billing"
curl -s "$MAILPIT_API_URL/api/v1/message/iAfZuC9x4Pq2wKvNhLmRtY"

# pull an attachment out
curl -s "$MAILPIT_API_URL/api/v1/message/Da3ZkFpQwSxEvRtYuIoLm1/part/2"

# what is wrong with this mail?
curl -s "$MAILPIT_API_URL/api/v1/message/Ek6MbNcVxZaSdFgHjKlPq4/html-check"
curl -s "$MAILPIT_API_URL/api/v1/message/Lm4TgVhNpZxCwQdRsFuKb8/link-check"
curl -s "$MAILPIT_API_URL/api/v1/message/Yb9PxJqWnMkTvRzHcAeDs2/sa-check"

# send one, then relay one
curl -s -X POST "$MAILPIT_API_URL/api/v1/send" \
  -H 'Content-Type: application/json' \
  -d '{"From": {"Email": "noor.aziz@orbit-labs.com"},
       "To": [{"Email": "dmitri.volkov@orbit-labs.com"}],
       "Subject": "Sandbox ready", "Text": "Your tenant is live."}'
curl -s -X POST "$MAILPIT_API_URL/api/v1/message/iAfZuC9x4Pq2wKvNhLmRtY/release" \
  -H 'Content-Type: application/json' \
  -d '{"To": ["amelia.ortega@orbit-labs.com"]}'
```

Release is checked against the relay's allow/block rules, which
`/api/v1/webui` reports: `@orbit-labs.com` and `@acme-partner.example` are
permitted, and anything at `audit@` or `no-reply@` is blocked.

Chaos rolls, for planning a test: priya 2, rohit 16, jonas 41, oncall 44,
dmitri 53, amelia 59, helena 68, noor 75. At `Probability: 50`, the first four
are refused and the last four go through. A refusal is HTTP 400 with the SMTP
code in `smtpErrorCode`.

Sends, releases, refusals and deletes are all recorded in `RuntimeStats` on
`/api/v1/info`, which is how a mutation is verified — nothing was added to the
API for it.

The audit log of every call the agent makes is available at
`$MAILPIT_API_URL/audit/requests` (used for grading).
