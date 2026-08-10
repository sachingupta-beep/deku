# mailpit-api

Mock of Mailpit, MailHog's successor — and deliberately not a reskin of it.

Run it as its own container (build context is the environment root):
```
docker compose up -d mailpit-api
curl http://localhost:8122/health
curl "http://localhost:8122/api/v1/search?query=is:unread"
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir mailpit-api --port 8122
```

Four things separate it from `mailhog-api`, and all four are modelled rather
than flattened:

- **Search is a real query language.** MailHog takes `kind=from|to|containing`.
  Mailpit takes `query=from:billing is:unread -tag:receipt "order total"` —
  prefixed terms (`from:`, `to:`, `cc:`, `bcc:`, `reply-to:`, `addressed:`,
  `subject:`, `message-id:`, `tag:`, `before:`, `after:`), `is:`/`has:` flags,
  quoted phrases, and negation with `-` or `!`, all ANDed together. An unknown
  prefix or flag value is a 400 that names what was expected.
- **A message has state.** Read/unread is tracked and mutable, and
  `GET /api/v1/message/{id}` marks a message read *as a side effect*. Tags are
  first-class: settable in bulk, renameable across every message that carries
  them, deletable, and immediately searchable.
- **Mailpit analyses what it captured.** `html-check` scores the HTML against a
  client matrix, `link-check` reports what each link answered, and `sa-check`
  returns SpamAssassin rule hits with a total score. None of these exist in
  MailHog.
- **Chaos is error codes, not behaviours.** MailHog's Jim rolls against
  behavioural chances (`DisconnectChance`, `RejectSenderChance`) as floats.
  Mailpit's Chaos gives each trigger — Sender, Recipient, Authentication — an
  **SMTP error code** and a **whole percentage**, and returns that code. The
  roll is seeded from the address, so the same address always meets the same
  fate at the same setting.

Note the singular/plural split in the paths: `/api/v1/messages` is the list
(summaries, read state, bulk delete), `/api/v1/message/{id}` is the read (the
bodies, the parts, the analyses). That is Mailpit's, not a typo. The two shapes
differ on purpose — the list gives a `Snippet` and an attachment *count*, the
read gives `Text`, `HTML` and the attachment *list*.

Unlike MailHog, Mailpit can also **send**: `POST /api/v1/send` accepts a message
over HTTP and it lands in the same mailbox, which is where Chaos bites.

Nine messages are captured, chosen to give the query language and the analyses
something to bite on:

| Message | Shape | Notable |
|---------|-------|---------|
| order confirmation | text + HTML | PDF attachment, tagged `billing;receipt`, **unread** |
| password reset | text only | recovery code `770412`, tagged `auth` |
| May digest | text + HTML | inline logo, four links (**two fail**), `List-Unsubscribe` |
| promo blast | text + HTML | **spam**, score 6.839, **untagged** |
| incident notice | text + HTML | two `Cc` recipients, tagged `ops;incident` |
| invoice | text only | CSV attachment, a **`Bcc`** the headers do not show |
| partner welcome | text + HTML | **four html-check failures**, a `301` link |
| bounce | text only | empty return path, **untagged** |
| deploy notice | text only | from the sync bot, tagged `ops;deploy` |

Nothing is invented here: every endpoint is one Mailpit serves. Releases and
sends are recorded in the `RuntimeStats` counters on `/api/v1/info`, which is
how a client verifies them.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`mailpit_api_postman_collection.json` for the runnable collection.
