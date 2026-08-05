# Ethara — Seat Allocation & Project Mapping System

Build and deploy a working web application from this brief. There is no starting
codebase. When you are done, a stranger must be able to open the app in a browser,
log in, and use every feature described below without hitting an error page.

---

## Overview

Ethara has ~5,000 employees spread across 12 projects and 5 floors, and hiring is
continuous. There is no single source of truth for where someone sits, what project
they are on, or which desks are free — the data lives in scattered spreadsheets. HR
wastes time hunting for a desk for every new joiner, and employees cannot find their
own seat or their teammates.

Build the system that centralizes employee seating, project mapping, floor
allocation, and joining updates into one searchable application: self-service search
plus a natural-language assistant for employees, and bulk data management, smart
proximity-based seat allocation, and a live utilization dashboard for HR.

---

## User roles

| Role | Can do |
|---|---|
| `admin` (HR / Admin / Growth) | Everything: create, update and deactivate employees; manage projects and seats; allocate and release seats; bulk CSV import; read the dashboard; use the assistant |
| `employee` | Log in; read employees, seats, projects and the dashboard; use the assistant; look up their own seat. **Cannot mutate anything.** |

A project lead is an `employee` — the role has no extra privileges; they use the
projects view to see their team's seat footprint.

Authorization is enforced **server-side on every mutating endpoint**. Hiding a
button in the UI is not authorization: a direct API call from an `employee` session
to any mutating endpoint must be rejected with `401` or `403`.

---

## Core features

### Employee management
Create, list, retrieve, update and deactivate employees. An employee has an employee
code, name, email, department, job role, joining date, status, exactly one project,
and a derived seat-allocation status (allocated or pending).

- Employee email is unique. Creating a second employee with an existing email must be
  rejected with a `4xx` error, not silently accepted.
- Deactivation is a soft delete — the record stays, its status becomes inactive.

### Project mapping
12 projects. Every employee maps to exactly one active project. List employees per
project, and the seat footprint (how many seats, on which floors) per project.

The 12 projects are: **Indigo, Indreed, Mydreed, Preed, Serfy, Oreed, bedegreed,
Opreed, Serry, Kaary, Mered, Talos**.

### Seat management
Create, list, retrieve, update and delete seats. A seat has a floor (1–5), a zone
(`A` or `B`), a bay (1–15), a seat number formatted `{zone}{bay}-{index}` (for
example `B4-23`), and a status: `available`, `occupied`, `reserved`, or
`maintenance`. List available seats, filterable by floor and zone.

Seat numbers are unique within a floor and zone.

### Seat allocation engine
This is the heart of the app. Allocate a seat to an employee, and release it, under
all of the following rules:

1. An employee may hold **at most one active seat allocation** at a time.
2. A seat may hold **at most one active allocation** at a time. Two concurrent
   allocation attempts on the same seat must not both succeed — exactly one wins and
   the other is rejected. This must hold at the database level, not only in
   application logic.
3. Releasing an allocation immediately returns the seat to `available` and records
   the release time on the allocation record.
4. Only `available` seats may be allocated. Attempting to allocate a seat that is
   `occupied`, `reserved` or `maintenance` must be rejected with a `4xx` error.
5. When no specific seat is requested, the system **suggests seats near the
   employee's project team** — ranked by the zone where that project already sits,
   then the same floor, then bay clustering. If the preferred zone has no capacity,
   return available seats from alternate zones, flagged as a fallback.
6. Employee email is unique (see above).
7. Seat numbers are unique within a floor and zone (see above).
8. An inactive employee cannot be allocated a seat.

Allocation and release are synchronous and transactional. A failed allocation must
leave no partial state: no orphaned allocation row, no seat left marked `occupied`.

### New-joiner flow
HR creates an employee on a project; the system offers ranked seat suggestions near
that project's team; HR picks one and allocates. The employee can then find
themselves by search or by asking the assistant. The count of employees pending
allocation drops by one and the dashboard reflects it on the next read.

### Search and filter
Search employees by name, employee code and email. Filter by project, floor, zone,
seat status and employee status. Results must be usable against the full seeded data
volume without a visible stall.

### Dashboard
A single page showing: total employees; total, occupied, available and reserved
seats; project-wise allocation; floor-wise occupancy; and the count of new joiners
pending allocation, which links through to the filtered list of those employees.

Every tile reflects true state within one request of any allocate or release. No
stale counts.

### AI assistant
A natural-language query endpoint and a chat panel over it. It must answer, at
minimum:

- Where does a given employee sit? (floor, zone, bay, seat number, and project)
- What project is a given employee assigned to?
- Which seats are available, optionally on a given floor?
- Where does a given project's team sit?
- What is current seat utilization?

The assistant must work with **zero external dependencies** — a deterministic
rule-based intent parser is the default and must be fully functional on its own. An
LLM adapter may be added as an optional upgrade that activates only when an API key
is configured, but no API key will be present in this environment and the assistant
must still answer every query above correctly.

The assistant is read-only. It must never mutate data.

### CSV bulk import
Admins can upload a CSV of employees and allocations. Parse in-request, never
persist the file. Report how many rows were imported and how many were skipped, with
reasons. Reject files over 5 MB or of the wrong content type.

### Auth
Email and password login returning a stateless JWT (HS256, 8 hour expiry), sent by
the client as `Authorization: Bearer <token>`. Passwords stored hashed, never in
plain text. Two seeded accounts (below). No signup, no password reset, no SSO.

---

## User flow

| Route | Purpose | Auth |
|---|---|---|
| `/login` | Email + password login | No |
| `/` | Dashboard — summary tiles, project and floor charts, pending joiners | Any role |
| `/employees` | Searchable, filterable employee table; row opens a detail drawer | Any role |
| `/employees/new` | Add employee, then seat suggestions | `admin` |
| `/employees/:id` | Employee detail: profile, project, current seat, allocate / release | Any role (actions `admin`) |
| `/seats` | Seat table with floor / zone / status filters; allocate / release | Any role (actions `admin`) |
| `/projects` | Project list with per-project employee count and seat footprint | Any role |
| `/assistant` | Natural-language assistant chat panel | Any role |
| `/import` | CSV bulk import | `admin` |

**Navigation.** Fixed left sidebar (Dashboard, Employees, Seats, Projects,
Assistant, Import) with a top bar carrying search, the current user, their role, and
logout. On small screens the sidebar collapses to a hamburger drawer and tables
become horizontally scrollable.

**Entry and redirects.**

- Unauthenticated visitor to any protected route → redirect to `/login?next=<path>`.
- Login success → the `next` param if present, otherwise `/`.
- Logout → `/login`.
- Token expired mid-action → clear the token, redirect to `/login?next=<current>`,
  and surface a "session expired" message.
- An `employee` attempting an admin action → the action is blocked and an error is
  shown. No redirect.

**Journeys.**

1. **Employee finds their own seat.** Ask the assistant "Where is my seat? My email
   is amit@ethara.ai", or search their own name in `/employees` and open the detail
   drawer. Either path shows floor, zone, bay, seat number and project.
2. **HR onboards a new joiner.** `/employees/new` → fill the form → submit → the app
   presents ranked seat suggestions near that project's team → pick one → allocate →
   confirmation, and dashboard counts update.
3. **HR releases a leaver's seat.** Open the employee or the seat → Release → confirm
   in a destructive-style dialog → seat becomes available immediately.
4. **HR audits utilization.** Dashboard tiles and charts; clicking the pending-
   allocation tile opens the filtered list of employees without a seat.
5. **Anyone filters free seats on a floor.** `/seats` with floor and status filters,
   or ask the assistant.

**States.** Every list has an empty state with a clear message and a way out (for
example "clear filters"). Every page has a loading state — skeletons, not a blank
screen. Errors are handled distinctly and never crash the app: network failure shows
an inline retry; `404` shows a not-found card with a back link; `5xx` is caught by an
error boundary; business-rule rejections surface the specific reason (for example
that a particular seat is already occupied, or that reserved seats cannot be
allocated). Successful mutations confirm visibly and the affected lists refresh.

---

## UI/UX notes

Clean, dense, trustworthy enterprise dashboard — an operations console, not a toy.
Light-first, calm neutrals with one confident indigo accent, data-forward tables and
charts, generous whitespace around dense data. Reference points: Linear's typographic
precision and restraint, the Vercel dashboard's calm neutrals and crisp cards, and
the tasteful data density of a good internal tool. Not flashy, not default-Bootstrap.

**Palette.** Background `#F8FAFC`, surface `#FFFFFF`, primary text `#0F172A`, muted
text `#64748B`, primary / CTA `#4F46E5` (hover `#4338CA`), border `#E2E8F0`, danger
`#DC2626`, success `#16A34A`, warning `#D97706`, accent `#0EA5E9`. Dark mode is a
supported toggle persisted per user: background `#0B1120`, surface `#111827`, text
`#F1F5F9`, muted `#94A3B8`, primary `#6366F1`, border `#1F2937`.

**Seat-status colors**, used consistently across tables, chips and charts: available
green `#16A34A`, occupied slate `#64748B`, reserved amber `#D97706`, maintenance red
`#DC2626`.

**Type.** Inter for UI, JetBrains Mono for seat codes and employee codes. Heading
scale 30 / 24 / 20 / 16, body 14 with 16 for emphasis, caption 12. Line height 1.5
body, 1.25 headings. Tabular numerals in every table and metric tile.

**Shape.** 8px radius default, 12px on cards, full-round pills for status chips. 1px
hairline borders. Cards carry a soft two-layer shadow; modals a larger one.

**Density.** Balanced-to-dense. Tables are the primary surface: 40px rows, sticky
header, hover highlight, status as a colored pill with a text label. Metric tiles
stay airy and scannable with a large tabular number over a small muted label.

**Components.** Buttons in primary, secondary, ghost, destructive and link variants
at 28 / 36 / 44px. Inputs with a 2px indigo focus ring, labels above, errors below in
danger color. Toasts top-right, auto-dismissing, color-coded. Modals centered with a
blurred backdrop, closable with Escape, and a confirm step before any destructive
release. Charts: horizontal bar for project-wise allocation, segmented bar for
floor-wise occupancy, donut for the overall status split — always with a legend and
value labels, never conveying meaning by color alone.

**Motion.** 150ms standard, 250ms entering, `cubic-bezier(0.16, 1, 0.3, 1)`. No
bounce. Respect `prefers-reduced-motion`.

**Responsive and accessible.** Breakpoints at 640 / 768 / 1024 / 1280, touch targets
at least 44×44. WCAG AA: contrast at least 4.5:1 for body text, full keyboard
navigation, a visible focus ring on every interactive element, meaningful labels on
icon-only buttons, and a text or table fallback for every chart.

---

## Technical requirements

- **Frontend:** React 18 with Vite, TypeScript in strict mode, Tailwind CSS v3.
  TanStack Query for server state, React Context for the session, React Router v6,
  react-hook-form for forms, Zod for shared request and response shapes, Recharts for
  the dashboard charts. A typed `fetch` wrapper injects the JWT and handles `401`.
- **Backend:** Python 3.12 with FastAPI on Uvicorn. REST over JSON, with OpenAPI at
  `/docs`. Pydantic v2 for settings and request/response models. Allocation is
  synchronous and transactional — no background jobs.
- **Database:** PostgreSQL, reached via the `DATABASE_URL` environment variable
  already present in this environment. SQLAlchemy 2.0 with typed `Mapped[...]`
  models, Alembic for forward-only migrations.
- **Auth:** in-app, no third-party identity provider. Email and password, JWT HS256
  with an 8 hour expiry, bcrypt password hashing via passlib.
- **Health:** `GET /health` returns success once the API is ready.
- **Logging:** structured logging to stdout.

Use only the libraries named here plus their direct dependencies. Do not introduce a
second database, cache, queue, object store or identity provider — the only backing
service available in this environment is the PostgreSQL instance at `DATABASE_URL`,
and reaching for anything else is a contract violation.

---

## Data model

Five tables. All timestamps are UTC.

**Every seeded account uses the password `deku-demo-pw-2026`.** It is benchmark fixture data, not a secret. Hash it as normal; the exact literal must work at login, and it must be written into `/app/USER_README.md` alongside each account so a grader can sign in.


**`users`** — login accounts, separate from employee records. Auto-increment id;
unique indexed email; bcrypt password hash; role (`admin` or `employee`); nullable FK
to `employees.id` linking a login to its employee record; created timestamp.

**`projects`** — id; unique indexed name; nullable description and manager name;
status (`active` or `inactive`, defaulting to active); created timestamp.

**`employees`** — id; unique indexed employee code (for example `ETH-00042`); indexed
name; unique indexed email; department; job role; joining date; status (`active`,
`inactive`, or `pending` for a new joiner awaiting a seat); FK to `projects.id`;
created and updated timestamps. Seat-allocation status is **derived**, not stored —
it is whether an active allocation row exists — and is exposed in API responses via a
join.

**`seats`** — id; floor (1–5); zone (`A` or `B`); bay (1–15); indexed seat number;
status (`available`, `occupied`, `reserved`, `maintenance`); created timestamp.

**`seat_allocations`** — the allocation ledger. Id; FK to `employees.id`; FK to
`seats.id`; FK to `projects.id` snapshotting the employee's project at allocation
time; allocation status (`active` or `released`); allocation timestamp; nullable
release timestamp.

**Constraints — the business rules live here.**

- `seats`: unique on (floor, zone, seat_number). Indexes on (floor, status) and
  (status).
- `seat_allocations`: a **partial unique index on `seat_id` where the allocation is
  active**, and a **partial unique index on `employee_id` where the allocation is
  active**. These are what make rules 1 and 2 hold under concurrency — application
  checks alone are not sufficient.
- `employees`: unique email, unique employee code; indexes on name, project and
  status.
- `projects`: unique name.

**Seed data.** The database must be seeded deterministically on first start:

- The 12 projects listed above.
- 6,000 seats = 5 floors × 2 zones × 15 bays × 40 seats, with at least 500
  `available`, at least 100 `reserved`, and some in `maintenance`; the remainder
  `occupied`.
- 5,000 employees distributed across the 12 projects and realistic departments and
  job roles, of which **at least 50 are `pending`** with no seat.
- A canonical record: employee **Amit**, email `amit@ethara.ai`, on project
  **Talos**, holding an active allocation at **floor 2, zone B, bay 4, seat
  `B4-23`**.
- Two login accounts: `admin@ethara.ai` with role `admin`, and `amit@ethara.ai` with
  role `employee` linked to the Amit employee record.

Seeding must be idempotent — restarting the app must not duplicate rows.

---

## Constraints

- Single company, single tenant. No multi-org support.
- No desk booking, hoteling, or time-based reservations.
- No calendar, badge, access-control or HRIS integrations.
- Responsive web only. No native mobile app.
- No password reset flow and no SSO — the two seeded accounts are the only logins.
- No external network calls at runtime. Everything the app needs is in this
  environment.
- The app must handle the full seeded volume (5,000 employees, 6,000 seats) with
  responsive list and dashboard queries.

---

## Deployment contract

Non-negotiable. The application is graded through a browser and over HTTP by a
process that knows nothing about your code, so the following must hold exactly.

- The app is reachable at the URL in the `APP_PUBLIC_URL` environment variable, served
  on the port in `APP_PUBLIC_PORT` (`4173`). Never hardcode the port — read it from
  the environment.
- The REST API is served on that **same origin** under the `/api` prefix. Concretely:
  `POST /api/auth/login`, `GET /api/employees`, `POST /api/employees`,
  `GET /api/employees/{id}`, `PATCH /api/employees/{id}`, `GET /api/projects`,
  `GET /api/seats`, `GET /api/seats/available`, `POST /api/seats/allocate`,
  `POST /api/seats/release`, `GET /api/seats/suggest`, `GET /api/dashboard`,
  `POST /api/ai/query`, `POST /api/import`, `GET /api/health`.
- The app starts from this environment image with **no manual steps**. The healthcheck
  must go green on its own.
- Default login credentials are written to **`/app/USER_README.md`** so a grader can
  sign in.
- Reserve the directories `.browser_screenshots/` and `.downloads/` at the app root
  and leave them empty.
- The frontend is served as a **production build behind a preview server** — never a
  dev server.
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
- Use **only** the PostgreSQL instance at `DATABASE_URL`. No other backing service.
- No persistent volumes, no fixed container names, no custom networks. The app must
  tear down and re-run cleanly.

### API shapes

Everything internal is your choice. These request and response shapes are not —
they are the interface the grader holds you to. Field names are exact.

| Endpoint | Request body | Success | On success returns |
|---|---|---|---|
| `POST /api/auth/login` | `{"email": str, "password": str}` | `200` | `{"access_token": str, ...}` |
| `POST /api/employees` | `{"name", "email", "department", "role", "joining_date", "project_id"}` | `200` or `201` | the created employee including `id` |
| `GET /api/employees` | — | `200` | JSON array of employees |
| `GET /api/employees/{id}` | — | `200` | the employee, including their current `seat_number` and project name |
| `GET /api/projects` | — | `200` | JSON array of `{"id", "name", ...}` |
| `GET /api/seats` | query: `floor`, `zone`, `status` | `200` | JSON array of seats |
| `GET /api/seats/available` | query: `floor`, `zone` | `200` | JSON array of `{"id", "seat_number", "floor", "zone", "status"}` |
| `GET /api/seats/suggest` | query: `employee_id` | `200` | ranked JSON array of candidate seats |
| `POST /api/seats/allocate` | `{"employee_id": int, "seat_id": int \| null}` | `200` or `201` | the created allocation |
| `POST /api/seats/release` | `{"employee_id": int}` | `200`, `201` or `204` | — |
| `GET /api/dashboard` | — | `200` | an object carrying total employees and total, occupied, available and reserved seat counts |
| `POST /api/ai/query` | `{"query": str}` | `200` | `{"answer": str, ...}` |
| `GET /api/health` | — | `200` | — |

Rules:

- Every business-rule violation returns a `4xx` with a message naming the reason.
  Never a `5xx`, never a silent `200`.
- Every endpoint except `POST /api/auth/login` and `GET /api/health` requires a valid
  bearer token; anonymous callers get `401` or `403`.
- Every mutating endpoint additionally requires the `admin` role; an `employee` token
  gets `401` or `403`.
- List endpoints return a JSON array at the top level.

---

## Definition of done

The app is deployed and healthy; every feature above works through the browser; every
allocation rule holds including under concurrent attempts; an `employee` session
cannot mutate anything through the API; the dashboard matches actual database state;
and the assistant answers every listed query correctly without any external service.

Test your own work in a browser before you finish.
