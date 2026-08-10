# mailhog-api

Mock of MailHog, which **captures** mail instead of delivering it.

Run it as its own container (build context is the environment root):
```
docker compose up -d mailhog-api
curl http://localhost:8121/health
curl http://localhost:8121/api/v2/messages?limit=3
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir mailhog-api --port 8121
```

Three things follow from being a capture tool rather than a mail server, and
all three are modelled rather than flattened:

- **Addresses are structured, not strings.** Every `From` and `To` is a MailHog
  `Path` — `{Relays, Mailbox, Domain, Params}` — because what was captured is
  the SMTP envelope, not a rendered header.
- **v1 and v2 return the same messages in different shapes.**
  `/api/v1/messages` is a bare array; `/api/v2/messages` is a paginated
  envelope with `total`, `count`, `start` and `items`. Both are served, because
  clients in the wild use both.
- **Jim, the chaos monkey.** MailHog can be told to fail on purpose. He is off
  in the seed, and `GET /api/v2/jim` answers **404** until he is switched on —
  that is how a client discovers chaos is disabled. Once enabled, his chances
  are applied to the release endpoint, seeded from the recipient so the outcome
  is deterministic per address.

MIME parts are addressable individually
(`/api/v1/messages/{id}/mime/part/{n}/download`), which is how a single
attachment is pulled out of a captured multipart message.

Eight messages are captured, chosen to span the shapes a real inbox sees:

| Message | Shape |
|---------|-------|
| verification code to rohit | `text/plain` |
| recovery code to jonas | `text/plain` |
| incident notification | `multipart/alternative` (text + HTML) |
| weekly uptime digest | `multipart/mixed` with a **CSV attachment** |
| invoice to amelia | `multipart/mixed` with a **PDF attachment**, plus a `Cc` |
| security alert | `text/plain` with a **Bcc** |
| partner welcome | `text/html` |
| undeliverable bounce | `multipart/report` with a `message/delivery-status` part |

Two deliberate additions, both marked in the responses: `/api/v1/releases`
records what was released so a release can be verified, and `/api/v1/events`
returns a snapshot rather than holding open an SSE stream.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`mailhog_api_postman_collection.json` for the runnable collection.
