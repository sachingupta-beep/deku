# Ethara — Event RSVP & Confirmations

Build and deploy a working web application from this brief. There is no starting
codebase. When you are done, a stranger must be able to open the app in a browser,
sign up, RSVP to an event, and receive a confirmation email — without hitting an
error page.

---

## Overview

A small event-hosting app. An **organiser** creates events with a fixed capacity,
publishes them, and watches the guest list fill up. **Guests** sign up, browse
the upcoming events, and RSVP `yes` or `no`. Every `yes` RSVP triggers a real
confirmation email to the guest. The organiser sees, per event, the guest list
and how many spots remain.

The product is deliberately small — one entity, one workflow, one integration.
The integration is the interesting part: the confirmation email must be sent
over real SMTP, to a real mail server the environment runs, that is inspected
out-of-band by the grader.

---

## User roles

| Role | Can do |
|---|---|
| `organiser` | Create, update and cancel their own events. See every RSVP on their events. Cannot modify events they did not create. |
| `guest` | Browse published events. RSVP `yes` or `no`, and change their answer. See their own RSVPs. Cannot edit another guest's RSVP, cannot see the organiser's admin views, cannot modify events. |

Authorization is enforced **server-side on every mutating endpoint**. Hiding a
button in the UI is not authorization: a direct API call from a `guest` session
to another guest's RSVP, or to any organiser-only endpoint, must be rejected
with `401` or `403`.

Signup is open — anyone can create a `guest` account. `organiser` accounts are
seeded; there is no self-serve organiser signup.

---

## Core features

### Event management (organiser)
Create, update and cancel events. An event has a title, description, a start
time (future, UTC), a location string, and an integer `capacity` between 1 and
500. An event is either `draft`, `published` or `cancelled`. Only `published`
events are visible to guests.

- Cancelling an event moves it to `cancelled` and prevents any new RSVPs.
  Existing `yes` RSVPs on a cancelled event stay on the record but no longer
  count against capacity.
- An organiser can only touch their own events. Attempting to modify another
  organiser's event must be rejected with `403`.

### Guest signup and browsing
Open signup with email + password. Once signed in, a guest sees a list of every
`published` event with future start time, plus each event's remaining capacity.

### RSVP
A guest RSVPs `yes` or `no` to an event, and may change their answer any number
of times. The organiser sees the current guest list per event and the count of
remaining spots.

- **One RSVP per (guest, event).** A guest submitting a second RSVP for an
  event they already answered updates the existing row rather than creating a
  second one. Duplicate submission must never double-count against capacity.
- **Capacity is a hard cap.** When an event has `capacity` `yes` RSVPs, the
  next guest trying to RSVP `yes` must be rejected with a `4xx` error naming
  capacity as the reason. This must hold under two guests trying to grab the
  last seat at the same time — exactly one succeeds, the other is rejected.
  The guarantee must hold at the database level, not only in application
  logic.
- **Changing `yes` to `no` frees a slot.** Immediately, on the next request. A
  guest previously blocked by capacity may then RSVP `yes` successfully.
- A guest may not modify another guest's RSVP under any circumstances.

### Confirmation email
Every `yes` RSVP — new, or changed from `no` — sends a confirmation email to
the guest's registered address over **real SMTP** to the mail server this
environment provides at `SMTP_HOST:SMTP_PORT`. The email must:

- Be addressed **to the RSVPing guest's email**, no cc, no bcc.
- Have a subject that begins with the exact prefix `RSVP confirmed:` followed
  by a space and the event title — for example
  `RSVP confirmed: Summer Meetup 2026`.
- Have a non-empty body that references the event title.

The email is a real integration, not a UI affordance. An in-process no-op, an
in-memory list, a logged line, or any stand-in the app itself controls is a
contract violation. There will be no API key for any third-party mail vendor;
use the SMTP credentials the environment gives you and nothing else.

Changing an existing `yes` to `no` **does not** send an email. Only
transitions into `yes` do.

### Organiser guest list
Per event, the organiser can see every `yes` RSVP with the guest's name and
email, the total `yes` count, and the remaining capacity. Guests cannot access
this view.

### Auth
Email and password login returning a stateless JWT (HS256, 8 hour expiry),
sent by the client as `Authorization: Bearer <token>`. Passwords stored
hashed, never in plain text. Two seeded accounts (below) plus open guest
signup. No password reset, no SSO.

---

## User flow

| Route | Purpose | Auth |
|---|---|---|
| `/login` | Email + password login | No |
| `/signup` | Create a guest account | No |
| `/` | Guest — list of upcoming published events with remaining capacity | Any signed-in role |
| `/events/:id` | Event detail with the RSVP control | Any signed-in role |
| `/my-rsvps` | Guest — the events this guest has RSVP'd to | `guest` |
| `/organiser/events` | Organiser — the organiser's own events | `organiser` |
| `/organiser/events/new` | Organiser — create an event | `organiser` |
| `/organiser/events/:id` | Organiser — event edit, cancel, and guest list | `organiser` |

**Entry and redirects.**

- Unauthenticated visitor to any protected route → redirect to
  `/login?next=<path>`.
- Login success → the `next` param if present, otherwise `/` for guests and
  `/organiser/events` for organisers.
- Token expired mid-action → clear the token, redirect to
  `/login?next=<current>`, surface a "session expired" message.
- A `guest` navigating to any `/organiser/*` route → blocked with an error,
  no redirect.

**Journeys.**

1. **Guest RSVPs to an event.** Sign in → home → click an event with capacity
   left → RSVP `yes` → the app confirms visibly, and a confirmation email
   lands in the guest's inbox.
2. **Guest changes their mind.** `/my-rsvps` → change a `yes` to `no` → the
   count on that event drops by one, and no further email is sent.
3. **Capacity fills up.** A guest RSVPs `yes` to an event with one spot left
   → success. The next guest RSVPing `yes` to the same event → a clear
   rejection message naming capacity as the reason, no email sent.
4. **Organiser creates an event.** `/organiser/events/new` → fill the form →
   publish → the event appears on the guest home page.
5. **Organiser reviews attendance.** `/organiser/events/:id` → see every
   `yes` RSVP with name and email, and the remaining capacity.
6. **Organiser cancels an event.** From the event page → cancel → the event
   disappears from the guest home page. No new RSVPs accepted.

**States.** Every list has an empty state with a clear message. Every page
has a loading state — skeletons, not a blank screen. Errors are handled
distinctly and never crash the app: network failure shows an inline retry;
`404` shows a not-found card with a back link; business-rule rejections
surface the specific reason (capacity full, event cancelled, event in the
past). Successful mutations confirm visibly.

---

## UI/UX notes

Calm, friendly, consumer-facing — a small community app, not an enterprise
dashboard. Light-first with one warm coral accent, generous whitespace, clear
typographic hierarchy, cards over dense tables. Reference points: the
restraint of Partiful, the typographic clarity of Notion's public pages, and
the calm neutrals of Linear's marketing site. Not flashy, not
default-Bootstrap.

**Palette.** Background `#FDFCF9`, surface `#FFFFFF`, primary text `#1C1917`,
muted text `#78716C`, primary / CTA `#E85A4F` (hover `#D14A40`), border
`#E7E5E4`, danger `#B91C1C`, success `#15803D`, warning `#B45309`, accent
`#0891B2`. Dark mode toggle persisted per user: background `#111827`, surface
`#1F2937`, text `#F3F4F6`, muted `#9CA3AF`, primary `#F97066`, border
`#374151`.

**RSVP-status colors** used consistently across chips and pills: `yes`
success green `#15803D`, `no` slate `#78716C`, remaining-capacity accent
`#0891B2`, capacity-full danger `#B91C1C`.

**Type.** Inter for UI, Fraunces (or a similar serif) for event titles on
the detail page. Heading scale 30 / 24 / 20 / 16, body 15 with 17 for event
titles in the list, caption 12. Line height 1.55 body, 1.2 headings.

**Shape.** 10px radius default, 16px on event cards, full-round pills for
RSVP chips. 1px hairline borders. Cards carry a single soft shadow; modals a
larger one.

**Density.** Airy on the guest side, denser on the organiser guest list. The
event list uses cards, not a table. The organiser guest list uses a table
with 40px rows and a sticky header.

**Components.** Buttons in primary, secondary, ghost and destructive
variants at 32 / 40 / 48px. Inputs with a 2px coral focus ring, labels above,
errors below in danger color. Toasts top-right, auto-dismissing, color-coded.
Modals centered with a blurred backdrop, closable with Escape, and a confirm
step before cancelling an event.

**Motion.** 150ms standard, 250ms entering, `cubic-bezier(0.16, 1, 0.3, 1)`.
Respect `prefers-reduced-motion`.

**Responsive and accessible.** Breakpoints at 640 / 768 / 1024 / 1280, touch
targets at least 44×44. WCAG AA: contrast at least 4.5:1 for body text, full
keyboard navigation, visible focus ring on every interactive element,
meaningful labels on icon-only buttons.

---

## Technical requirements

- **Frontend:** React 18 with Vite, TypeScript in strict mode, Tailwind CSS
  v3. TanStack Query for server state, React Context for the session, React
  Router v6, react-hook-form for forms, Zod for shared request and response
  shapes. A typed `fetch` wrapper injects the JWT and handles `401`.
- **Backend:** Python 3.12 with FastAPI on Uvicorn. REST over JSON, with
  OpenAPI at `/docs`. Pydantic v2 for settings and request/response models.
  RSVP create/update and capacity enforcement are synchronous and
  transactional — no background jobs and no queues.
- **Database:** **PostgreSQL**, reached via the `DATABASE_URL` environment
  variable already present in this environment. SQLAlchemy 2.0 with typed
  `Mapped[...]` models, Alembic for forward-only migrations.
- **Email:** **Mailpit** — a real SMTP server, already running in this
  environment. Send via the `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` and
  `SMTP_PASS` environment variables using Python's standard `smtplib` (or
  any real SMTP client). Do not add a mail vendor SDK, do not queue, do not
  batch — send synchronously from the RSVP request path.
- **Auth:** in-app, no third-party identity provider. Email and password,
  JWT HS256 with an 8 hour expiry, bcrypt password hashing via passlib.
- **Health:** `GET /health` returns success once the API is ready.
- **Logging:** structured logging to stdout.

Use only the libraries named here plus their direct dependencies. Do not
introduce a second database, cache, queue, object store, identity provider
or mail vendor — the only backing services available in this environment
are the PostgreSQL instance at `DATABASE_URL` and the SMTP server at
`SMTP_HOST`, and reaching for anything else is a contract violation.

---

## Data model

Four tables. All timestamps are UTC.

**Every seeded account uses the password `deku-demo-pw-2026`.** It is benchmark fixture data, not a secret. Hash it as normal; the exact literal must work at login, and it must be written into `/app/USER_README.md` alongside each account so a grader can sign in.


**`users`** — login accounts. Auto-increment id; unique indexed email;
bcrypt password hash; role (`organiser` or `guest`); display name; created
timestamp.

**`events`** — id; FK to `users.id` naming the owning organiser; title
(indexed); description text; start time (timestamptz, future at create
time); location string; capacity integer with a
`CHECK (capacity BETWEEN 1 AND 500)`; status (`draft`, `published`,
`cancelled`) defaulting to `draft`; created and updated timestamps.

**`rsvps`** — the RSVP ledger. Id; FK to `events.id`; FK to `users.id`
naming the guest; response (`yes` or `no`); created and updated timestamps.

**`email_log`** — a durable audit of every confirmation the app dispatched
over SMTP. Id; FK to `rsvps.id`; recipient email (indexed); subject; sent-at
timestamp. Written **only after** `smtplib` reports the send succeeded. The
existence of a row here is not proof of delivery — the mail server's inbox
is — but its absence proves the app never called `smtplib`.

**Constraints — the business rules live here.**

- `rsvps`: a **unique index on (event_id, user_id)**. This is what makes
  duplicate submission update the row rather than double-counting.
  Application checks alone are not sufficient under concurrent submissions.
- `events`: index on (status, start_time) for the guest home page query.
- `users`: unique email.

**Seed data.** The database must be seeded deterministically on first start:

- One organiser: `organiser@ethara.ai`, display name `Ethara Events`.
- One guest: `guest@ethara.ai`, display name `Amit Roy`.
- One `published` event titled **`Summer Meetup 2026`**, owned by the
  seeded organiser, with **capacity 3**, a future start time (at least 7
  days ahead of the seed date), and location `Ethara HQ, Bangalore`.

Seeding must be idempotent — restarting the app must not duplicate rows.

---

## Constraints

- Single tenant. No org / workspace concept.
- No waitlist, no ticketing, no payments.
- No calendar integration, no ICS export, no reminders.
- No email vendor SDK. SMTP only, via the environment's `SMTP_*` variables.
- No external network calls at runtime. Everything the app needs is in this
  environment.
- Confirmation emails are synchronous from the RSVP request path. If the
  send fails, the request must fail; do not "eventually consistent" this —
  a `yes` RSVP without a confirmation email is not a `yes` RSVP.
- Responsive web only. No native mobile app.

---

## Deployment contract

Non-negotiable. The application is graded through a browser and over HTTP
by a process that knows nothing about your code, so the following must hold
exactly.

- The app is reachable at the URL in the `APP_PUBLIC_URL` environment
  variable, served on the port in `APP_PUBLIC_PORT` (`4173`). Never
  hardcode the port — read it from the environment.
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
  grader can sign in.
- Reserve the directories `.browser_screenshots/` and `.downloads/` at the
  app root and leave them empty.
- The frontend is served as a **production build behind a preview
  server** — never a dev server.
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
- Use **only** the PostgreSQL instance at `DATABASE_URL` and the SMTP
  server at `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS`. No other
  backing service.
- No persistent volumes, no fixed container names, no custom networks. The
  app must tear down and re-run cleanly.

### API shapes

Everything internal is your choice. These request and response shapes are
not — they are the interface the grader holds you to. Field names are
exact.

| Endpoint | Request body | Success | On success returns |
|---|---|---|---|
| `POST /api/auth/signup` | `{"email": str, "password": str, "name": str}` | `200` or `201` | the created user including `id` and `role: "guest"` |
| `POST /api/auth/login` | `{"email": str, "password": str}` | `200` | `{"access_token": str, ...}` |
| `GET /api/events` | — | `200` | JSON array of `published` future events, each including `id`, `title`, `start_time`, `location`, `capacity`, and `remaining` |
| `GET /api/events/{id}` | — | `200` | the event including `capacity` and `remaining` |
| `POST /api/events` | `{"title","description","start_time","location","capacity","status"}` | `200` or `201` | the created event including `id` |
| `PATCH /api/events/{id}` | any subset of the create body plus `status` | `200` | the updated event |
| `POST /api/rsvps` | `{"event_id": int, "response": "yes"` or `"no"}` | `200` or `201` | the created or updated RSVP including `id` and `response` |
| `GET /api/rsvps/me` | — | `200` | JSON array of the caller's RSVPs |
| `GET /api/events/{id}/rsvps` | — | `200` | organiser-only; JSON array of `{"user_id","name","email","response"}` for `yes` RSVPs |
| `GET /api/health` | — | `200` | — |

Rules:

- Every business-rule violation returns a `4xx` with a message naming the
  reason (capacity full, event cancelled, event in the past, RSVP not
  yours). Never a `5xx`, never a silent `200`.
- Every endpoint except `POST /api/auth/signup`, `POST /api/auth/login` and
  `GET /api/health` requires a valid bearer token; anonymous callers get
  `401` or `403`.
- `POST /api/events`, `PATCH /api/events/{id}` and
  `GET /api/events/{id}/rsvps` are organiser-only; a `guest` token gets
  `401` or `403`.
- A `guest` can only modify RSVPs they own. Any attempt to modify another
  guest's RSVP returns `403`.
- List endpoints return a JSON array at the top level.

---

## Definition of done

The app is deployed and healthy; a guest can sign up, RSVP, and receive a
real confirmation email at their signup address; capacity is a hard cap
that holds under two concurrent RSVPs racing for the last seat; changing a
`yes` to `no` frees a slot; a `guest` cannot see the organiser's guest
list; and duplicate RSVPs update rather than double-count.

Test your own work in a browser before you finish. Send yourself a
confirmation email and open Mailpit to verify it arrived.
