# Ethara — Kestrel Yard Allocation Board

Build and deploy a working web application from this brief. There is no starting
codebase. When you are done, a stranger must be able to open the app in a
browser, sign in as a planner, reserve pallets against a live item, and watch
free stock fall on the board and a line appear in the ledger without hitting an
error page. Free stock can never go below zero, and the thing that holds that is
a database constraint rather than a check in your code — a separate verifier
fires two reservations at one item at the same instant, so a build that is only
correct one request at a time scores zero.

---

## Overview

Kestrel Yard holds pallet stock that several planners draw on at once. A planner
reserves a quantity of an item; the on-hand count does not move, the held count
rises, and free stock falls by the same amount. A planner releases their own
hold and the stock returns. A stock admin moves the on-hand count by a signed
delta with a reason. That is the whole product.

Every accepted reservation, release and adjustment appends exactly one immutable
ledger line. Nothing edits a line and nothing deletes one.

A reservation that would take free stock below `0` is refused and says how many
are still free. An adjustment that would push on-hand below the quantity already
held is refused the same way.

---

## User roles

| Role | Can do |
|---|---|
| `planner` | Sign in; read the board and the ledger; reserve stock; release their own reservation; list their own reservations. **Cannot adjust on-hand counts.** Two seeded accounts. |
| `stock_admin` | Sign in; read the board and the ledger; adjust on-hand counts. **Cannot reserve and cannot release.** One seeded account. |
| `auditor` | Sign in; read the board and the ledger. **Cannot reserve, cannot release and cannot adjust.** One seeded account. |

Authorization is enforced **server-side on every mutating endpoint**. Hiding a
button in the UI is not authorization: a direct API call from a `planner`
session against any `stock_admin`-only endpoint must be rejected with `401` or
`403`.

There is no signup. Every account is seeded, no endpoint creates an account, and
no path changes a role. A planner reaches only their own reservations: a release
aimed at another planner's reservation is rejected.

---

## Core features

### Reserving stock

1. A planner reserves a whole number of pallets of one item. The reservation
   opens with `status` `held`, `on_hand` does not change, `reserved` rises by the
   quantity, and free stock is `on_hand` minus `reserved` computed on every read.
   No stored or cached free column exists.
2. A reservation whose quantity exceeds free stock is refused with `409` and a
   body carrying `free_quantity`, the whole number still free. Nothing moves and
   no ledger line is written.
3. **The refusal is held by the database, not by your code.** `stock_items`
   carries `CHECK (reserved >= 0 AND reserved <= on_hand)`, and the reservation
   moves the counter, writes the reservation and appends the ledger line in one
   transaction with the item row locked. Two simultaneous reservations for the
   last pallets leave exactly one success and one `409`.
4. A quantity below `1` is refused with `422`.

### Releasing

5. A planner releases their own `held` reservation by its `reference`. The
   reservation becomes `released`, `reserved` falls by its quantity, and free
   stock returns. Releasing a reservation that is already `released` is refused
   with `409`.

### Adjusting on-hand stock

6. A stock admin moves `on_hand` by a signed `delta` with a written `reason`.
   `reserved` never changes. An adjustment leaving `on_hand` below `reserved` is
   refused with `409` and a body carrying `free_quantity`, and `on_hand` is
   unchanged afterwards.

### The immutable ledger

7. Every accepted reservation, release and adjustment appends exactly one line
   recording the item, the `kind`, the signed `quantity_delta` in free stock,
   the `free_after` count, the actor and the time. A refused mutation appends
   nothing.
8. Lines are append-only. Releasing a reservation appends a `release` line and
   leaves its `reserve` line standing. No endpoint edits or deletes a line.

### The live board

9. The board shows one row per item with on-hand, held and free counts derived
   from rows on every read. A change made by one signed-in user reaches every
   other open board within `5` seconds with no manual reload, and each changed
   count animates to its new value.

---

## User flow

| Route | Purpose | Auth |
|---|---|---|
| `/login` | Email and password sign in | No |
| `/board` | The live allocation board, one row per item | Any role |
| `/board/:sku` | One item: its counts, its ledger, the action for the role | Any role |
| `/reservations` | The planner's own reservations | Planner |
| `/ledger` | Every movement, newest first | Any role |

`/` redirects to `/board` when signed in and to `/login` otherwise. An anonymous
visitor at any other route is redirected to `/login`. A `stock_admin` or
`auditor` at `/reservations` is redirected to `/board`, and the API returns
`403` whatever the interface did.

**Journeys.**

1. **Reserve.** Sign in as `planner@example.com` → `/board` → open `PLT-1001`,
   free `18` → reserve `4` → free animates to `14`, held to `10`, and a
   `reserve` line appears naming `Dana Ryecroft`.
2. **Release.** `/reservations` → release that hold → free animates back to `18`
   and a `release` line joins the ledger above the `reserve` line, which is
   still there.
3. **Adjust.** Sign in as `stock_admin@example.com` → `PLT-1004` → adjust `+5`
   with a reason → on-hand `15`, free `15`, and an `adjust` line carrying the
   reason.
4. **The refusal.** As a planner open `PLT-1002`, free `0` → ask for `1` → the
   page states `0` are free and the reserve control stays in place. Nothing
   moves and no line appears.
5. **The live board.** Two browsers on `/board`. One reserves `2` of `PLT-1003`;
   within `5` seconds the other's free count animates from `8` to `6` untouched.

**States.** Every page has a loading state, and a failed request leaves the page
standing with a retry. `PLT-1005` reads three zeros and a short line saying
nothing has moved yet, never an error. A planner holding nothing sees a short
line, never a blank panel.

---

## UI/UX notes

Industrial, dense, high contrast: a control surface read at distance.

**Palette.** background `#0F1211`, surface `#171B1A`, text `#E8EDEB`, muted
`#8A9491`, primary and CTA `#2FA37A` with hover `#248260`, border `#2A3230`,
held `#C2833B`, refused or zero free `#D4525F`. Green marks free stock and
nothing else; amber marks held stock.

**Type.** `"IBM Plex Sans", system-ui, sans-serif` for prose and
`"IBM Plex Mono", ui-monospace, monospace` for every quantity, sku and
reference. Page title 30/38, section heading 20/28, body 15/22, meta 12/18, and
the free-count numeral 40/44 in tabular numerals — the largest thing on a row.

**Shape.** Cards `10px` radius, buttons `6px`, count chips a `999px` pill.
Hairline `1px` borders, never a shadow. Card padding `20px`, an `8px` spacing
step, board rows on a `56px` grid.

**Motion.** Two durations only: `150ms` for hover and focus, `250ms` for a count
change. Easing `ease-out`. A changed count counts to its new value over `250ms`
rather than snapping, and its row briefly highlights. Under
`prefers-reduced-motion: reduce` every transition drops to `0ms`.

**The board row.** Sku, name, then three chips in fixed order: on hand, held,
free. Each chip carries its label as text as well as colour.

**The refusal** is part of the page beside the control that caused it, states
the quantity still free as a number, and persists until the planner acts — never
a toast that vanishes.

**Responsive and accessible.** Breakpoints `640px`, `768px`, `1024px`; one
column below `640px`. Touch targets `44x44px`. WCAG AA contrast for all text.
Full keyboard navigation with a visible `2px` focus ring, and count changes
announced in a polite live region.

---

## Constraints

- No purchase orders, receipts, shipments, picking or despatch. Stock enters and
  leaves only through an admin adjustment.
- No second warehouse, no bins, no locations, no lots, no serial numbers.
- No reservation expiry, editing, partial release or transfer between planners.
- No signup, no password reset, no SSO, no second factor, no role change.
- No backdated adjustment, no approval step, no reversal endpoint. A correction
  is a new adjustment in the opposite direction.
- No email, no file upload, no export, no report beyond the board and the
  ledger.
- No cost, price, currency or valuation anywhere in the product.
- No third-party integration beyond the one service named in this brief.
- No external network call at run time.

---

## Technical requirements

- **Frontend:** React 18 with Vite, TypeScript in strict mode, Tailwind CSS v3.
  TanStack Query for server state, React Router v6, react-hook-form for the
  reserve and adjust forms. A typed `fetch` wrapper injects the bearer token.
- **Backend:** Python 3.12 with FastAPI on Uvicorn, REST over JSON, Pydantic v2.
- **Database:** PostgreSQL at `DATABASE_URL`. SQLAlchemy 2.0 with typed
  `Mapped[...]` models, Alembic for forward-only migrations.
- **Auth:** in-app, JWT HS256, eight-hour expiry, bcrypt hashing via passlib.
  Login returns the token as `access_token`; the client sends it as
  `Authorization: Bearer <token>`.
- **Health:** `GET /api/health` returns `200` once migrations, the seed and the
  database are ready.

Use only the libraries named here plus their direct dependencies. Do not
introduce a second database, a cache, a queue, an object store, a realtime
broker, or any vendor SDK.

### PostgreSQL — the one declared service

PostgreSQL runs as a sidecar and is reachable at `DATABASE_URL`. It is already
running. Do not download, install, compile or start a copy of it. The verifier
reads this database directly during grading, so the table and column names below
are an interface, not an implementation detail.

### The concurrency rule, stated as an engineering requirement

`stock_items` carries the constraint `CHECK (reserved >= 0 AND reserved <=
on_hand)`. A reservation, a release and an adjustment each take the item row
with `SELECT ... FOR UPDATE`, move the counter, write or update the reservation
where one is involved, and append the ledger line — all inside **one**
transaction. A constraint violation is caught and answered `409` with
`free_quantity`. It is never allowed to surface as a `500`.

Reading free stock, deciding in application code, then writing is the defect
this task exists to detect. It passes every serial reading of this brief and
loses under two simultaneous requests.

### Live board delivery

The board converges across clients within `5` seconds of a change with no manual
reload. A polling refresh or a same-origin server-sent event stream are both
acceptable — the requirement is the convergence, not the transport. No external
broker exists in this environment and none may be introduced.

---

## Data model

Four tables. All timestamps are UTC. Every quantity is a whole number of pallets;
there is no money and no fractional quantity anywhere in this product.

**Every seeded account uses the password `deku-demo-pw-2026`.** It is benchmark
fixture data, not a secret. Hash it as normal; the exact literal must work at
login, and it must be written into `/app/USER_README.md` alongside each account.

Table and column names below are exact. Internal types are your choice, but a
reader of the database must find these names.

**`users`** — `id`; unique indexed `email`; password hash; `role`, one of
`planner`, `stock_admin` or `auditor`; `name`; created timestamp.

**`stock_items`** — `id`; unique indexed `sku`, the string `PLT-` followed by
four digits; `name`; `on_hand`, an integer never below `0`; `reserved`, an
integer never below `0` and never above `on_hand`, held by the check constraint
named above; created and updated timestamps. Free stock is `on_hand` minus
`reserved` and is never stored.

**`reservations`** — `id`; unique indexed `reference`, the string `RSV-`
followed by four digits; `stock_item_id` referencing `stock_items`;
`planner_id` referencing `users`; `quantity`, an integer of at least `1`;
`status`, one of `held` or `released`; created and released timestamps.
`reference` is the public handle — every route naming a reservation names it by
`reference`, never by `id`. For every item, `reserved` equals the sum of
`quantity` over that item's `held` reservations.

**`ledger_entries`** — `id`; `stock_item_id` referencing `stock_items`;
`reservation_id` referencing `reservations`, null on an adjustment; `kind`, one
of `reserve`, `release` or `adjust`; `quantity_delta`, the signed change in free
stock; `free_after`, free stock immediately after the line; `actor_id`
referencing `users`; `reason`, null except on an adjustment; created timestamp.
`quantity_delta` is minus the quantity for a `reserve`, plus the quantity for a
`release`, and the admin's delta for an `adjust`.

**Seed data.** Deterministic and idempotent, keyed on `email`, on `sku` and on
`reference` — restarting must not duplicate a row or re-append a line.

- Four accounts: `planner@example.com` named `Dana Ryecroft` and
  `planner2@example.com` named `Marek Toll`, both `planner`;
  `stock_admin@example.com` named `Ivo Bell`, the `stock_admin`; and
  `auditor@example.com` named `Sofia Crane`, the `auditor`.
- Five pallet items: `PLT-1001` `Oak Pallet Standard` with `on_hand` `24` and
  `reserved` `6`; `PLT-1002` `Steel Cage Pallet` with `on_hand` `12` and
  `reserved` `12`; `PLT-1003` `Euro Pallet Light` with `on_hand` `8` and
  `reserved` `0`; `PLT-1004` `Chill Pallet Insulated` with `on_hand` `10` and
  `reserved` `0`; `PLT-1005` `Drum Cradle Pallet` with `on_hand` `0` and
  `reserved` `0`.
- Two held reservations: `RSV-1001`, `6` of `PLT-1001` for
  `planner@example.com`; and `RSV-1002`, `12` of `PLT-1002` for
  `planner2@example.com`.
- Two opening `reserve` ledger lines, one per seeded reservation, so the ledger
  reconciles with `reserved` before anything else happens. `PLT-1003`,
  `PLT-1004` and `PLT-1005` open with no lines. New references continue from
  `RSV-1003`.

---

## Build plan

1. **Skeleton.** One origin, port from `APP_PUBLIC_PORT`, bind `0.0.0.0`,
   production build behind a preview server, `GET /api/health` green.
2. **Data.** Migrations, the check constraint, the unique indexes, the
   idempotent seed. Running the seed twice must leave the row counts unchanged.
3. **Auth and roles.** Login, bearer middleware, the three role checks.
4. **Reads.** The board, the ledger, and a planner's own reservations, all
   computing free stock from rows.
5. **Reserve and release.** The locked transaction and the `409` with
   `free_quantity`. **Do this before the interface** — a reservation route that
   is correct only when nobody else is pressing the button looks identical on
   screen to one that is right.
6. **Adjust.** The same lock, the reason, and the `409` from the other
   direction.
7. **Interface.** The board, the item page, the reservations list, the ledger,
   the palette, the type scale, the count animation, reduced motion, the
   breakpoints, the focus ring, the live region, the persistent refusal.
8. **Live convergence.** Board refresh by interval or same-origin event stream.
9. **Detach and verify.** Start the server so it outlives your session, then
   confirm the listening process and the port.

---

## Deployment contract

Your application is graded through a browser and over HTTP by a process that
knows nothing about your code, after your session has ended.

- The app must be reachable at `APP_PUBLIC_URL`. The port mapping is
  `${APP_PUBLIC_PORT}:4173` — `4173` is the container-internal port and
  `APP_PUBLIC_PORT` is what the outside world uses. Never hardcode either; read
  them from the environment.
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
  lines from this file; prose around them is ignored, so anything not in that
  shape is invisible to it.
- Reserved `.browser_screenshots/` and `.downloads/` directories exist at the app
  root, empty.
- **Write `/app/start.sh`, and make it executable.** Grading may redeploy your
  app into a *clean* container: same base image, your `/app` files copied in, and
  nothing else — no processes running, no caches you warmed, no packages you
  installed outside `/app`, no state you created by hand. Postgres is still there
  at the same address, but **its data is re-created from scratch**, so any rows
  you wrote during this session are gone and your schema, constraints and seed
  must be applied by the script. That includes the database constraint the
  oversell rule depends on — a constraint that only exists because you typed it
  once by hand does not survive. `start.sh` must:
  - install whatever it needs from inside the script — do not assume anything you
    installed during this session still exists. **A virtualenv is not portable**:
    `.venv` records absolute paths and holds binaries built for one machine, so
    copying it into `/app` produces `cannot execute binary file` in a clean
    container. Create the environment inside `start.sh`, or install into the
    system interpreter. The same applies to `node_modules` containing compiled
    native modules.
  - apply migrations and seed data against `DATABASE_URL`, and be safe to run
    against an already-populated database as well as an empty one,
  - read the port from `APP_PUBLIC_PORT` and the database address from the
    environment, never hardcoded,
  - start the server detached, and exit `0` once the app is answering.
- **Prove `start.sh` works before you finish.** Kill every process you started,
  run `bash /app/start.sh` yourself, and confirm `GET /api/health` returns `200`
  afterwards. An app that only runs because of something you did by hand in this
  session is not a deployable app, and will score zero.
- Serve a production build behind a static or preview server — never a dev
  server.
- The server must outlive this session. Grading runs after your session ends.
  Start it fully detached:
  `setsid nohup <command> > /tmp/app.log 2>&1 < /dev/null &`
  An ordinary background job is killed the instant the session ends, and the app
  scores zero however correct it is.
- Bind `0.0.0.0`, never `127.0.0.1` or `localhost`.
- Before finishing, verify persistence: the listening process's parent is not
  your shell, and the port still answers.
- The backing services named in this brief are already running and reachable at
  their environment variables. Do not download, install, compile or start a copy
  of any of them.
- Use only the providers named in this brief: PostgreSQL at `DATABASE_URL`. No
  edge functions.
- No persistent volumes, no fixed container names, no custom networks.

### API shapes

Everything internal is your choice. These are not — they are the interface you
are held to. Field names are exact. Every quantity is a whole number.

| Endpoint | Request | Success | Returns |
|---|---|---|---|
| `POST /api/auth/login` | `{"email", "password"}` | `200` | `{"access_token"}` |
| `GET /api/health` | — | `200` | — |
| `GET /api/board` | — | `200` | array of `{"sku", "name", "on_hand", "reserved", "free"}` |
| `GET /api/reservations` | — | `200` for a planner; `403` otherwise | array of the caller's own `{"reference", "sku", "quantity", "status"}` |
| `POST /api/reservations` | `{"sku", "quantity"}` | `200` or `201`; `409` over free stock; `422` below `1`; `403` for another role | `{"reference", "sku", "quantity", "status", "free_after"}` |
| `POST /api/reservations/{reference}/release` | — | `200`; `409` when already released; `403` for another planner | `{"reference", "status", "free_after"}` |
| `POST /api/adjustments` | `{"sku", "delta", "reason"}` | `200` or `201`; `409` below held stock; `403` for another role | `{"sku", "on_hand", "reserved", "free", "delta"}` |
| `GET /api/ledger` | optional `sku` query parameter | `200`; `404` for an unknown `sku` | array newest first of `{"sku", "kind", "quantity_delta", "free_after", "actor_email", "created_at"}` |

Rules:

- Every endpoint except `POST /api/auth/login` and `GET /api/health` requires a
  valid bearer token. An anonymous call to any other endpoint is rejected with
  `401`.
- Both stock refusals return `409` with a body carrying `free_quantity` as a
  whole number, alongside a message naming the reason.
- An unknown `sku` is answered `404` on every route that takes one, including a
  ledger read filtered by `sku`. An empty collection is the answer for a known
  item that has never moved, never for an item that does not exist.
- Every business-rule violation returns a `4xx` with a message. Never a `5xx`,
  never a silent `200` on a refused mutation.

### No shortcuts — enforced by real inspection

The verifier reads PostgreSQL directly and fires simultaneous requests at one
item. Any of the following is a contract violation:

- Checking free stock in application code and then writing, with no database
  constraint behind it.
- A stored or cached free column, or any counter the board reads instead of
  deriving from `on_hand` and `reserved`.
- Editing or deleting a ledger line, or omitting a line for an accepted
  mutation.
- Answering a refused mutation with a `200`, or letting a constraint violation
  surface as a `5xx`.

Do not explain in the UI how any of this is detected. Just do it correctly.

---

## Definition of done

The app is deployed and healthy. A planner signs in, reserves pallets against
`PLT-1001`, and the board free count falls by the reserved quantity while
on-hand stays put. Releasing returns the stock and leaves the original ledger
line standing. The stock admin moves `PLT-1004` by a signed delta with a reason
and the ledger records it. A reservation against `PLT-1002` is refused with
`409` and the free quantity is named. An adjustment that would push on-hand
below held stock is refused the same way. Two simultaneous reservations for the
last pallets of `PLT-1003` leave exactly one success. A planner cannot adjust,
the stock admin cannot reserve, the auditor can do neither, and no planner can
release another planner's reservation. A second browser's board moves on its own
within `5` seconds.

Try your own work in a browser before you finish. Open two windows signed in as
the two planners and watch one board move the other.
