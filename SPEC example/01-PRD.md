# 01 — PRD: Ethara Seat Allocation & Project Mapping System

> Find any employee's seat, project, and floor in seconds — for ~5,000 people across 5 floors.

## Problem

Ethara has ~5,000 employees spread across multiple projects and 5 floors, and hiring is continuous. Today there is no single source of truth for *where someone sits*, *what project they're on*, or *which seats are free* — the data lives in scattered spreadsheets, so HR wastes time hunting for a free desk for every new joiner and employees can't find their own seat or their teammates. This system centralizes employee seating, project mapping, floor allocation, and joining updates in one searchable app.

## Target user

- **HR / Admin / Growth team** — maintains employee and allocation data, onboards new joiners, allocates and releases seats, watches utilization. Today they juggle Excel sheets and Slack pings; they need bulk import, fast search, and a live dashboard.
- **Employee** — wants to quickly answer "where is my seat?", "what project am I on?", "who sits near me?" without emailing HR. Today they ask around; they need self-service search and a natural-language assistant.
- **Project lead** — wants to see their team's seat footprint and how many seats a project occupies.

## Value proposition

One centralized, searchable system that answers any seat/project/floor question instantly — for employees via self-service + AI assistant, and for HR via bulk data management, smart proximity-based allocation, and a live utilization dashboard.

## Features

### Must have (v1)

- **Employee management** — CRUD employees (create, list, get, update, deactivate) with code, name, email, department, role, joining date, status, project, and seat-allocation status.
- **Project mapping** — 12 projects; each employee maps to exactly one active project; list employees per project.
- **Seat management** — CRUD seats with floor/zone/bay/seat_number and status (Available/Occupied/Reserved/Maintenance); list available seats.
- **Seat allocation engine** — allocate a seat to an employee and release it, enforcing all 8 business rules, with **proximity-based suggestions** (seat near the employee's project team) and alternate-zone fallback. Prevents duplicate allocation transactionally.
- **New-joiner flow** — HR adds an employee, system suggests the best available seats near their project, HR allocates; employee can then look themselves up.
- **Search & filter** — by employee name, employee ID/code, email, project, floor, zone, seat status.
- **Dashboard** — total employees, total/occupied/available/reserved seats, project-wise allocation, floor-wise occupancy, and new-joiners-pending-allocation.
- **AI assistant** (`POST /ai/query`) — natural-language answers for employee seat, project assignment, available seats, team location, and seat utilization; deterministic rule-based parser with optional LLM upgrade.
- **Auth** — JWT login with `admin` (HR/Admin) and `employee` roles; only admins mutate.

### Nice to have (v2+)

- CSV bulk import of employee↔seat data (included in v1 as it directly serves the HR workflow).
- Real LLM-backed assistant (adapter shipped; activate by setting an API key).
- Interactive floor-map visualization of seats.
- Redis caching of dashboard aggregates.

### Out of scope (v1)

- Multi-org / multi-tenant support (single company: Ethara).
- Desk booking / hoteling / time-based reservations.
- Calendar, badge/access-control, or HRIS integrations.
- Mobile native apps (responsive web only).
- Password reset email flow / SSO (seeded credentials only).

## User stories

- As an **employee**, I want to ask "where is my seat?" and get my exact floor/zone/bay/seat + project, so I don't have to email HR.
- As an **HR admin**, I want to add a new joiner and have the system suggest available seats near their project team, so onboarding takes seconds.
- As an **HR admin**, I want to release a leaver's seat so it immediately becomes available for the next joiner.
- As a **project lead**, I want to see how many seats my project occupies and where, so I can plan space.
- As **anyone**, I want to filter seats by floor and status so I can find every free desk on Floor 3.

## Success metrics

- **Time-to-answer** "where is X seated?" drops from minutes (ask around / search spreadsheets) to < 3 seconds via search or the AI assistant.
- **New-joiner allocation** completes in < 30 seconds (add employee → accept a suggested seat).
- Dashboard reflects the true state (occupied/available/reserved) within one request of every allocate/release — zero stale counts.
- Seed data loads a realistic org: 5,000 employees, 6,000 seats, 12 projects, ≥500 available / ≥100 reserved / ≥50 pending — and every required AI example query returns a correct answer.

## Non-goals

- Not optimized for real-time collaborative editing (single-writer admin actions are fine).
- Not a general facilities-management suite — scoped to seat/project mapping only.
- Not offline-first — assumes a live backend.

---
*PRD is the north star. All other docs defer to this one.*
