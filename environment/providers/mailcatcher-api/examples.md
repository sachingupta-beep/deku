# MailCatcher Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$MAILCATCHER_API_URL`; responses are verbatim (long lists elided
with `…`).

## The list

```bash
curl -s "$MAILCATCHER_API_URL/messages"
```
```json
[
  {"id": 1, "sender": "<billing@orbit-labs.com>",
   "recipients": ["<amelia.ortega@orbit-labs.com>"],
   "subject": "Your Orbit Labs order ORD-2026-4417 is confirmed",
   "size": "1280", "type": "multipart/mixed",
   "created_at": "2026-05-28T09:14:12+00:00"},
  {"id": 2, "sender": "<billing@orbit-labs.com>",
   "recipients": ["<finance@orbit-labs.com>", "<audit@orbit-labs.com>"],
   "subject": "Invoice INV-2026-0417 for Orbit Labs",
   "size": "956", "type": "multipart/mixed",
   "created_at": "2026-05-27T14:30:55+00:00"},
  "…"
]
```

Plain **integer** ids. Angle-bracketed addresses, because MailCatcher reports
the envelope. `size` is a **string** and the keys are snake_case — Ruby
serialised them that way.

## The read, and the `formats` array

```bash
curl -s "$MAILCATCHER_API_URL/messages/1.json"
```
```json
{
  "id": 1,
  "sender": "<billing@orbit-labs.com>",
  "recipients": ["<amelia.ortega@orbit-labs.com>"],
  "subject": "Your Orbit Labs order ORD-2026-4417 is confirmed",
  "size": "1280",
  "type": "multipart/mixed",
  "created_at": "2026-05-28T09:14:12+00:00",
  "cc": [],
  "formats": ["source", "html", "plain"],
  "attachments": [
    {"cid": "receipt-4417@orbit-labs.com", "type": "application/pdf",
     "filename": "receipt-ORD-2026-4417.pdf", "size": 120,
     "is_attachment": true,
     "href": "/messages/1/parts/receipt-4417@orbit-labs.com"}
  ]
}
```

`formats` is the contract: it says which extensions will work. Message 5 offers
`["source", "html"]` and message 4 offers `["source", "plain"]`.

The bounce reports a real, empty return path:

```bash
curl -s "$MAILCATCHER_API_URL/messages/8.json"
```
```json
{"id": 8, "sender": "<>", "recipients": ["<status@orbit-labs.com>"],
 "subject": "Undelivered Mail Returned to Sender", "size": "598",
 "type": "text/plain", "created_at": "2026-05-21T18:12:59+00:00",
 "cc": [], "formats": ["source", "plain"], "attachments": []}
```

## The format is the extension

```bash
curl -s "$MAILCATCHER_API_URL/messages/1.plain"
curl -s "$MAILCATCHER_API_URL/messages/1.html"
curl -s "$MAILCATCHER_API_URL/messages/1.source"
curl -s "$MAILCATCHER_API_URL/messages/1.eml"
```

`.source` and `.eml` return the same bytes; `.eml` sets `message/rfc822` so a
browser downloads it. Asking for one a message does not offer says what it does
offer:

```json
{"error": "Message 4 has no html part; it offers source, plain"}
{"error": "Message 5 has no plain part; it offers source, html"}
```

An extension the API does not know at all is a 400:

```json
{"error": "'txt' is not a supported format; this message offers source, html, plain (and eml, which mirrors source)"}
```

An unknown *message* is a 404 whichever extension is used — the message is
checked before the format.

## `.html` rewrites `cid:` so the result is renderable

Message 5's stored HTML has an inline image:

```html
<img src="cid:partner-hero@orbit-labs.com" alt="Orbit Labs partners" width="600">
```

```bash
curl -s "$MAILCATCHER_API_URL/messages/5.html"
```
```html
<html><body><img src="/messages/5/parts/partner-hero@orbit-labs.com" alt="Orbit Labs partners" width="600"><h2>Welcome aboard</h2><p>Your sandbox tenant is ready and the API keys are in the partner console.</p><p><a href="https://orbit-labs.com/partners/start">Get started</a></p></body></html>
```

The `cid:` URI nothing can fetch has become a path that can be:

```bash
curl -s "$MAILCATCHER_API_URL/messages/5/parts/partner-hero@orbit-labs.com"
```
```
iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==
```

## Attachments by Content-ID

```bash
curl -s "$MAILCATCHER_API_URL/messages/1/parts/receipt-4417@orbit-labs.com"
curl -s "$MAILCATCHER_API_URL/messages/2/parts/invoice-0417@orbit-labs.com"
curl -s "$MAILCATCHER_API_URL/messages/6/parts/uptime-w21@orbit-labs.com"
```

Not an index, not a filename, not a MIME section number. Three distinguishable
404s:

```json
{"error": "Message 6 has no part with cid 'nope@orbit-labs.com'; it has orbit-logo@orbit-labs.com, uptime-w21@orbit-labs.com"}
{"error": "Message 4 has no parts"}
{"error": "Message not found"}
```

A cid that belongs to another message is unknown here too — cids are scoped to
their message.

## Delivering

```bash
curl -s -X POST "$MAILCATCHER_API_URL/messages" \
  -H 'Content-Type: application/json' \
  -d '{"sender": "monitoring@orbit-labs.com",
       "recipients": ["oncall@orbit-labs.com"],
       "subject": "Disk pressure on node-7",
       "plain": "node-7 root filesystem at 91%."}'
```
```json
{"id": 9, "sender": "<monitoring@orbit-labs.com>",
 "recipients": ["<oncall@orbit-labs.com>"],
 "subject": "Disk pressure on node-7", "size": "268", "type": "text/plain",
 "created_at": "2026-08-06T10:30:18+00:00", "cc": [],
 "formats": ["source", "plain"], "attachments": [],
 "note": "not a MailCatcher endpoint; it stands in for the SMTP delivery a mock cannot accept"}
```

`201`, the next free integer id, and a `formats` array that reflects what was
actually posted — send both bodies and it becomes
`["source", "html", "plain"]` with `type: "multipart/alternative"`. Addresses
are accepted with or without angle brackets and normalised.

Refusals:

```json
{"error": "sender is required"}
{"error": "at least one recipient is required"}
{"error": "sender 'not-an-address' is not a valid address"}
{"error": "a plain or html body is required"}
```

## Deleting, and the ids starting over

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -X DELETE "$MAILCATCHER_API_URL/messages/7"
curl -s -X DELETE "$MAILCATCHER_API_URL/messages/7"
curl -s -X DELETE "$MAILCATCHER_API_URL/messages"
curl -s "$MAILCATCHER_API_URL/messages"
```
```
204
```
```json
{"error": "Message not found"}
{"deleted": 10}
[]
```

`204` with no body is MailCatcher's answer to a successful delete — the only one
in this fleet. Deleting a message takes its parts with it, so a cid that
resolved a moment ago now 404s.

And the numbering starts again:

```bash
curl -s -X POST "$MAILCATCHER_API_URL/messages" \
  -H 'Content-Type: application/json' \
  -d '{"sender": "auth@orbit-labs.com",
       "recipients": ["rohit.bansal@orbit-labs.com"],
       "subject": "Verify your email address",
       "plain": "Your code is 482913."}'
```
```json
{"id": 1, "…": "…"}
```

## The capture summary

```bash
curl -s "$MAILCATCHER_API_URL/info"
```
```json
{"version": "0.10.0", "ruby": "ruby 3.3.6", "smtp": "0.0.0.0:1025",
 "http": "0.0.0.0:1080", "messages": 8,
 "note": "MailCatcher itself serves only the web UI at /; this summary is a convenience for the mock"}
```
