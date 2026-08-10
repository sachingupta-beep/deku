# MailCatcher API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$MAILCATCHER_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MAILCATCHER_API_URL` | Base URL for all requests |

## The shape of the whole API

Thirteen routes, all under `/messages`. There is no search, no tags, no read
state, no mailboxes, no sessions and no settings — that is MailCatcher, not a
gap in the mock. The interesting behaviour is in how the formats work.

```bash
curl -s "$MAILCATCHER_API_URL/health"
curl -s "$MAILCATCHER_API_URL/info"
curl -s "$MAILCATCHER_API_URL/messages"
```

The list gives integer ids, angle-bracketed addresses, a `size` **string** and
snake_case keys:

```json
[{"id": 1, "sender": "<billing@orbit-labs.com>",
  "recipients": ["<amelia.ortega@orbit-labs.com>"],
  "subject": "Your Orbit Labs order ORD-2026-4417 is confirmed",
  "size": "1280", "type": "multipart/mixed",
  "created_at": "2026-05-28T09:14:12+00:00"}, "…"]
```

## Read the message, then read its `formats`

```bash
curl -s "$MAILCATCHER_API_URL/messages/1.json"
```

The read adds `cc`, `attachments` and — the important one — `formats`:

| Id | `formats` |
|----|-----------|
| 1, 3, 6 | `["source", "html", "plain"]` |
| 2, 4, 7, 8 | `["source", "plain"]` |
| 5 | `["source", "html"]` |

`source` is always available; `eml` mirrors it. Check `formats` before asking
for `.html` or `.plain`.

## The format is a file extension

```bash
curl -s "$MAILCATCHER_API_URL/messages/1.plain"
curl -s "$MAILCATCHER_API_URL/messages/1.html"
curl -s "$MAILCATCHER_API_URL/messages/1.source"
curl -s "$MAILCATCHER_API_URL/messages/1.eml"
```

`.source` and `.eml` return the same bytes; `.eml` sets `message/rfc822`.

Errors name the alternative rather than just refusing:

```json
{"error": "Message 4 has no html part; it offers source, plain"}
{"error": "Message 5 has no plain part; it offers source, html"}
{"error": "'txt' is not a supported format; this message offers source, html, plain (and eml, which mirrors source)"}
```

An unknown **message** is a 404 whichever extension is used — the message is
checked before the format:

```bash
curl -s "$MAILCATCHER_API_URL/messages/99.html"   # 404 Message not found
curl -s "$MAILCATCHER_API_URL/messages/99.txt"    # 404, not 400
```

## `.html` rewrites `cid:` references

Message 5's stored HTML contains
`<img src="cid:partner-hero@orbit-labs.com" …>`. What the endpoint serves is:

```bash
curl -s "$MAILCATCHER_API_URL/messages/5.html"
```
```html
<img src="/messages/5/parts/partner-hero@orbit-labs.com" alt="Orbit Labs partners" width="600">
```

That is the reason the endpoint exists: the HTML comes back directly
renderable, with every inline image pointing at something fetchable.

```bash
curl -s "$MAILCATCHER_API_URL/messages/5/parts/partner-hero@orbit-labs.com"
```

## Attachments by Content-ID

```bash
curl -s "$MAILCATCHER_API_URL/messages/1/parts/receipt-4417@orbit-labs.com"
curl -s "$MAILCATCHER_API_URL/messages/2/parts/invoice-0417@orbit-labs.com"
curl -s "$MAILCATCHER_API_URL/messages/6/parts/orbit-logo@orbit-labs.com"
curl -s "$MAILCATCHER_API_URL/messages/6/parts/uptime-w21@orbit-labs.com"
```

| Message | cid | File |
|---------|-----|------|
| 1 | `receipt-4417@orbit-labs.com` | `receipt-ORD-2026-4417.pdf` |
| 2 | `invoice-0417@orbit-labs.com` | `invoice-INV-2026-0417.csv` |
| 5 | `partner-hero@orbit-labs.com` | `partner-hero.png` (inline) |
| 6 | `orbit-logo@orbit-labs.com` | `orbit-logo.png` (inline) |
| 6 | `uptime-w21@orbit-labs.com` | `uptime-2026-w21.csv` |

Not an index, not a filename, not a MIME section number. A cid is **scoped to
its message** — message 6 will not answer for message 1's cid. Three
distinguishable 404s: an unknown cid lists the real ones, a message with no
parts says so, and an unknown message says that.

## Delivering

```bash
curl -s -X POST "$MAILCATCHER_API_URL/messages" \
  -H 'Content-Type: application/json' \
  -d '{"sender": "monitoring@orbit-labs.com",
       "recipients": ["oncall@orbit-labs.com"],
       "cc": ["sre@orbit-labs.com"],
       "subject": "Disk pressure on node-7",
       "plain": "node-7 root filesystem at 91%.",
       "html": "<p>node-7 root filesystem at 91%.</p>"}'
```

Answers **201** with the full read shape, so the new `id`, `type` and `formats`
are visible immediately — post both bodies and `type` becomes
`multipart/alternative` with all three formats. Addresses are accepted with or
without angle brackets and normalised on the way in.

Not a MailCatcher endpoint: it stands in for the SMTP delivery a mock cannot
accept, and the response says so.

Refusals: no `sender`, no `recipients`, a malformed address in either, and no
body at all — each 400.

## Deleting

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X DELETE "$MAILCATCHER_API_URL/messages/7"     # 204, no body
curl -s -X DELETE "$MAILCATCHER_API_URL/messages/7"   # 404 second time
curl -s -X DELETE "$MAILCATCHER_API_URL/messages"     # clears everything
```

`204` with an empty body is MailCatcher's answer to a successful delete.
Deleting a message takes its parts with it, so a cid that resolved a moment ago
404s afterwards. Clearing an empty catcher is fine.

**Ids restart.** After a clear, the next delivery is id **1** again.

## Errors

| HTTP | When |
|------|------|
| 400 | an unrecognised extension on a known message; a delivery with no `sender`, no `recipients`, a malformed address, or no body |
| 404 | an unknown message (whichever extension); a format the message does not offer; an unknown or out-of-scope cid; a message with no parts; deleting a message twice |
