# MailHog Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$MAILHOG_API_URL`; responses are verbatim (long lists elided with
`…`). Message ids used below:

```bash
export VERIFY='3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example'   # plain text
export INCIDENT='Kf7bVpQnRtLmYcXwEjH0Zg@mailhog.example' # multipart/alternative
export DIGEST='Wq3ZmNbXcVpLkJhGfDsA2Q@mailhog.example'   # multipart/mixed + CSV
export INVOICE='Bn5XcTgYuIoPlKjHgFdSa1@mailhog.example'  # multipart/mixed + PDF
export BOUNCE='Hg2FdSaPoIuYtReWq9MnBv@mailhog.example'   # multipart/report
```

## Health and capture state

```bash
curl -s "$MAILHOG_API_URL/health"
```
```json
{"status": "ok"}
```

```bash
curl -s "$MAILHOG_API_URL/api/v1/info"
```
```json
{"version": "v1.0.1", "smtp": "0.0.0.0:1025", "http": "0.0.0.0:8025",
 "hostname": "mailhog.example", "storage": "memory", "messages": 8,
 "jim": "disabled"}
```

## The same inbox, two shapes

`v1` is a bare array:

```bash
curl -s "$MAILHOG_API_URL/api/v1/messages"
```
```json
[{"ID": "3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example", "…": "…"}, "…"]
```

`v2` wraps it:

```bash
curl -s "$MAILHOG_API_URL/api/v2/messages?limit=1"
```
```json
{
  "total": 8,
  "count": 1,
  "start": 0,
  "items": [
    {
      "ID": "3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example",
      "From": {"Relays": null, "Mailbox": "auth", "Domain": "orbit-labs.com",
               "Params": ""},
      "To": [{"Relays": null, "Mailbox": "rohit.bansal",
              "Domain": "orbit-labs.com", "Params": ""}],
      "Content": {
        "Headers": {
          "Content-Type": ["text/plain; charset=UTF-8"],
          "Date": ["Tue, 26 May 2026 08:12:04 +0000"],
          "From": ["auth@orbit-labs.com"],
          "To": ["rohit.bansal@orbit-labs.com"],
          "Message-ID": ["<3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example>"],
          "MIME-Version": ["1.0"],
          "Received": ["from kratos.orbit-labs.com by mailhog.example (MailHog)\r\n\tid 3PLnAiuwhrDzFsyOBpp7Nw; Tue, 26 May 2026 08:12:04 +0000"],
          "Return-Path": ["<auth@orbit-labs.com>"],
          "Subject": ["Please verify your email address"]
        },
        "Body": "Hi Rohit,\n\nPlease verify your Orbit Labs account by entering the following code:\n\n  482913\n…",
        "Size": 146,
        "MIME": null
      },
      "Created": "2026-05-26T08:12:04.418293471Z",
      "MIME": null,
      "Raw": {"From": "auth@orbit-labs.com",
              "To": ["rohit.bansal@orbit-labs.com"],
              "Data": "Return-Path: <auth@orbit-labs.com>\r\nReceived: …",
              "Helo": "kratos.orbit-labs.com"}
    }
  ]
}
```

Note the address shape. `From` and `To` are `Path` objects, not strings, because
MailHog reports the SMTP envelope. `To` also carries the `Cc` and `Bcc`
recipients — what the server actually saw.

## Download the raw source

```bash
curl -s "$MAILHOG_API_URL/api/v1/messages/$VERIFY/download"
```
```
Return-Path: <auth@orbit-labs.com>
Received: from kratos.orbit-labs.com by mailhog.example (MailHog)
	id 3PLnAiuwhrDzFsyOBpp7Nw; Tue, 26 May 2026 08:12:04 +0000
Date: Tue, 26 May 2026 08:12:04 +0000
From: auth@orbit-labs.com
To: rohit.bansal@orbit-labs.com
Subject: Please verify your email address
Message-ID: <3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Hi Rohit,
…
```

Served as `message/rfc822` with a `.eml` filename.

## Pull one attachment out of a multipart message

```bash
curl -s "$MAILHOG_API_URL/api/v1/messages/$DIGEST/mime/part/1/download"
```
```
c2VydmljZSx1cHRpbWUsaW5jaWRlbnRzCmFwaSw5OS45OCwxCnN0YXR1cywxMDAuMDAsMApiaWxsaW5nLDk5LjkxLDIK
```

Served as `text/csv` with `Content-Disposition: attachment;
filename="uptime-2026-w21.csv"`. Part 0 of the same message is the plain-text
body.

Out-of-range and non-multipart requests are distinguishable:

```json
{"error": "Message has 2 MIME parts; 9 is out of range"}
{"error": "Message has no MIME parts"}
{"error": "Part index must be an integer"}
```

## Search

`containing` searches the subject and the *rebuilt* body, so it reaches inside a
multipart message:

```bash
curl -s "$MAILHOG_API_URL/api/v2/search?kind=containing&query=INC-4417"
```
```json
{"total": 1, "count": 1, "start": 0,
 "items": [{"ID": "Kf7bVpQnRtLmYcXwEjH0Zg@mailhog.example",
            "From": {"Mailbox": "status", "Domain": "orbit-labs.com", "…": "…"},
            "To": [{"Mailbox": "subscribers", "…": "…"},
                   {"Mailbox": "oncall", "…": "…"}],
            "Content": {"Headers": {"Subject": ["[Orbit Status] Investigating elevated API latency"], "…": "…"}, "…": "…"},
            "…": "…"}]}
```

`kind=to` matches the `Cc` and `Bcc` too, because those are recipients as far as
the envelope is concerned. An unsupported `kind` or a missing `query` is 400.

## Jim, the chaos monkey

Off by default, and saying so is the API's job:

```bash
curl -s "$MAILHOG_API_URL/api/v2/jim"
```
```json
{"error": "Jim is not enabled"}
```
```
HTTP 404
```

Switch him on:

```bash
curl -s -X POST "$MAILHOG_API_URL/api/v2/jim" \
  -H 'Content-Type: application/json' \
  -d '{"AcceptChance": 0.99, "RejectRecipientChance": 0.4,
       "DisconnectChance": 0.0}'
```
```json
{"DisconnectChance": 0.0, "AcceptChance": 0.99, "LinkSpeedAffected": 0.1,
 "LinkSpeedMin": 1024, "LinkSpeedMax": 10240, "RejectSenderChance": 0.05,
 "RejectRecipientChance": 0.4, "RejectAuthChance": 0.05}
```

Now the same settings give two different outcomes, because the roll is seeded
from the recipient:

```bash
curl -s -X POST "$MAILHOG_API_URL/api/v1/messages/$INCIDENT/release" \
  -H 'Content-Type: application/json' \
  -d '{"Host": "smtp.orbit-labs.com", "Port": "587",
       "Email": "oncall@orbit-labs.com"}'
```
```json
{"error": "Jim rejected the recipient oncall@orbit-labs.com"}
```

```bash
curl -s -X POST "$MAILHOG_API_URL/api/v1/messages/$VERIFY/release" \
  -H 'Content-Type: application/json' \
  -d '{"Host": "smtp.orbit-labs.com", "Port": "587",
       "Email": "rohit.bansal@orbit-labs.com"}'
```
```json
{"released": true, "messageId": "3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example",
 "to": "rohit.bansal@orbit-labs.com", "via": "smtp.orbit-labs.com:587",
 "note": "no mail is actually delivered by the mock; the release is recorded and readable at /api/v1/releases"}
```

Raising `DisconnectChance` to 0.2 changes *which* refusal `oncall` gets:

```json
{"error": "Jim disconnected the session before DATA"}
```

Validation is enforced:

```json
{"error": "AcceptChance must be between 0 and 1"}
{"error": "LinkSpeedMin must not exceed LinkSpeedMax"}
```

## Release

Credentials inline, or by naming a configured server:

```bash
curl -s "$MAILHOG_API_URL/api/v2/outgoing-smtp"
```
```json
{"orbit-relay": {"Name": "orbit-relay", "Save": true,
                 "Email": "status@orbit-labs.com",
                 "Host": "smtp.orbit-labs.com", "Port": "587",
                 "Username": "status@orbit-labs.com",
                 "Password": "orbit-relay-app-password",
                 "Mechanism": "PLAIN"},
 "acme-partner": {"Host": "smtp.acme-partner.com", "Port": "465",
                  "Mechanism": "CRAM-MD5", "…": "…"}}
```

```bash
curl -s -X POST "$MAILHOG_API_URL/api/v1/messages/$DIGEST/release" \
  -H 'Content-Type: application/json' \
  -d '{"Name": "orbit-relay", "Email": "subscribers@orbit-labs.com"}'
```

Refusals name the problem:

```json
{"error": "Host and Port are required to release a message"}
{"error": "Unsupported auth mechanism 'OAUTHBEARER'; use PLAIN or CRAM-MD5"}
{"error": "PLAIN authentication requires a Username"}
{"error": "Unknown outgoing SMTP server 'not-a-relay'"}
```

Releases are recorded so they can be checked afterwards:

```bash
curl -s "$MAILHOG_API_URL/api/v1/releases"
```
```json
{"releases": [{"id": "841e60cc-ab60-4cfd-9ca3-004ca0ca7c72",
               "messageId": "3PLnAiuwhrDzFsyOBpp7Nw@mailhog.example",
               "host": "smtp.orbit-labs.com", "port": "587",
               "recipient": "rohit.bansal@orbit-labs.com",
               "mechanism": "none", "username": "",
               "releasedAt": "2026-08-06T…"}]}
```

## Emptying the capture

```bash
curl -s -X DELETE "$MAILHOG_API_URL/api/v1/messages/$BOUNCE"
```
```
HTTP 200
```

Deleting it again is 404. `DELETE /api/v1/messages` empties everything and
reports the count:

```json
{"deleted": 7}
```

After which both APIs agree the inbox is empty — `[]` from v1, and
`{"total": 0, "count": 0, "start": 0, "items": []}` from v2.
