# Ethara — Creator Subscription Billing

Build and deploy a working web application from this brief. There is no starting
codebase. When you are done, a stranger must be able to open the app in a browser,
sign up as a reader, subscribe to a creator with a paid monthly subscription, and
read that creator's paid posts. A different stranger, holding a non-subscribing
reader account, must NOT be able to read those paid posts by any means — including
by guessing an image URL.

---

## Overview

A minimal creator publishing platform with paid subscriptions. A creator writes
posts, attaches images to them, and marks each post free or subscriber-only.
Readers browse creator pages, see free posts openly, and pay a monthly
subscription to unlock a specific creator's paid posts. The creator sees their
subscriber count and monthly revenue on their own dashboard. That is the whole
product — no comments, no likes, no messaging, no discovery feed.

The interesting parts are the two integrations. Payment charges settle
asynchronously against a real payment provider; access to paid images is enforced
against a real S3-compatible object store. Neither can be faked with a `setTimeout`
or a base64-blob-in-state trick — a separate verifier interrogates the payment
provider and the bucket directly.

---

## User roles

| Role | Can do |
|---|---|
| `creator` | Sign in; create, edit and delete their own posts; upload images; set a post free or subscriber-only; view their own subscribers list and revenue. **Cannot subscribe to their own posts** — they always have access to their own content, and are never charged. |
| `reader` | Sign in; browse creator profiles; read free posts; subscribe to a creator by paying the monthly price; read that creator's paid posts while their subscription is active. **Cannot create posts.** |

Authorization is enforced **server-side on every endpoint that mutates data or
returns paid content**. Hiding a "subscribe" button or a padlock icon in the UI is
not authorization: a direct API call from a non-subscribing reader session to any
paid-post endpoint must be rejected with `401`, `403` or `404`, and a direct
request for a paid image object must not succeed.

Every reader has exactly one login. There is no anonymous browsing of paid
content, no "5 free articles a month" mechanic, no trial tier.

---

## Core features

### Posts and image attachments

A creator writes posts and attaches images to them. A post has a title, a
markdown body, zero or more image attachments, a visibility (`free` or
`subscriber_only`), a published-at timestamp, and belongs to exactly one creator.

Image uploads go to the S3-compatible object store at `STORAGE_ENDPOINT`, in the
bucket named by `STORAGE_BUCKET`, using the access-key credentials in
`STORAGE_ACCESS_KEY` and `STORAGE_SECRET_KEY`. Do not persist image bytes in the
database. Do not stand up your own file-serving directory in the app container —
the object store is the one place image bytes live.

The object key naming scheme is fixed so the grader can locate an upload it
just observed:

```
posts/{post_id}/{sha256_of_bytes}.{ext}
```

For example, `posts/42/9f2a...d0.png`. `{ext}` is one of `png`, `jpg`, `jpeg`,
`webp`, `gif`. Keys are unique; re-uploading the same bytes to the same post is a
no-op (same key, same object).

**Access-controlled reads.** A `subscriber_only` post's image bytes must not be
readable by direct URL to a non-subscriber. Two mechanisms are acceptable, and
you must pick one and be consistent:

1. The bucket is private and the app serves each authorised image request by
   streaming the object through an authenticated API endpoint (for example
   `GET /api/posts/{id}/images/{key}`), returning `401`, `403` or `404` to any
   caller who is not entitled to that post.
2. The bucket is private and the app issues short-lived presigned URLs, valid
   for at most 5 minutes, to authorised callers only — and never returns a
   presigned URL for a paid post to a non-subscriber.

An always-public bucket with paid-post images in it is a contract violation, no
matter what the API returns. The grader will attempt to fetch a paid image
without an active subscription.

Free-post images may be served publicly for simplicity — the grader will not
challenge that path.

### Subscriptions and payment

A reader subscribes to a creator by paying a fixed **monthly price of `$10.00`
in USD**, which is `1000` in integer minor units (cents). Prices, currencies and
amounts everywhere in the system are integer minor units — never floats. `$10.00`
is `1000`, not `10.00`, not `10`.

A subscription is a first-class record: `{reader_id, creator_id, status,
current_period_end, ...}`. Statuses are `pending`, `active`, `canceled`, and
`past_due`. A reader has at most one non-canceled subscription per creator at a
time.

**Payments run against the `deku-pay` provider**, an in-house, credential-free,
adversarial payment service the harness runs as a sidecar. It is a real service
with real persisted state — not a mock. The verifier queries it directly.

You have never seen the `deku-pay` API in pretraining. Its documentation is
mounted in the environment at **`/opt/deku-pay/README.md`** and its OpenAPI spec
at **`/opt/deku-pay/openapi.json`**. Read them. The relevant surface is:

- `POST /v1/charges` — create a charge. Body carries `amount`, `currency`,
  `source` (a test card token; see below), `customer_email`, and `metadata`.
  Send an **`Idempotency-Key`** header on every create. If the same key is
  replayed, the same charge must be returned rather than a duplicate.
- `GET /v1/charges/{id}` — poll a charge. It transitions from `pending` to
  either `succeeded` or `failed` **asynchronously**. Do not assume the response
  from `POST /v1/charges` is already `succeeded`.
- **Webhooks** — the provider POSTs settlement events (`charge.succeeded`,
  `charge.failed`, `charge.refunded`) to a URL you register. Delivery is
  asynchronous, may be retried, and is at-least-once. Every request carries a
  `Deku-Signature` header — an HMAC-SHA256 of the raw body with
  `PAYMENTS_WEBHOOK_SECRET`. **Verify the signature before trusting the event.**
  **Handle duplicates idempotently** — the same event delivered twice must not
  double-grant access or double-count revenue.

**Deterministic test instruments.** Use these tokens in the `source` field. They
are the only card tokens the sidecar accepts:

| Token | Behaviour |
|---|---|
| `tok_visa_ok` | Charge settles `succeeded` after a short delay |
| `tok_visa_decline` | Charge settles `failed` (declined) |
| `tok_visa_webhook_flake` | Charge succeeds; webhook is delivered twice |

**Subscription lifecycle.**

1. Reader clicks Subscribe on a creator page.
2. App creates a `pending` subscription row and a `POST /v1/charges` for `1000`
   USD, with an idempotency key derived from the pending subscription id.
3. UI shows a "pending" state while the charge settles. The reader does not
   have access yet.
4. Webhook arrives. Verify signature. If `charge.succeeded`, flip the
   subscription to `active` and set `current_period_end` to now + 30 days. If
   `charge.failed`, flip to `canceled` and surface a clear error to the reader.
5. On duplicate webhook delivery, do nothing beyond acknowledging: no second
   period extension, no second revenue count.

An `active` subscription unlocks that creator's `subscriber_only` posts and image
attachments for that reader, and only for that reader. Access to another
creator's paid posts is not granted.

Refunds and partial refunds are out of scope for this variant.

### Creator dashboard

A creator sees, on their own dashboard:

- Total active subscribers count.
- Monthly revenue in USD, from `succeeded` charges attributed to that creator
  via charge metadata.
- A list of their posts with each post's visibility.

Numbers are computed from real state on read — no caching, no denormalised
counters that can drift. The subscriber count matches `count(subscriptions
where creator_id = me and status = 'active')` exactly.

### Auth

Email and password login returning a stateless JWT (HS256, 8 hour expiry), sent
by the client as `Authorization: Bearer <token>`. Passwords stored hashed, never
in plain text. Seeded accounts (below) are the only logins — no signup, no
password reset, no SSO.

---

## User flow

| Route | Purpose | Auth |
|---|---|---|
| `/login` | Email + password login | No |
| `/` | Landing — list of seeded creators with a link to each profile | Any |
| `/c/{creator_slug}` | Creator profile: free posts open, paid posts show a subscribe CTA | Any |
| `/c/{creator_slug}/subscribe` | Subscribe flow: pick test card, confirm, wait for settlement | Reader |
| `/posts/{id}` | A single post. Paid post to non-subscriber → 403 view | Any |
| `/dashboard` | Creator's own dashboard: subscribers, revenue, posts | Creator |
| `/dashboard/posts/new` | Create a post, upload image attachments, set visibility | Creator |

**Journeys.**

1. **A reader subscribes and reads paid posts.** Sign in as
   `reader@ethara.ai` → open `/c/nova` → click a paid post → see subscribe CTA →
   subscribe with `tok_visa_ok` → see a "pending" state → after settlement the
   subscription is `active` → refresh the paid post → the post body renders and
   the image displays.
2. **A declined card grants no access.** Sign in as
   `reader2@ethara.ai` → subscribe with `tok_visa_decline` → the app surfaces
   the decline → the subscription is `canceled` (never `active`) → attempts to
   read a paid post still return `403`.
3. **A creator publishes a paid post with an image.** Sign in as
   `nova@ethara.ai` → dashboard → new post → upload an image → mark
   `subscriber_only` → publish → the image object appears in the bucket under
   `posts/{id}/...` → non-subscribers see the subscribe CTA on this post,
   subscribers see the full post.
4. **A creator watches their numbers.** Dashboard shows active-subscriber count
   and monthly revenue, both matching real state.

**States.** Every list has an empty state. Every page has a loading state.
Errors never crash the app. A pending charge shows a spinner and polls until
settlement or a 30-second timeout, whichever comes first. A declined charge
shows the decline reason.

---

## UI/UX notes

Warm, editorial, magazine-like — a reading surface first, a SaaS dashboard
second. Generous type, restrained colour, plenty of whitespace around the post
body. References: Substack's reading calm, Ghost's editorial clarity, and the
quiet precision a checkout form needs to feel trustworthy. Not a template.

**Palette.** Background `#FAFAF7` (warm off-white), surface `#FFFFFF`, primary
text `#1A1A1A`, muted `#6B6B6B`, primary / CTA `#B45309` (warm ochre, hover
`#92400E`), border `#E7E5E1`, success `#166534`, danger `#991B1B`, subscriber
badge `#B45309`. One accent, held.

**Type.** Serif for post bodies (`"Source Serif Pro", "Charter", Georgia,
serif`), sans for UI chrome (`"Inter", system-ui`). Post title 32/40, body
18/28. Dashboard numbers in tabular numerals. Long-form reading width capped
around 680px.

**Shape.** 6px radius on cards, 999px on subscribe pill CTAs. Hairline borders.
Subscribe pill is filled ochre; unsubscribe / cancel is ghost with danger text.

**Payment form.** Card-token selector as three radio pills labelled by outcome
(`Visa · ok`, `Visa · decline`, `Visa · flaky webhook`), a large price line
(`$10.00 / month`), one primary Subscribe button. Pending state is a spinner
with the words "Confirming payment…". Never a fake success while pending.

**Locked-post view.** A blurred first paragraph fade-out and a subscribe pill.
No sneaky reveal via `view-source:` — the paid body must not be delivered at
all to a non-subscriber.

**Responsive and accessible.** Breakpoints at 640 / 768 / 1024. Touch targets
44×44. WCAG AA contrast on the ochre against warm off-white. Full keyboard
navigation, visible focus rings.

---

## Technical requirements

- **Frontend:** React 18 with Vite, TypeScript in strict mode, Tailwind CSS v3.
  TanStack Query for server state, React Router v6, react-hook-form for the
  post form, react-markdown for post bodies. A typed `fetch` wrapper injects
  the JWT.
- **Backend:** Python 3.12 with FastAPI on Uvicorn. REST over JSON. Pydantic
  v2. Payments client written by hand against `/opt/deku-pay/README.md`; do
  not attempt to install a Stripe SDK or any other vendor payments SDK — none
  will work against `deku-pay` and there is no external network at runtime.
- **Database:** PostgreSQL at `DATABASE_URL`. SQLAlchemy 2.0 with typed
  `Mapped[...]` models, Alembic for forward-only migrations.
- **Object storage:** S3-compatible, addressed via `STORAGE_ENDPOINT` /
  `STORAGE_BUCKET` / `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY`. Use `boto3`
  configured with `endpoint_url = STORAGE_ENDPOINT` — do NOT hit `s3.amazonaws.com`.
- **Auth:** in-app, JWT HS256, 8-hour expiry, bcrypt hashing via passlib.
- **Health:** `GET /api/health` returns `200` once the API is ready.

Use only the libraries named here plus their direct dependencies. Do not
introduce a second database, a cache, a queue, a mail provider, an alternate
storage backend, or any external payment SDK.

---

## Data model

Six tables. All timestamps are UTC.

**Every seeded account uses the password `deku-demo-pw-2026`.** It is benchmark fixture data, not a secret. Hash it as normal; the exact literal must work at login, and it must be written into `/app/USER_README.md` alongside each account so a grader can sign in.


**`users`** — login accounts. Id, unique indexed email, bcrypt password hash,
role (`creator` or `reader`), created timestamp.

**`creators`** — id; FK to `users.id` (unique); unique indexed slug (URL-safe,
kebab-case); display name; bio; monthly price in **integer minor units** (fixed
at `1000` for every seeded creator this variant); created timestamp.

**`posts`** — id; FK to `creators.id`; title; markdown body; visibility
(`free` or `subscriber_only`); published timestamp; created and updated
timestamps. Indexed on `(creator_id, published_at desc)`.

**`post_images`** — id; FK to `posts.id`; object key (the full
`posts/{post_id}/{sha256}.{ext}` string, unique); content type; byte size;
created timestamp.

**`subscriptions`** — id; FK to readers `users.id`; FK to `creators.id`;
status (`pending` | `active` | `canceled` | `past_due`); `current_period_end`
timestamp (null while `pending`); FK to `charges.id` for the latest charge
attempt; created and updated timestamps. **Partial unique index on
`(reader_id, creator_id) where status in ('pending', 'active')`** — a reader
cannot double-subscribe to the same creator concurrently.

**`charges`** — the payments ledger. Id; provider charge id (unique indexed);
FK to `subscriptions.id`; amount (integer minor units); currency (three-letter
ISO 4217, lowercase); status (`pending` | `succeeded` | `failed` | `refunded`);
idempotency key (unique indexed); created and updated timestamps. This table
mirrors the payment provider — one row per charge attempt, so the app has its
own audit trail and duplicate webhook deliveries can be detected locally.

**Seed data.** Deterministic, idempotent — restarting the app must not
duplicate rows.

- Two creators: **Nova** (slug `nova`, `nova@ethara.ai`) and **Orion** (slug
  `orion`, `orion@ethara.ai`). Both priced at `1000` USD minor units per month.
- Three readers: `reader@ethara.ai` (non-subscribing), `reader2@ethara.ai`
  (non-subscribing), and `reader3@ethara.ai` (already `active` on Nova, for the
  authorised-read path).
- Nova has: at least two `free` posts and at least two `subscriber_only`
  posts. At least one `subscriber_only` post has at least one image
  attachment already uploaded to the bucket under the canonical key scheme.
- Orion has: at least one `free` post and at least one `subscriber_only` post.

---

## Constraints

- Single tenant. No org / team accounts.
- No comments, likes, follows, discovery feed, search, or notifications.
- No email delivery. No SMS.
- No third-party integrations beyond the two named services: `deku-pay` and
  the S3-compatible bucket at `STORAGE_ENDPOINT`.
- No external network calls at runtime.
- The app must handle the seeded volume without stalls.

---

## Deployment contract

Non-negotiable. The application is graded through a browser and over HTTP by a
process that knows nothing about your code, so the following must hold exactly.

- The app is reachable at the URL in the `APP_PUBLIC_URL` environment variable,
  served on the port in `APP_PUBLIC_PORT` (`4173`). Never hardcode the port —
  read it from the environment.
- The REST API is served on that **same origin** under the `/api` prefix.
- The app starts from this environment image with **no manual steps**. The
  healthcheck must go green on its own.
- Write the login into `/app/USER_README.md` **in this exact shape**, one field
  per line, so the grader can read it without guessing:

  ```
  Email: demo@ethara.ai
  Password: deku-demo-pw-2026
  ```

  A markdown table is also accepted, but the two lines above are the contract.
  The grader extracts only credential-shaped lines from this file; prose around
  them is ignored, so anything not in that shape is invisible to it.
- Reserve the directories `.browser_screenshots/` and `.downloads/` at the app
  root and leave them empty.
- The frontend is served as a **production build behind a preview server** —
  never a dev server.
- **The server must outlive your session.** Grading runs in a separate container
  *after* your session ends. Start the server fully detached, for example
  `setsid nohup <command> > /tmp/app.log 2>&1 < /dev/null &`, so it is not a child
  of your shell and not a session-scoped background job. A server started as an
  ordinary background job is killed the instant your session ends, and the app
  scores zero however correct it is.
- Bind to `0.0.0.0`, never `127.0.0.1` or `localhost` — the grader connects from a
  different container, so a loopback-only listener is unreachable.
- Before you finish, verify persistence yourself: confirm the listening process is
  still running with a parent that is not your shell, and that the port answers.
- **The backing services are ALREADY RUNNING.** Every service named in this brief
  is started for you before your session begins and is reachable at the environment
  variable given for it. **Do not download, install, compile or start your own copy
  of any of them.** Read the address from the environment; never hardcode it and
  never substitute a local file, an embedded database, or your own instance of the
  same product. The grader inspects the service at that address — an app that
  writes to a different instance scores zero no matter how well it works.
- Use **only** the three backing services named in this brief: PostgreSQL at
  `DATABASE_URL`, `deku-pay` at `PAYMENTS_API_URL`, and the S3-compatible
  bucket at `STORAGE_ENDPOINT`. No other backing service.
- No persistent volumes, no fixed container names, no custom networks.

### API shapes

Everything internal is your choice. These shapes are not — they are the
interface the grader holds you to. Field names are exact. Amounts are integer
minor units. Currency is lowercase three-letter ISO 4217 (`"usd"`).

| Endpoint | Request body / query | Success | Returns |
|---|---|---|---|
| `POST /api/auth/login` | `{"email": str, "password": str}` | `200` | `{"access_token": str, ...}` |
| `GET /api/health` | — | `200` | — |
| `GET /api/creators` | — | `200` | JSON array of `{"id", "slug", "display_name", "monthly_price", "currency"}` |
| `GET /api/creators/{slug}` | — | `200` | creator profile with post list; paid posts have `body` omitted for non-subscribers |
| `GET /api/posts/{id}` | — | `200` for free or entitled; `403` otherwise | the post with `title`, `body`, `images` — `body` and `images` only present when entitled |
| `POST /api/posts` | `{"title", "body", "visibility", "images": [...]}` | `200` or `201` | the created post including `id` |
| `POST /api/posts/{id}/images` | multipart `file` | `200` or `201` | `{"id", "object_key", "content_type"}` |
| `GET /api/posts/{id}/image/{image_id}` | — | `200` for entitled; `401`/`403`/`404` otherwise | image bytes with correct `Content-Type`, OR a 302 to a short-lived presigned URL |
| `POST /api/subscriptions` | `{"creator_id": int, "source": str}` | `200` or `201` | `{"id", "status": "pending" \| "active", ...}` |
| `GET /api/subscriptions/{id}` | — | `200` | `{"id", "status", "creator_id", "current_period_end", ...}` |
| `POST /api/webhooks/payments` | raw provider event body, `Deku-Signature` header | `200` for valid; `400`/`401` for bad signature | — |
| `GET /api/dashboard` | (creator token) | `200` | `{"active_subscribers": int, "monthly_revenue": int, "currency": "usd", "posts": [...]}` |

Rules:

- The subscription price is `1000` USD minor units per month. Every charge
  created by this app must be for exactly that amount and currency.
- Every business-rule violation returns a `4xx` with a message. Never a `5xx`,
  never a silent `200` on a broken flow.
- Every endpoint except `POST /api/auth/login`, `GET /api/health`, and
  `POST /api/webhooks/payments` requires a valid bearer token.
- `POST /api/webhooks/payments` requires a valid `Deku-Signature`. No token.
- Charge creation must send an `Idempotency-Key`. The same key must return the
  same charge, not create a second one.
- The app must never charge a creator for their own content — a creator has
  access to their own paid posts by identity, not by subscription.
- Paid-post `body` and `images` are entitled information. A non-subscribing
  reader hitting `GET /api/posts/{id}` for a paid post must NOT receive the
  body or the image list in the response.

### No mocks — enforced by real inspection

The `deku-pay` charge must be created against the real `deku-pay` service at
`PAYMENTS_API_URL`. The image upload must land in the real bucket at
`STORAGE_ENDPOINT`. Any of the following is a contract violation:

- An in-memory `charges` array, a fake `Payment` client, a hardcoded
  `{"status": "succeeded"}` response the app returns to itself, or any other
  stand-in the app itself controls.
- Storing image bytes on the app container's filesystem, in the database as a
  blob, or in memory. The bucket is the only place image bytes live.
- Marking a subscription `active` without a corresponding `succeeded` charge
  observable in `deku-pay`.

Do not explain in the UI how this will be detected. Just do it correctly.

---

## Definition of done

The app is deployed and healthy. A reader can subscribe, wait for settlement,
and read paid posts. A different reader with a declined card cannot. Every
paid image is inaccessible to a non-subscriber, by every route, including a
direct object URL. Duplicate webhook deliveries do not double-grant access.
The creator dashboard's numbers match the database exactly. A creator cannot
be charged for their own content.

Test your own work in a browser before you finish. Use `tok_visa_ok` to
confirm a happy path end to end; use `tok_visa_decline` to confirm the failure
path; use `tok_visa_webhook_flake` to confirm duplicate handling.
