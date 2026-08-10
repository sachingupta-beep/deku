---
name: mailhog-api-connector
description: >
  MailHog API (Mock) mock HTTP API. Base URL is provided via the
  `MAILHOG_API_URL` environment variable. 16 endpoint(s) across GET, POST, PUT, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# MailHog API (Mock)

Mock of MailHog, which **captures** mail instead of delivering it. **All
requests go to the base URL in `$MAILHOG_API_URL`.** Responses are deterministic
fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MAILHOG_API_URL` | Base URL for all requests (e.g. `http://mailhog-api:8121`) |

## Three things to know first

**Addresses are structured, not strings.** Every `From` and `To` is
`{Relays, Mailbox, Domain, Params}`, because what was captured is the SMTP
envelope. `To` includes the `Cc` and `Bcc` recipients.

**v1 and v2 return the same messages differently.** `/api/v1/messages` is a bare
array; `/api/v2/messages` is `{total, count, start, items}`.

**Jim is off until enabled.** `GET /api/v2/jim` returns **404** while chaos is
disabled — that is the discovery mechanism, not an error.

## Captured messages

| Id | Shape | Notable |
|----|-------|---------|
| `3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example` | `text/plain` | verification code `482913` |
| `9tQrKcVmXwLpZbN2eHjD4A@mailhog.example` | `text/plain` | recovery code `770412` |
| `Kf7bVpQnRtLmYcXwEjH0Zg@mailhog.example` | `multipart/alternative` | text + HTML, has a `Cc` |
| `Wq3ZmNbXcVpLkJhGfDsA2Q@mailhog.example` | `multipart/mixed` | **CSV attachment** at part 1 |
| `Bn5XcTgYuIoPlKjHgFdSa1@mailhog.example` | `multipart/mixed` | **PDF attachment** at part 1 |
| `Mj8LkQwErTyUiOpAsDfGh3@mailhog.example` | `text/plain` | has a **Bcc** |
| `Zx4CvBnMqWeRtYuIoPaSd6@mailhog.example` | `text/html` | partner welcome |
| `Hg2FdSaPoIuYtReWq9MnBv@mailhog.example` | `multipart/report` | bounce, `message/delivery-status` at part 1 |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/api/v1/info` · `/api/v1/events` |
| GET/DELETE | `/api/v1/messages` |
| GET/DELETE | `/api/v1/messages/{id}` |
| GET | `/api/v1/messages/{id}/download` |
| GET | `/api/v1/messages/{id}/mime/part/{n}/download` |
| POST | `/api/v1/messages/{id}/release` |
| GET | `/api/v1/releases` |
| GET | `/api/v2/messages?start=&limit=` |
| GET | `/api/v2/search?kind=from\|to\|containing&query=` |
| GET/POST/PUT/DELETE | `/api/v2/jim` |
| GET | `/api/v2/outgoing-smtp` |

## Usage

```bash
# list, then read one
curl -s "$MAILHOG_API_URL/api/v2/messages?limit=5"
curl -s "$MAILHOG_API_URL/api/v1/messages/3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example"

# find the mail carrying a code
curl -s "$MAILHOG_API_URL/api/v2/search?kind=containing&query=482913"

# pull one attachment out
curl -s "$MAILHOG_API_URL/api/v1/messages/Wq3ZmNbXcVpLkJhGfDsA2Q@mailhog.example/mime/part/1/download"

# release to a configured relay
curl -s -X POST "$MAILHOG_API_URL/api/v1/messages/3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example/release" \
  -H 'Content-Type: application/json' \
  -d '{"Name": "orbit-relay", "Email": "rohit.bansal@orbit-labs.com"}'
```

Jim's failure roll is seeded from the recipient, so it is deterministic per
address: at `RejectRecipientChance: 0.4`, `oncall@orbit-labs.com` is rejected
and `rohit.bansal@orbit-labs.com` is let through.

Two additions to the real API, both marked in their responses:
`/api/v1/releases` records what was released so it can be verified, and
`/api/v1/events` returns a snapshot rather than an SSE stream.

The audit log of every call the agent makes is available at
`$MAILHOG_API_URL/audit/requests` (used for grading).
