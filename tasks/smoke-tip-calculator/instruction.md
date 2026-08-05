# Deku — Smoke Tip Calculator

Build and deploy a working web application from this brief. There is no starting
codebase. When you are done, a stranger must be able to open the app in a browser,
type a bill amount, pick a tip percentage, and see the tip and total update.

This spec is deliberately tiny. The whole thing should take a handful of minutes.

---

## Overview

A single-page tip calculator. One user, no login, no database, no persistence.
The page has three inputs — bill amount, tip percentage, split-between-people —
and shows three live-updating numbers: the tip amount, the total, and the amount
per person. There is also a small JSON API the same page can use, and which
outside callers can hit directly.

There is no backing service. Everything runs in one process on one port.

---

## Core features

### The page (served at `/`)

- A numeric input for **bill amount** in dollars.
- A control for **tip percentage**. A range slider, a set of preset buttons, or a
  numeric input is fine — any of them satisfies the brief.
- A numeric input for **split between people**. When absent or `1`, the
  per-person amount equals the total.
- Three visible outputs, updated live as the inputs change: **tip amount**,
  **total**, and **per-person amount**. All three are formatted to two decimal
  places (for example `15.00`, not `15`).
- A **validation message** that appears whenever any input is invalid (see
  Invalid input below). While it is showing, the three outputs must not display
  computed numbers (blank them out, show a dash, or hide them — any of these is
  fine, but do not display stale values).

### JSON API

The same origin exposes two JSON endpoints:

`GET /api/health` — returns HTTP `200` once the app is ready. Body is any valid
JSON (for example `{"ok": true}`). Used by the healthcheck.

`GET /api/calculate?bill=<num>&tip=<num>&people=<int>` — computes the tip.
`people` is optional and defaults to `1`. On success returns HTTP `200` and a
JSON object with **exactly** these field names:

```json
{
  "bill": 100.00,
  "tip_percent": 15.00,
  "people": 1,
  "tip_amount": 15.00,
  "total": 115.00,
  "per_person": 115.00
}
```

Field types:

- `bill`, `tip_percent`, `tip_amount`, `total`, `per_person` are JSON numbers
  rounded to exactly 2 decimal places (see Rounding below).
- `people` is a JSON integer.

The page must produce the same numbers the API produces for the same inputs —
mechanically consistent, not "roughly the same".

### Rounding

Compute in full precision, then round **each** returned monetary field to two
decimal places using **half-up rounding** (0.005 rounds to 0.01, not to 0.00).

Concrete examples the grader will hold you to:

| bill | tip_percent | people | tip_amount | total  | per_person |
|-----:|------------:|-------:|-----------:|-------:|-----------:|
| 100  | 15          | 1      | 15.00      | 115.00 | 115.00     |
| 100  | 20          | 4      | 20.00      | 120.00 | 30.00      |
| 50   | 18          | 3      | 9.00       | 59.00  | 19.67      |
| 99.99| 18          | 2      | 18.00      | 117.99 | 58.99      |
| 10   | 5           | 1      | 0.50       | 10.50  | 10.50      |
| 0.05 | 10          | 1      | 0.01       | 0.06   | 0.06       |

Row 4 shows how full-precision compute + per-field half-up round interact:
`99.99 * 0.18 = 17.9982` → `tip_amount = 18.00`; the untruncated total
`117.9882` divided by 2 is `58.9941` → `per_person = 58.99`. Round each field
from full precision at the very end; do not round intermediates and then
re-divide, which is a subtly different answer.

Row 6 shows the half-up rule itself: `0.05 * 0.10 = 0.005` → `0.01`.

### Invalid input

The endpoint (and the page) must reject the following with an HTTP `400` and a
JSON body of shape `{"error": "<human-readable reason>"}`:

- `bill` missing, empty, non-numeric, or negative
- `tip` missing, empty, non-numeric, or negative
- `people` present and either non-integer, less than `1`, or non-numeric

A `bill` of `0` is valid (produces zero everywhere). A `tip` of `0` is valid.

On the page, invalid input from the user must surface a **visible validation
message** somewhere the user can see it, and the three output numbers must not
show a stale computed value while the input is invalid.

---

## Technical requirements

- One process, one port. Any language and any runtime that is already on the
  agent's PATH is fine — Python's `http.server` is enough; a small Node or Go
  server is also fine. No build step required. No framework required. No
  database. No external services.
- The page and the JSON API share the same origin.
- Logging to stdout is enough. No log framework required.

---

## Constraints

- No backing services of any kind. No database, no cache, no queue, no auth,
  no external API. If your solution requires one, the solution is wrong.
- No dev server. Whatever you serve from must be able to answer requests
  after your session ends.
- No native mobile app. Responsive web only (a phone-width viewport is fine;
  the page does not need a fancy mobile layout).

---

## Deployment contract

Non-negotiable. The application is graded by a process that knows nothing
about your code, so the following must hold exactly.

- The app is reachable at the URL in the `APP_PUBLIC_URL` environment variable,
  served on the port in `APP_PUBLIC_PORT` (`4173`). Never hardcode the port —
  read it from the environment.
- `GET /api/health` returns `200` once the app is ready.
- The app starts from this environment image with **no manual steps**. The
  healthcheck must go green on its own.
- Reserve the directories `.browser_screenshots/` and `.downloads/` at the app
  root and leave them empty.
- Any static assets are served as-is; there is no build step.
- **The server must outlive your session.** Grading runs in a separate container
  *after* your session ends. Start the server fully detached, for example
  `setsid nohup <command> > /tmp/app.log 2>&1 < /dev/null &`, so it is not a
  child of your shell and not a session-scoped background job. A server started
  as an ordinary background job is killed the instant your session ends, and
  the app scores zero however correct it is.
- Bind to `0.0.0.0`, never `127.0.0.1` or `localhost` — the grader connects from
  a different container, so a loopback-only listener is unreachable.
- Before you finish, verify persistence yourself: confirm the listening process
  is still running with a parent that is not your shell, and that the port
  answers.
- There are no backing services. Do not download, install, compile or start
  a database, queue, cache, auth provider, or any other service. If you catch
  yourself typing `docker`, `psql`, `redis`, or `pocketbase`, stop.
- Write the default (empty) login section into `/app/USER_README.md` so a
  grader knows there are no credentials.

---

## Definition of done

The healthcheck is green; opening the app in a browser shows a working
calculator; typing values into the three inputs updates the three outputs live
with the exact numbers from the Rounding table above; the JSON endpoint returns
the exact field shape above; invalid input returns `400` with a JSON error and
the page shows a visible validation message. That is the whole task.
