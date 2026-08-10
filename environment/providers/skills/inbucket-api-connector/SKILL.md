---
name: inbucket-api-connector
description: >
  Inbucket API (Mock) mock HTTP API. Base URL is provided via the
  `INBUCKET_API_URL` environment variable. 12 endpoint(s) across GET, POST, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Inbucket API (Mock)

Mock of Inbucket. **All requests go to the base URL in `$INBUCKET_API_URL`.**
Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `INBUCKET_API_URL` | Base URL for all requests (e.g. `http://inbucket-api:8123`) |

## Five things to know first

**There is no global inbox.** Every read names a mailbox. Nothing lists all
mail, and nothing lists the mailboxes — you are expected to know the address.
The monitor is the only cross-mailbox view.

**The mailbox is derived, not stored.** Local part, lowercased, `+subaddress`
stripped. `Amelia.Ortega@orbit-labs.com`, `amelia.ortega+billing@orbit-labs.com`
and `AMELIA.ORTEGA@acme-partner.example` → **`amelia.ortega`**. The `{name}`
segment takes a bare name or a full address; both go through the policy.

**Every mailbox exists.** An unknown one is `200 []`, never 404. The 404s here
are all about messages.

**A message to two recipients is two messages** — one per mailbox, each with its
own id and `seen` flag.

**Deletion is per-mailbox.** Nothing empties the server.

## Mailboxes

| Mailbox | Messages |
|---------|----------|
| `amelia.ortega` | `20260528T091412-0001` order + PDF · `20260527T143055-0002` invoice + CSV · `20260526T101733-0003` partner credentials |
| `jonas.pereira` | `20260527T164155-0004` password reset, code `770412` · `20260525T075500-0005` uptime digest |
| `oncall` | `20260526T142208-0006` incident INC-4417 · `20260524T193012-0008` ingest-lag alert |
| `helena.park` | `20260526T142208-0007` — her copy of the same incident |
| `billing` | `20260523T111020-0009` settled payout |
| `support` | `20260522T083045-0010` customer report + PNG |

## Endpoints

| Method | Path |
|--------|------|
| GET | `/health` · `/status` · `/debug/vars` |
| GET/POST/DELETE | `/api/v1/mailbox/{name}` — list, deliver, purge |
| GET/PATCH/DELETE | `/api/v1/mailbox/{name}/{id}` |
| GET | `/api/v1/mailbox/{name}/{id}/source` |
| GET | `/api/v1/mailbox/{name}/{id}/attach/{index}/{filename}` |
| GET | `/api/v1/monitor/messages` · `/api/v1/monitor/mailbox/{name}` |

## Usage

```bash
# any of these read the same mailbox
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega%2Bbilling@orbit-labs.com"

# read one, then pull its attachment
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega/20260528T091412-0001"
curl -s "$INBUCKET_API_URL/api/v1/mailbox/amelia.ortega/20260528T091412-0001/attach/0/receipt-ORD-2026-4417.pdf"

# mark it seen
curl -s -X PATCH "$INBUCKET_API_URL/api/v1/mailbox/oncall/20260526T142208-0006" \
  -H 'Content-Type: application/json' -d '{"seen": true}'

# deliver, and watch where the address lands
curl -s -X POST "$INBUCKET_API_URL/api/v1/mailbox/Jonas.Pereira%2Bci@orbit-labs.com" \
  -H 'Content-Type: application/json' \
  -d '{"from": "ci@orbit-labs.com", "subject": "Nightly build", "text": "Green."}'

# purge one mailbox
curl -s -X DELETE "$INBUCKET_API_URL/api/v1/mailbox/loadtest"
```

The attachment **filename is part of the path and is checked** — a mismatch is a
404 that reports the real name. Each attachment carries a genuine MD5.

Mailboxes list **oldest first**, and the keys are hyphenated (`posix-millis`,
`content-type`, `download-link`) — both are Inbucket's, not slips.

The per-mailbox cap is **5** here (Inbucket defaults to 500), so a sixth
delivery evicts the oldest and reports it in `evicted`.

Two endpoints are marked in their own responses as mock additions:
`POST /api/v1/mailbox/{name}` stands in for the SMTP delivery a mock cannot
accept, and the monitor returns a snapshot rather than an SSE stream.

The audit log of every call the agent makes is available at
`$INBUCKET_API_URL/audit/requests` (used for grading).
