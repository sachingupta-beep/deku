# 06 — Implementation Plan: Ethara Seat Allocation & Project Mapping System

The build sequence. Phases, not just tasks. Each phase has explicit done criteria — don't move on until they're true.

> Read this WITH the other 5 docs:
> [PRD](01-PRD.md) · [TRD](02-TRD.md) · [App Flow](03-app-flow.md) · [UI/UX Brief](04-uiux-brief.md) · [Schema](05-backend-schema.md)

Testing is test-first (RED → GREEN → real-surface) for every business rule and endpoint per TRD.

---

## Phase 1 — Setup
**Goal**: Both apps boot, typecheck/lint pass, env wired, Docker parity.

Tasks:
- Init repo, `.gitignore`, root `README.md`, `docker-compose.yml` (postgres + backend + frontend).
- Backend: `requirements.txt`, FastAPI app skeleton, `config.py` (Pydantic settings), `database.py`, `/health`, CORS, Dockerfile (`python:3.12-slim`), `.env.example`.
- Frontend: Vite + React + TS + Tailwind scaffold, `@/` alias, ESLint/Prettier, `.env.example` (`VITE_API_BASE_URL`), base layout + sidebar shell.
- CI-ready scripts: backend `pytest`/`ruff`, frontend `tsc --noEmit`/`build`.

**Done when**: `docker-compose up` serves backend `/health` and the frontend shell; backend `ruff` + frontend `tsc` pass.

---

## Phase 2 — Database & seed
**Goal**: Schema from doc 05 lives in the DB; realistic seed loads fast.

Tasks:
- SQLAlchemy models: `users`, `projects`, `employees`, `seats`, `seat_allocations` (doc 05).
- Alembic initial migration incl. UNIQUE(`floor`,`zone`,`seat_number`) and the two partial-unique active-allocation indexes.
- `seeds/seed.py`: deterministic bulk seed — 12 projects, 6,000 seats, 5,000 employees (50 pending), 4,950 active allocations, statuses per doc 05, plus the canonical **Amit/Talos/B4-23** record and seeded `admin` + `amit` users.

**Done when**: migration applies on SQLite and Postgres; seed completes in seconds; row counts + status distribution assert against PDF §6 minimums in a test.

---

## Phase 3 — Auth
**Goal**: JWT login + role guards match docs 02/05.

Tasks:
- Password hashing (passlib bcrypt), JWT issue/verify (HS256), `POST /auth/login`, `GET /auth/me`.
- `require_auth` + `require_admin` FastAPI dependencies.
- Frontend: `/login`, auth context, token persistence, `Authorization` header injection, 401 → `/login?next=`, route guards, role-gated action buttons.

**Done when**: seeded admin + employee can log in; protected endpoints reject no/expired token (401) and employee mutations (403); frontend redirects logged-out users. Tests cover all four cases.

---

## Phase 4 — Employee & Project management
**Goal**: PRD "employee management" + "project mapping" stories pass.

Tasks:
- Backend: `POST/GET/GET{id}/PUT/DELETE /employees` (DELETE = deactivate + release seat), `POST/GET /projects`, `GET /projects/{id}/employees`. Duplicate-email rejection (rule 6). Employee responses include derived seat-allocation status + current seat.
- Frontend: `/employees` table (search + filters), detail drawer, `/employees/new` form, `/projects` list with counts.

**Done when**: create→list→get→update→deactivate round-trips on dev; duplicate email returns 409; project employee list works. Endpoint tests green.

---

## Phase 5 — Seat management & allocation engine
**Goal**: All 8 business rules enforced; proximity allocation + release work. This is the core.

Tasks:
- Backend: `POST/GET /seats`, `GET /seats/available` (filter floor/zone), `POST /seats/allocate`, `POST /seats/release`.
- Allocation service (doc 05): rule enforcement, transactional allocate, proximity suggestion + alternate-zone fallback, release → seat Available.
- Duplicate/concurrent allocation prevented by partial-unique indexes — **write a concurrency test** firing two allocations at one seat, assert exactly one succeeds.
- Frontend: `/seats` table with status pills + filters, allocate/release actions, new-joiner suggestion modal wired into Phase 4's form.

**Done when**: every rule 1–8 has a passing test; allocate rejects Reserved/Maintenance/Occupied; release frees the seat; concurrency test proves single-winner; UI allocate/release round-trips with live count updates.

---

## Phase 6 — Dashboard
**Goal**: PRD "audit utilization" story passes; counts always current (rule 8).

Tasks:
- Backend: `GET /dashboard/summary` (total employees, total/occupied/available/reserved seats, pending count), `GET /dashboard/project-utilization`, `GET /dashboard/floor-utilization` — indexed `GROUP BY`.
- Frontend: metric tiles, project-wise bar chart, floor-wise segmented chart, donut of status split, pending-joiners tile → filtered employees.

**Done when**: dashboard numbers match DB truth; after an allocate/release the summary changes by exactly one on the next fetch (tested); charts render with seed data.

---

## Phase 7 — AI Assistant
**Goal**: `POST /ai/query` answers every required question type; LLM optional.

Tasks:
- Intent parser: extract email (regex), employee name, floor number, project name, seat status, and intent (my-seat, my-project, available-on-floor, who-is-near-me, project-utilization, allocate-new). Map to service calls; format natural-language answers matching the PDF's response shape.
- LLM adapter behind `AI_PROVIDER` (none→rule-based). When enabled, ground the model with retrieved data (no hallucinated seats).
- Frontend: `/assistant` chat panel with example-prompt chips.

**Done when**: the 7 PDF example queries (incl. "Where is employee Amit seated?" → Floor 2, Zone B, Bay 4, Seat B4-23, Project Talos, and the `amit@ethara.ai` /ai/query contract) return correct answers with the rule-based parser and `AI_PROVIDER=none`. Parser tests cover each intent.

---

## Phase 8 — Search, filter & CSV import
**Goal**: PRD search story + HR bulk-data story pass.

Tasks:
- Backend: unified employee search/filter (name, code, email, project, floor, zone, seat status) via query params on `GET /employees`; `POST /import/employees` CSV (multipart) → bulk upsert with per-row validation + skip report.
- Frontend: `/import` page (upload, preview, result summary); wire all filters on `/employees` and `/seats`.

**Done when**: each filter narrows results correctly; CSV import of a sample file reports imported/skipped counts; malformed rows are rejected without aborting the batch. Tests cover filter + import.

---

## Phase 9 — UI polish
**Goal**: Visual language from doc 04 applied everywhere.

Tasks:
- Empty/loading/error states for every list, form, and the assistant (doc 03 § States).
- Responsive pass on every screen (doc 04 breakpoints); light/dark toggle.
- Status color system consistent across tables/chips/charts; mono for codes; tabular numerals.
- Motion pass respecting `prefers-reduced-motion`.

**Done when**: manual walkthrough shows no broken states, no jank; design matches doc 04 in light + dark on desktop + mobile widths.

---

## Phase 10 — Hardening & tests
**Goal**: Survives edge cases and bad input; full suite green.

Tasks:
- Pydantic validation on every input boundary; consistent error envelope; business-rule rejections return precise 4xx.
- App-root error boundary; `require_admin` verified on every mutation; CORS locked to configured origins.
- Full pytest suite (rules, endpoints, auth, AI intents, concurrency, dashboard-consistency); frontend `tsc` + build clean; `lsp_diagnostics` clean.
- Manual QA pass against every journey in doc 03 (real curl + real browser).

**Done when**: every journey passes; no console errors; validation rejects bad input gracefully; all tests green; diagnostics clean.

---

## Phase 11 — Deploy
**Goal**: Live on prod; every journey works on prod.

Tasks:
- Prod env vars per TRD; `render.yaml`/Railway (backend + Postgres), `vercel.json`/`netlify.toml` (frontend).
- Run migration + seed against prod Postgres.
- Smoke-test every journey on the live URLs; verify Swagger `/docs` reachable.
- Finalize `README.md` (run + deploy + credentials + API docs link), `AI_PROMPTS.md`, screenshots, debugging + deployment notes.

**Done when**: live frontend URL + live backend URL serve the working app; every journey works on prod; Swagger reachable; submission checklist (§12) complete.

---

## Definition of done (v1)
- Every must-have feature in PRD ships; all 17 endpoints implemented and documented.
- Every journey in app flow works locally and on prod.
- All 8 business rules enforced with passing tests (incl. concurrency).
- Seed satisfies PDF §6; canonical Amit/Talos example queries return exact answers.
- Lint, typecheck/build, and tests pass; live URLs + README + AI_PROMPTS.md + Swagger delivered.
