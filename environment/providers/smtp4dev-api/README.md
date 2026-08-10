# smtp4dev-api

Mock of smtp4dev — a .NET capture tool, and it shows in every contract.

Run it as its own container (build context is the environment root):
```
docker compose up -d smtp4dev-api
curl http://localhost:8124/health
curl "http://localhost:8124/api/Messages?page=1&pageSize=5&sortColumn=receivedDate"
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir smtp4dev-api --port 8124
```

Five things separate it from the other three mail services, and all five are
modelled rather than smoothed into a common shape:

- **Pages, not offsets.** Every list is a `PagedResult`:
  `{results, firstRowOnPage, lastRowOnPage, currentPage, pageCount, pageSize,
  rowCount}`, driven by `page` (1-based), `pageSize`, `sortColumn` and
  `sortIsDescending`. MailHog and Mailpit count from a `start` offset;
  smtp4dev counts pages, and an unsortable column is a 400 that lists the ones
  that work.
- **Sessions are first-class, and separate from messages.** A session is the
  SMTP *conversation*, kept with its full transcript — including the two seeded
  ones that produced no message at all, because the client failed to
  authenticate three times or hung up after both recipients were rejected.
  Nothing else in this fleet keeps the conversation, and deleting every message
  leaves the sessions standing with `numberOfMessages: 0`.
- **Mailboxes are recipient-matching rules.** Mail is filed by testing the
  recipient against each mailbox's patterns, with `Default` as the catch-all
  checked last. Inbucket *derives* a mailbox from the address; smtp4dev
  *routes* to one — `sre@orbit-labs.com` lands in `Alerts` because that mailbox
  claims `sre@*`.
- **MIME parts are a tree, not a list.** Parts are addressed by section number
  — `1`, `1.1`, `1.1.2` — and a container part has `childParts` rather than
  content, so asking for its content is a 400 that says which container it is.
  An unknown section number 404s *and lists the real ones*.
- **The server settings are writable.** `POST /api/Server` is the Settings
  dialog: it changes the host name, the ports, the TLS mode and the relay
  options. Lowering `numberOfMessagesToKeep` trims the store on the spot, which
  is exactly how smtp4dev behaves.

Eight messages across three mailboxes and seven sessions:

| Message | Mailbox | Notable |
|---------|---------|---------|
| order confirmation | `Default` | three-level part tree, PDF attachment |
| invoice | `Billing` | CSV attachment, a `Cc` |
| incident notice | `Alerts` | `multipart/alternative`, a `Cc` |
| password reset | `Default` | recovery code `770412` |
| partner welcome | `Default` | HTML only, **already relayed** |
| ingest-lag alert | `Alerts` | a **failed relay**: `451 4.7.1 Greylisted` |
| nightly archive | `Default` | a **MIME parse error** and a truncated attachment |
| payout notice | `Billing` | plain text |

| Session | Produced |
|---------|----------|
| `3a9c4e17…` | 2 messages, authenticated over STARTTLS |
| `4b0d5f28…` | 1, from an external relay |
| `5c1e6039…` | 2, plaintext HELO |
| `6d2f714a…` | 1, authenticated |
| `7e30825b…` | **nothing** — three failed `AUTH LOGIN` attempts, then `421` |
| `8f41936c…` | **nothing** — both recipients `550`, client disconnected |
| `9052a47d…` | 2, one of them the message with the MIME warning |

One endpoint is marked in its own response as a mock addition:
`POST /api/Messages` stands in for the SMTP delivery a mock cannot accept — and
it opens a session with a matching transcript, so the routing, the retention
trim and the session view can all be exercised.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`smtp4dev_api_postman_collection.json` for the runnable collection.
