# Checklist: Ethara Revenue Desk

Source: instruction.md
Sections present: overview, roles, features, flow, uiux, technical, datamodel, constraints, deployment
Sections absent: buildplan
Items: 305
Unpinned values flagged: 1

## C-OV Overview

- [ ] `C-OV-01` `capability` The app publishes a revenue report over a closed date period. `src: Overview para 1`
- [ ] `C-OV-02` `capability` The app shows a grand total for a report. `src: Overview para 1`
- [ ] `C-OV-03` `capability` The app shows a breakdown by region for a report. `src: Overview para 1`
- [ ] `C-OV-04` `capability` The app shows a breakdown by product line for a report. `src: Overview para 1`
- [ ] `C-OV-05` `data` The app computes every report figure at the moment the page is read. `src: Overview para 1`
- [ ] `C-OV-06` `role` The app shows a manager their own region in all three figures. `src: Overview para 3`
- [ ] `C-OV-07` `constraint` The app keeps the three views of one period in agreement with each other. `src: Overview para 3`

## C-RL User roles

- [ ] `C-RL-01` `role` An analyst reads every report, `draft` or `published`. `src: User roles table row 1`
- [ ] `C-RL-02` `role` An analyst reads every region. `src: User roles table row 1`
- [ ] `C-RL-03` `role` An analyst reads every product line. `src: User roles table row 1`
- [ ] `C-RL-04` `role` An analyst creates a report. `src: User roles table row 1`
- [ ] `C-RL-05` `role` An analyst publishes a report once. `src: User roles table row 1`
- [ ] `C-RL-06` `role` A manager reads `published` reports only. `src: User roles table row 2`
- [ ] `C-RL-07` `role` A manager reads only their own region's figures inside a report. `src: User roles table row 2`
- [ ] `C-RL-08` `constraint` A manager reads no `draft` report. `src: User roles table row 2`
- [ ] `C-RL-09` `constraint` A manager reads no other region's rows. `src: User roles table row 2`
- [ ] `C-RL-10` `constraint` A manager writes nothing. `src: User roles table row 2`
- [ ] `C-RL-11` `constraint` The app enforces authorization server-side on every mutating endpoint. `src: User roles, authorization para`
- [ ] `C-RL-12` `constraint` The app enforces authorization on every read that would return another region's rows. `src: User roles, authorization para`
- [ ] `C-RL-13` `constraint` The app rejects a manager call to an analyst-only endpoint with `401` or `403`. `src: User roles, authorization para`
- [ ] `C-RL-14` `constraint` The app offers no way to create an account. `src: User roles, signup para`
- [ ] `C-RL-15` `literal` The app accepts `deku-demo-pw-2026` at login for every seeded account. `src: User roles, signup para`
- [ ] `C-RL-16` `data` The app seeds three accounts. `src: User roles, accounts table`

## C-CF Core features

- [ ] `C-CF-01` `capability` The app returns an access token from `POST /api/auth/login`. `src: Core features, Sign in`
- [ ] `C-CF-02` `constraint` The app requires a bearer token on every endpoint except `GET /api/health`. `src: Core features, Sign in`
- [ ] `C-CF-03` `constraint` The app rejects a missing, malformed or expired token with `401`. `src: Core features, Sign in`
- [ ] `C-CF-04` `capability` The app returns the caller's `role` from `GET /api/me`. `src: Core features, Sign in`
- [ ] `C-CF-05` `capability` The app returns the caller's `region` from `GET /api/me`. `src: Core features, Sign in`
- [ ] `C-CF-06` `capability` The app creates a `draft` report from `POST /api/reports` on an analyst token. `src: Core features, Reports rule 1`
- [ ] `C-CF-07` `data` The app treats both report period dates as inclusive. `src: Core features, Reports rule 1`
- [ ] `C-CF-08` `constraint` The app rejects a `period_end` earlier than `period_start` with `400`. `src: Core features, Reports rule 1`
- [ ] `C-CF-09` `constraint` The app names the reason on a rejected report creation. `src: Core features, Reports rule 1`
- [ ] `C-CF-10` `constraint` The app creates no report row when the period is rejected. `src: Core features, Reports rule 1`
- [ ] `C-CF-11` `capability` The app turns a `draft` report `published` from `POST /api/reports/{id}/publish`. `src: Core features, Reports rule 2`
- [ ] `C-CF-12` `capability` The app stamps `published_at` on a successful publish. `src: Core features, Reports rule 2`
- [ ] `C-CF-13` `capability` The app returns `200` from a successful publish. `src: Core features, Reports rule 2`
- [ ] `C-CF-14` `constraint` The app rejects a second publish of the same report with `409`. `src: Core features, Reports rule 2`
- [ ] `C-CF-15` `constraint` The app leaves `published_at` unmoved on a second publish. `src: Core features, Reports rule 2`
- [ ] `C-CF-16` `capability` The app returns a JSON array from `GET /api/reports`. `src: Core features, Reports rule 3`
- [ ] `C-CF-17` `role` The app returns all reports to an analyst from `GET /api/reports`. `src: Core features, Reports rule 3`
- [ ] `C-CF-18` `role` The app returns only `published` reports to a manager from `GET /api/reports`. `src: Core features, Reports rule 3`
- [ ] `C-CF-19` `constraint` The app returns `404` to a manager asking for a `draft` report by id. `src: Core features, Reports rule 3`
- [ ] `C-CF-20` `constraint` The app rejects a manager token on either write endpoint with `401` or `403`. `src: Core features, Reports rule 4`
- [ ] `C-CF-21` `constraint` The app changes no row when a manager write is rejected. `src: Core features, Reports rule 4`
- [ ] `C-CF-22` `data` The app returns `report_id`, `total`, `by_region`, `by_product_line` from the summary endpoint. `src: Core features, summary rule 5`
- [ ] `C-CF-23` `data` The app derives every summary figure on the read that asks for the figure. `src: Core features, summary rule 5`
- [ ] `C-CF-24` `data` The app counts a transaction whose `occurred_on` lies inside the report period. `src: Core features, summary rule 5`
- [ ] `C-CF-25` `data` The app counts a transaction whose `status` is `settled`. `src: Core features, summary rule 5`
- [ ] `C-CF-26` `constraint` The app counts no `refunded` transaction in any figure. `src: Core features, summary rule 5`
- [ ] `C-CF-27` `constraint` The app counts no `void` transaction in any figure. `src: Core features, summary rule 5`
- [ ] `C-CF-28` `data` The app makes `total` equal the sum of the `by_region` totals. `src: Core features, summary rule 6`
- [ ] `C-CF-29` `data` The app makes `total` equal the sum of the `by_product_line` totals. `src: Core features, summary rule 6`
- [ ] `C-CF-30` `literal` The app returns `total` `415000` to an analyst for `January 2026 Revenue`. `src: Core features, summary rule 6`
- [ ] `C-CF-31` `literal` The app returns region totals `195000`, `150000`, `70000` to an analyst for `January 2026 Revenue`. `src: Core features, summary rule 6`
- [ ] `C-CF-32` `literal` The app returns product line totals `325000`, `90000` to an analyst for `January 2026 Revenue`. `src: Core features, summary rule 6`
- [ ] `C-CF-33` `capability` The app returns a JSON array from `GET /api/reports/{id}/transactions`. `src: Core features, summary rule 7`
- [ ] `C-CF-34` `data` The app returns exactly the rows behind the summary from the transactions endpoint. `src: Core features, summary rule 7`
- [ ] `C-CF-35` `data` The app makes the returned row amounts sum to the caller's `total`. `src: Core features, summary rule 7`
- [ ] `C-CF-36` `constraint` The app returns `total` `0` for a period holding no matching rows. `src: Core features, summary rule 7`
- [ ] `C-CF-37` `constraint` The app returns empty breakdown arrays for a period holding no matching rows. `src: Core features, summary rule 7`
- [ ] `C-CF-38` `role` The app narrows every figure to a manager's own region. `src: Core features, region scope rule 8`
- [ ] `C-CF-39` `data` The app returns one `by_region` entry to a manager. `src: Core features, region scope rule 8`
- [ ] `C-CF-40` `literal` The app returns `195000` over three rows to `manager@example.com`. `src: Core features, region scope rule 8`
- [ ] `C-CF-41` `literal` The app returns `150000` over two rows to `manager2@example.com`. `src: Core features, region scope rule 8`
- [ ] `C-CF-42` `constraint` The app rejects a manager summary request naming another region with `403`. `src: Core features, region scope rule 9`
- [ ] `C-CF-43` `constraint` The app returns no figure for a region a manager may not read. `src: Core features, region scope rule 9`
- [ ] `C-CF-44` `role` The app accepts any region name on a summary request from an analyst. `src: Core features, region scope rule 9`
- [ ] `C-CF-45` `role` The app returns all regions to an analyst from `GET /api/regions`. `src: Core features, region scope rule 10`
- [ ] `C-CF-46` `role` The app returns only the caller's own region to a manager from `GET /api/regions`. `src: Core features, region scope rule 10`
- [ ] `C-CF-47` `capability` The app returns `Aurora`, `Basalt` from `GET /api/product-lines`. `src: Core features, region scope rule 10`
- [ ] `C-CF-48` `data` Each `by_region` entry holds a `region` name beside a `total`. `src: Core features, summary rule 5`
- [ ] `C-CF-49` `data` Each `by_product_line` entry holds a `product_line` name beside a `total`. `src: Core features, summary rule 5`
- [ ] `C-CF-50` `data` The app returns six rows to an analyst behind `January 2026 Revenue`. `src: Definition of done, sentence 4`

## C-UF User flow

- [ ] `C-UF-01` `ui` The app serves a sign-in page at `/login` without a token. `src: User flow route table row 1`
- [ ] `C-UF-02` `ui` The app serves a report list at the root route to any signed-in role. `src: User flow route table row 2`
- [ ] `C-UF-03` `ui` The app orders the report list newest first. `src: User flow route table row 2`
- [ ] `C-UF-04` `ui` The app serves a report creation page at `/reports/new` to an analyst. `src: User flow route table row 3`
- [ ] `C-UF-05` `ui` The app serves a report summary at `/reports/:id` to any signed-in role. `src: User flow route table row 4`
- [ ] `C-UF-06` `ui` The app serves the underlying rows at `/reports/:id/transactions` to any signed-in role. `src: User flow route table row 5`
- [ ] `C-UF-07` `capability` The app redirects an unauthenticated visitor on a protected route to `/login`. `src: User flow, entry para`
- [ ] `C-UF-08` `capability` The app carries the requested path in a `next` query parameter on redirect. `src: User flow, entry para`
- [ ] `C-UF-09` `capability` The app sends a signed-in user to the `next` path after login. `src: User flow, entry para`
- [ ] `C-UF-10` `capability` The app sends a signed-in user to the root route after login without a `next` path. `src: User flow, entry para`
- [ ] `C-UF-11` `capability` The app clears the token on logout. `src: User flow, entry para`
- [ ] `C-UF-12` `capability` The app returns to `/login` on logout. `src: User flow, entry para`
- [ ] `C-UF-13` `capability` The app clears a token that expires mid-action. `src: User flow, entry para`
- [ ] `C-UF-14` `ui` The app shows a session-expired message after a token expires. `src: User flow, entry para`
- [ ] `C-UF-15` `constraint` The app blocks a manager opening `/reports/new` with a permission message. `src: User flow, entry para`
- [ ] `C-UF-16` `ui` The app shows the not-found card to a manager opening a `draft` report. `src: User flow, entry para`
- [ ] `C-UF-17` `ui` The app shows an empty state on every list. `src: User flow, states para`
- [ ] `C-UF-18` `ui` The app shows a loading state on every page. `src: User flow, states para`
- [ ] `C-UF-19` `ui` The app renders a not-found card for a missing report. `src: User flow, states para`
- [ ] `C-UF-20` `ui` The app names the reason on a rejected request. `src: User flow, states para`
- [ ] `C-UF-21` `ui` The app survives a rejected request without crashing. `src: User flow, states para`
- [ ] `C-UF-22` `literal` The `North` manager sees `TX-1001`, `TX-1002`, `TX-1003` behind `January 2026 Revenue`. `src: User flow, journey 2`

## C-UX UI and UX notes

- [ ] `C-UX-01` `ui` The app designs light mode fully. `src: UI/UX notes para 1`
- [ ] `C-UX-02` `ui` The app leaves dark mode optional. `src: UI/UX notes para 1`
- [ ] `C-UX-03` `ui` The app uses background `#F7F8FA`. `src: UI/UX notes, palette para`
- [ ] `C-UX-04` `ui` The app uses surface `#FFFFFF`. `src: UI/UX notes, palette para`
- [ ] `C-UX-05` `ui` The app uses text `#0F172A`. `src: UI/UX notes, palette para`
- [ ] `C-UX-06` `ui` The app uses muted `#64748B`. `src: UI/UX notes, palette para`
- [ ] `C-UX-07` `ui` The app uses primary `#1D4ED8`. `src: UI/UX notes, palette para`
- [ ] `C-UX-08` `ui` The app uses primary hover `#1E40AF`. `src: UI/UX notes, palette para`
- [ ] `C-UX-09` `ui` The app uses border `#E2E8F0`. `src: UI/UX notes, palette para`
- [ ] `C-UX-10` `ui` The app uses danger `#B91C1C`. `src: UI/UX notes, palette para`
- [ ] `C-UX-11` `ui` The app uses success `#15803D`. `src: UI/UX notes, palette para`
- [ ] `C-UX-12` `ui` The app uses warning `#B45309`. `src: UI/UX notes, palette para`
- [ ] `C-UX-13` `ui` The app uses accent `#0E7490`. `src: UI/UX notes, palette para`
- [ ] `C-UX-14` `ui` The app colours a `settled` transaction `#15803D`. `src: UI/UX notes, palette para`
- [ ] `C-UX-15` `ui` The app colours a `refunded` transaction `#B45309`. `src: UI/UX notes, palette para`
- [ ] `C-UX-16` `ui` The app colours a `void` transaction `#64748B`. `src: UI/UX notes, palette para`
- [ ] `C-UX-17` `ui` The app colours a `draft` report `#64748B`. `src: UI/UX notes, palette para`
- [ ] `C-UX-18` `ui` The app colours a `published` report `#1D4ED8`. `src: UI/UX notes, palette para`
- [ ] `C-UX-19` `ui` The app sets `Inter` as the font family throughout. `src: UI/UX notes, type para`
- [ ] `C-UX-20` `ui` The app sets the heading scale to `32/40`, `24/32`, `20/28`. `src: UI/UX notes, type para`
- [ ] `C-UX-21` `ui` The app sets body type to `15/24`. `src: UI/UX notes, type para`
- [ ] `C-UX-22` `ui` The app sets caption type to `13/18`. `src: UI/UX notes, type para`
- [ ] `C-UX-23` `ui` The app uses tabular numerals on every amount, count, date. `src: UI/UX notes, type para`
- [ ] `C-UX-24` `ui` The app renders money as `$1,950.00`. `src: UI/UX notes, type para`
- [ ] `C-UX-25` `ui` The app uses an `8px` radius on cards, tables. `src: UI/UX notes, shape para`
- [ ] `C-UX-26` `ui` The app uses a `6px` radius on buttons, inputs. `src: UI/UX notes, shape para`
- [ ] `C-UX-27` `ui` The app draws `1px` borders in `#E2E8F0`. `src: UI/UX notes, shape para`
- [ ] `C-UX-28` `ui` The app applies one elevation on the summary cards. `src: UI/UX notes, shape para`
- [ ] `C-UX-29` `ui` The app sizes rows, buttons, inputs at `40px`. `src: UI/UX notes, shape para`
- [ ] `C-UX-30` `ui` The app places input labels above the input. `src: UI/UX notes, shape para`
- [ ] `C-UX-31` `ui` The app places input errors below the input in `#B91C1C`. `src: UI/UX notes, shape para`
- [ ] `C-UX-32` `ui` The app draws a `2px` focus ring in `#1D4ED8`. `src: UI/UX notes, shape para`
- [ ] `C-UX-33` `ui` The app right-aligns amounts. `src: UI/UX notes, shape para`
- [ ] `C-UX-34` `ui` The app closes toasts on Escape. `src: UI/UX notes, shape para`
- [ ] `C-UX-35` `ui` The app closes modals on Escape. `src: UI/UX notes, shape para`
- [ ] `C-UX-36` `ui` The app confirms before publishing. `src: UI/UX notes, shape para`
- [ ] `C-UX-37` `ui` The app animates transitions at `150ms`. `src: UI/UX notes, motion para`
- [ ] `C-UX-38` `ui` The app animates entering elements at `250ms`. `src: UI/UX notes, motion para`
- [ ] `C-UX-39` `ui` The app eases motion with `cubic-bezier(0.16, 1, 0.3, 1)`. `src: UI/UX notes, motion para`
- [ ] `C-UX-40` `constraint` The app applies no bounce to motion. `src: UI/UX notes, motion para`
- [ ] `C-UX-41` `constraint` The app applies no counting-up animation to totals. `src: UI/UX notes, motion para`
- [ ] `C-UX-42` `ui` The app removes transitions under `prefers-reduced-motion: reduce`. `src: UI/UX notes, motion para`
- [ ] `C-UX-43` `ui` The app sets breakpoints at `640`, `768`, `1024`. `src: UI/UX notes, responsive para`
- [ ] `C-UX-44` `ui` The app stacks the breakdown cards below `768`. `src: UI/UX notes, responsive para`
- [ ] `C-UX-45` `ui` The app scrolls each table inside its own card. `src: UI/UX notes, responsive para`
- [ ] `C-UX-46` `constraint` The app never scrolls the page sideways. `src: UI/UX notes, responsive para`
- [ ] `C-UX-47` `ui` The app holds its layout at `1920x1200`, `768x1024`, `390x844`. `src: UI/UX notes, responsive para`
- [ ] `C-UX-48` `ui` The app sizes touch targets at `44x44` or larger. `src: UI/UX notes, responsive para`
- [ ] `C-UX-49` `ui` The app meets WCAG AA contrast of `4.5:1`. `src: UI/UX notes, responsive para`
- [ ] `C-UX-50` `ui` The app supports keyboard navigation with visible focus rings. `src: UI/UX notes, responsive para`
- [ ] `C-UX-51` `ui` The app labels icon-only controls. `src: UI/UX notes, responsive para`
- [ ] `C-UX-52` `ui` The app shows every status as a word. `src: UI/UX notes, responsive para`

## C-TR Technical requirements

- [ ] `C-TR-01` `capability` The app builds its frontend with React 18 on Vite. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-02` `capability` The app compiles TypeScript in strict mode. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-03` `capability` The app styles with Tailwind CSS v3. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-04` `capability` The app holds server state in TanStack Query. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-05` `capability` The app routes with React Router v6. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-06` `capability` The app builds the create-report form with react-hook-form. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-07` `capability` The app validates the create-report form with Zod. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-08` `capability` A typed fetch wrapper attaches the bearer token. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-09` `capability` A typed fetch wrapper normalises a `401`. `src: Technical requirements, frontend bullet`
- [ ] `C-TR-10` `capability` The app runs Python 3.12 with FastAPI on Uvicorn. `src: Technical requirements, backend bullet`
- [ ] `C-TR-11` `capability` The app speaks REST over JSON. `src: Technical requirements, backend bullet`
- [ ] `C-TR-12` `capability` The app models settings with Pydantic v2. `src: Technical requirements, backend bullet`
- [ ] `C-TR-13` `capability` The app models requests, responses with Pydantic v2. `src: Technical requirements, backend bullet`
- [ ] `C-TR-14` `capability` The app reaches PostgreSQL at `DATABASE_URL`. `src: Technical requirements, database bullet`
- [ ] `C-TR-15` `capability` The app maps tables with SQLAlchemy 2.0 typed models. `src: Technical requirements, database bullet`
- [ ] `C-TR-16` `capability` The app migrates forward-only with Alembic. `src: Technical requirements, database bullet`
- [ ] `C-TR-17` `capability` The app holds email, password authentication itself. `src: Technical requirements, auth bullet`
- [ ] `C-TR-18` `capability` The app hashes passwords with bcrypt. `src: Technical requirements, auth bullet`
- [ ] `C-TR-19` `literal` The app issues a bearer token lasting `12 hours`. `src: Technical requirements, auth bullet`
- [ ] `C-TR-20` `capability` The app resolves the caller's role from the token subject. `src: Technical requirements, auth bullet`
- [ ] `C-TR-21` `capability` The app resolves the caller's region from the token subject. `src: Technical requirements, auth bullet`
- [ ] `C-TR-22` `constraint` The app refuses a client-supplied region that is not the caller's own. `src: Technical requirements, auth bullet`
- [ ] `C-TR-23` `constraint` The app stores no total anywhere. `src: Technical requirements, aggregation bullet`
- [ ] `C-TR-24` `data` A changed transaction `status` moves the next summary read by exactly that amount. `src: Technical requirements, aggregation bullet`
- [ ] `C-TR-25` `data` The scope filter, the aggregate come from one row set. `src: Technical requirements, aggregation bullet`
- [ ] `C-TR-26` `data` Two simultaneous publish requests produce exactly one `200`. `src: Technical requirements, publishing bullet`
- [ ] `C-TR-27` `data` Two simultaneous publish requests produce exactly one `409`. `src: Technical requirements, publishing bullet`
- [ ] `C-TR-28` `constraint` A set `published_at` never moves again. `src: Technical requirements, publishing bullet`
- [ ] `C-TR-29` `constraint` A later publish request still reads `409`. `src: Technical requirements, publishing bullet`
- [ ] `C-TR-30` `capability` The app writes structured JSON logs to stdout. `src: Technical requirements, logging bullet`
- [ ] `C-TR-31` `capability` The app writes one log record per request. `src: Technical requirements, logging bullet`
- [ ] `C-TR-32` `constraint` The app uses only the named libraries plus their direct dependencies. `src: Technical requirements, closing para`
- [ ] `C-TR-33` `constraint` The app introduces no second database. `src: Technical requirements, closing para`
- [ ] `C-TR-34` `constraint` The app introduces no queue. `src: Technical requirements, closing para`
- [ ] `C-TR-35` `constraint` The app introduces no object store. `src: Technical requirements, closing para`
- [ ] `C-TR-36` `constraint` The app introduces no identity provider. `src: Technical requirements, closing para`
- [ ] `C-TR-37` `constraint` The app introduces no mail vendor. `src: Technical requirements, closing para`

## C-DM Data model

- [ ] `C-DM-01` `data` The app holds five tables. `src: Data model para 1`
- [ ] `C-DM-02` `data` The app records all timestamps in UTC. `src: Data model para 1`
- [ ] `C-DM-03` `data` The app records every amount as an integer in minor units of `usd`. `src: Data model para 1`
- [ ] `C-DM-04` `literal` The app accepts `deku-demo-pw-2026` at login. `src: Data model, password para`
- [ ] `C-DM-05` `contract` The app writes the password into `/app/USER_README.md` beside each account. `src: Data model, password para`
- [ ] `C-DM-06` `data` The `users` table holds a unique lowercased `email`. `src: Data model, users para`
- [ ] `C-DM-07` `data` The `users` table holds a `password_hash`. `src: Data model, users para`
- [ ] `C-DM-08` `data` The `users` table holds a `name`. `src: Data model, users para`
- [ ] `C-DM-09` `data` The `users` table holds a `role` of `analyst` or `manager`. `src: Data model, users para`
- [ ] `C-DM-10` `data` The `users` table sets `region_id` for a manager. `src: Data model, users para`
- [ ] `C-DM-11` `data` The `users` table leaves `region_id` empty for an analyst. `src: Data model, users para`
- [ ] `C-DM-12` `data` The `regions` table holds a unique `name`. `src: Data model, regions para`
- [ ] `C-DM-13` `data` The `product_lines` table holds a unique `name`. `src: Data model, product lines para`
- [ ] `C-DM-14` `data` The `transactions` table holds a unique `external_ref`. `src: Data model, transactions para`
- [ ] `C-DM-15` `data` The `transactions` table references `regions`. `src: Data model, transactions para`
- [ ] `C-DM-16` `data` The `transactions` table references `product_lines`. `src: Data model, transactions para`
- [ ] `C-DM-17` `data` The `transactions` table holds a never-negative integer `amount`. `src: Data model, transactions para`
- [ ] `C-DM-18` `data` The `transactions` table holds `occurred_on` as a UTC calendar date. `src: Data model, transactions para`
- [ ] `C-DM-19` `data` The `transactions` table holds a `status` of `settled`, `refunded` or `void`. `src: Data model, transactions para`
- [ ] `C-DM-20` `data` The `reports` table holds a `title`. `src: Data model, reports para`
- [ ] `C-DM-21` `data` The `reports` table holds `period_start` as a date. `src: Data model, reports para`
- [ ] `C-DM-22` `data` The `reports` table holds `period_end` as a date. `src: Data model, reports para`
- [ ] `C-DM-23` `constraint` The `reports` table keeps `period_end` no earlier than `period_start`. `src: Data model, reports para`
- [ ] `C-DM-24` `data` The `reports` table holds a `status` of `draft` or `published`. `src: Data model, reports para`
- [ ] `C-DM-25` `data` The `reports` table references an analyst in `created_by`. `src: Data model, reports para`
- [ ] `C-DM-26` `data` The `reports` table leaves `published_at` empty exactly when `status` is `draft`. `src: Data model, reports para`
- [ ] `C-DM-27` `constraint` No table carries an aggregate column. `src: Data model, derived para`
- [ ] `C-DM-28` `constraint` The app holds no summary table. `src: Data model, derived para`
- [ ] `C-DM-29` `data` A transaction belongs to a report when `occurred_on` falls inside the report period. `src: Data model, derived para`
- [ ] `C-DM-30` `data` A transaction belongs to a report when the transaction `status` is `settled`. `src: Data model, derived para`
- [ ] `C-DM-31` `literal` The app seeds regions `North`, `South`, `West`. `src: Data model, seed data bullet 1`
- [ ] `C-DM-32` `literal` The app seeds product lines `Aurora`, `Basalt`. `src: Data model, seed data bullet 1`
- [ ] `C-DM-33` `literal` The app seeds `analyst@example.com` as `Dana Okafor`. `src: Data model, seed data bullet 2`
- [ ] `C-DM-34` `literal` The app seeds `manager@example.com` as `Ines Bravo` in `North`. `src: Data model, seed data bullet 2`
- [ ] `C-DM-35` `literal` The app seeds `manager2@example.com` as `Rui Santos` in `South`. `src: Data model, seed data bullet 2`
- [ ] `C-DM-36` `constraint` The app seeds no manager for `West`. `src: Data model, seed data bullet 2`
- [ ] `C-DM-37` `data` The app seeds ten transactions. `src: Data model, seed transactions table`
- [ ] `C-DM-38` `literal` The app seeds `TX-1004` at `25000` as `refunded` inside the January period. `src: Data model, seed transactions table row 4`
- [ ] `C-DM-39` `literal` The app seeds `TX-1007` at `15000` as `void` inside the January period. `src: Data model, seed transactions table row 7`
- [ ] `C-DM-40` `literal` The app seeds `TX-1009` at `99000` dated `2026-02-02`. `src: Data model, seed transactions table row 9`
- [ ] `C-DM-41` `literal` The app seeds `TX-1010` at `88000` dated `2025-12-31`. `src: Data model, seed transactions table row 10`
- [ ] `C-DM-42` `literal` The app seeds `January 2026 Revenue` over `2026-01-01` to `2026-01-31` as `published`. `src: Data model, seed data bullet 3`
- [ ] `C-DM-43` `literal` The app seeds `February 2026 Revenue` over `2026-02-01` to `2026-02-28` as `draft`. `src: Data model, seed data bullet 3`
- [ ] `C-DM-44` `constraint` The app seeds idempotently. `src: Data model, closing para`
- [ ] `C-DM-45` `constraint` Restarting the app duplicates no row. `src: Data model, closing para`
- [ ] `C-DM-46` `literal` The app seeds `TX-1001` at `120000` in `North` for `Aurora`. `src: Data model, seed transactions table row 1`
- [ ] `C-DM-47` `literal` The app seeds `TX-1002` at `45000` in `North` for `Aurora`. `src: Data model, seed transactions table row 2`
- [ ] `C-DM-48` `literal` The app seeds `TX-1003` at `30000` in `North` for `Basalt`. `src: Data model, seed transactions table row 3`
- [ ] `C-DM-49` `literal` The app seeds `TX-1005` at `90000` in `South` for `Aurora`. `src: Data model, seed transactions table row 5`
- [ ] `C-DM-50` `literal` The app seeds `TX-1006` at `60000` in `South` for `Basalt`. `src: Data model, seed transactions table row 6`
- [ ] `C-DM-51` `literal` The app seeds `TX-1008` at `70000` in `West` for `Aurora`. `src: Data model, seed transactions table row 8`

## C-CN Constraints

- [ ] `C-CN-01` `constraint` The app scopes data by region only. `src: Constraints bullet 1`
- [ ] `C-CN-02` `constraint` The app holds no second tenant. `src: Constraints bullet 1`
- [ ] `C-CN-03` `constraint` The app holds no sub-region. `src: Constraints bullet 1`
- [ ] `C-CN-04` `constraint` The app holds no per-region pricing. `src: Constraints bullet 1`
- [ ] `C-CN-05` `constraint` The app treats transactions as read-only reference data. `src: Constraints bullet 2`
- [ ] `C-CN-06` `constraint` The app offers no transaction entry screen. `src: Constraints bullet 2`
- [ ] `C-CN-07` `constraint` The app offers no CSV export. `src: Constraints bullet 3`
- [ ] `C-CN-08` `constraint` The app offers no PDF export. `src: Constraints bullet 3`
- [ ] `C-CN-09` `constraint` The app offers no spreadsheet export. `src: Constraints bullet 3`
- [ ] `C-CN-10` `constraint` The app offers no print view. `src: Constraints bullet 3`
- [ ] `C-CN-11` `constraint` The app draws no chart. `src: Constraints bullet 4`
- [ ] `C-CN-12` `constraint` The app draws no time series. `src: Constraints bullet 4`
- [ ] `C-CN-13` `constraint` The app produces no forecast. `src: Constraints bullet 4`
- [ ] `C-CN-14` `constraint` The app produces no period-over-period comparison. `src: Constraints bullet 4`
- [ ] `C-CN-15` `constraint` The app converts no currency. `src: Constraints bullet 5`
- [ ] `C-CN-16` `constraint` The app offers no comments. `src: Constraints bullet 6`
- [ ] `C-CN-17` `constraint` The app offers no annotations. `src: Constraints bullet 6`
- [ ] `C-CN-18` `constraint` The app offers no share links. `src: Constraints bullet 6`
- [ ] `C-CN-19` `constraint` The app offers no revision history. `src: Constraints bullet 6`
- [ ] `C-CN-20` `constraint` The app offers no unpublish. `src: Constraints bullet 6`
- [ ] `C-CN-21` `constraint` The app runs no background job. `src: Constraints bullet 7`
- [ ] `C-CN-22` `constraint` The app runs no cache. `src: Constraints bullet 7`
- [ ] `C-CN-23` `constraint` The app runs no scheduled work. `src: Constraints bullet 7`
- [ ] `C-CN-24` `constraint` The app recomputes nothing on a timer. `src: Constraints bullet 7`
- [ ] `C-CN-25` `constraint` The app sends no email. `src: Constraints bullet 8`
- [ ] `C-CN-26` `constraint` The app sends no notification. `src: Constraints bullet 8`
- [ ] `C-CN-27` `constraint` The app makes no external network call at runtime. `src: Constraints bullet 8`
- [ ] `C-CN-28` `constraint` The app ships no native mobile client. `src: Constraints bullet 9`
- [ ] `C-CN-29` `constraint` The app stays responsive at ten thousand transaction rows. `src: Constraints bullet 9`

## C-DC Deployment contract

- [ ] `C-DC-01` `contract` The app is reachable at `APP_PUBLIC_URL`. `src: Deployment contract bullet 1`
- [ ] `C-DC-02` `contract` The app maps `${APP_PUBLIC_PORT}:4173` as the port mapping. `src: Deployment contract bullet 1`
- [ ] `C-DC-03` `contract` The app reads both port values from the environment. `src: Deployment contract bullet 1`
- [ ] `C-DC-04` `contract` The app hardcodes neither port value. `src: Deployment contract bullet 1`
- [ ] `C-DC-05` `contract` The app serves the HTTP API on the same origin under `/api`. `src: Deployment contract bullet 2`
- [ ] `C-DC-06` `contract` The app returns `200` from `GET /api/health` once ready. `src: Deployment contract bullet 3`
- [ ] `C-DC-07` `contract` The app starts from the environment image with no manual steps. `src: Deployment contract bullet 4`
- [ ] `C-DC-08` `contract` The app writes login credentials to `/app/USER_README.md`. `src: Deployment contract bullet 5`
- [ ] `C-DC-09` `contract` The app holds an empty `.browser_screenshots/` directory at the app root. `src: Deployment contract bullet 6`
- [ ] `C-DC-10` `contract` The app holds an empty `.downloads/` directory at the app root. `src: Deployment contract bullet 6`
- [ ] `C-DC-11` `contract` The app serves a production build behind a static or preview server. `src: Deployment contract bullet 7`
- [ ] `C-DC-12` `contract` The app serves no dev server. `src: Deployment contract bullet 7`
- [ ] `C-DC-13` `contract` The server keeps running after the session ends. `src: Deployment contract bullet 8`
- [ ] `C-DC-14` `contract` The server is no child of the shell. `src: Deployment contract bullet 8`
- [ ] `C-DC-15` `contract` The app binds `0.0.0.0`. `src: Deployment contract bullet 9`
- [ ] `C-DC-16` `contract` The app binds neither `127.0.0.1` nor `localhost`. `src: Deployment contract bullet 9`
- [ ] `C-DC-17` `contract` The app downloads no copy of a backing service. `src: Deployment contract bullet 10`
- [ ] `C-DC-18` `contract` The app installs no copy of a backing service. `src: Deployment contract bullet 10`
- [ ] `C-DC-19` `contract` The app starts no copy of a backing service. `src: Deployment contract bullet 10`
- [ ] `C-DC-20` `contract` The app uses only the providers named in the brief. `src: Deployment contract bullet 11`
- [ ] `C-DC-21` `contract` The app uses no edge function. `src: Deployment contract bullet 11`
- [ ] `C-DC-22` `contract` The app uses no persistent volume. `src: Deployment contract bullet 12`
- [ ] `C-DC-23` `contract` The app uses no fixed container name. `src: Deployment contract bullet 12`
- [ ] `C-DC-24` `contract` The app uses no custom network. `src: Deployment contract bullet 12`
- [ ] `C-DC-25` `capability` The app returns the created report from `POST /api/reports` with `201`. `src: Deployment contract, API shapes row 6`
- [ ] `C-DC-26` `capability` The app returns one report from `GET /api/reports/{id}`. `src: Deployment contract, API shapes row 8`
- [ ] `C-DC-27` `data` The app returns `id`, `email`, `name`, `role`, `region` from `GET /api/me`. `src: Deployment contract, API shapes row 3`
- [ ] `C-DC-28` `data` The app returns `id`, `name` pairs from `GET /api/regions`. `src: Deployment contract, API shapes row 4`
- [ ] `C-DC-29` `data` The app returns `id`, `name` pairs from `GET /api/product-lines`. `src: Deployment contract, API shapes row 5`
- [ ] `C-DC-30` `data` The app returns `external_ref`, `region`, `product_line`, `amount`, `occurred_on`, `status` per transaction row. `src: Deployment contract, API shapes row 11`
- [ ] `C-DC-31` `constraint` The app returns a `4xx` naming the reason on every business-rule violation. `src: Deployment contract, rules bullet 1`
- [ ] `C-DC-32` `constraint` The app returns no `5xx` for a business-rule violation. `src: Deployment contract, rules bullet 1`
- [ ] `C-DC-33` `constraint` The app returns no silent success for a business-rule violation. `src: Deployment contract, rules bullet 1`
- [ ] `C-DC-34` `constraint` The app returns a top-level JSON array from every list endpoint. `src: Deployment contract, rules bullet 5`
- [ ] `C-DC-35` `constraint` The ledger lives only in PostgreSQL at `DATABASE_URL`. `src: Deployment contract, No mocks para`
- [ ] `C-DC-36` `constraint` The app keeps no in-memory list of transactions. `src: Deployment contract, No mocks para`
- [ ] `C-DC-37` `constraint` The app keeps no hardcoded summary object. `src: Deployment contract, No mocks para`
- [ ] `C-DC-38` `constraint` The app caches no total in a file. `src: Deployment contract, No mocks para`
- [ ] `C-DC-39` `constraint` The app holds no total in a module variable. `src: Deployment contract, No mocks para`
- [ ] `C-DC-40` `constraint` The app renders no figure the ledger does not support. `src: Deployment contract, No mocks para`
- [ ] `C-DC-41` `data` The app takes `email`, `password` in the login request body. `src: Deployment contract, API shapes row 1`

## Pinned literals

| Value | What it is | Item | Stated in |
|---|---|---|---|
| `deku-demo-pw-2026` | password for every seeded account | C-DM-04 | Data model, password para |
| `analyst@example.com` | seeded analyst email | C-DM-33 | Data model, seed data bullet 2 |
| `manager@example.com` | seeded North manager email | C-DM-34 | Data model, seed data bullet 2 |
| `manager2@example.com` | seeded South manager email | C-DM-35 | Data model, seed data bullet 2 |
| `Dana Okafor` | seeded analyst name | C-DM-33 | Data model, seed data bullet 2 |
| `Ines Bravo` | seeded North manager name | C-DM-34 | Data model, seed data bullet 2 |
| `Rui Santos` | seeded South manager name | C-DM-35 | Data model, seed data bullet 2 |
| `North` | seeded region | C-DM-31 | Data model, seed data bullet 1 |
| `South` | seeded region | C-DM-31 | Data model, seed data bullet 1 |
| `West` | seeded region without a manager | C-DM-36 | Data model, seed data bullet 1 |
| `Aurora` | seeded product line | C-DM-32 | Data model, seed data bullet 1 |
| `Basalt` | seeded product line | C-DM-32 | Data model, seed data bullet 1 |
| `January 2026 Revenue` | seeded published report title | C-DM-42 | Data model, seed data bullet 3 |
| `February 2026 Revenue` | seeded draft report title | C-DM-43 | Data model, seed data bullet 3 |
| `2026-01-01` | January report period start | C-DM-42 | Data model, seed data bullet 3 |
| `2026-01-31` | January report period end | C-DM-42 | Data model, seed data bullet 3 |
| `2026-02-01` | February report period start | C-DM-43 | Data model, seed data bullet 3 |
| `2026-02-28` | February report period end | C-DM-43 | Data model, seed data bullet 3 |
| `TX-1001` | seeded North Aurora row inside the January period | C-DM-46 | Data model, seed transactions table row 1 |
| `TX-1002` | seeded North Aurora row inside the January period | C-DM-47 | Data model, seed transactions table row 2 |
| `TX-1003` | seeded North Basalt row inside the January period | C-DM-48 | Data model, seed transactions table row 3 |
| `TX-1004` | seeded refunded row inside the January period | C-DM-38 | Data model, seed transactions table row 4 |
| `TX-1005` | seeded South Aurora row inside the January period | C-DM-49 | Data model, seed transactions table row 5 |
| `TX-1006` | seeded South Basalt row inside the January period | C-DM-50 | Data model, seed transactions table row 6 |
| `TX-1007` | seeded void row inside the January period | C-DM-39 | Data model, seed transactions table row 7 |
| `TX-1008` | seeded West Aurora row inside the January period | C-DM-51 | Data model, seed transactions table row 8 |
| `TX-1009` | seeded row one day after the January period | C-DM-40 | Data model, seed transactions table row 9 |
| `TX-1010` | seeded row one day before the January period | C-DM-41 | Data model, seed transactions table row 10 |
| `120000` | amount on the first seeded North Aurora row | C-DM-46 | Data model, seed transactions table row 1 |
| `45000` | amount on the second seeded North Aurora row | C-DM-47 | Data model, seed transactions table row 2 |
| `30000` | amount on the seeded North Basalt row | C-DM-48 | Data model, seed transactions table row 3 |
| `25000` | amount on the seeded refunded row | C-DM-38 | Data model, seed transactions table row 4 |
| `90000` | amount on the seeded South Aurora row | C-DM-49 | Data model, seed transactions table row 5 |
| `60000` | amount on the seeded South Basalt row | C-DM-50 | Data model, seed transactions table row 6 |
| `15000` | amount on the seeded void row | C-DM-39 | Data model, seed transactions table row 7 |
| `99000` | amount on the seeded row after the January period | C-DM-40 | Data model, seed transactions table row 9 |
| `88000` | amount on the seeded row before the January period | C-DM-41 | Data model, seed transactions table row 10 |
| `2026-02-02` | date of the row after the January period | C-DM-40 | Data model, seed transactions table row 9 |
| `2025-12-31` | date of the row before the January period | C-DM-41 | Data model, seed transactions table row 10 |
| `415000` | analyst grand total for the January report | C-CF-30 | Core features, summary rule 6 |
| `195000` | North region total for the January report | C-CF-31 | Core features, summary rule 6 |
| `150000` | South region total for the January report | C-CF-31 | Core features, summary rule 6 |
| `70000` | West region total for the January report | C-CF-31 | Core features, summary rule 6 |
| `325000` | Aurora product line total for the January report | C-CF-32 | Core features, summary rule 6 |
| `90000` | Basalt product line total for the January report | C-CF-32 | Core features, summary rule 6 |
| `total` | grand total field in the summary response | C-CF-22 | Core features, summary rule 5 |
| `report_id` | report id field in the summary response | C-CF-22 | Core features, summary rule 5 |
| `by_region` | region breakdown field in the summary response | C-CF-22 | Core features, summary rule 5 |
| `by_product_line` | product line breakdown field in the summary response | C-CF-22 | Core features, summary rule 5 |
| `region` | region name field inside a by_region entry | C-CF-48 | Core features, summary rule 5 |
| `product_line` | product line name field inside a by_product_line entry | C-CF-49 | Core features, summary rule 5 |
| `email` | login request field | C-DC-41 | Deployment contract, API shapes row 1 |
| `password` | login request field | C-DC-41 | Deployment contract, API shapes row 1 |
| `external_ref` | ledger reference field on a transaction | C-DM-14 | Data model, transactions para |
| `occurred_on` | transaction date field | C-DM-18 | Data model, transactions para |
| `period_start` | report period start field | C-DM-21 | Data model, reports para |
| `period_end` | report period end field | C-DM-22 | Data model, reports para |
| `published_at` | publication timestamp field | C-DM-26 | Data model, reports para |
| `settled` | counted transaction status | C-CF-25 | Core features, summary rule 5 |
| `refunded` | excluded transaction status | C-CF-26 | Core features, summary rule 5 |
| `void` | excluded transaction status | C-CF-27 | Core features, summary rule 5 |
| `draft` | unpublished report status | C-DM-24 | Data model, reports para |
| `published` | published report status | C-DM-24 | Data model, reports para |
| `analyst` | publishing role | C-DM-09 | Data model, users para |
| `manager` | reading role | C-DM-09 | Data model, users para |
| `12 hours` | bearer token lifetime | C-TR-19 | Technical requirements, auth bullet |
| `POST /api/auth/login` | login endpoint | C-CF-01 | Core features, Sign in |
| `GET /api/health` | health endpoint | C-DC-06 | Deployment contract bullet 3 |
| `GET /api/me` | caller identity endpoint | C-CF-04 | Core features, Sign in |
| `GET /api/regions` | region list endpoint | C-CF-45 | Core features, region scope rule 10 |
| `GET /api/product-lines` | product line list endpoint | C-CF-47 | Core features, region scope rule 10 |
| `POST /api/reports` | report creation endpoint | C-CF-06 | Core features, Reports rule 1 |
| `GET /api/reports` | report list endpoint | C-CF-16 | Core features, Reports rule 3 |
| `GET /api/reports/{id}` | single report endpoint | C-DC-26 | Deployment contract, API shapes row 8 |
| `POST /api/reports/{id}/publish` | publish endpoint | C-CF-11 | Core features, Reports rule 2 |
| `GET /api/reports/{id}/transactions` | underlying rows endpoint | C-CF-33 | Core features, summary rule 7 |
| `/login` | sign-in route | C-UF-01 | User flow route table row 1 |
| `/reports/new` | report creation route | C-UF-04 | User flow route table row 3 |
| `/reports/:id` | report summary route | C-UF-05 | User flow route table row 4 |
| `/reports/:id/transactions` | underlying rows route | C-UF-06 | User flow route table row 5 |
| `next` | redirect query parameter | C-UF-08 | User flow, entry para |
| `400` | status for a backwards report period | C-CF-08 | Core features, Reports rule 1 |
| `401` | status for a missing or invalid token | C-CF-03 | Core features, Sign in |
| `403` | status for a cross-region request | C-CF-42 | Core features, region scope rule 9 |
| `404` | status for a draft report seen by a manager | C-CF-19 | Core features, Reports rule 3 |
| `409` | status for a second publish | C-CF-14 | Core features, Reports rule 2 |
| `200` | status for a successful publish | C-CF-13 | Core features, Reports rule 2 |
| `201` | status for a created report | C-DC-25 | Deployment contract, API shapes row 6 |
| `0` | grand total for an empty period | C-CF-36 | Core features, summary rule 7 |
| `usd` | currency of every amount | C-DM-03 | Data model para 1 |
| `DATABASE_URL` | PostgreSQL connection variable | C-TR-14 | Technical requirements, database bullet |
| `APP_PUBLIC_URL` | public base URL variable | C-DC-01 | Deployment contract bullet 1 |
| `${APP_PUBLIC_PORT}:4173` | port mapping | C-DC-02 | Deployment contract bullet 1 |
| `/app/USER_README.md` | credentials file path | C-DC-08 | Deployment contract bullet 5 |
| `.browser_screenshots/` | reserved directory | C-DC-09 | Deployment contract bullet 6 |
| `.downloads/` | reserved directory | C-DC-10 | Deployment contract bullet 6 |
| `0.0.0.0` | bind address | C-DC-15 | Deployment contract bullet 9 |
| `127.0.0.1` | forbidden bind address | C-DC-16 | Deployment contract bullet 9 |
| `localhost` | forbidden bind address | C-DC-16 | Deployment contract bullet 9 |
| `/api` | API path prefix | C-DC-05 | Deployment contract bullet 2 |
| `#F7F8FA` | background colour | C-UX-03 | UI/UX notes, palette para |
| `#FFFFFF` | surface colour | C-UX-04 | UI/UX notes, palette para |
| `#0F172A` | primary text colour | C-UX-05 | UI/UX notes, palette para |
| `#64748B` | muted text colour | C-UX-06 | UI/UX notes, palette para |
| `#1D4ED8` | primary colour | C-UX-07 | UI/UX notes, palette para |
| `#1E40AF` | primary hover colour | C-UX-08 | UI/UX notes, palette para |
| `#E2E8F0` | border colour | C-UX-09 | UI/UX notes, palette para |
| `#B91C1C` | danger colour | C-UX-10 | UI/UX notes, palette para |
| `#15803D` | success colour | C-UX-11 | UI/UX notes, palette para |
| `#B45309` | warning colour | C-UX-12 | UI/UX notes, palette para |
| `#0E7490` | accent colour | C-UX-13 | UI/UX notes, palette para |
| `Inter` | font family | C-UX-19 | UI/UX notes, type para |
| `32/40` | first heading size over line height | C-UX-20 | UI/UX notes, type para |
| `24/32` | second heading size over line height | C-UX-20 | UI/UX notes, type para |
| `20/28` | third heading size over line height | C-UX-20 | UI/UX notes, type para |
| `15/24` | body size over line height | C-UX-21 | UI/UX notes, type para |
| `13/18` | caption size over line height | C-UX-22 | UI/UX notes, type para |
| `$1,950.00` | rendered money format | C-UX-24 | UI/UX notes, type para |
| `8px` | card radius | C-UX-25 | UI/UX notes, shape para |
| `6px` | button radius | C-UX-26 | UI/UX notes, shape para |
| `1px` | border width | C-UX-27 | UI/UX notes, shape para |
| `40px` | row height | C-UX-29 | UI/UX notes, shape para |
| `2px` | focus ring width | C-UX-32 | UI/UX notes, shape para |
| `150ms` | standard transition duration | C-UX-37 | UI/UX notes, motion para |
| `250ms` | entering transition duration | C-UX-38 | UI/UX notes, motion para |
| `cubic-bezier(0.16, 1, 0.3, 1)` | easing curve | C-UX-39 | UI/UX notes, motion para |
| `prefers-reduced-motion: reduce` | reduced motion query | C-UX-42 | UI/UX notes, motion para |
| `640` | first breakpoint | C-UX-43 | UI/UX notes, responsive para |
| `768` | second breakpoint | C-UX-43 | UI/UX notes, responsive para |
| `1024` | third breakpoint | C-UX-43 | UI/UX notes, responsive para |
| `1920x1200` | desktop viewport | C-UX-47 | UI/UX notes, responsive para |
| `768x1024` | tablet viewport | C-UX-47 | UI/UX notes, responsive para |
| `390x844` | phone viewport | C-UX-47 | UI/UX notes, responsive para |
| `44x44` | minimum touch target | C-UX-48 | UI/UX notes, responsive para |
| `4.5:1` | minimum contrast ratio | C-UX-49 | UI/UX notes, responsive para |

### Referenced but not pinned

| What the instruction calls it | Item | Why it matters |
|---|---|---|
| the elevation value on the summary cards | C-UX-28 | the brief gives the shadow value in prose only, so a builder can read the token but no downstream row pins it |

## Coverage ledger

| Section | Obligation-bearing sentences | Items produced |
|---|---|---|
| Overview | 3 | 7 |
| User roles | 6 | 16 |
| Core features | 26 | 50 |
| User flow | 15 | 22 |
| UI/UX notes | 10 | 52 |
| Technical requirements | 14 | 37 |
| Data model | 20 | 51 |
| Constraints | 4 | 29 |
| Deployment contract | 27 | 41 |
