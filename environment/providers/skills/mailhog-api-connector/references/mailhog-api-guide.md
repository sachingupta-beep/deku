# MailHog API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in
`$MAILHOG_API_URL`.** Responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `MAILHOG_API_URL` | Base URL for all requests |

Set the message ids once to follow the examples:

```bash
export VERIFY='3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example'
export RECOVER='9tQrKcVmXwLpZbN2eHjD4A@mailhog.example'
export INCIDENT='Kf7bVpQnRtLmYcXwEjH0Zg@mailhog.example'
export DIGEST='Wq3ZmNbXcVpLkJhGfDsA2Q@mailhog.example'
export INVOICE='Bn5XcTgYuIoPlKjHgFdSa1@mailhog.example'
export SECURITY='Mj8LkQwErTyUiOpAsDfGh3@mailhog.example'
export WELCOME='Zx4CvBnMqWeRtYuIoPaSd6@mailhog.example'
export BOUNCE='Hg2FdSaPoIuYtReWq9MnBv@mailhog.example'
```

## The message shape

MailHog captured the SMTP envelope, so addresses are objects:

```json
{"ID": "3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example",
 "From": {"Relays": null, "Mailbox": "auth", "Domain": "orbit-labs.com",
          "Params": ""},
 "To": [{"Relays": null, "Mailbox": "rohit.bansal",
         "Domain": "orbit-labs.com", "Params": ""}],
 "Content": {"Headers": {"Subject": ["…"], "Date": ["…"], "…": "…"},
             "Body": "…", "Size": 146, "MIME": null},
 "Created": "2026-05-26T08:12:04.418293471Z",
 "MIME": {"Parts": [ … ]},
 "Raw": {"From": "…", "To": ["…"], "Data": "…", "Helo": "kratos.orbit-labs.com"}}
```

`To` collects the `To`, `Cc` and `Bcc` recipients — the envelope, not the
headers. `MIME` is `null` for a single-part message and carries `Parts` for a
multipart one. `Raw.Data` is the full RFC 822 source.

## Service state

```bash
curl -s "$MAILHOG_API_URL/health"
curl -s "$MAILHOG_API_URL/api/v1/info"
curl -s "$MAILHOG_API_URL/api/v1/events?limit=5"
```

`/api/v1/info` reports the message count and whether Jim is on. `/api/v1/events`
is a snapshot — the real endpoint is a server-sent-event stream, which a mock
cannot usefully hold open, and the response says so.

## Listing

```bash
curl -s "$MAILHOG_API_URL/api/v1/messages"                    # bare array
curl -s "$MAILHOG_API_URL/api/v2/messages?start=0&limit=10"   # envelope
curl -s "$MAILHOG_API_URL/api/v1/messages/$VERIFY"
```

Newest first, as MailHog's UI shows them. The v2 envelope is
`{total, count, start, items}`.

## Downloads and MIME traversal

```bash
curl -s "$MAILHOG_API_URL/api/v1/messages/$VERIFY/download"
curl -s "$MAILHOG_API_URL/api/v1/messages/$INCIDENT/mime/part/0/download"
curl -s "$MAILHOG_API_URL/api/v1/messages/$DIGEST/mime/part/1/download"
curl -s "$MAILHOG_API_URL/api/v1/messages/$INVOICE/mime/part/1/download"
curl -s "$MAILHOG_API_URL/api/v1/messages/$BOUNCE/mime/part/1/download"
```

| Message | Part 0 | Part 1 |
|---------|--------|--------|
| `$INCIDENT` | `text/plain` | `text/html` |
| `$DIGEST` | `text/plain` | `text/csv` — `uptime-2026-w21.csv` |
| `$INVOICE` | `text/plain` | `application/pdf` — `INV-2026-0417.pdf` |
| `$BOUNCE` | `text/plain` | `message/delivery-status` |

Each part is served with its own content type and a `Content-Disposition`
filename. Errors are distinguishable: an index out of range is 404 naming the
part count, a non-multipart message is 404 `Message has no MIME parts`, and a
non-numeric index is 400.

## Search

```bash
curl -s "$MAILHOG_API_URL/api/v2/search?kind=from&query=auth@orbit-labs.com"
curl -s "$MAILHOG_API_URL/api/v2/search?kind=to&query=subscribers"
curl -s "$MAILHOG_API_URL/api/v2/search?kind=to&query=soc@orbit-labs.com"
curl -s "$MAILHOG_API_URL/api/v2/search?kind=containing&query=482913"
curl -s "$MAILHOG_API_URL/api/v2/search?kind=containing&query=INC-4417"
curl -s "$MAILHOG_API_URL/api/v2/search?kind=from&query=orbit-labs.com&start=1&limit=2"
```

| `kind` | Searches |
|--------|----------|
| `from` | the sender address |
| `to` | every recipient, including `Cc` and `Bcc` |
| `containing` | the subject and the rebuilt body, so it reaches inside multipart |

Results use the same envelope as `/api/v2/messages`, so `start` and `limit`
work. Any other `kind`, or a missing `query`, is 400.

## Jim, the chaos monkey

```bash
curl -s "$MAILHOG_API_URL/api/v2/jim"                       # 404 while off
curl -s -X POST "$MAILHOG_API_URL/api/v2/jim" \
  -H 'Content-Type: application/json' \
  -d '{"AcceptChance": 0.99, "RejectRecipientChance": 0.4,
       "DisconnectChance": 0.0}'
curl -s -X PUT "$MAILHOG_API_URL/api/v2/jim" \
  -H 'Content-Type: application/json' -d '{"DisconnectChance": 0.2}'
curl -s -X DELETE "$MAILHOG_API_URL/api/v2/jim"
```

Settings: `DisconnectChance`, `AcceptChance`, `LinkSpeedAffected`,
`RejectSenderChance`, `RejectRecipientChance`, `RejectAuthChance` (each `0..1`),
plus `LinkSpeedMin` and `LinkSpeedMax` (integers).

While Jim is off, `GET`, `PUT` and `DELETE` are all 404 — that is how a client
discovers chaos is disabled. Enabling twice is 400. A chance outside `0..1`, a
non-numeric chance, or `LinkSpeedMin > LinkSpeedMax` is 400 naming the field.

Once on, his chances apply to the **release** endpoint, with the roll seeded
from the recipient so the same address always meets the same fate:

| Recipient | Roll | At `RejectRecipientChance: 0.4` |
|-----------|------|--------------------------------|
| `oncall@orbit-labs.com` | 0.114 | rejected |
| `status@orbit-labs.com` | 0.282 | rejected |
| `subscribers@orbit-labs.com` | 0.302 | rejected |
| `rohit.bansal@orbit-labs.com` | 0.420 | let through |
| `amelia.ortega@orbit-labs.com` | 0.749 | let through |

Real MailHog reports a refused release as 500; this mock returns **400** with
the reason in the body, so the fleet harness does not read a deliberate refusal
as a broken service.

## Release

```bash
curl -s "$MAILHOG_API_URL/api/v2/outgoing-smtp"

# inline credentials
curl -s -X POST "$MAILHOG_API_URL/api/v1/messages/$RECOVER/release" \
  -H 'Content-Type: application/json' \
  -d '{"Host": "smtp.orbit-labs.com", "Port": "587",
       "Email": "jonas.pereira@orbit-labs.com",
       "Username": "status@orbit-labs.com",
       "Password": "orbit-relay-app-password", "Mechanism": "PLAIN"}'

# or a named server from the outgoing-smtp book
curl -s -X POST "$MAILHOG_API_URL/api/v1/messages/$DIGEST/release" \
  -H 'Content-Type: application/json' \
  -d '{"Name": "orbit-relay", "Email": "subscribers@orbit-labs.com"}'

curl -s "$MAILHOG_API_URL/api/v1/releases"
```

Configured servers: `orbit-relay` (`smtp.orbit-labs.com:587`, PLAIN) and
`acme-partner` (`smtp.acme-partner.com:465`, CRAM-MD5).

Refusals, each 400 naming the problem: missing `Host`/`Port`, missing `Email`,
an unknown named server, a mechanism other than `PLAIN` or `CRAM-MD5`, and a
mechanism with no `Username`. An unknown message is 404.

Nothing is delivered — the response says so, and `/api/v1/releases` records what
was released so it can be verified.

## Deleting

```bash
curl -s -X DELETE "$MAILHOG_API_URL/api/v1/messages/$SECURITY"
curl -s -X DELETE "$MAILHOG_API_URL/api/v1/messages"
```

Deleting a message removes its MIME parts too; deleting it again is 404.
Deleting everything reports the count that went.

## Errors

| HTTP | When |
|------|------|
| 400 | unsupported search `kind`, missing `query`, non-numeric part index, invalid Jim setting, enabling Jim twice, an incomplete or unsupported release, a Jim-injected refusal |
| 404 | unknown message, part index out of range, a part requested from a non-multipart message, Jim while disabled |
