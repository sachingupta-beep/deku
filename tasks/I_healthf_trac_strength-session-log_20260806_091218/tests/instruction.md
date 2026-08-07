# Ethara — Strength Session Log

Build and deploy a working web application from this brief. There is no starting codebase. When
you are done, a stranger must be able to open the app in a browser, sign in as the seeded lifter,
log a set of an exercise with a weight and a rep count, and see that set counted exactly once in
the per-exercise weekly trend — without hitting an error page. The hard part is that a set
submitted twice with the same identifier must be stored once and counted once, even when both
submissions arrive at the same moment; a separate verifier checks the database directly, so a set
that merely looks deduplicated on screen does not count.

## Overview

A lifter records every working set during a training session: which exercise, how much weight, how
many reps. Between training blocks they open the trend for one exercise and read whether the
weight is going up.

The log is written on a phone, mid-session, on an unreliable gym connection. A submission that
appears to fail gets retried. Every set therefore carries a client-generated identifier,
`set_uid`, and the app must treat a repeat of that identifier as the **same set** — not a second
one. A tracker that double-counts a retried set makes the lifter's own trend lie to them.

## User roles

One role: **lifter**. There is no signup and no administrator. Two accounts are seeded, both with
the password `deku-demo-pw-2026`:

| Account | Contents |
|---|---|
| `lifter@ethara.ai` | one finished session with three seeded sets |
| `lifter2@ethara.ai` | no sessions, no sets |

Sign-in exchanges email and password for a bearer token at `/api/auth/login`, which returns `200`
and a body carrying a `token` string. Every route under `/api` other than `/api/health` and
`/api/auth/login` requires an `Authorization: Bearer <token>` header and answers `401` without
one.

Every read and every write is scoped to the authenticated lifter's own rows. Authorization is
enforced **server-side on every mutating endpoint**. Hiding a control in the UI is not
authorization: a direct API call carrying no token, or carrying a token for one lifter against
another lifter's session, must be rejected by the server.

## Core features

1. **Log a set.** `POST /api/sets` with `session_id`, `exercise_slug`, `weight_kg`, `reps` and
   `set_uid` stores one set and returns `201` with the stored set. Sets are append-only:
   no edit, no delete.

2. **The same set never counts twice.** `set_uid` is unique per lifter and that uniqueness is
   enforced by the database, not by a check performed before the insert. Re-submitting a
   `set_uid` already stored for that lifter returns `200` and the **originally stored set** — same
   set id, same `weight_kg`, same `reps` — and writes no second row. A replay that carries a
   different `weight_kg` or `reps` still returns the originally stored values: first write wins,
   bodies are never merged. Two identical submissions arriving concurrently resolve to exactly one
   stored row.

3. **Per-exercise weekly trend.** `GET /api/trend?exercise=<slug>` returns `200` and a `series`
   array for the authenticated lifter, one entry per ISO week that has sets, oldest week first.
   Each entry carries `iso_week` labelled `YYYY-Www`, `top_weight_kg` (the heaviest single set
   that week), `volume_kg` (the sum of `weight_kg` × `reps` over that week's sets) and `set_count`
   (how many sets were counted). Weeks with no sets are omitted. Because a replay stores no row,
   a replay moves none of the three numbers.

4. **Session lifecycle.** `POST /api/sessions` opens a session and returns `201`. A lifter holds
   at most one session with status `open`; opening a second while one is `open` is rejected with
   `409`. `POST /api/sessions/{id}/finish` returns `200` and moves the status to `finished`.
   `GET /api/sessions` lists the caller's sessions, newest first. Statuses are lowercase exactly
   as written.

5. **Validation, each with an exact rejection.** A `weight_kg` of zero or less, a `reps` of zero
   or less, and an `exercise_slug` outside the seeded catalogue are each rejected with `422` and a
   message naming the reason, and no row is written. Logging a set into a session whose status is
   `finished` is rejected with `409`. Logging a set into a session belonging to another lifter is
   rejected with `404`.

6. **The exercise catalogue is closed.** `GET /api/exercises` returns `200` and exactly the three
   seeded exercises: `back-squat` (Back Squat), `bench-press` (Bench Press) and `deadlift`
   (Deadlift). The app never creates an exercise at runtime.

## User flow

Four routes: `/login`, `/` (today's session), `/history`, `/trend`.

An unauthenticated visit to any route other than `/login` redirects to `/login`. A successful
sign-in lands on `/`. An authenticated visit to `/login` redirects to `/`.

**Logging.** On `/`, the lifter sees either the open session or a control to start one. Starting a
session reveals a set-entry form with exercise, weight and reps. Submitting adds the set to the
session's set list immediately, showing its weight and reps. The lifter repeats this between sets.

**Retrying.** When a submission stalls and the client retries the same set, the set list still
shows that set exactly once, and `/trend` for that exercise is unchanged — `set_count` and
`volume_kg` do not move.

**Reading the trend.** On `/trend` the lifter picks an exercise and reads a weekly series, oldest
week first, each row showing the week label, top weight, volume and set count. For
`lifter@ethara.ai` and `back-squat`, week `2026-W28` shows a top weight of `105`, a volume of
`815` and a set count of `2`.

**Finishing.** Pressing Finish on the open session moves it to `finished` and withdraws the
set-entry form. A later attempt to log into it is refused with a message naming the reason.

Each surface has an explicit empty state — "No session open", "No sets logged yet", "No sessions
yet", "No sets logged for this exercise" — and a loading state. A rejected submission keeps the
entered values in the form and shows the reason; it never clears the form silently.

## UI/UX notes

**Dark mode is the designed mode**; a light mode is optional and ungraded. Exact palette:
background `#0F1115`, surface `#181B22`, text `#F2F4F8`, muted `#9AA3B2`, CTA `#4F8CFF` with
hover `#3B78EB`, border `#262A33`, success `#3DDC97`, warning `#F5B546`, danger `#FF5C5C`. Text
on background and text on surface both meet WCAG AA (at least 4.5:1).

Type: one system family, scale ratio 1.25 — `0.8rem` helper text, `1.0rem` body, `1.25rem`
section headings, `1.563rem` page title, `1.953rem` for the top-weight figure on a trend row. Body
line-height `1.5`. Weight, reps and volume columns use tabular figures so digits align.

Shape and density: `8px` radius on cards and inputs, `6px` on buttons, control height at least
`44px`, card padding `16px`, row rhythm `12px`, content width capped at `720px` and centred.

Motion: a new set row fades in and rises `8px` over `250ms` `cubic-bezier(0.16, 1, 0.3, 1)`;
button and banner transitions run `150ms` with the same easing. All motion is suppressed under
`prefers-reduced-motion: reduce`.

Accessibility: every control is keyboard reachable in DOM order with a visible `2px` CTA focus
ring; every input has an associated `<label>` and never relies on a placeholder alone; a rejected
submission announces its reason in an `aria-live="polite"` region; touch targets are at least
`44×44px`.

Responsiveness: one breakpoint at `768px`. Below it, a single column with the set-entry form above
the set list and trend rows stacked as cards. At or above it, the trend renders as a table with
the week label first. No horizontal scrolling at `375px` width.

## Technical requirements

Language and framework are yours. Behaviour at the HTTP boundary is fixed; internal structure is
not.

- Persistence is **PostgreSQL**, reached at `DATABASE_URL`.
- The `set_uid` uniqueness constraint is declared in PostgreSQL, unique per lifter. Do not rely on
  reading first and inserting second — two concurrent submissions of one `set_uid` must still
  resolve to a single stored row.
- Authentication is app-native email and password exchanged for a bearer token. No third-party
  identity provider.
- `GET /api/health` returns `200` once the app can serve, and requires no token.
- The HTTP API is served under the `/api` prefix on the same origin as the UI.
- Seeding is idempotent: starting the app twice against the same database must not duplicate rows.
- All timestamps are UTC. Weights are kilograms; there is no unit toggle.

## Data model

Three entities.

**exercise** — `slug` (unique, kebab-case, the value the API accepts) and `name` (title-case).
Seeded with exactly `back-squat`/Back Squat, `bench-press`/Bench Press, `deadlift`/Deadlift.

**session** — belongs to one lifter; carries `started_at` (UTC) and `status`, which is `open` or
`finished`, lowercase.

**set_entry** — belongs to one session; carries `exercise_slug`'s exercise, `set_uid`,
`weight_kg` (greater than zero), `reps` (an integer greater than zero) and a server-assigned
`logged_at` (UTC). `set_uid` is unique per lifter, enforced by a database constraint.

Seed data, for `lifter@ethara.ai`: one finished session in ISO week `2026-W28` holding exactly
three sets — `back-squat` at `100` kg for `5` reps with `set_uid` `seed-squat-w28-1`; `back-squat`
at `105` kg for `3` reps with `set_uid` `seed-squat-w28-2`; and `bench-press` at `60` kg for `8`
reps with `set_uid` `seed-bench-w28-1`. `lifter2@ethara.ai` is seeded with no sessions and no sets.

Both seeded accounts use the password `deku-demo-pw-2026`. Write these credentials to
`/app/USER_README.md`:

```
lifter@ethara.ai / deku-demo-pw-2026
lifter2@ethara.ai / deku-demo-pw-2026
```

## Build plan

1. Schema and idempotent seed, with the per-lifter `set_uid` uniqueness constraint created in the
   same migration as the set table.
2. Health and login; every other `/api` route `401` without a bearer token.
3. Sessions: open, list newest-first, finish, the one-open-session rule.
4. The idempotent set write: insert, let the database constraint decide, return the stored row.
5. The trend endpoint: group by ISO week in UTC, oldest first.
6. The rejection paths, each with its exact status.
7. The four UI routes with their empty, loading and error states.
8. Deploy per the deployment contract below.

## Constraints

- The backing services named in this brief are **already running** and reachable at their
  environment variables. Do not download, install, compile or start a copy of any of them.
- Use only the providers named in this brief. No edge functions.
- No persistent volumes, no fixed container names, no custom networks.
- No signup, no password reset, no second role, no sharing between lifters.
- Sets are append-only: no edit endpoint, no delete endpoint.
- The exercise catalogue is fixed at the three seeded rows and is never extended at runtime.
- Do not hardcode a host or a port; read them from the environment.

## Deployment contract

Your application is graded through a browser and over HTTP by a process that knows nothing about
your code, after your session has ended.

- The app must be reachable at `APP_PUBLIC_URL`. The port mapping is `${APP_PUBLIC_PORT}:4173` —
  `4173` is the container-internal port and `APP_PUBLIC_PORT` is what the outside world uses.
  Never hardcode either; read them from the environment.
- The HTTP API is served on that same origin under the `/api` prefix.
- `GET /api/health` returns `200` once the app is ready.
- The app starts from the environment image with no manual steps.
- Login credentials are written to `/app/USER_README.md` **in this exact shape**, one field per
  line, so the grader can read them without guessing:

  ```
  Email: lifter@ethara.ai
  Password: <the seeded password>
  ```

  A markdown table is also accepted, but the two lines above are the contract. The grader extracts
  only credential-shaped lines from this file; prose around them is ignored, so anything not in
  that shape is invisible to it. If the app has no login, say so explicitly.
- Reserved `.browser_screenshots/` and `.downloads/` directories exist at the app root, empty.
- Serve a production build behind a static or preview server — never a dev server.
- The server must outlive this session. Grading runs after your session ends. Start it fully
  detached:
  `setsid nohup <command> > /tmp/app.log 2>&1 < /dev/null &`
  An ordinary background job is killed the instant the session ends, and the app scores zero
  however correct it is.
- **Write `/app/start.sh`, and make it executable.** Grading may redeploy your app into a *clean*
  container: same base image, your `/app` files copied in, and nothing else — no processes running,
  no caches you warmed, no packages you installed outside `/app`, no state you created by hand.
  Postgres is still there at the same address, but **its data is re-created from scratch**, so any
  rows you wrote during this session are gone and your schema and seed must be applied by the
  script. `start.sh` is the only thing that turns your files back into a running app, so it must:
  - install whatever it needs (vendor dependencies into `/app`, or install them inside the script —
    do not assume anything you installed during this session still exists),
  - apply migrations and seed data against `DATABASE_URL`, and be safe to run against a database
    that is already populated as well as an empty one,
  - read the port from `APP_PUBLIC_PORT` and the database address from the environment, never
    hardcoded,
  - start the server detached exactly as described above,
  - exit `0` once the app is answering, and non-zero if it cannot start.
- **Prove `start.sh` works before you finish.** Kill every process you started, run
  `bash /app/start.sh` yourself, and confirm `GET /api/health` returns `200` afterwards. An app that
  only runs because of something you did by hand in this session is not a deployable app, and will
  score zero.
- Bind `0.0.0.0`, never `127.0.0.1` or `localhost`.
- Before finishing, verify persistence: the listening process's parent is not your shell, and the
  port still answers.
- The backing services named in this brief are already running and reachable at their environment
  variables. Do not download, install, compile or start a copy of any of them.
- Use only the providers named in this brief. No edge functions.
- No persistent volumes, no fixed container names, no custom networks.

## Definition of done

- A stranger signs in as `lifter@ethara.ai`, opens a session, logs a set, and sees it once.
- The same `set_uid` submitted twice yields `201` then `200`, both carrying the same stored set,
  and exactly one row exists.
- Two concurrent submissions of one `set_uid` leave exactly one stored row.
- `GET /api/trend?exercise=back-squat` for the seeded lifter reports week `2026-W28` with
  `top_weight_kg` `105`, `volume_kg` `815` and `set_count` `2`, and replaying a seeded `set_uid`
  leaves all three unchanged.
- Every rejection path returns its exact status and writes no row.
- The app answers at `APP_PUBLIC_URL` after the session ends.
