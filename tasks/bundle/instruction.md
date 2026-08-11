# Ethara — Revenue Desk

Build and deploy a working web application from this brief. There is no starting codebase. When you are done, a stranger must be able to open the app in a browser, sign in as a regional manager, open the published January report, and read a revenue total that equals the sum of the transaction rows that same report lists, without hitting an error page. A different stranger, managing a different region, must NOT be able to reach those figures by any means. Every total must be computed from the transaction rows on the read that asks for it; a number the app stored earlier and repeats back to itself does not count.

## Overview

`Revenue Desk` is the internal reporting console for one hardware distributor. An analyst opens a report over a closed date period and publishes it; regional managers read it. Every report yields three figures — a grand `total`, a breakdown by region and a breakdown by product line — all computed from the transaction ledger at the moment the page is read.

It is not a ledger editor, an export tool or a chart library: no transaction entry, no CSV or PDF, no graphs, no email, no comments, no signup.

The hard part is that those three views of one period must never disagree with each other or with the rows they came from, and that a manager sees their own region in all three or nothing at all.

## User roles

| Role | Can read | Can write |
|---|---|---|
| `analyst` | every report, `draft` and `published`; every region and product line | create a report; publish once |
| `manager` | `published` reports only, and inside them only their own region's figures and rows. **Cannot** read a `draft` or any other region's figures or rows | **Nothing** |

Authorization is enforced **server-side on every mutating endpoint**, and on every read that would otherwise return another region's rows. Hiding a button in the UI is not authorization: a direct API call from a `manager` session against any `analyst`-only endpoint must be rejected with `401` or `403`.

Signup is closed: the three seeded accounts below are the only ones, all with password `deku-demo-pw-2026`.

| Email | Name | Role | Region |
|---|---|---|---|
| `analyst@example.com` | `Dana Okafor` | `analyst` | — |
| `manager@example.com` | `Ines Bravo` | `manager` | `North` |
| `manager2@example.com` | `Rui Santos` | `manager` | `South` |

## Core features

### Sign in
`POST /api/auth/login` returns `{"access_token":str}`. Every endpoint but `GET /api/health` needs a bearer token; missing, malformed or expired is `401`. `GET /api/me` returns the caller's `role` and `region`.

### Reports
1. `POST /api/reports` on an `analyst` token creates a `draft` from `{"title","period_start","period_end"}`; both dates inclusive. `period_end` before `period_start` is rejected `400` naming the reason, and no row is created.
2. `POST /api/reports/{id}/publish` on an `analyst` token turns a `draft` `published`, stamps `published_at` and returns `200`. A second publish is rejected `409` and `published_at` does not move.
3. `GET /api/reports` returns a JSON array: all reports for an `analyst`, `published` only for a `manager`. A `manager` asking for a `draft` by id gets `404`.
4. A `manager` token on either write endpoint is rejected `401` or `403`; no row changes.

### The summary
5. `GET /api/reports/{id}/summary` returns `{"report_id","total","by_region":[{"region","total"}],"by_product_line":[{"product_line","total"}]}`. Every figure is derived on the read, from transactions whose `occurred_on` lies inside the period — both endpoints inclusive — and whose `status` is `settled`; `refunded` and `void` rows count for nothing.
6. All three agree: `total` equals the sum of the `by_region` totals and of the `by_product_line` totals. On `January 2026 Revenue` the analyst reads `total` `415000`; `by_region` `North` `195000`, `South` `150000`, `West` `70000`; `by_product_line` `Aurora` `325000`, `Basalt` `90000`.
7. `GET /api/reports/{id}/transactions` returns a JSON array of exactly the rows behind that summary, whose `amount`s sum to the `total` that caller reads. A period with no matching rows gives `total` `0` and empty arrays.

### Region scope
8. For a `manager` every figure narrows to their region: one `by_region` entry, `total` that region's, `by_product_line` and the transaction array over their rows only. `manager@example.com` reads `195000` over three rows; `manager2@example.com` reads `150000` over two.
9. `GET /api/reports/{id}/summary?region=<name>` for a region that is not the caller's own is rejected `403`, with no figure for it in the body; the analyst may name any region.
10. `GET /api/regions` returns all regions for an `analyst`, the caller's own for a `manager`. `GET /api/product-lines` returns `Aurora`, `Basalt`.

## User flow

| Route | Purpose | Auth |
|---|---|---|
| `/login` | Email and password sign-in | No |
| `/` | Report list, newest first | Any signed-in role |
| `/reports/new` | Create a draft report | `analyst` |
| `/reports/:id` | Grand total, `by_region` card, `by_product_line` card | Any signed-in role |
| `/reports/:id/transactions` | The rows the summary came from | Any signed-in role |

**Entry and redirects.** An unauthenticated visitor to a protected route is redirected to `/login?next=<path>`; login sends them to `next` when present, otherwise `/`. Logout clears the token and returns to `/login`. A token expiring mid-action clears, redirects to `/login?next=<current path>` and shows a session-expired message. A `manager` opening `/reports/new` is blocked with a permission message, not redirected; a `draft` gives the not-found card.

**Journeys.**
1. Sign in as `manager@example.com` → `/` lists `January 2026 Revenue` and nothing else → open it → the grand total reads `$1,950.00` and `by_region` shows one row, `North`.
2. Open `/reports/:id/transactions` from there → three rows, `TX-1001`, `TX-1002`, `TX-1003` → their amounts sum to the total on the previous screen.
3. Sign in as `analyst@example.com` → open `January 2026 Revenue` → three region rows and two product-line rows, each list summing to `415000`.
4. `manager@example.com` asks for another region's figures → refused, reason shown, no figures rendered.
5. `manager2@example.com` opens `February 2026 Revenue` → not-found card; the analyst opens it and reads it.
6. The analyst creates a report with the period backwards → the form shows the reason and no report appears.

**States.** Every list has an empty state and every page a loading state. A missing report renders a not-found card. Rejections surface their reason — permission denied, not found, period end before start, already published — and never crash the app.

## UI/UX notes

A calm internal finance console: dense, legible, figures first and chrome last, in the register of accounting ledgers. **Light mode**, designed fully; dark mode is optional.

**Palette.** Background `#F7F8FA`, surface `#FFFFFF`, text `#0F172A`, muted `#64748B`, primary/CTA `#1D4ED8` (hover `#1E40AF`), border `#E2E8F0`, danger `#B91C1C`, success `#15803D`, warning `#B45309`, accent `#0E7490`. Transaction status: `settled` `#15803D`, `refunded` `#B45309`, `void` `#64748B`. Report status: `draft` `#64748B`, `published` `#1D4ED8`.

**Type.** `Inter` throughout. Headings `32/40`, `24/32`, `20/28`; body `15/24`; caption `13/18`. Tabular numerals on every amount, count and date; money as `$1,950.00`.

**Shape and components.** Radii `8px` on cards and tables, `6px` on buttons and inputs; `1px` `#E2E8F0` borders; one elevation on the summary cards, `0 1px 2px rgba(15, 23, 42, 0.06)`. Rows, buttons and inputs `40px`; labels above, errors below in `#B91C1C`, a `2px` `#1D4ED8` focus ring. Amounts right-aligned. Toasts and modals close on Escape; publishing confirms first.

**Motion.** Transitions animate at `150ms`, entering elements at `250ms`, easing `cubic-bezier(0.16, 1, 0.3, 1)`. No bounce or counting-up on totals. `prefers-reduced-motion: reduce` removes transitions rather than shortening them.

**Responsive and accessible.** Breakpoints `640` / `768` / `1024`; below `768` the cards stack and each table scrolls inside its own card, never the page. The layout holds at `1920x1200`, `768x1024` and `390x844`. Touch targets `44x44`; WCAG AA contrast `4.5:1`; keyboard navigation with visible focus rings; labels on icon-only controls; every status shown as a word, never colour alone.

## Technical requirements

- **Frontend.** React 18 with Vite, TypeScript in strict mode, Tailwind CSS v3. TanStack Query for server state, React Router v6, react-hook-form with Zod for the create-report form. A typed `fetch` wrapper attaches the bearer token and normalises a `401`.
- **Backend.** Python 3.12 with FastAPI on Uvicorn. REST over JSON, Pydantic v2 for settings and for request and response models.
- **Database.** PostgreSQL, reached at `DATABASE_URL`. SQLAlchemy 2.0 with typed `Mapped[...]` models and Alembic for forward-only migrations.
- **Auth.** Email and password held by the app itself, hashed with bcrypt. `POST /api/auth/login` returns a bearer token that lasts 12 hours. The caller's role and region are resolved from the token's subject against the `users` table and never read from a request field: a `region` supplied by the client that is not the caller's own is refused rather than honoured.
- **Aggregation, stated as an observable property.** No total is stored anywhere. Change one transaction's `status` between `settled` and `refunded`, and the very next summary read must differ by exactly that transaction's `amount`, in the grand `total`, in its region's entry and in its product line's entry. A figure that survives such a change is stale, and the report then disagrees with the rows it claims to summarise. The scope filter and the aggregate must come out of one and the same row set, so a caller's `total`, their breakdowns and their transaction list cannot contradict one another.
- **Publishing, stated as an observable property.** Two `POST /api/reports/{id}/publish` requests issued simultaneously for the same `draft` must produce exactly one `200` and one `409` — never two `200`s, never two `published_at` stamps. Once set, `published_at` never moves again, and a request arriving later still reads `409`. Checks written only in application code do not hold under simultaneous requests; any approach that delivers these outcomes is acceptable.
- **Health.** `GET /api/health` returns `200` once the API is ready.
- **Logging.** Structured JSON to stdout, one record per request.

Use only the libraries named here plus their direct dependencies. Do not introduce a second database, cache, queue, object store, identity provider or mail vendor — the only backing service available in this environment is PostgreSQL at `DATABASE_URL`, and reaching for anything else is a contract violation.

## Data model

Five tables. All timestamps are UTC and every amount is an integer in minor units of `usd`, so `195000` is `$1,950.00`.

**Every seeded account uses the password `deku-demo-pw-2026`.** It is benchmark fixture data, not a secret. Hash it as normal; the exact literal must work at login, and it must be written into `/app/USER_README.md` alongside each account so a grader can sign in.

**`users`** — `id`; `email`, unique and lowercased; `password_hash`; `name`; `role`, either `analyst` or `manager`; `region_id`, referencing `regions`, which is set for a `manager` and empty for an `analyst`; created timestamp.

**`regions`** — `id`; `name`, unique.

**`product_lines`** — `id`; `name`, unique.

**`transactions`** — `id`; `external_ref`, unique, the ledger's own reference; `region_id` referencing `regions`; `product_line_id` referencing `product_lines`; `amount`, an integer of minor units that is never negative; `occurred_on`, a UTC calendar date; `status`, one of `settled`, `refunded` or `void`; created timestamp.

**`reports`** — `id`; `title`; `period_start` and `period_end`, both dates, with `period_end` never earlier than `period_start`; `status`, either `draft` or `published`; `created_by` referencing a `users` row whose `role` is `analyst`; `published_at`, a timestamp that is empty exactly when `status` is `draft`; created timestamp.

**Derived, never stored.** `total`, every `by_region[].total`, every `by_product_line[].total` and the row set behind a report are all computed on read. No table carries an aggregate column and there is no summary table. A transaction belongs to a report when its `occurred_on` falls between `period_start` and `period_end` with both endpoints included, and its `status` is `settled`.

**Seed data.**
- Regions `North`, `South` and `West`. Product lines `Aurora` and `Basalt`.
- Three accounts: `analyst@example.com` (`Dana Okafor`, `analyst`), `manager@example.com` (`Ines Bravo`, `manager`, `North`), `manager2@example.com` (`Rui Santos`, `manager`, `South`). `West` has no manager.
- Ten transactions:

| `external_ref` | Region | Product line | `amount` | `occurred_on` | `status` |
|---|---|---|---|---|---|
| `TX-1001` | `North` | `Aurora` | `120000` | `2026-01-05` | `settled` |
| `TX-1002` | `North` | `Aurora` | `45000` | `2026-01-18` | `settled` |
| `TX-1003` | `North` | `Basalt` | `30000` | `2026-01-22` | `settled` |
| `TX-1004` | `North` | `Basalt` | `25000` | `2026-01-24` | `refunded` |
| `TX-1005` | `South` | `Aurora` | `90000` | `2026-01-09` | `settled` |
| `TX-1006` | `South` | `Basalt` | `60000` | `2026-01-15` | `settled` |
| `TX-1007` | `South` | `Basalt` | `15000` | `2026-01-30` | `void` |
| `TX-1008` | `West` | `Aurora` | `70000` | `2026-01-11` | `settled` |
| `TX-1009` | `North` | `Aurora` | `99000` | `2026-02-02` | `settled` |
| `TX-1010` | `South` | `Aurora` | `88000` | `2025-12-31` | `settled` |

- Two reports, both created by `analyst@example.com`: `January 2026 Revenue` over `2026-01-01` to `2026-01-31`, already `published`; and `February 2026 Revenue` over `2026-02-01` to `2026-02-28`, still a `draft`.

Seeding must be idempotent — restarting the app must not duplicate rows. A duplicated transaction row silently doubles a regional total, which is the one failure this product exists to prevent.

## Constraints

- One company, one ledger. Region is the only scope: no second tenant, no sub-region, no per-region pricing.
- Transactions are read-only reference data — never created, edited or imported, and there is no entry screen.
- No export: no CSV, PDF, spreadsheet or print view.
- No charts, no time series, no forecasting, no period-over-period comparison. A report is two breakdown tables and a total.
- No currency conversion; every amount is integer minor units of `usd`.
- No comments, no annotations, no share links, no revision history, no unpublish.
- No background jobs, no cache, no scheduled work; nothing recomputes on a timer.
- No email, notifications or external network calls at runtime.
- Responsive web only, no native app. The app stays responsive at ten thousand transaction rows.

## Deployment contract

- The app must be reachable at `APP_PUBLIC_URL`. The port mapping is
  `${APP_PUBLIC_PORT}:4173` — `4173` is the container-internal port and
  `APP_PUBLIC_PORT` is what the outside world uses. Read both from the
  environment; never hardcode either.
- The HTTP API is served on that same origin under the `/api` prefix.
- `GET /api/health` returns `200` once the app is ready.
- The app starts from the environment image with no manual steps.
- Login credentials — or an explicit statement that there are none — are
  written to `/app/USER_README.md`.
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

### API shapes

| Endpoint | Request body / query | Success | Returns |
|---|---|---|---|
| `POST /api/auth/login` | `{"email":str,"password":str}` | `200` | `{"access_token":str}` |
| `GET /api/health` | — | `200` | — |
| `GET /api/me` | — | `200` | `id`, `email`, `name`, `role`, `region` |
| `GET /api/regions` | — | `200` | JSON array of `{"id","name"}` |
| `GET /api/product-lines` | — | `200` | JSON array of `{"id","name"}` |
| `POST /api/reports` | `{"title":str,"period_start":str,"period_end":str}` | `201` | the created report with `status` `draft` |
| `GET /api/reports` | — | `200` | JSON array of reports |
| `GET /api/reports/{id}` | — | `200` | one report |
| `POST /api/reports/{id}/publish` | — | `200` | the report with `status` `published` and a `published_at` |
| `GET /api/reports/{id}/summary` | optional `?region=<name>` | `200` | `report_id`, `total`, `by_region`, `by_product_line` |
| `GET /api/reports/{id}/transactions` | — | `200` | JSON array of `external_ref`, `region`, `product_line`, `amount`, `occurred_on`, `status` |

Rules:
- Every business-rule violation returns a `4xx` naming the reason. Never `5xx`, never a silent success.
- Every endpoint except `POST /api/auth/login` and `GET /api/health` requires a valid bearer token.
- `POST /api/reports` and `POST /api/reports/{id}/publish` are `analyst`-only; a `manager` token gets `401` or `403`.
- A `manager` reads only their own region. Any request that would return another region's figures or rows is `403`; a `draft` report is `404`.
- List endpoints return a JSON array at the top level.

**No mocks.** PostgreSQL at `DATABASE_URL` is where the ledger lives, and it is the only place it lives. An in-memory list of transactions, a hardcoded summary object, a total cached in a file or held in a module variable, or a screen that renders figures the ledger does not support is a contract violation however convincing the page looks. The named provider is the fact — the app's UI and its own tables can only reflect what lives in the provider, never substitute for it.

## Definition of done

The app is deployed and healthy. `Ines Bravo` signs in and sees one report, `January 2026 Revenue`, whose grand total is `$1,950.00`; the three transaction rows behind it add up to exactly that, and there is no way for her to reach `South`'s figures or `West`'s. `Rui Santos` signs in to the same report and reads `$1,500.00` over two rows. `Dana Okafor` opens the same report and reads `415000` across three regions and two product lines, with each breakdown adding to the grand total and the six underlying rows adding to it as well; the refunded row, the void row and the two rows outside January are absent from every figure. `Dana Okafor` can draft a new report and publish it once — a second publish leaves the first publication time untouched — while neither manager can create or publish anything, and `February 2026 Revenue` does not exist for either of them until it is published. A period containing no settled transactions reports a total of zero with empty breakdowns rather than an error.
