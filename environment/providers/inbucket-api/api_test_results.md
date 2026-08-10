# Inbucket Mock API — Test Results

Base URL: `http://localhost:8123` (in docker-compose: `http://inbucket-api:8123`)

## Endpoints covered

| Method | Path                                                       | Status      |
|--------|------------------------------------------------------------|-------------|
| GET    | /health                                                    | 200         |
| GET    | /status                                                    | 200         |
| GET    | /debug/vars                                                | 200         |
| GET    | /api/v1/mailbox/{name}                                     | 200         |
| POST   | /api/v1/mailbox/{name}                                     | 201/400     |
| DELETE | /api/v1/mailbox/{name}                                     | 200         |
| GET    | /api/v1/mailbox/{name}/{id}                                | 200/404     |
| PATCH  | /api/v1/mailbox/{name}/{id}                                | 200/400/404 |
| DELETE | /api/v1/mailbox/{name}/{id}                                | 200/404     |
| GET    | /api/v1/mailbox/{name}/{id}/source                         | 200/404     |
| GET    | /api/v1/mailbox/{name}/{id}/attach/{index}/{filename}      | 200/400/404 |
| GET    | /api/v1/monitor/messages                                   | 200         |
| GET    | /api/v1/monitor/mailbox/{name}                             | 200         |

Collection run: **PASS 58 / WARN 16 / FAIL 0 / SKIP 0** over 74 requests. Every
WARN is an intentional error-path request, labelled `(N expected)` in the
collection, and every label matches the status the harness observed.

Note what is **not** in that table: there is no endpoint that lists all mail,
and none that lists the mailboxes. That absence is Inbucket's design, not an
omission.

## The naming policy is the whole service

The mailbox is computed from the address, never stored. The collection reads
the *same three messages* through six different `{name}` values:

| `{name}` | Resolves to |
|----------|-------------|
| `amelia.ortega` | `amelia.ortega` |
| `Amelia.Ortega@orbit-labs.com` | `amelia.ortega` |
| `amelia.ortega+billing@orbit-labs.com` | `amelia.ortega` |
| `AMELIA.ORTEGA@acme-partner.example` | `amelia.ortega` |
| `Amelia Ortega <amelia.ortega@orbit-labs.com>` | `amelia.ortega` |
| `AMELIA.ORTEGA` | `amelia.ortega` |

Three addresses, two domains, one mailbox. The policy applies to every route
that takes a `{name}`, so a message can be read, patched, deleted or purged
through any of those forms.

`/status` reports the configuration that drives it:

```json
{"mailbox-naming": "local", "case-sensitive": false, "strip-subaddress": true,
 "mailbox-message-cap": 5, "retention-period": "72h"}
```

## Every mailbox exists

An unknown mailbox is `200 []`. The collection asks three ways — a bare name
nobody uses, an address at a domain the server has never seen, and a mailbox
that was never created — and all three answer with an empty list. There is no
404 anywhere on the mailbox route, because there is nothing to create and so
nothing to be missing.

Contrast: `GET /api/v1/mailbox/{name}/{id}` **is** 404 for an unknown id, and
also for a *real* id read through the wrong mailbox.

## One message, two mailboxes

The incident notice was addressed to `oncall@orbit-labs.com` and
`helena.park@orbit-labs.com`, so Inbucket stored two copies:

```
oncall       20260526T142208-0006
helena.park  20260526T142208-0007
```

Same subject, same body, different ids, independent `seen` flags. The
collection proves the independence three ways: asking for helena's id inside
`oncall` is a 404; marking oncall's copy seen leaves helena's unseen; and
purging `oncall` leaves helena's copy standing.

## Read state

`PATCH /api/v1/mailbox/{name}/{id}` takes `{"seen": true|false}` and is the only
mutation on a message. A missing `seen` and a non-boolean `seen` are each 400;
patching through the wrong mailbox is 404.

## Attachments carry their filename in the URL

`/attach/{index}/{filename}` — and the filename is **checked**, so asking for
index 0 under the wrong name is a 404 that reports what the file is actually
called. An index out of range is 404 naming the count, a non-numeric index is
400, and a message with no attachments is 404.

Each attachment reports a real MD5 of its bytes:

| File | Type | Size | MD5 |
|------|------|------|-----|
| `receipt-ORD-2026-4417.pdf` | `application/pdf` | 90 | `4ccc175219d79ab9f36dd3a111e10c26` |
| `invoice-INV-2026-0417.csv` | `text/csv` | 156 | `ff85013f7b19cd169282f88a32906b59` |
| `export-error.png` | `image/png` | 70 | `2cd8bde463f5d82aae0f0cec061d6b8f` |

## The per-mailbox cap

Inbucket drops the oldest message once a mailbox exceeds its cap. The default
is 500; this instance is configured to **5** so the behaviour is observable.
The collection delivers six messages to a fresh `loadtest` mailbox: the first
five report `"evicted": []`, the sixth reports
`"evicted": ["<the first one>"]`, and the mailbox then holds exactly five,
starting at `burst 2`.

## Deletion is per-mailbox

| | Effect |
|---|--------|
| `DELETE /api/v1/mailbox/{name}/{id}` | one message; deleting it again is 404 |
| `DELETE /api/v1/mailbox/{name}` | purges that mailbox and reports the count |

Purging twice reports `"purged": 0` rather than failing, and purging a mailbox
that never existed does the same — consistent with every mailbox existing.
There is no endpoint that empties the server.

## Two mock additions, both marked in their responses

- `POST /api/v1/mailbox/{name}` — Inbucket only accepts mail over SMTP, which a
  mock cannot offer. This stands in for that delivery, and doubles as the
  clearest demonstration of the naming policy: post to
  `Jonas.Pereira+ci@orbit-labs.com` and the response reports
  `"mailbox": "jonas.pereira"`. It answers **201**.
- `GET /api/v1/monitor/messages` and `/monitor/mailbox/{name}` return a snapshot
  rather than an SSE stream, and say so — a mock cannot usefully hold a
  connection open.

Delivery refuses a missing `from`, a malformed `from`, and a `{name}` that is a
half-written address (`broken@`) — each 400.

## Seed data summary

- **Messages** (10) across **6 mailboxes**: `amelia.ortega` 3, `jonas.pereira`
  2, `oncall` 2, `helena.park` 1, `billing` 1, `support` 1
- **Attachments** (3), keyed `{messageId}#{index}` — a PDF, a CSV and a PNG
- **Config**: `local` naming, case-insensitive, subaddress stripping on, cap 5
- **Counters**: seeded expvar totals that the run then moves

The mail matches the rest of the fleet: the recovery code `770412` is the
authentication services', `INC-4417` is the incident MailHog and Mailpit also
captured, and `EXP-2026-9931` is the export the support message complains about.

## Notes

- Mailboxes list **oldest first** — arrival order. MailHog and Mailpit list
  newest first; this is Inbucket's order, not an oversight.
- Keys are hyphenated (`posix-millis`, `content-type`, `download-link`) because
  Inbucket's are.
- `download-link` is returned as a relative API path, since the mock has no
  reliable notion of its own external host.
- Ids from a delivery are the arrival timestamp plus a sequence, so they differ
  per run; the collection verifies a delivery by listing the mailbox rather
  than by quoting the new id back.
- Mutations are held in process memory and reset on container restart.
