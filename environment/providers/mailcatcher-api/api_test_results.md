# MailCatcher Mock API — Test Results

Base URL: `http://localhost:8125` (in docker-compose: `http://mailcatcher-api:8125`)

## Endpoints covered

| Method | Path                              | Status      |
|--------|-----------------------------------|-------------|
| GET    | /health                           | 200         |
| GET    | /info                             | 200         |
| GET    | /messages                         | 200         |
| POST   | /messages                         | 201/400     |
| DELETE | /messages                         | 200         |
| GET    | /messages/{id}.json               | 200/404     |
| GET    | /messages/{id}.html               | 200/404     |
| GET    | /messages/{id}.plain              | 200/404     |
| GET    | /messages/{id}.source             | 200/404     |
| GET    | /messages/{id}.eml                | 200/404     |
| GET    | /messages/{id}.{extension}        | 400/404     |
| GET    | /messages/{id}/parts/{cid}        | 200/404     |
| DELETE | /messages/{id}                    | 204/404     |

Collection run: **PASS 39 / WARN 23 / FAIL 0 / SKIP 0** over 62 requests. Every
WARN is an intentional error-path request, labelled `(N expected)` in the
collection, and every label matches the status the harness observed.

Thirteen rows is the whole API. That is MailCatcher: no search, no tags, no
read state, no mailboxes, no sessions, no settings. The minimalism is the
identity, and the interesting behaviour lives in how the formats work.

## The format is a file extension

`/messages/1.json` · `.html` · `.plain` · `.source` · `.eml` — and the message
tells you in advance which ones will work:

| Id | `formats` |
|----|-----------|
| 1, 3, 6 | `["source", "html", "plain"]` |
| 2, 4, 7, 8 | `["source", "plain"]` |
| 5 | `["source", "html"]` |

`source` is always there; `eml` mirrors it with a `message/rfc822` content type.
Asking for a format a message does not offer is a **404 that names what it
does**:

```json
{"error": "Message 4 has no html part; it offers source, plain"}
{"error": "Message 5 has no plain part; it offers source, html"}
```

An unrecognised extension is a **400** that does the same:

```json
{"error": "'txt' is not a supported format; this message offers source, html, plain (and eml, which mirrors source)"}
```

Route order matters here and is deliberate: the five known extensions are
declared before the catch-all `/{id}.{extension}`, so only genuinely unknown
ones fall through to it. And an unknown *message* is a 404 whichever extension
is asked for, checked before the format is.

## Integer ids, and they restart

Ids are `1`–`8`, assigned in arrival order. A delivery takes the next free
integer. After `DELETE /messages` clears the catcher, the next delivery is **id
1 again** — the collection ends by proving exactly that.

## Angle-bracketed addresses

```json
"sender": "<billing@orbit-labs.com>",
"recipients": ["<finance@orbit-labs.com>", "<audit@orbit-labs.com>"]
```

MailCatcher reports the envelope, so message 8 — a bounce — has
`"sender": "<>"`. That is a real, empty return path, not a missing field. On
the way in, `POST /messages` accepts an address with or without the brackets
and normalises it.

## Attachments by Content-ID

`/messages/{id}/parts/{cid}` — not by index, not by filename, not by MIME
section number.

| Message | cid | File |
|---------|-----|------|
| 1 | `receipt-4417@orbit-labs.com` | `receipt-ORD-2026-4417.pdf` |
| 2 | `invoice-0417@orbit-labs.com` | `invoice-INV-2026-0417.csv` |
| 5 | `partner-hero@orbit-labs.com` | `partner-hero.png` (inline) |
| 6 | `orbit-logo@orbit-labs.com` | `orbit-logo.png` (inline) |
| 6 | `uptime-w21@orbit-labs.com` | `uptime-2026-w21.csv` |

Three distinguishable 404s: an unknown cid **lists the real ones**, a message
with no parts says so, and a cid that belongs to a *different* message is
treated as unknown here — the collection asks message 6 for message 1's cid to
show it.

## `.html` rewrites `cid:` so the result is renderable

This is the reason the endpoint exists. Message 5's stored HTML contains:

```html
<img src="cid:partner-hero@orbit-labs.com" alt="Orbit Labs partners" width="600">
```

and `GET /messages/5.html` returns:

```html
<img src="/messages/5/parts/partner-hero@orbit-labs.com" alt="Orbit Labs partners" width="600">
```

The collection then fetches that exact path, so the rewrite is verified rather
than asserted. Message 6's inline logo gets the same treatment.

## Deleting

`DELETE /messages/{id}` answers **204 with no body** — MailCatcher's response,
and the only 204 in this fleet. Deleting again is 404. Deleting a message takes
its parts with it, which the collection checks by fetching a cid that was live
a moment earlier.

`DELETE /messages` clears everything and reports the count. Clearing an empty
catcher is fine.

## Seed data summary

- **Messages** (8): three with both bodies, four plain-text only, one **HTML
  only**; one with a `Cc`, one with two recipients, one with a null `<>` sender
- **Parts** (5), keyed `{messageId}#{cid}` — a PDF, two CSVs and two inline
  PNGs, across four messages
- Nothing else. There is no other seed file, because there is nothing else to
  configure.

The mail matches the rest of the fleet: the recovery code `770412` is the
authentication services', `INC-4417` is the incident the other four mail
services also captured, and the bounce is addressed to the deactivated account.

## Notes

- Messages list **oldest first**, which for integer ids is the same as id order.
- `size` is a **string** and keys are snake_case, because Ruby serialised them
  that way.
- `POST /messages` is the one mock addition and is marked in its own response;
  MailCatcher itself only accepts mail over SMTP.
- `/info` is a convenience summary — MailCatcher's `/` serves the web UI, which
  a JSON mock has nothing useful to say about.
- Mutations are held in process memory and reset on container restart.
