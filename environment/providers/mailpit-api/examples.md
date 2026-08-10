# Mailpit Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$MAILPIT_API_URL`; responses are verbatim (long lists elided with
`…`). Message ids used below:

```bash
export ORDER='iAfZuC9x4Pq2wKvNhLmRtY'    # text + HTML, PDF attachment
export RESET='Rn7KdWpXsE3zQjBvUyTaHc'    # text only
export DIGEST='Lm4TgVhNpZxCwQdRsFuKb8'   # inline logo, four links
export PROMO='Yb9PxJqWnMkTvRzHcAeDs2'    # spam
export INCIDENT='Ct5NrXbGmVpLdWyQzKfJh7' # two Cc recipients
export INVOICE='Da3ZkFpQwSxEvRtYuIoLm1'  # CSV attachment, a Bcc
export WELCOME='Ek6MbNcVxZaSdFgHjKlPq4'  # four html-check failures
```

## Two shapes for the same message

The list gives a snippet and an attachment *count*:

```bash
curl -s "$MAILPIT_API_URL/api/v1/messages?limit=1"
```
```json
{
  "total": 9, "unread": 4, "count": 1, "messages_count": 9, "start": 0,
  "tags": ["auth", "billing", "deploy", "incident", "marketing",
           "newsletter", "ops", "partners", "receipt"],
  "messages": [
    {
      "ID": "iAfZuC9x4Pq2wKvNhLmRtY",
      "MessageID": "20260528091412.a91f3c7d@billing.orbit-labs.com",
      "Read": false,
      "From": {"Name": "Orbit Labs Billing", "Address": "billing@orbit-labs.com"},
      "To": [{"Name": "Amelia Ortega", "Address": "amelia.ortega@orbit-labs.com"}],
      "Cc": [], "Bcc": [],
      "ReplyTo": [{"Name": "Orbit Labs Support", "Address": "support@orbit-labs.com"}],
      "Subject": "Your Orbit Labs order ORD-2026-4417 is confirmed",
      "Created": "2026-05-28T09:14:12.804Z",
      "Tags": ["billing", "receipt"],
      "Size": 1657, "Attachments": 1,
      "Snippet": "Hi Amelia, Thanks for your order. ORD-2026-4417 is confirmed and the receipt is attached as a PDF. O..."
    }
  ]
}
```

The read gives the bodies and the attachment *list* — note the `Bcc` the
rendered mail would never show:

```bash
curl -s "$MAILPIT_API_URL/api/v1/message/$INVOICE"
```
```json
{
  "ID": "Da3ZkFpQwSxEvRtYuIoLm1",
  "MessageID": "20260525110344.1c84f065@billing.orbit-labs.com",
  "Read": true,
  "From": {"Name": "Orbit Labs Billing", "Address": "billing@orbit-labs.com"},
  "To": [{"Name": "", "Address": "finance@orbit-labs.com"}],
  "Cc": [],
  "Bcc": [{"Name": "", "Address": "audit@orbit-labs.com"}],
  "ReplyTo": [],
  "ReturnPath": "bounces@orbit-labs.com",
  "Subject": "Invoice INV-2026-0417 for Orbit Labs",
  "Date": "2026-05-25T11:03:44Z",
  "Tags": ["billing"],
  "Text": "Invoice INV-2026-0417\n\nPeriod: 2026-05-01 to 2026-05-31\n…",
  "HTML": "",
  "Size": 1009,
  "ListUnsubscribe": {"Header": "", "Links": [], "HeaderPost": "", "Errors": ""},
  "Inline": [],
  "Attachments": [
    {"PartID": "2", "FileName": "invoice-INV-2026-0417.csv",
     "ContentType": "text/csv", "ContentID": "", "Size": 208}
  ]
}
```

## Search is a query language

```bash
curl -s "$MAILPIT_API_URL/api/v1/search?query=is:unread"                    # 4
curl -s "$MAILPIT_API_URL/api/v1/search?query=tag:billing"                  # 2
curl -s "$MAILPIT_API_URL/api/v1/search?query=has:attachment"               # 2
curl -s "$MAILPIT_API_URL/api/v1/search?query=addressed:helena.park@orbit-labs.com"
curl -s "$MAILPIT_API_URL/api/v1/search?query=%22elevated+api+latency%22"
curl -s "$MAILPIT_API_URL/api/v1/search?query=after:2026-05-25+before:2026-05-28"
curl -s "$MAILPIT_API_URL/api/v1/search?query=orbit+-tag:ops"
curl -s "$MAILPIT_API_URL/api/v1/search?query=tag:billing+has:attachment+is:read"
```

Results use the same envelope as the list, with `messages_count` giving the
number that matched.

Errors say what was expected rather than just refusing:

```json
{"error": "unknown search prefix 'sender'; expected one of from, to, cc, bcc, reply-to, addressed, subject, message-id, tag, before, after, is, has"}
{"error": "unknown is: value 'banana'; expected one of read, unread, tagged, untagged, attachment"}
{"error": "before: expects a YYYY-MM-DD date, got 'yesterday'"}
{"error": "query is required"}
```

## Reading a message changes it

```bash
curl -s "$MAILPIT_API_URL/api/v1/search?query=is:unread" | jq .messages_count   # 4
curl -s "$MAILPIT_API_URL/api/v1/message/$ORDER" > /dev/null
curl -s "$MAILPIT_API_URL/api/v1/search?query=is:unread" | jq .messages_count   # 3
```

Set it back in bulk — an empty `IDs` applies to every message:

```bash
curl -s -X PUT "$MAILPIT_API_URL/api/v1/messages" \
  -H 'Content-Type: application/json' \
  -d '{"IDs": ["'$INCIDENT'"], "Read": false}'
```
```json
{"updated": 1, "read": false}
```

## Tags

```bash
curl -s "$MAILPIT_API_URL/api/v1/tags"
curl -s -X PUT "$MAILPIT_API_URL/api/v1/tags" \
  -H 'Content-Type: application/json' \
  -d '{"IDs": ["Gp8WqErTyUiOpAsDfGhZx5"], "Tags": ["bounce", "ops"]}'
curl -s -X PUT "$MAILPIT_API_URL/api/v1/tags/receipt" \
  -H 'Content-Type: application/json' -d '{"Name": "receipts"}'
curl -s -X DELETE "$MAILPIT_API_URL/api/v1/tags/receipts"
```
```json
{"updated": 1, "tags": ["bounce", "ops"]}
{"renamed": 1, "from": "receipt", "to": "receipts"}
{"removed": 1, "tag": "receipts"}
```

A newly-set tag is searchable immediately with `tag:bounce`. An invalid tag is
refused:

```json
{"error": "invalid tag 'not/valid'; tags may contain letters, digits, spaces, dashes, dots and underscores"}
```

## html-check

```bash
curl -s "$MAILPIT_API_URL/api/v1/message/$WELCOME/html-check"
```
```json
{
  "Platforms": {"outlook": ["windows", "macos"],
                "gmail": ["desktop-webmail", "android"],
                "apple mail": ["macos", "ios"],
                "yahoo! mail": ["desktop-webmail"],
                "thunderbird": ["macos"]},
  "Total": {"Nodes": 7, "Tests": 4, "Supported": 75.0, "Partial": 3.12,
            "Unsupported": 21.88},
  "Warnings": [
    {
      "Slug": "css-background-image-linear-gradient",
      "Title": "linear-gradient()",
      "Description": "The gradient is dropped entirely; always set a solid background-color first so the panel is not left transparent.",
      "Category": "css", "Tags": ["css", "background"], "NotesByNumber": {},
      "Results": [
        {"Family": "Outlook", "Platform": "windows", "Version": "2019",
         "Support": "no", "NotesByNumber": ""},
        {"Family": "Outlook", "Platform": "macos", "Version": "16.78",
         "Support": "partial", "NotesByNumber": ""},
        {"Family": "Gmail", "Platform": "desktop-webmail", "Version": "",
         "Support": "yes", "NotesByNumber": ""},
        "…"
      ],
      "Score": {"Found": 1, "Supported": 75.0, "Partial": 12.5,
                "Unsupported": 12.5}
    },
    "… css-border-radius, css-display-flex, css-gap …"
  ]
}
```

The order confirmation trips nothing and comes back clean:

```json
{"Platforms": {"…": "…"},
 "Total": {"Nodes": 16, "Tests": 0, "Supported": 100.0, "Partial": 0.0,
           "Unsupported": 0.0},
 "Warnings": []}
```

A message with no HTML part is 400:

```json
{"error": "message does not contain an HTML part"}
```

## link-check

```bash
curl -s "$MAILPIT_API_URL/api/v1/message/$DIGEST/link-check"
```
```json
{
  "Errors": 2,
  "Links": [
    {"URL": "https://cdn.orbit-labs.example/assets/hero-may.png",
     "StatusCode": 0,
     "Status": "dial tcp: lookup cdn.orbit-labs.example: no such host"},
    {"URL": "https://orbit-labs.com/changelog/2026-05", "StatusCode": 200,
     "Status": "200 OK"},
    {"URL": "https://orbit-labs.com/unsubscribe?t=9f14c73e", "StatusCode": 200,
     "Status": "200 OK"},
    {"URL": "https://orbit-labs.com/webinar/june", "StatusCode": 404,
     "Status": "404 Not Found"}
  ]
}
```

A DNS failure has no HTTP status at all, so Mailpit reports `StatusCode 0` with
the resolver's message. `follow=true` resolves a redirect to its target:

```bash
curl -s "$MAILPIT_API_URL/api/v1/message/$WELCOME/link-check"
curl -s "$MAILPIT_API_URL/api/v1/message/$WELCOME/link-check?follow=true"
```
```json
{"Errors": 0, "Links": [{"URL": "https://orbit-labs.com/partners/start",
                         "StatusCode": 301, "Status": "301 Moved Permanently"}]}
{"Errors": 0, "Links": [{"URL": "https://orbit-labs.com/partners/getting-started",
                         "StatusCode": 200, "Status": "200 OK"}]}
```

## sa-check

```bash
curl -s "$MAILPIT_API_URL/api/v1/message/$PROMO/sa-check"
```
```json
{
  "Error": "", "IsSpam": true, "Score": 6.839,
  "Rules": [
    {"Score": 1.506, "Name": "SUBJ_ALL_CAPS",
     "Description": "Subject is all capitals"},
    {"Score": 1.274, "Name": "RDNS_NONE",
     "Description": "Delivered to internal network by a host with no rDNS"},
    {"Score": 1.181, "Name": "URG_BIZ", "Description": "Contains urgent matter"},
    {"Score": 1.104, "Name": "MONEY_PERCENT",
     "Description": "Lots of money and a percentage"},
    "… SPF_SOFTFAIL, DKIM_ADSP_NXDOMAIN, HTML_FONT_SIZE_HUGE, HTML_MESSAGE …"
  ]
}
```

The order confirmation is negative (`-0.2`) and a message with no rule hits
returns `{"Error": "", "IsSpam": false, "Score": 0.0, "Rules": []}`.

## Chaos

```bash
curl -s "$MAILPIT_API_URL/api/v1/chaos"
```
```json
{"Sender": {"ErrorCode": 451, "Probability": 0},
 "Recipient": {"ErrorCode": 451, "Probability": 0},
 "Authentication": {"ErrorCode": 535, "Probability": 0}}
```

Arm one trigger and the same setting gives two outcomes, because the roll is
seeded from the address:

```bash
curl -s -X PUT "$MAILPIT_API_URL/api/v1/chaos" \
  -H 'Content-Type: application/json' \
  -d '{"Recipient": {"ErrorCode": 451, "Probability": 50}}'

curl -s -X POST "$MAILPIT_API_URL/api/v1/send" \
  -H 'Content-Type: application/json' \
  -d '{"From": {"Email": "noor.aziz@orbit-labs.com"},
       "To": [{"Email": "priya.raman@orbit-labs.com"}], "Subject": "roll 2"}'
```
```json
{"error": "chaos: recipient priya.raman@orbit-labs.com rejected",
 "smtpErrorCode": 451}
```

```bash
curl -s -X POST "$MAILPIT_API_URL/api/v1/send" \
  -H 'Content-Type: application/json' \
  -d '{"From": {"Email": "noor.aziz@orbit-labs.com"},
       "To": [{"Email": "helena.park@orbit-labs.com"}], "Subject": "roll 68"}'
```
```json
{"ID": "kN4RyEqtR1n4Wz6lW9Dbzj"}
```

The SMTP code is not an HTTP status, so it travels in the body and the request
itself fails with 400. Validation is enforced:

```json
{"error": "Recipient.Probability must be a whole percentage between 0 and 100"}
{"error": "Sender.ErrorCode must be an SMTP error code between 400 and 599"}
{"error": "unknown trigger 'Greeting'; expected one of Sender, Recipient, Authentication"}
```

## Sending

```bash
curl -s -X POST "$MAILPIT_API_URL/api/v1/send" \
  -H 'Content-Type: application/json' \
  -d '{"From": {"Email": "noor.aziz@orbit-labs.com", "Name": "Noor Aziz"},
       "To": [{"Email": "dmitri.volkov@orbit-labs.com"}],
       "Subject": "Sandbox tenant is ready",
       "Text": "Your partner sandbox is live.", "Tags": ["partners"]}'
```
```json
{"ID": "bBRIEwdnuXIXrAvC1MtulA"}
```

The id is derived from the sender, subject and recipients, so the same payload
always produces the same id. The message lands in the mailbox and is searchable
straight away.

## Release goes through the relay rules

```bash
curl -s "$MAILPIT_API_URL/api/v1/webui"
```
```json
{"DisableDelete": false, "DisableHTMLCheck": false, "DisableSMTPLog": false,
 "HideDeleteAllButton": false, "Label": "Orbit Labs (mock)",
 "SpamAssassin": true,
 "MessageRelay": {"Enabled": true, "SMTPServer": "smtp.orbit-labs.com:587",
                  "ReturnPath": "bounces@orbit-labs.com",
                  "AllowedRecipients": "@(orbit-labs\\.com|acme-partner\\.example)$",
                  "BlockedRecipients": "^(audit|no-reply)@",
                  "OverrideFrom": "", "PreserveMessageIDs": true}}
```

```bash
curl -s -X POST "$MAILPIT_API_URL/api/v1/message/$ORDER/release" \
  -H 'Content-Type: application/json' \
  -d '{"To": ["amelia.ortega@orbit-labs.com"]}'
```
```json
{"released": true, "messageId": "iAfZuC9x4Pq2wKvNhLmRtY",
 "to": ["amelia.ortega@orbit-labs.com"], "via": "smtp.orbit-labs.com:587",
 "note": "no mail is actually relayed by the mock; the accepted count in /api/v1/info records the release"}
```

Both rules are enforced:

```json
{"error": "recipient audit@orbit-labs.com is blocked by the relay's blocked-recipients rule"}
{"error": "recipient someone@elsewhere.example is not permitted by the relay's allowed-recipients rule"}
```

## Deleting, and the counters that record it

```bash
curl -s -X DELETE "$MAILPIT_API_URL/api/v1/search?query=tag:marketing"
curl -s -X DELETE "$MAILPIT_API_URL/api/v1/messages" \
  -H 'Content-Type: application/json' -d '{"IDs": ["Gp8WqErTyUiOpAsDfGhZx5"]}'
curl -s -X DELETE "$MAILPIT_API_URL/api/v1/messages" \
  -H 'Content-Type: application/json' -d '{}'
```
```json
{"deleted": 1}
{"deleted": 1}
{"deleted": 10}
```

`DELETE /api/v1/search` removes exactly what the same query would have listed.
An empty or absent `IDs` empties the mailbox. What happened is readable back
without any endpoint being invented for it:

```bash
curl -s "$MAILPIT_API_URL/api/v1/info"
```
```json
{"Database": "/data/mailpit.db", "DatabaseSize": 32768,
 "LatestVersion": "v1.21.3", "Messages": 0, "Tags": {}, "Unread": 0,
 "Version": "v1.21.3",
 "RuntimeStats": {"Memory": 18874368, "MessagesDeleted": 12,
                  "SMTPAccepted": 16, "SMTPAcceptedSize": 11846,
                  "SMTPIgnored": 0, "SMTPRejected": 2, "Uptime": 84213}}
```
