# 05 — Backend Schema: Ethara Seat Allocation & Project Mapping System

The data model and access rules. Hardest doc to change after launch — get it right now.

Engine: SQLAlchemy 2.0 over SQLite (local) / PostgreSQL (prod). Types below list the portable SQLAlchemy type; Postgres/SQLite specifics noted where they matter. All timestamps stored UTC.

## Tables

### `users`
Login accounts for auth. Separate from `employees` (an employee may or may not have a login; seeded admins do).

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK autoincrement | |
| `email` | `str` | UNIQUE, indexed |
| `password_hash` | `str` | bcrypt (passlib) |
| `role` | `str` | `admin` \| `employee` |
| `employee_id` | `int` FK → `employees.id` NULL | links an employee login to their record |
| `created_at` | `datetime` | default now (UTC) |

### `projects`
(from PDF §7)

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `name` | `str` | UNIQUE, indexed |
| `description` | `str` NULL | |
| `manager_name` | `str` NULL | |
| `status` | `str` | `active` \| `inactive` (default `active`) |
| `created_at` | `datetime` | default now |

Seed: Indigo, Indreed, Mydreed, Preed, Serfy, Oreed, bedegreed, Opreed, Serry, Kaary, Mered, **Talos** (12 total; Talos added because every PDF AI example references it).

### `employees`
(from PDF §7)

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `employee_code` | `str` | UNIQUE, indexed (e.g. `ETH-00042`) |
| `name` | `str` | indexed |
| `email` | `str` | UNIQUE, indexed — **duplicate email rejected (rule 6)** |
| `department` | `str` | e.g. Engineering, Design, HR, Sales, Ops |
| `role` | `str` | job title |
| `joining_date` | `date` | |
| `status` | `str` | `active` \| `inactive` \| `pending` — `pending` = new joiner awaiting allocation; `inactive` = deactivated (soft-delete) |
| `project_id` | `int` FK → `projects.id` | each employee maps to exactly one active project |
| `created_at` | `datetime` | default now |
| `updated_at` | `datetime` | default now, on update now |

Derived (not stored): `seat_allocation_status` = whether an active `seat_allocations` row exists (Allocated vs Pending). Exposed in API responses via a join.

### `seats`
(from PDF §7)

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `floor` | `int` | 1..5 |
| `zone` | `str` | `A` \| `B` (10 zones = 5 floors × 2) |
| `bay` | `int` | 1..15 |
| `seat_number` | `str` | format `{zone}{bay}-{index}` e.g. `B4-23`, indexed |
| `status` | `str` | `available` \| `occupied` \| `reserved` \| `maintenance` |
| `created_at` | `datetime` | default now |

### `seat_allocations`
(from PDF §7) — the allocation ledger; one **active** row per employee and per seat.

| Column | Type | Notes |
|---|---|---|
| `id` | `int` PK | |
| `employee_id` | `int` FK → `employees.id` | |
| `seat_id` | `int` FK → `seats.id` | |
| `project_id` | `int` FK → `projects.id` | snapshot of employee's project at allocation time |
| `allocation_status` | `str` | `active` \| `released` |
| `allocation_date` | `datetime` | default now |
| `released_date` | `datetime` NULL | set on release |

## Relationships

- `employees.project_id` → `projects.id` (many-to-one)
- `users.employee_id` → `employees.id` (one-to-one, nullable)
- `seat_allocations.employee_id` → `employees.id` (many-to-one; ledger)
- `seat_allocations.seat_id` → `seats.id` (many-to-one; ledger)
- `seat_allocations.project_id` → `projects.id` (many-to-one)

## Indexes & constraints (the rules live here)

- `seats`: **UNIQUE (`floor`, `zone`, `seat_number`)** → enforces rule 7 (no duplicate seat number on same floor/zone). Index on (`floor`, `status`) and (`status`) for available/floor queries.
- `seat_allocations`: **partial UNIQUE on `seat_id` WHERE `allocation_status='active'`** → rule 2 (a seat has ≤1 active allocation). **Partial UNIQUE on `employee_id` WHERE `allocation_status='active'`** → rule 1 (an employee has ≤1 active seat). On SQLite these are filtered unique indexes; identical in Postgres.
- `employees`: UNIQUE `email` (rule 6), UNIQUE `employee_code`; index on `name`, `project_id`, `status`.
- `projects`: UNIQUE `name`.

## Allocation engine (service, not a table — but the heart of the app)

`allocate(employee_id, seat_id?)`:
1. Load employee; reject if inactive.
2. Reject if employee already has an active allocation (rule 1).
3. If `seat_id` given: load seat; reject unless `status == available` (rules 2, 4 — Reserved/Maintenance/Occupied blocked).
4. If no `seat_id`: run **proximity suggestion** → pick best Available seat (see below).
5. In one transaction: create `seat_allocations(active)`, set `seats.status = occupied`. The partial unique indexes make concurrent double-allocation fail on one side (rule 2 / duplicate prevention).
6. Return allocation + seat.

`release(employee_id | seat_id)`:
1. Find active allocation; set `allocation_status='released'`, `released_date=now`.
2. Set `seats.status='available'` (rule 3).

**Proximity suggestion** (rule 5, §3.4): given the employee's `project_id`, rank Available seats by closeness to where that project already sits — same zone as the project's existing seats first, then same floor, then same bay clustering; if the preferred zone has no capacity, return Available seats from alternate zones (flagged as fallback). Returns a ranked list for the UI to present.

## Auth model

- **Provider**: in-app custom
- **Token type**: JWT (HS256), payload `{sub: user_id, role, email, exp}`
- **Session storage**: client localStorage (`Authorization: Bearer`)
- **Refresh**: re-login on expiry (8h); no refresh tokens in v1

## Authorization (app-layer — no RLS, SQLite/Postgres via app guards)

| Resource | Read | Write (create/update/delete/allocate/release) |
|---|---|---|
| `employees` | any authed | `admin` only |
| `projects` | any authed | `admin` only |
| `seats` | any authed | `admin` only |
| `seat_allocations` | any authed | `admin` only |
| `dashboard/*` | any authed | — |
| `ai/query` | any authed | — (read-only NL queries) |
| `import` (CSV) | — | `admin` only |

Middleware: `require_auth` dependency on all routers except `/auth/login` and `/health`; `require_admin` dependency on every mutation. Employees may read everything and use the assistant, but cannot mutate.

## Roles

| Role | Can do |
|---|---|
| `employee` | log in, read employees/seats/projects/dashboard, use AI assistant, look up their own seat |
| `admin` | everything: CRUD employees/projects/seats, allocate/release, CSV import |

## Migrations

- **Tooling**: Alembic
- **Location**: `backend/alembic/versions/`
- **Naming**: `YYYYMMDDHHMM_description.py`
- **Rollback policy**: forward-only after merge to main
- Initial migration creates all 5 tables + indexes/partial-unique constraints above.

## Seed data (fixture for local dev + demo — satisfies PDF §6)

- **12 projects** (list above).
- **6,000 seats** = 5 floors × 2 zones (A,B) × 15 bays × 40 seats. Statuses: 4,950 occupied, 700 available (≥500 ✓), 300 reserved (≥100 ✓), 50 maintenance.
- **5,000 employees**: 4,950 `active` with an active allocation; **50 `pending`** (no seat) (≥50 ✓). Distributed across 12 projects and realistic departments/roles.
- **Canonical demo record**: employee **Amit** (`amit@ethara.ai`) → active allocation at **Floor 2, Zone B, Bay 4, Seat `B4-23`**, project **Talos** — so the PDF's exact example queries return the PDF's exact answers.
- **Test users**: `admin@ethara.ai` / (seeded pw) role `admin`; `amit@ethara.ai` / (seeded pw) role `employee` linked to the Amit record. Credentials documented in README.
- Seeding is deterministic (fixed RNG seed) and uses bulk inserts for performance.

## File / blob storage

CSV import only — files are parsed in-request and discarded, never persisted. Max 5 MB, `text/csv`. No blob bucket in v1.
