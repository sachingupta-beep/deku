# inbucket-api

Mock of Inbucket — a third capture model, and the difference from `mailhog-api`
and `mailpit-api` is structural rather than cosmetic.

Run it as its own container (build context is the environment root):
```
docker compose up -d inbucket-api
curl http://localhost:8123/health
curl http://localhost:8123/api/v1/mailbox/amelia.ortega
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir inbucket-api --port 8123
```

Five consequences of Inbucket's design, all modelled:

- **There is no global inbox.** Every read names a mailbox. No endpoint lists
  all captured mail, and none lists the mailboxes either — a client is expected
  to know the address it sent to. The monitor is the only cross-mailbox view.
- **The mailbox is derived from the address, not stored.** Under the `local`
  policy it is the local part, lowercased, with any `+subaddress` stripped. So
  `Amelia.Ortega@orbit-labs.com`, `amelia.ortega+billing@orbit-labs.com` and
  `AMELIA.ORTEGA@acme-partner.example` are three addresses across two domains
  and **one mailbox**. The `{name}` path segment takes a bare mailbox name or a
  full address and puts both through the same policy.
- **Every mailbox exists.** An unknown one is `200 []`, never a 404. There is
  nothing to create, so there is nothing to be missing — which is the opposite
  of how MailHog and Mailpit answer for an unknown message.
- **A message to two recipients is two messages.** Inbucket stores a copy per
  mailbox, each with its own id and its own `seen` flag. The seeded incident
  notice sits in `oncall` and `helena.park`; marking one seen leaves the other
  alone, and purging one mailbox leaves the other's copy intact.
- **Deletion is per-mailbox.** `DELETE /api/v1/mailbox/{name}` purges one
  mailbox. Nothing empties the server.

Smaller things that are Inbucket's and are kept: keys are hyphenated
(`posix-millis`, `content-type`, `download-link`), mailboxes list **oldest
first** where the other two list newest first, the attachment filename is part
of its URL *and is checked*, and each attachment carries a real MD5 of its
bytes.

There is also a **per-mailbox message cap**: once a mailbox is over it, the
oldest message is evicted. Inbucket defaults to 500; this instance is
configured to **5** so the eviction is actually observable, and `/status`
reports the figure.

Ten messages across six mailboxes:

| Mailbox | Holds |
|---------|-------|
| `amelia.ortega` | 3 — reached via a plain address, a `+billing` subaddress, and a different domain in upper case |
| `jonas.pereira` | 2 — password reset (code `770412`) and a weekly digest |
| `oncall` | 2 — the incident notice and a monitoring alert with a `Cc` |
| `helena.park` | 1 — her own copy of that same incident notice |
| `billing` | 1 — a settled payout |
| `support` | 1 — a customer report with a PNG screenshot |

Two endpoints are marked in their own responses as mock additions:
`POST /api/v1/mailbox/{name}` stands in for the SMTP delivery a mock cannot
accept — and doubles as the clearest demonstration of the naming policy, since
the response says which mailbox the address resolved to — and the monitor
returns a snapshot rather than holding open an SSE stream.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`inbucket_api_postman_collection.json` for the runnable collection.
