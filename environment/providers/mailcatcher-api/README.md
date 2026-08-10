# mailcatcher-api

Mock of MailCatcher — a Ruby/Sinatra app, and the smallest surface of the five
mail services in this fleet.

Run it as its own container (build context is the environment root):
```
docker compose up -d mailcatcher-api
curl http://localhost:8125/health
curl http://localhost:8125/messages
curl http://localhost:8125/messages/1.json
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir mailcatcher-api --port 8125
```

**The minimalism is the identity, not an omission.** There is no search, no
tags, no read state, no mailboxes, no sessions and no settings. Everything
hangs off `/messages`. What it does have is distinctive, and all of it is
modelled:

- **The format is a file extension, not a path segment.** `/messages/1.json`,
  `.html`, `.plain`, `.source`, `.eml`. Which extensions will work for a given
  message is advertised in its `formats` array, so a client checks that rather
  than guessing — asking for `.html` on a text-only message is a 404 that names
  what the message *does* offer. An unrecognised extension is a 400 that does
  the same.
- **Ids are plain integers** in arrival order: `1`, `2`, `3`. Every other
  capture tool here uses an opaque token, a 22-character id, a timestamp or a
  GUID. And after `DELETE /messages` the numbering **starts again at 1**.
- **Addresses come back angle-bracketed**, as the SMTP envelope wrote them:
  `"<billing@orbit-labs.com>"`. A null return path is the literal `"<>"`, which
  the seeded bounce has.
- **Attachments are addressed by Content-ID** — `/messages/{id}/parts/{cid}` —
  not by index, filename or MIME section number. A cid that belongs to another
  message is still unknown here, and the 404 lists the ones that are real.
- **`.html` rewrites `cid:` references** to those part URLs. That is the whole
  point of the endpoint: what comes back is directly renderable, with every
  inline image pointing somewhere fetchable instead of at a `cid:` URI nothing
  can resolve.

Keys are snake_case (`created_at`, `is_attachment`) and `size` is a **string**,
because Ruby serialised them that way.

Eight messages, chosen so the `formats` array actually varies:

| Id | Formats | Notable |
|----|---------|---------|
| 1 | source, html, plain | order confirmation, **PDF** by cid |
| 2 | source, plain | invoice, **CSV** by cid, two recipients |
| 3 | source, html, plain | incident INC-4417, has a `Cc` |
| 4 | source, plain | password reset, code `770412` |
| 5 | source, **html only** | partner welcome, **inline image via `cid:`** |
| 6 | source, html, plain | May digest, an inline logo **and** a CSV |
| 7 | source, plain | deploy notice from the sync bot |
| 8 | source, plain | bounce, sender is the literal **`<>`** |

One endpoint is marked in its own response as a mock addition:
`POST /messages` stands in for the SMTP delivery a mock cannot accept — and it
is what makes the id scheme and the `formats` array demonstrable.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`mailcatcher_api_postman_collection.json` for the runnable collection.
