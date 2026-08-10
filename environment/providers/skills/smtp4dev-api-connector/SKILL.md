---
name: smtp4dev-api-connector
description: >
  smtp4dev API (Mock) mock HTTP API. Base URL is provided via the
  `SMTP4DEV_API_URL` environment variable. 22 endpoint(s) across GET, POST, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# smtp4dev API (Mock)

Mock of smtp4dev, a .NET capture tool. **All requests go to the base URL in
`$SMTP4DEV_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `SMTP4DEV_API_URL` | Base URL for all requests (e.g. `http://smtp4dev-api:8124`) |

## Five things to know first

**Pages, not offsets.** Lists are `PagedResult`:
`{results, firstRowOnPage, lastRowOnPage, currentPage, pageCount, pageSize,
rowCount}`, driven by `page` (**1-based**), `pageSize`, `sortColumn`,
`sortIsDescending`.

**Sessions are peers of messages, not a view.** A session is the SMTP
conversation with its full transcript — two of the seeded ones produced no
message at all. Deleting every message leaves them standing.

**Mailboxes route, they don't derive.** Each has recipient patterns; `Default`
is the catch-all and is checked last. Filtering by a mailbox that doesn't exist
**is** a 404.

**MIME parts are a tree**, addressed by section number (`1`, `1.1`, `1.1.2`). A
container part has `childParts`, not content.

**The settings are writable.** `POST /api/Server` is the Settings dialog, and
lowering `numberOfMessagesToKeep` trims the store on the spot.

## Seeded ids

| Message | Notable |
|---------|---------|
| `a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54` | order, **3-level part tree**, PDF at `1.2` |
| `b2e4d8ea-5c3f-4d7b-8e96-4a8f2c1d3e65` | invoice, CSV at `1.2`, in `Billing` |
| `c3f5e9fb-6d40-4e8c-9fa7-5b903d2e4f76` | incident INC-4417, in `Alerts` |
| `d4a6fa0c-7e51-4f9d-80b8-6ca14e3f5087` | password reset, code `770412` |
| `e5b70b1d-8f62-40ae-91c9-7db25f406198` | welcome, HTML only, **relayed** |
| `f6c81c2e-9073-41bf-a2da-8ec360517209` | alert, **relayError** `451 Greylisted` |
| `07d92d3f-a184-42c0-b3eb-9f047162831a` | archive, **mimeParseError** |
| `18ea3e40-b295-43d1-84fc-a0158273942b` | payout, in `Billing` |

| Session | Notable |
|---------|---------|
| `3a9c4e17-2b81-4f60-9d3e-7c05a1b2c3d4` | 2 messages, authenticated |
| `7e30825b-6fc5-43a4-b172-b049e5f60718` | **0 messages** — auth failed 3× |
| `8f41936c-70d6-44b5-8283-c15af6071829` | **0 messages** — recipients `550` |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/health` · `/api/Version` · `/api/Mailboxes` |
| GET/POST | `/api/Server` — read and write the settings |
| GET/POST | `/api/Messages` — paged list, deliver |
| DELETE | `/api/Messages/*` (optional `?mailboxName=`) |
| POST | `/api/Messages/markAllRead` |
| GET/DELETE | `/api/Messages/{id}` |
| GET | `/api/Messages/{id}/source` · `/html` · `/plaintext` |
| GET | `/api/Messages/{id}/part/{partId}/content` · `/source` |
| POST | `/api/Messages/{id}/markRead` · `/relay` |
| GET | `/api/Sessions` — paged · `DELETE /api/Sessions/*` |
| GET/DELETE | `/api/Sessions/{id}` · `GET /api/Sessions/{id}/log` |

## Usage

```bash
# page and sort
curl -s "$SMTP4DEV_API_URL/api/Messages?page=1&pageSize=5&sortColumn=attachmentCount&sortIsDescending=true"
curl -s "$SMTP4DEV_API_URL/api/Messages?mailboxName=Billing&searchTerms=INV-2026-0417"

# read, then walk the part tree
curl -s "$SMTP4DEV_API_URL/api/Messages/a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54"
curl -s "$SMTP4DEV_API_URL/api/Messages/a1f3c7d9-4b2e-4c6a-9d85-3f7e1b0c2d54/part/1.2/content"

# the conversation that produced nothing
curl -s "$SMTP4DEV_API_URL/api/Sessions/7e30825b-6fc5-43a4-b172-b049e5f60718/log"

# relay, and change the settings that govern it
curl -s -X POST "$SMTP4DEV_API_URL/api/Messages/d4a6fa0c-7e51-4f9d-80b8-6ca14e3f5087/relay" \
  -H 'Content-Type: application/json' \
  -d '{"overrideRecipientAddresses": ["qa@orbit-labs.com"]}'
curl -s -X POST "$SMTP4DEV_API_URL/api/Server" \
  -H 'Content-Type: application/json' -d '{"relayOptions": {"isEnabled": false}}'
```

Sortable columns — messages: `receivedDate`, `from`, `to`, `subject`,
`attachmentCount`, `isUnread`, `mailbox`. Sessions: `startDate`, `endDate`,
`clientAddress`, `numberOfMessages`, `terminatedWithError`. Anything else is a
400 that lists the valid ones.

`mimeParseError` and `relayError` are different failures and both are seeded —
the archive could not be *parsed*, the alert could not be *relayed*.

**Careful with `POST /api/Server`**: lowering `numberOfMessagesToKeep` or
`numberOfSessionsToKeep` deletes immediately and reports what went in
`trimmed`.

One endpoint is marked in its own response as a mock addition:
`POST /api/Messages` stands in for the SMTP delivery a mock cannot accept, and
opens a matching session.

The audit log of every call the agent makes is available at
`$SMTP4DEV_API_URL/audit/requests` (used for grading).
