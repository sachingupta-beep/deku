# Checklist: Ethara Strength Session Log

Source: instruction.md
Sections present: overview, roles, features, flow, uiux, technical, datamodel, buildplan, constraints, deployment
Sections absent: none
Items: 146
Unpinned values flagged: 0

## C-OV Overview

- [ ] `C-OV-01` `capability` The app records one set of an exercise with a load in kilograms. `src: Overview para 1`
- [ ] `C-OV-02` `capability` The app records the rep count of a logged set. `src: Overview para 1`
- [ ] `C-OV-03` `capability` The app shows a per exercise trend of the recorded loads. `src: Overview para 1`
- [ ] `C-OV-04` `literal` The app treats a repeat of a stored `set_uid` as the same set. `src: Overview para 2`

## C-RL User roles

- [ ] `C-RL-01` `role` The app offers one role of lifter. `src: User roles para 1`
- [ ] `C-RL-02` `constraint` The app offers no signup route. `src: User roles para 1`
- [ ] `C-RL-03` `constraint` The app offers no administrator role. `src: User roles para 1`
- [ ] `C-RL-04` `literal` The app seeds the account `lifter@ethara.ai` with one finished session. `src: User roles, table row 1`
- [ ] `C-RL-05` `literal` The app seeds the account `lifter2@ethara.ai` with no sessions. `src: User roles, table row 2`
- [ ] `C-RL-06` `literal` The app accepts email with password at `/api/auth/login`. `src: User roles para 2`
- [ ] `C-RL-07` `literal` The app returns status `200` from a successful login. `src: User roles para 2`
- [ ] `C-RL-08` `literal` The app returns a `token` string in the login body. `src: User roles para 2`
- [ ] `C-RL-09` `literal` The app requires a bearer token on every `/api` route beyond health with login. `src: User roles para 2`
- [ ] `C-RL-10` `literal` The app returns status `401` to a request carrying no bearer token. `src: User roles para 2`
- [ ] `C-RL-11` `constraint` The app scopes every read to the authenticated lifter own rows. `src: User roles para 3`
- [ ] `C-RL-12` `constraint` The app scopes every write to the authenticated lifter own rows. `src: User roles para 3`
- [ ] `C-RL-13` `role` The app enforces authorization server side on every mutating endpoint. `src: User roles para 3`

## C-CF Core features

- [ ] `C-CF-01` `literal` The app stores one set from `/api/sets`. `src: Core features, rule 1`
- [ ] `C-CF-02` `literal` The app returns status `201` for a newly stored set. `src: Core features, rule 1`
- [ ] `C-CF-03` `data` The app accepts `session_id` in a set submission. `src: Core features, rule 1`
- [ ] `C-CF-04` `data` The app accepts `exercise_slug` in a set submission. `src: Core features, rule 1`
- [ ] `C-CF-05` `data` The app accepts `weight_kg` in a set submission. `src: Core features, rule 1`
- [ ] `C-CF-06` `data` The app accepts `reps` in a set submission. `src: Core features, rule 1`
- [ ] `C-CF-07` `data` The app accepts `set_uid` in a set submission. `src: Core features, rule 1`
- [ ] `C-CF-08` `constraint` The app offers no edit path for a stored set. `src: Core features, rule 1`
- [ ] `C-CF-09` `constraint` The app offers no delete path for a stored set. `src: Core features, rule 1`
- [ ] `C-CF-10` `data` The app keeps `set_uid` unique per lifter. `src: Core features, rule 2`
- [ ] `C-CF-11` `data` The app enforces the `set_uid` uniqueness in the database. `src: Core features, rule 2`
- [ ] `C-CF-12` `constraint` The app avoids resolving a duplicate submission by a lookup performed before the insert. `src: Core features, rule 2`
- [ ] `C-CF-13` `literal` The app returns status `200` for a resubmitted `set_uid`. `src: Core features, rule 2`
- [ ] `C-CF-14` `capability` The app returns the originally stored set for a resubmitted `set_uid`. `src: Core features, rule 2`
- [ ] `C-CF-15` `constraint` The app writes no second row for a resubmitted `set_uid`. `src: Core features, rule 2`
- [ ] `C-CF-16` `capability` The app returns the originally stored `weight_kg` for a replay carrying a different load. `src: Core features, rule 2`
- [ ] `C-CF-17` `capability` The app returns the originally stored `reps` for a replay carrying different reps. `src: Core features, rule 2`
- [ ] `C-CF-18` `constraint` The app stores exactly one row for two concurrent submissions of one `set_uid`. `src: Core features, rule 2`
- [ ] `C-CF-19` `literal` The app serves a trend at `/api/trend` for a named exercise. `src: Core features, rule 3`
- [ ] `C-CF-20` `literal` The app returns status `200` from the trend route. `src: Core features, rule 3`
- [ ] `C-CF-21` `data` The app returns a `series` array from the trend route. `src: Core features, rule 3`
- [ ] `C-CF-22` `constraint` The app scopes the trend to the authenticated lifter. `src: Core features, rule 3`
- [ ] `C-CF-23` `capability` The app emits one trend entry per ISO week holding sets. `src: Core features, rule 3`
- [ ] `C-CF-24` `capability` The app orders the trend series oldest week first. `src: Core features, rule 3`
- [ ] `C-CF-25` `literal` The app labels each trend entry `iso_week` in the form `YYYY-Www`. `src: Core features, rule 3`
- [ ] `C-CF-26` `data` The app reports `top_weight_kg` as the heaviest single set of a week. `src: Core features, rule 3`
- [ ] `C-CF-27` `data` The app reports `volume_kg` as the summed `weight_kg` times `reps` of a week. `src: Core features, rule 3`
- [ ] `C-CF-28` `data` The app reports `set_count` as the number of counted sets of a week. `src: Core features, rule 3`
- [ ] `C-CF-29` `constraint` The app omits a week holding no sets from the series. `src: Core features, rule 3`
- [ ] `C-CF-30` `constraint` The app leaves every trend number unmoved by a replayed set. `src: Core features, rule 3`
- [ ] `C-CF-31` `literal` The app opens a session from `/api/sessions` returning status `201`. `src: Core features, rule 4`
- [ ] `C-CF-32` `constraint` The app holds at most one session of status `open` per lifter. `src: Core features, rule 4`
- [ ] `C-CF-33` `literal` The app returns status `409` for a second open session attempt. `src: Core features, rule 4`
- [ ] `C-CF-34` `literal` The app finishes a session returning status `200`. `src: Core features, rule 4`
- [ ] `C-CF-35` `capability` The app moves a finished session to status `finished`. `src: Core features, rule 4`
- [ ] `C-CF-36` `capability` The app lists the caller sessions newest first. `src: Core features, rule 4`
- [ ] `C-CF-37` `literal` The app writes every session status in lowercase. `src: Core features, rule 4`
- [ ] `C-CF-38` `literal` The app returns status `422` for a `weight_kg` of zero or less. `src: Core features, rule 5`
- [ ] `C-CF-39` `literal` The app returns status `422` for a `reps` value of zero or less. `src: Core features, rule 5`
- [ ] `C-CF-40` `literal` The app returns status `422` for an unseeded `exercise_slug`. `src: Core features, rule 5`
- [ ] `C-CF-41` `capability` The app names the reason in a rejection message. `src: Core features, rule 5`
- [ ] `C-CF-42` `constraint` The app writes no row for a rejected submission. `src: Core features, rule 5`
- [ ] `C-CF-43` `literal` The app returns status `409` for a set logged into a finished session. `src: Core features, rule 5`
- [ ] `C-CF-44` `literal` The app returns status `404` for a set logged into another lifter session. `src: Core features, rule 5`
- [ ] `C-CF-45` `literal` The app serves the exercise catalogue at `/api/exercises` with status `200`. `src: Core features, rule 6`
- [ ] `C-CF-46` `literal` The app seeds the exercise `back-squat` named `Back Squat`. `src: Core features, rule 6`
- [ ] `C-CF-47` `literal` The app seeds the exercise `bench-press` named `Bench Press`. `src: Core features, rule 6`
- [ ] `C-CF-48` `literal` The app seeds the exercise `deadlift` named `Deadlift`. `src: Core features, rule 6`
- [ ] `C-CF-49` `constraint` The app creates no exercise at runtime. `src: Core features, rule 6`

## C-UF User flow

- [ ] `C-UF-01` `ui` The app serves a route `/login`. `src: User flow para 1`
- [ ] `C-UF-02` `ui` The app serves a route `/` showing the current session. `src: User flow para 1`
- [ ] `C-UF-03` `ui` The app serves a route `/history`. `src: User flow para 1`
- [ ] `C-UF-04` `ui` The app serves a route `/trend`. `src: User flow para 1`
- [ ] `C-UF-05` `ui` The app redirects an unauthenticated visitor to `/login`. `src: User flow para 2`
- [ ] `C-UF-06` `ui` The app lands a signed in lifter on `/`. `src: User flow para 2`
- [ ] `C-UF-07` `ui` The app redirects an authenticated visitor away from `/login`. `src: User flow para 2`
- [ ] `C-UF-08` `ui` The app offers a control to start a session on `/`. `src: User flow para 3`
- [ ] `C-UF-09` `ui` The app reveals a set entry form after a session starts. `src: User flow para 3`
- [ ] `C-UF-10` `ui` The app adds a submitted set to the session set list. `src: User flow para 3`
- [ ] `C-UF-11` `ui` The app shows the `weight_kg` of each listed set. `src: User flow para 3`
- [ ] `C-UF-12` `ui` The app shows the rep count of each listed set. `src: User flow para 3`
- [ ] `C-UF-13` `ui` The app shows a retried set exactly once in the set list. `src: User flow para 4`
- [ ] `C-UF-14` `ui` The app offers an exercise picker on `/trend`. `src: User flow para 5`
- [ ] `C-UF-15` `ui` The app withdraws the set entry form from a finished session. `src: User flow para 6`
- [ ] `C-UF-16` `ui` The app shows an empty state on each surface. `src: User flow para 7`
- [ ] `C-UF-17` `ui` The app shows a loading state on each surface. `src: User flow para 7`
- [ ] `C-UF-18` `ui` The app keeps the entered values in a form after a rejection. `src: User flow para 7`

## C-UX UI and UX notes

- [ ] `C-UX-01` `ui` The app designs the dark mode fully. `src: UI/UX notes para 1`
- [ ] `C-UX-02` `ui` The app uses the palette hex values named in the brief. `src: UI/UX notes para 1`
- [ ] `C-UX-03` `ui` The app meets WCAG AA contrast for text on background. `src: UI/UX notes para 1`
- [ ] `C-UX-04` `ui` The app uses the type scale ratio named in the brief. `src: UI/UX notes para 2`
- [ ] `C-UX-05` `ui` The app aligns numeric columns with tabular figures. `src: UI/UX notes para 2`
- [ ] `C-UX-06` `ui` The app sizes every control at least `44px` tall. `src: UI/UX notes para 3`
- [ ] `C-UX-07` `ui` The app caps content width at `720px`. `src: UI/UX notes para 3`
- [ ] `C-UX-08` `ui` The app animates a new set row over `250ms`. `src: UI/UX notes para 4`
- [ ] `C-UX-09` `ui` The app suppresses motion under a reduced motion preference. `src: UI/UX notes para 4`
- [ ] `C-UX-10` `ui` The app draws a visible focus ring on every control. `src: UI/UX notes para 5`
- [ ] `C-UX-11` `ui` The app associates a label with every input. `src: UI/UX notes para 5`
- [ ] `C-UX-12` `ui` The app announces a rejection reason in a polite live region. `src: UI/UX notes para 5`
- [ ] `C-UX-13` `ui` The app breaks the layout at `768px`. `src: UI/UX notes para 6`
- [ ] `C-UX-14` `ui` The app avoids horizontal scrolling at `375px` width. `src: UI/UX notes para 6`

## C-TR Technical requirements

- [ ] `C-TR-01` `contract` The app persists data in PostgreSQL at `DATABASE_URL`. `src: Technical requirements, bullet 1`
- [ ] `C-TR-02` `data` The app declares the `set_uid` uniqueness constraint in PostgreSQL. `src: Technical requirements, bullet 2`
- [ ] `C-TR-03` `capability` The app exchanges email with password for a bearer token. `src: Technical requirements, bullet 3`
- [ ] `C-TR-04` `constraint` The app uses no third party identity provider. `src: Technical requirements, bullet 3`
- [ ] `C-TR-05` `literal` The app serves `/api/health` with status `200` without a token. `src: Technical requirements, bullet 4`
- [ ] `C-TR-06` `literal` The app serves the HTTP API under the `/api` prefix. `src: Technical requirements, bullet 5`
- [ ] `C-TR-07` `constraint` The app seeds idempotently across a restart. `src: Technical requirements, bullet 6`
- [ ] `C-TR-08` `constraint` The app stores every timestamp in UTC. `src: Technical requirements, bullet 7`
- [ ] `C-TR-09` `constraint` The app offers no unit toggle for the load. `src: Technical requirements, bullet 7`

## C-DM Data model

- [ ] `C-DM-01` `data` The app keeps an exercise `slug` unique in kebab case. `src: Data model para 1`
- [ ] `C-DM-02` `data` The app keeps an exercise name in title case. `src: Data model para 1`
- [ ] `C-DM-03` `data` The app ties a session to one lifter. `src: Data model para 2`
- [ ] `C-DM-04` `data` The app stores a session `started_at` in UTC. `src: Data model para 2`
- [ ] `C-DM-05` `data` The app limits a session status to `open` with `finished`. `src: Data model para 2`
- [ ] `C-DM-06` `data` The app ties a set entry to one session. `src: Data model para 3`
- [ ] `C-DM-07` `data` The app requires a `weight_kg` above zero. `src: Data model para 3`
- [ ] `C-DM-08` `data` The app requires an integer `reps` above zero. `src: Data model para 3`
- [ ] `C-DM-09` `data` The app assigns `logged_at` on the server in UTC. `src: Data model para 3`
- [ ] `C-DM-10` `literal` The app seeds a session in ISO week `2026-W28` holding three sets. `src: Data model para 4`
- [ ] `C-DM-11` `literal` The app seeds a `back-squat` set of `100` kg for `5` reps under `seed-squat-w28-1`. `src: Data model para 4`
- [ ] `C-DM-12` `literal` The app seeds a `back-squat` set of `105` kg for `3` reps under `seed-squat-w28-2`. `src: Data model para 4`
- [ ] `C-DM-13` `literal` The app seeds a `bench-press` set of `60` kg for `8` reps under `seed-bench-w28-1`. `src: Data model para 4`
- [ ] `C-DM-14` `literal` The app seeds both accounts with the password `deku-demo-pw-2026`. `src: Data model para 5`
- [ ] `C-DM-15` `contract` The app writes the seeded credentials to `/app/USER_README.md`. `src: Data model para 5`

## C-BP Build plan

- [ ] `C-BP-01` `data` The app creates the `set_uid` uniqueness constraint in the set table migration. `src: Build plan, step 1`

## C-CN Constraints

- [ ] `C-CN-01` `constraint` The app starts no copy of a backing service. `src: Constraints, bullet 1`
- [ ] `C-CN-02` `constraint` The app uses only the providers named in the brief. `src: Constraints, bullet 2`
- [ ] `C-CN-03` `constraint` The app uses no edge function. `src: Constraints, bullet 2`
- [ ] `C-CN-04` `constraint` The app declares no persistent volume. `src: Constraints, bullet 3`
- [ ] `C-CN-05` `constraint` The app declares no fixed container name. `src: Constraints, bullet 3`
- [ ] `C-CN-06` `constraint` The app declares no custom network. `src: Constraints, bullet 3`
- [ ] `C-CN-07` `constraint` The app offers no password reset. `src: Constraints, bullet 4`
- [ ] `C-CN-08` `constraint` The app offers no sharing between lifters. `src: Constraints, bullet 4`
- [ ] `C-CN-09` `constraint` The app hardcodes no host. `src: Constraints, bullet 7`
- [ ] `C-CN-10` `constraint` The app hardcodes no port. `src: Constraints, bullet 7`

## C-DC Deployment contract

- [ ] `C-DC-01` `contract` The app answers at `APP_PUBLIC_URL`. `src: Deployment contract, bullet 1`
- [ ] `C-DC-02` `contract` The app listens on the container internal port `4173`. `src: Deployment contract, bullet 1`
- [ ] `C-DC-03` `contract` The app reads the public port from `APP_PUBLIC_PORT`. `src: Deployment contract, bullet 1`
- [ ] `C-DC-04` `contract` The app serves the API on the origin of the UI. `src: Deployment contract, bullet 2`
- [ ] `C-DC-05` `contract` The app returns status `200` from `/api/health` once ready. `src: Deployment contract, bullet 3`
- [ ] `C-DC-06` `contract` The app starts from the environment image with no manual step. `src: Deployment contract, bullet 4`
- [ ] `C-DC-07` `contract` The app writes login credentials to `/app/USER_README.md`. `src: Deployment contract, bullet 5`
- [ ] `C-DC-08` `contract` The app creates an empty `.browser_screenshots/` directory at the app root. `src: Deployment contract, bullet 6`
- [ ] `C-DC-09` `contract` The app creates an empty `.downloads/` directory at the app root. `src: Deployment contract, bullet 6`
- [ ] `C-DC-10` `contract` The app serves a production build behind a static server. `src: Deployment contract, bullet 7`
- [ ] `C-DC-11` `constraint` The app serves no dev server. `src: Deployment contract, bullet 7`
- [ ] `C-DC-12` `contract` The app starts detached so the server outlives the session. `src: Deployment contract, bullet 8`
- [ ] `C-DC-13` `contract` The app binds `0.0.0.0`. `src: Deployment contract, bullet 9`

## Pinned literals

| Value | What it is | Item | Stated in |
|---|---|---|---|
| `lifter@ethara.ai` | seeded lifter email | C-RL-04 | User roles table row 1 |
| `lifter2@ethara.ai` | second seeded lifter email | C-RL-05 | User roles table row 2 |
| `deku-demo-pw-2026` | password for both seeded accounts | C-DM-14 | Data model para 5 |
| `/api/auth/login` | login route | C-RL-06 | User roles para 2 |
| `/api/sets` | set logging route | C-CF-01 | Core features rule 1 |
| `/api/trend` | trend route | C-CF-19 | Core features rule 3 |
| `/api/sessions` | session route | C-CF-31 | Core features rule 4 |
| `/api/exercises` | exercise catalogue route | C-CF-45 | Core features rule 6 |
| `/api/health` | health route | C-TR-05 | Technical requirements bullet 4 |
| `/api` | API prefix | C-TR-06 | Technical requirements bullet 5 |
| `/login` | sign in route | C-UF-01 | User flow para 1 |
| `/` | session route | C-UF-02 | User flow para 1 |
| `/history` | session history route | C-UF-03 | User flow para 1 |
| `/trend` | trend route | C-UF-04 | User flow para 1 |
| `set_uid` | client supplied set identifier | C-OV-04 | Overview para 2 |
| `session_id` | set submission field | C-CF-03 | Core features rule 1 |
| `exercise_slug` | set submission field | C-CF-04 | Core features rule 1 |
| `weight_kg` | set weight field | C-CF-05 | Core features rule 1 |
| `reps` | set rep count field | C-CF-06 | Core features rule 1 |
| `series` | trend array field | C-CF-21 | Core features rule 3 |
| `iso_week` | trend week label field | C-CF-25 | Core features rule 3 |
| `YYYY-Www` | ISO week label format | C-CF-25 | Core features rule 3 |
| `top_weight_kg` | heaviest set of a week | C-CF-26 | Core features rule 3 |
| `volume_kg` | summed weight times reps of a week | C-CF-27 | Core features rule 3 |
| `set_count` | counted sets of a week | C-CF-28 | Core features rule 3 |
| `token` | login response field | C-RL-08 | User roles para 2 |
| `open` | session status | C-CF-32 | Core features rule 4 |
| `finished` | session status | C-CF-35 | Core features rule 4 |
| `200` | status for a login | C-RL-07 | User roles para 2 |
| `201` | status for a stored set | C-CF-02 | Core features rule 1 |
| `401` | status for a missing bearer token | C-RL-10 | User roles para 2 |
| `404` | status for another lifter session | C-CF-44 | Core features rule 5 |
| `409` | status for a second open session | C-CF-33 | Core features rule 4 |
| `422` | status for an invalid weight | C-CF-38 | Core features rule 5 |
| `back-squat` | seeded exercise slug | C-CF-46 | Core features rule 6 |
| `Back Squat` | seeded exercise name | C-CF-46 | Core features rule 6 |
| `bench-press` | seeded exercise slug | C-CF-47 | Core features rule 6 |
| `Bench Press` | seeded exercise name | C-CF-47 | Core features rule 6 |
| `deadlift` | seeded exercise slug | C-CF-48 | Core features rule 6 |
| `Deadlift` | seeded exercise name | C-CF-48 | Core features rule 6 |
| `2026-W28` | seeded ISO week | C-DM-10 | Data model para 4 |
| `seed-squat-w28-1` | seeded set identifier | C-DM-11 | Data model para 4 |
| `seed-squat-w28-2` | seeded set identifier | C-DM-12 | Data model para 4 |
| `seed-bench-w28-1` | seeded set identifier | C-DM-13 | Data model para 4 |
| `100` | seeded squat weight in kg | C-DM-11 | Data model para 4 |
| `5` | seeded squat rep count | C-DM-11 | Data model para 4 |
| `105` | seeded squat weight in kg | C-DM-12 | Data model para 4 |
| `3` | seeded squat rep count | C-DM-12 | Data model para 4 |
| `60` | seeded bench weight in kg | C-DM-13 | Data model para 4 |
| `8` | seeded bench rep count | C-DM-13 | Data model para 4 |
| `DATABASE_URL` | database connection variable | C-TR-01 | Technical requirements bullet 1 |
| `APP_PUBLIC_URL` | public app address variable | C-DC-01 | Deployment contract bullet 1 |
| `APP_PUBLIC_PORT` | public port variable | C-DC-03 | Deployment contract bullet 1 |
| `4173` | container internal port | C-DC-02 | Deployment contract bullet 1 |
| `0.0.0.0` | bind address | C-DC-13 | Deployment contract bullet 9 |
| `/app/USER_README.md` | credentials file path | C-DC-07 | Deployment contract bullet 5 |
| `.browser_screenshots/` | reserved directory | C-DC-08 | Deployment contract bullet 6 |
| `.downloads/` | reserved directory | C-DC-09 | Deployment contract bullet 6 |
| `44px` | minimum control height | C-UX-06 | UI/UX notes para 3 |
| `720px` | maximum content width | C-UX-07 | UI/UX notes para 3 |
| `250ms` | set row animation duration | C-UX-08 | UI/UX notes para 4 |
| `768px` | layout breakpoint | C-UX-13 | UI/UX notes para 6 |
| `375px` | narrow viewport width | C-UX-14 | UI/UX notes para 6 |

## Coverage ledger

| Section | Obligation-bearing sentences | Items produced |
|---|---|---|
| Overview | 1 | 4 |
| User roles | 3 | 13 |
| Core features | 9 | 49 |
| User flow | 5 | 18 |
| UI/UX notes | 0 | 14 |
| Technical requirements | 3 | 9 |
| Data model | 0 | 15 |
| Build plan | 1 | 1 |
| Constraints | 0 | 10 |
| Deployment contract | 5 | 13 |
