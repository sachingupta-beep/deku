# Ethara — Team Expense Approval

Build and deploy a working internal expense-approval tool from this brief. There is
no starting codebase. When you are done, a stranger must be able to open the app in
a browser, sign in through the identity provider, and exercise every role's dashboard
without hitting an error page.

---

## Overview

Ethara reimburses employees for out-of-pocket work expenses — travel, meals, client
gifts, home-office equipment. Today claims move through email, shared spreadsheets
and Slack DMs. Managers approve claims from their own reports, finance settles the
approved ones from the company account, and nobody can answer "how much did we
approve last month" without a two-hour spreadsheet exercise.

Build the system that centralises the whole flow: employees submit claims, their
managers approve or reject them, finance marks the approved ones reimbursed. Each
role sees a different dashboard tailored to what they can act on. Authentication is
done through an external identity provider so the same login works with the rest of
Ethara's tooling.

---

## User roles

Three roles, all present in the identity provider from first boot. The role a user
carries is the sole authorization signal — there is no per-user override, no team
membership beyond the manager-report relationship, no admin bypass.

| Role | Read | Write |
|---|---|---|
| `employee` | Only their own claims and their own profile | Create a claim; cancel one of their own claims while it is still `submitted` |
| `manager` | Every claim submitted by one of **their direct reports** — not their peers', not another manager's reports, not their own | Approve or reject a submitted claim from one of their direct reports; nothing else |
| `finance` | Every claim in every state | Mark an `approved` claim as `reimbursed`; nothing else |

**Data-scope rules (the heart of this task).**

- An `employee` may read `claim.id = X` only if `claim.employee_id` is their own
  employee record. Every other case is `403`, and the row must not appear in a list
  either.
- A `manager` may read or act on `claim.id = X` only if the claim's employee reports
  directly to them — that is, `claims.employee_id -> employees.manager_id ==
  manager.employee_id`. Peer managers' reports are `403` from both read and write.
  Approving another manager's report's claim through a direct API call must fail
  with `403` and must leave the claim's state untouched.
- A `manager` cannot approve their own claim, even if they route it through the API
  with their manager token — a claim's approver must be a different user from the
  claimant.
- Finance can read everything, cannot approve or reject anything, and can only
  transition an already-`approved` claim to `reimbursed`. Attempting to approve or
  reject as finance is `403`.

**Server-side enforcement.** Every authorization decision is made server-side on
the endpoint. Hiding an "Approve" button in the UI is not authorization: a direct
`POST /api/claims/{id}/approve` from an `employee` bearer token, or from a manager
whose token belongs to a different team, must be rejected with `401` or `403`, and
the underlying database row must not change.

---

## Core features

### Claim submission
An employee submits a claim with an amount in cents (integer, > 0), a currency
(three-letter ISO, always `USD` in this environment), a category (one of `travel`,
`meals`, `equipment`, `client_gifts`, `other`), a short description (1–280
characters), and an expense date not in the future. A claim starts in state
`submitted`. Amount of zero, negative amount, unknown category or a future date is
`400` — never `500`, never a silent `200`.

An employee may cancel one of their own claims while it is still `submitted`;
cancellation transitions the claim to `cancelled` and no further transitions apply.
An employee cannot cancel another employee's claim and cannot cancel a claim past
`submitted`.

### Approval
A manager approves or rejects a `submitted` claim from one of their direct reports.
Approval transitions the state to `approved` and stamps `approved_at` and
`approved_by`. Rejection transitions to `rejected` with a required reason (1–280
characters), `rejected_at` and `rejected_by`. Both transitions record the acting
user's employee id.

Once a claim is `approved`, `rejected`, `cancelled` or `reimbursed`, it may not be
approved or rejected again — a repeat call returns `409`. A `rejected` claim can
never become `approved` or `reimbursed`.

### Reimbursement
Finance moves an `approved` claim to `reimbursed`, stamping `reimbursed_at` and
`reimbursed_by`. Only `approved` claims may be reimbursed; attempting to reimburse
a `submitted`, `rejected` or `cancelled` claim returns `409` and does not mutate.

### Role dashboards
Three dashboards, one per role. The path is the same (`/`) — the payload adapts to
the caller's role.

- **Employee dashboard.** Their own submitted, approved, rejected and reimbursed
  totals; a table of their own recent claims; a "New claim" primary action.
- **Manager dashboard.** Count of claims from their reports awaiting approval;
  aggregate amount pending; a table of pending claims from their reports with a
  one-click approve / reject dialog; a small "team spend this month" tile.
- **Finance dashboard.** Count and aggregate amount of claims approved and awaiting
  reimbursement; a table of those claims across every team with a "Mark reimbursed"
  action; a "reimbursed this month" tile.

Every tile reflects true state within one request of any state transition. No
stale counts.

### Search and filter
An employee can filter their own claims by state and by category. A manager can
filter the queue of claims from their reports by state, category and claimant
name. Finance can filter across every team by state, category, claimant and
approving manager. Filters compose. Rows an actor is not entitled to read must
never appear regardless of filter.

### Auth
Authentication is delegated to the Keycloak instance at `AUTH_ISSUER_URL` using
the OIDC Authorization Code flow. The app is the OIDC client; it holds
`AUTH_CLIENT_ID` and `AUTH_CLIENT_SECRET` and performs the code exchange server
side. After a successful exchange the app issues its own **session bearer token**
that the browser and every API call use — the identity provider's ID token is
never exposed to the browser.

Because the identity provider does not expose password grant on its public client,
and because the grader is black-box HTTP, the app **also** exposes
`POST /api/auth/login` taking `{"email", "password"}` and returning
`{"access_token": "..."}`. The endpoint performs the OIDC exchange server-side —
authenticating the credentials against the Keycloak resource-owner password grant
on the confidential client — and returns the app's own session bearer token, the
same one the browser flow issues. The browser flow is a redirect; the API surface
is uniform.

Session tokens are opaque to the client, revocable on logout, and expire after 8
hours. Every mutating endpoint requires a valid bearer token.

---

## User flow

| Route | Purpose | Access |
|---|---|---|
| `/login` | Redirect to Keycloak, or a fallback email + password form | Anonymous |
| `/` | Role-aware dashboard | Any authenticated role |
| `/claims/new` | Submit a claim | `employee` |
| `/claims/mine` | An employee's own claim history with state filters | `employee` |
| `/claims/:id` | Claim detail: line items, state history, action buttons per role | Owner, that owner's manager, or finance |
| `/queue` | Manager approval queue for their reports | `manager` |
| `/reimburse` | Finance queue of approved claims awaiting settlement | `finance` |
| `/team` | Read-only view of a manager's direct reports and their current claim counts | `manager` |

**Entry and redirects.**

- Unauthenticated visitor to any protected route → redirect to
  `/login?next=<path>`; after a successful login the app resumes at `next` or `/`.
- Logout revokes the session token server-side and clears the browser session.
- An `employee` opening `/queue` or `/reimburse`, or a `manager` opening
  `/reimburse`, sees a permission-denied card. No redirect, no crash.
- An expired session mid-action clears the token, redirects to `/login?next=…`,
  and surfaces a "session expired" message on the login page.

**Journeys.**

1. **Employee submits and tracks.** `/claims/new` → fill amount, category,
   description and expense date → submit → the claim appears in `/claims/mine`
   with state `submitted`. Cancelling one before approval flips it to `cancelled`.
2. **Manager triages their queue.** `/queue` shows exactly their direct reports'
   submitted claims. Approve inline, or open the detail view and reject with a
   reason. The queue count on the dashboard drops immediately.
3. **Finance reimburses.** `/reimburse` shows every approved claim from every
   team. Marking one reimbursed flips its state, stamps `reimbursed_at`, and it
   leaves the queue.
4. **A manager peeks at a peer's queue.** The URL is guessable
   (`/claims/{id}`) — the API responds `403` and the app shows the same
   permission-denied card as any other unauthorized read.

**States.** Every list has an empty state with a specific message ("No pending
claims from your team", "No approved claims awaiting reimbursement"). Every page
has a loading skeleton. Errors are handled distinctly: network failure surfaces
an inline retry; a business-rule rejection (already-approved, non-manager, wrong
state) surfaces the specific reason from the response body; `5xx` is caught by an
error boundary and never crashes the app.

---

## UI/UX notes

Clean, dense, trustworthy operations console — an approvals inbox, not a spend
management SaaS marketing page. Light-first, calm neutrals with one confident
teal accent, data-forward tables with tabular numerals for amounts. Reference
points: Linear's typographic precision, the Vercel dashboard's calm neutral
palette, the tasteful data density of a good internal tool. Not flashy, not
default-Bootstrap.

**Palette.** Background `#F8FAFC`, surface `#FFFFFF`, primary text `#0F172A`,
muted text `#64748B`, primary / CTA `#0F766E` (hover `#115E59`), border
`#E2E8F0`, danger `#DC2626`, success `#16A34A`, warning `#D97706`. Dark mode
supported and persisted per user: background `#0B1120`, surface `#111827`,
primary `#14B8A6`.

**Claim-state colors**, applied consistently to chips, table cells and dashboard
badges: submitted slate `#64748B`, approved teal `#0F766E`, rejected danger
`#DC2626`, cancelled muted `#94A3B8`, reimbursed success `#16A34A`.

**Type.** Inter for UI, JetBrains Mono for amounts and claim ids. Heading scale
30 / 24 / 20 / 16, body 14 with 16 for emphasis, caption 12. Line height 1.5
body, 1.25 headings. **Tabular numerals in every amount column and metric tile**
so approved / pending totals line up.

**Shape.** 8px radius default, 12px on cards, full-round pills for state chips.
1px hairline borders. Cards carry a soft two-layer shadow; modals a larger one.

**Density.** Balanced-to-dense. Tables are the primary surface: 40px rows,
sticky header, right-aligned amount column, hover highlight, state as a coloured
pill. Amounts are always shown with currency and two decimal places.

**Components.** Buttons in primary, secondary, ghost, destructive and link
variants at 28 / 36 / 44px. Approve / reject are placed side-by-side; reject is
destructive-styled and always opens a confirmation dialog because the reason is
required. Toasts top-right, colour-coded, auto-dismissing.

**Motion.** 150ms standard, 250ms entering, `cubic-bezier(0.16, 1, 0.3, 1)`. No
bounce. Respect `prefers-reduced-motion`.

**Responsive and accessible.** Breakpoints at 640 / 768 / 1024 / 1280, touch
targets at least 44×44. WCAG AA contrast on body text, full keyboard navigation,
a visible focus ring on every interactive element, a text fallback for every
chip so state is never conveyed by colour alone.

---

## Technical requirements

- **Frontend:** React 18 with Vite, TypeScript in strict mode, Tailwind CSS v3.
  TanStack Query for server state, React Router v6, React Context for the
  session, react-hook-form for forms, Zod for shared request and response
  schemas. A typed `fetch` wrapper injects the session bearer token and handles
  `401` by redirecting to `/login?next=…`.
- **Backend:** Python 3.12 with FastAPI on Uvicorn. REST over JSON, OpenAPI at
  `/docs`. Pydantic v2 for settings and request/response models. State
  transitions are synchronous and transactional; no background jobs.
- **Database:** PostgreSQL, reached via the `DATABASE_URL` environment variable
  present in this environment. SQLAlchemy 2.0 with typed `Mapped[...]` models,
  Alembic for forward-only migrations.
- **Identity provider:** Keycloak, reached via `AUTH_ISSUER_URL` with the
  confidential client credentials in `AUTH_CLIENT_ID` and `AUTH_CLIENT_SECRET`.
  A realm named `ethara` is pre-provisioned with the seeded users below and the
  three roles as realm roles. The app is responsible for verifying tokens
  server-side against the issuer's JWKS.
- **Sessions:** the app issues its own opaque session bearer token after OIDC
  exchange, stored server-side keyed by a random 256-bit id, revocable on
  logout. Do not hand the raw Keycloak ID or access token to the browser.
- **Health:** `GET /api/health` returns `200` once the API and its database are
  ready.
- **Logging:** structured JSON to stdout.

Use only the libraries named here plus their direct dependencies. Do not
introduce a second database, cache, queue, object store, email provider or
alternate identity provider — the only backing services available in this
environment are the PostgreSQL instance at `DATABASE_URL` and the Keycloak
instance at `AUTH_ISSUER_URL`, and reaching for anything else is a contract
violation.

---

## Data model

Four tables. All timestamps are UTC and all amounts are integer cents.

**Every seeded account uses the password `deku-demo-pw-2026`.** It is benchmark fixture data, not a secret. Hash it as normal; the exact literal must work at login, and it must be written into `/app/USER_README.md` alongside each account so a grader can sign in.


**`users`** — the app's shadow of an OIDC subject. Auto-increment id; the
Keycloak `sub` claim (unique, indexed); email (unique, indexed); display name;
role (`employee`, `manager` or `finance`); FK to `employees.id`; created
timestamp. A row is upserted on first successful login.

**`employees`** — the reporting hierarchy. Id; unique indexed employee code (for
example `ETH-00042`); display name; email (unique, indexed); nullable FK
`manager_id -> employees.id` (a manager's own `manager_id` may be `NULL` if they
report directly to the CEO); indexed department; created and updated timestamps.
An employee row exists for every user; a manager's report is any employee whose
`manager_id` equals that manager's employee id.

**`claims`** — the ledger. Id; FK `employee_id -> employees.id` (the claimant,
indexed); amount in integer cents (`> 0`); currency (three-letter ISO);
category; description (1–280 chars); expense date (not future); state
(`submitted`, `approved`, `rejected`, `cancelled`, `reimbursed`); nullable FK
`approved_by -> employees.id`; nullable `approved_at`; nullable FK `rejected_by`
and `rejected_at` and `rejection_reason`; nullable FK `reimbursed_by` and
`reimbursed_at`; created and updated timestamps.

**`claim_events`** — append-only state history. Id; FK `claim_id`; the previous
and new state; FK `actor_id -> employees.id`; nullable note (the rejection
reason, for a `reject` event); created timestamp.

**Constraints — the business rules live here.**

- `claims`: `CHECK (amount > 0)`, `CHECK (state IN ('submitted','approved',
  'rejected','cancelled','reimbursed'))`, `CHECK (expense_date <= CURRENT_DATE)`.
- `claims`: a **partial unique index enforcing that a claim can only be marked
  reimbursed once** — `UNIQUE (id) WHERE state = 'reimbursed'` is implied by
  primary key uniqueness, and the transition guard is enforced by an application
  check inside the same transaction that updates the row.
- `employees`: unique email, unique employee code, FK self-reference on
  `manager_id`.
- `claim_events`: append-only — no `UPDATE` or `DELETE` from the application
  layer.

**Seed data.** The database must be seeded deterministically on first start.

- **Finance (1):** `finance@ethara.ai`, employee code `ETH-00001`, department
  `Finance`, no manager.
- **Managers (2):** `mia.manager@ethara.ai` (`ETH-00010`, department
  `Engineering`, no manager) and `mark.manager@ethara.ai` (`ETH-00011`,
  department `Sales`, no manager).
- **Employees, at least two per manager (4 minimum):**
  `ellen@ethara.ai` (`ETH-00100`, manager Mia), `evan@ethara.ai` (`ETH-00101`,
  manager Mia), `ethan@ethara.ai` (`ETH-00102`, manager Mark),
  `emma@ethara.ai` (`ETH-00103`, manager Mark).
- **Seeded claims, at least one of each state, per claimant Ellen (Mia's
  report):**
  - one `submitted` at `1250` cents, category `meals`
  - one `approved` at `9900` cents, category `travel`, approved by Mia
  - one `rejected` at `50000` cents, category `client_gifts`, rejected by Mia
    with reason "Above per-item limit"
  - one `reimbursed` at `4200` cents, category `equipment`, approved by Mia,
    reimbursed by finance
- **A `submitted` claim from Mark's report Ethan** at `3300` cents, category
  `meals` — used to prove cross-manager isolation.
- Corresponding rows in Keycloak's `ethara` realm: every seeded user exists with
  a stable password documented in `/app/USER_README.md`, and each is assigned
  exactly one of the realm roles `employee`, `manager` or `finance`.

Seeding is idempotent — restarting the app must not duplicate rows.

---

## Constraints

- Single tenant. No org or workspace concept beyond the manager-report tree.
- No delegation, no substitute approvers, no bulk approve.
- No attachments, no receipt upload, no OCR.
- No email notifications and no external network calls at runtime beyond the
  Keycloak issuer and the Postgres database.
- No password reset UI in the app itself — Keycloak owns credentials. The
  seeded passwords are the only credentials this environment carries.
- Responsive web only. No native mobile app.

---

## Deployment contract

Non-negotiable. The application is graded through a browser and over HTTP by a
process that knows nothing about your code, so the following must hold exactly.

- The app is reachable at the URL in `APP_PUBLIC_URL`, served on the port in
  `APP_PUBLIC_PORT` (`4173`). **Never** hardcode the port — read it from the
  environment.
- The REST API is served on that **same origin** under the `/api` prefix.
- The app starts from this environment image with **no manual steps**. The
  healthcheck must go green on its own.
- Default login credentials — the seeded Keycloak passwords for finance, both
  managers and every seeded employee — are written to **`/app/USER_README.md`**
  so a grader can sign in.
- Reserve the directories `.browser_screenshots/` and `.downloads/` at the app
- **The backing services are ALREADY RUNNING.** Every service named in this brief
  is started for you before your session begins and is reachable at the environment
  variable given for it. **Do not download, install, compile or start your own copy
  of any of them.** Read the address from the environment; never hardcode it and
  never substitute a local file, an embedded database, or your own instance of the
  same product. The grader inspects the service at that address — an app that
  writes to a different instance scores zero no matter how well it works.
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
- The **only** backing services are the PostgreSQL instance at `DATABASE_URL`
  and the Keycloak instance at `AUTH_ISSUER_URL`. No other backend, no other
  identity provider, no email service, no cache, no queue, no object store.
- No persistent volumes, no fixed container names, no custom networks. The app
  must tear down and re-run cleanly.

### API shapes

Everything internal is your choice. These request and response shapes are not —
they are the interface the grader holds you to. Field names are exact.

| Endpoint | Request body | Success | On success returns |
|---|---|---|---|
| `POST /api/auth/login` | `{"email": str, "password": str}` | `200` | `{"access_token": str, ...}` — the app's own session bearer token, issued after the server-side OIDC exchange |
| `POST /api/auth/logout` | — | `200` or `204` | — |
| `GET /api/me` | — | `200` | `{"id": int, "email": str, "role": "employee"\|"manager"\|"finance", "employee_id": int}` |
| `POST /api/claims` | `{"amount_cents": int, "currency": "USD", "category": str, "description": str, "expense_date": "YYYY-MM-DD"}` | `200` or `201` | the created claim including `id` and `state = "submitted"` |
| `GET /api/claims` | query: `state`, `category`, `claimant_id`, `manager_id` | `200` | JSON array of claims the caller is entitled to read |
| `GET /api/claims/{id}` | — | `200` | the claim; `403` if the caller cannot read it |
| `POST /api/claims/{id}/cancel` | — | `200` | the updated claim; `403` if not the claimant; `409` if the claim is not `submitted` |
| `POST /api/claims/{id}/approve` | — | `200` | the updated claim; `403` if the caller is not the claimant's direct manager; `409` if the claim is not `submitted` |
| `POST /api/claims/{id}/reject` | `{"reason": str}` | `200` | the updated claim; `403` if not the direct manager; `409` if not `submitted` |
| `POST /api/claims/{id}/reimburse` | — | `200` | the updated claim; `403` if the caller is not `finance`; `409` if the claim is not `approved` |
| `GET /api/dashboard` | — | `200` | role-aware summary object |
| `GET /api/health` | — | `200` | — |

Rules:

- Every business-rule violation returns a `4xx` with a message naming the
  reason. Never a `5xx`, never a silent `200`.
- Every endpoint except `POST /api/auth/login` and `GET /api/health` requires a
  valid bearer token; anonymous callers get `401`.
- Authorization on every claim-scoped endpoint is enforced against the
  caller's role **and** the caller's relationship to the claim's employee — a
  hidden UI button is not authorization.
- List endpoints return a JSON array at the top level.

---

## Definition of done

The app is deployed and healthy; every feature above works through the browser;
every state transition is guarded by both role and relationship; a peer
manager cannot approve another manager's report's claim through a direct API
call; an `employee` session cannot approve, reject or reimburse anything through
the API; finance cannot approve or reject; the dashboards match actual database
state; and the OIDC login flow works end to end with the seeded users.

Test your own work in a browser before you finish.
