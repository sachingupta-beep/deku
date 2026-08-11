# Ethara — Customer Issue Queue

Build and deploy a working web application from this brief. There is no starting codebase. When you
are done, a stranger must be able to open the app in a browser, sign in as a support agent, claim an
unowned ticket from the queue, and see it become theirs while the customer who raised it receives an
email about it — without hitting an error page. The assignment must be a real row change in
PostgreSQL and the notification must be a real message delivered to Mailpit addressed to the raising
customer; a status badge the app draws for itself, or an "email sent" toast with no SMTP
conversation behind it, is not the feature.

## Overview

A support desk for an organisation whose customers report issues by name. A customer raises an
issue; it enters a shared queue owned by nobody. An agent claims it and becomes its single owner. A
supervisor can move it to a different agent. Every time ownership changes, the customer who raised
it is told by email.

The hard part: the assignment and the notification must both be real and must agree. When two agents
claim the same ticket at the same moment, exactly one assignment persists and exactly one email is
delivered.

It is deliberately not a helpdesk suite: no comments, no attachments, no reopening, no SLA timers,
no search, no auto-assignment.

## User roles

| Role | Can read | Can write |
|---|---|---|
| `customer` | tickets they raised | create a ticket. **Cannot claim, reassign or resolve** |
| `agent` | the `open` queue plus their own | claim an `open` ticket; resolve one assigned to them. **Cannot reassign, cannot touch another agent's ticket** |
| `supervisor` | every ticket | reassign or resolve any `assigned` ticket. **Cannot raise a ticket** |

Authorization is enforced **server-side on every mutating endpoint**. Hiding a button in the UI is
not authorization: a direct API call from an `agent` session to any `supervisor`-only endpoint must
be rejected with `401` or `403`, and the underlying database row must not change.

Scope is by relationship, not role alone: agent B acting on agent A's ticket is `403`, and a
customer reading another customer's ticket is `403`.

Signup is closed. These five seeded accounts are the only ones that exist:
`customer@example.com` (Dana Reyes), `customer2@example.com` (Priya Shah), `agent@example.com`
(Marco Ruiz), `agent2@example.com` (Lena Fischer), `supervisor@example.com` (Ada Whitfield).

## Core features

**Auth.** Email and password, hashed at rest. `POST /api/auth/login` returns a bearer token sent as
`Authorization: Bearer <token>` on every other request. No signup, reset or refresh.

1. Login with a seeded email and `deku-demo-pw-2026` returns the user's `role`. A wrong password is
   rejected `401` with no token.
2. A `customer` submits `title`, `body` and `priority` (`low`, `normal`, `high`); the ticket stores
   `open`, no assignee, `customer_id` the raiser. Missing or empty `title` or `body` is rejected
   `422` naming the field.
3. An `agent` or `supervisor` raising a ticket is rejected `403`.
4. `GET /api/tickets` returns a top-level JSON array, newest-first by `created_at`. An `agent` sees
   `open` tickets plus their own; a `customer` only theirs; a `supervisor` all.
5. **Claiming an `open` ticket assigns it to the claiming agent**: `status` becomes `assigned`,
   `assignee_id` that agent, persisted before any response says it succeeded. Claiming an
   already-`assigned` ticket is rejected `409` and the stored `assignee_id` does not change.
6. Two agents claiming one `open` ticket simultaneously must not both succeed — exactly one wins,
   the other is rejected `409`, the stored assignee is the winner's and never the loser's, and the
   ticket is never `assigned` with no assignee. This must hold under real concurrency, not only in
   application-level checks.
7. A `customer` calling the claim endpoint is rejected `403`.
8. A `supervisor` reassigns an `assigned` ticket to a **different** agent: `assignee_id` becomes that
   agent, `status` stays `assigned`. Naming the current holder is rejected `409`; a non-agent `422`.
9. An `agent` calling reassign is rejected `403` and the assignee does not change.
10. Every persisted assignment change delivers **exactly one** email over SMTP to the raising
    customer — on claim, and again on each reassign — to that customer only, no cc, no bcc. The
    assigned agent is not a recipient.
11. The subject begins `Ticket assigned: ` then the ticket title; for ticket `1`, exactly
    `Ticket assigned: Payment page returns 500`. The body is non-empty and names the ticket title
    and the assigned agent's name.
12. **No other transition sends mail.** Raising, resolving, and any rejected claim or reassign send
    none.
13. The assignee, or any `supervisor`, moves an `assigned` ticket to `resolved`. Resolving an `open`
    ticket is rejected `409`; `resolved` is terminal and a further transition is `409`.

## User flow

| Route | Purpose | Auth |
|---|---|---|
| `/login` | email + password sign-in | public |
| `/queue` | unowned tickets, newest-first | `agent`, `supervisor` |
| `/my-tickets` | tickets assigned to me | `agent` |
| `/all-tickets` | every ticket, any status | `supervisor` |
| `/tickets/new` | raise an issue | `customer` |
| `/tickets/:id` | ticket detail and actions | raiser, assignee or `supervisor` |

**Entry and redirects.** An unauthenticated request to a protected route redirects to `/login` with
no flash of protected data. After login the landing page is role-dependent: `customer` →
`/my-tickets`, `agent` → `/queue`, `supervisor` → `/all-tickets`. Logout clears the token. A token
expiring mid-action refuses the action, applies nothing, and returns to `/login`. A route the role
does not hold shows a not-permitted state, never the data.

**Journeys.**
1. `customer@example.com` opens `/tickets/new`, submits `Checkout button unresponsive` at priority
   `high`, and lands on its detail page showing `open` with no assignee.
2. `agent@example.com` opens `/queue` and claims `Payment page returns 500`. It leaves the queue,
   the detail shows `assigned` to Marco Ruiz, and `customer@example.com` receives one email whose
   subject begins `Ticket assigned: `.
3. `agent2@example.com` opens ticket `3`, `Login loop on mobile`, which `agent@example.com` holds.
   No claim action is offered, and a direct claim is refused with the assignee unchanged.
4. `supervisor@example.com` reassigns ticket `3` to Lena Fischer. The detail shows her, and
   `customer@example.com` receives a second email.
5. The assignee resolves their ticket: it shows `resolved`, leaves the open views, no email.

**States.** An empty queue reads "No unclaimed tickets"; an agent with nothing assigned reads
"Nothing assigned to you"; a customer with none reads "You haven't raised any issues yet". Every
page has a loading state with no layout jump. A refused action leaves the visible state unchanged
and shows an inline reason; errors never blank the page.

## UI/UX notes

A calm operations console: dense enough to scan forty rows at once, quiet enough that the only
saturated colour means "act on this". Reference points are Linear's list density and Stripe's form
restraint. Light mode is committed; dark mode is optional and not specified.

**Palette.** Background `#F7F8FA`, surface `#FFFFFF`, text `#101828`, muted `#667085`, primary/CTA
`#1F6FEB` (hover `#1A5FCC`), border `#E4E7EC`, danger `#D92D20`, success `#067647`, warning
`#B54708`, accent `#6938EF`. Status: `open` `#B54708`, `assigned` `#1F6FEB`, `resolved` `#067647`.
Priority `high` is danger-coloured text, never a filled row.

**Type.** `Inter` with system sans fallback; `ui-monospace` for ids and timestamps. H1 `28px/36px`,
H2 `20px/28px`, H3 `16px/24px`, body `14px/20px`, caption `12px/16px`. Tabular numerals where
numbers align.

**Shape.** Radius `8px` on cards and inputs, `6px` on buttons; `1px` borders `#E4E7EC`; one shadow,
`0 1px 2px rgba(16,24,40,0.06)`, on raised surfaces only. Row height `44px`, cell padding
`12px 16px`, section gap `24px`.

**Components.** Primary buttons filled `#1F6FEB`, secondary outlined, danger text-only until
confirmed. Inputs take a `2px` focus ring `#1F6FEB` at `2px` offset. Labels above fields, errors
below in `#D92D20`. Toasts bottom-right, dismissing after `4s`. Modals close on Escape and confirm
before resolving.

**Motion.** `150ms` standard, `250ms` entering, `cubic-bezier(0.16, 1, 0.3, 1)`, no bounce.
`prefers-reduced-motion` drops transitions to `0ms`.

**Responsive and accessible.** Breakpoints `640` / `768` / `1024`; below `768` the queue collapses
to stacked cards. Touch targets at least `44×44`. WCAG AA contrast `4.5:1`. Full keyboard navigation
with a visible focus ring on every interactive element, accessible labels on icon-only controls,
status never by colour alone. Layout holds at `1920x1200`, `768x1024` and `390x844`.

## Technical requirements

Frontend React 18 with TypeScript, built by Vite and served as a production build behind Vite
preview on container port `4173`. Backend Node 20 with Express under the `/api` prefix on the same
origin, so no CORS configuration and no second host. Storage is PostgreSQL, read from `DATABASE_URL`.
Mail is Mailpit over real SMTP, read from `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` and `SMTP_PASS`.
Authentication is app-implemented email and password with bearer tokens and hashed passwords; there
is no external identity provider. `GET /api/health` returns `200` once the app is ready. Request
logs go to stdout.

PostgreSQL and Mailpit are **already running** and reachable at those environment variables. Read
every host and port from the environment; never hardcode one. Do not download, install, compile or
start a copy of either.

Use only the libraries named here plus their direct dependencies. Do not introduce a second
database, cache, queue, object store, identity provider or mail vendor — the only backing services
available in this environment are PostgreSQL and Mailpit, and reaching for anything else is a
contract violation.

Every business-rule violation returns `4xx` with a JSON body naming the reason: `401`
unauthenticated, `403` wrong role or wrong relationship, `409` state conflict, `422` malformed or
missing fields, `404` unknown ticket id. Never `5xx` for a rule violation, and never a silent
success.

## Data model

Two tables. All timestamps are UTC.

**Every seeded account uses the password `deku-demo-pw-2026`.** It is benchmark fixture data, not a
secret. Hash it as normal; the exact literal must work at login, and it must be written into
`/app/USER_README.md` alongside each account so a grader can sign in.

**`users`** — `id` integer primary key; `email` text, unique and case-insensitive; `password_hash`
text; `name` text; `role` text, one of `customer`, `agent`, `supervisor`; `created_at` timestamp.

**`tickets`** — `id` integer primary key; `title` text, non-empty; `body` text, non-empty;
`priority` text, one of `low`, `normal`, `high`; `status` text, one of `open`, `assigned`,
`resolved`; `customer_id` referencing `users.id`, the raiser, which never changes after creation;
`assignee_id` referencing `users.id`, nullable; `created_at`, `assigned_at` and `resolved_at`
timestamps, the last two nullable. The queue's age column and the per-status counts are computed on
read, not stored.

These properties must hold of the running system:

- `assignee_id` is null exactly when `status` is `open`. A ticket is never `assigned` without an
  assignee, and never `open` with one.
- An `open` ticket is claimed at most once. Two simultaneous claims of the same ticket produce
  exactly one success and one rejection, and the stored assignee is the winner's — never the
  loser's, never both. This must hold under concurrent requests, not merely in application-level
  checks.
- Every persisted change of `assignee_id` is followed by exactly one delivered email to the raising
  customer. A rejected change delivers none.
- `resolved` is terminal, and only a ticket that has an assignee can reach it.

**Seed data.** Five accounts: `customer@example.com` (Dana Reyes, `customer`), `customer2@example.com`
(Priya Shah, `customer`), `agent@example.com` (Marco Ruiz, `agent`), `agent2@example.com` (Lena
Fischer, `agent`), `supervisor@example.com` (Ada Whitfield, `supervisor`). Three tickets in this
order: id `1` `Payment page returns 500`, priority `high`, status `open`, raised by
`customer@example.com`; id `2` `Export CSV missing columns`, priority `normal`, status `open`,
raised by `customer2@example.com`; id `3` `Login loop on mobile`, priority `high`, status
`assigned`, raised by `customer@example.com` and assigned to `agent@example.com`.

Seeding must be idempotent — restarting the app must not duplicate rows.

## Constraints

Single organisation; no multi-tenancy beyond per-customer ownership. No public signup, password
reset or email verification. No comments, attachments or file uploads. No ticket editing after
creation, no deletion, no reopening a `resolved` ticket. No SLA timers, escalation rules or
auto-assignment. No search, saved filters, tags or bulk actions. No inbound mail. No realtime push —
lists update on navigation or reload. No analytics, reporting or export. No external network calls
at runtime beyond the two named backing services. No native app. The queue must stay responsive
with 500 tickets and 50 accounts.

## Deployment contract

- The app must be reachable at `APP_PUBLIC_URL`. The port mapping is
  `${APP_PUBLIC_PORT}:4173` — `4173` is the container-internal port and
  `APP_PUBLIC_PORT` is what the outside world uses. Read both from the
  environment; never hardcode either.
- The HTTP API is served on that same origin under the `/api` prefix.
- `GET /api/health` returns `200` once the app is ready.
- The app starts from the environment image with no manual steps.
- Login credentials are written to `/app/USER_README.md` **in this exact shape**,
  one field per line, so the grader can read them without guessing:

  ```
  Email: <account email>
  Password: <the seeded password>
  ```

  Repeat the pair for each account. A markdown table is also accepted, but the
  two lines above are the contract. The grader extracts only credential-shaped
  lines from this file; prose around them is ignored.
- Reserved `.browser_screenshots/` and `.downloads/` directories exist at the
  app root, empty.
- Serve a production build behind a static or preview server — never a dev
  server.
- The server must keep running after this session ends and must not be a
  child of the shell. An ordinary background job dies with its shell, and the
  app will not be running when it is next opened.
- Bind `0.0.0.0`, never `127.0.0.1` or `localhost`. A loopback-only listener
  is unreachable from outside the container.
- The backing services named in this brief are **already running** and
  reachable at their environment variables. Do not download, install, compile
  or start a copy of any of them.
- Use only the providers named in this brief. No edge functions.
- No persistent volumes, no fixed container names, no custom networks.

**API shapes.**

| Endpoint | Request body / query | Success | Returns |
|---|---|---|---|
| `POST /api/auth/login` | `{email, password}` | `200` | `{token, user:{id,email,name,role}}` |
| `GET /api/health` | — | `200` | `{status}` |
| `GET /api/tickets` | optional `?status=` | `200` | top-level JSON array of tickets |
| `POST /api/tickets` | `{title, body, priority}` | `201` | the created ticket |
| `GET /api/tickets/:id` | — | `200` | one ticket |
| `POST /api/tickets/:id/claim` | — | `200` | the updated ticket |
| `POST /api/tickets/:id/reassign` | `{assignee_id}` | `200` | the updated ticket |
| `POST /api/tickets/:id/resolve` | — | `200` | the updated ticket |

Every ticket object carries `id`, `title`, `body`, `priority`, `status`, `customer_id`,
`assignee_id`, `created_at`. Bearer auth is required on everything except `POST /api/auth/login` and
`GET /api/health`.

**No mocks.** The named providers are where the data actually lives. An in-memory array of tickets
that disappears on restart, a hardcoded `{"delivered":true}` the app returns to itself instead of an
SMTP conversation, a queued message written to a log file or a local outbox directory, or a UI badge
that reports an email nobody received — each is a contract violation however good the interface
looks. PostgreSQL and Mailpit are the fact: the app's UI and its own tables can only reflect what
lives in them, never substitute for them.

## Definition of done

A customer signs in, raises an issue, and sees it waiting with nobody on it. An agent opens the
queue, claims that issue, and it becomes theirs — and the customer who raised it has an email whose
subject begins `Ticket assigned: ` and which names the ticket. A second agent who tries to claim the
same issue does not get it, the first agent keeps it, and no second email reaches the customer. When
two agents reach for the same unclaimed issue at the same instant, one of them gets it and the other
is told it is taken. A supervisor moves an issue from one agent to another and the customer hears
about that too, once. An agent who tries to move someone else's issue cannot, and the issue stays
where it was. The assignee resolves the issue, it is finished for good, and the customer's inbox
stays quiet. Every account signs in with the password recorded in `/app/USER_README.md`, and the app
is still serving on `APP_PUBLIC_URL` long after the session that started it has ended.
