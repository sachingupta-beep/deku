# 03 — App Flow: Ethara Seat Allocation & Project Mapping System

Every screen, every transition, every redirect. The map of the product.

## Screens / routes

| Route | Purpose | Auth required |
|---|---|---|
| `/login` | Email + password login (seeded accounts) | No |
| `/` | Dashboard — summary tiles, project-wise + floor-wise charts, pending joiners | Yes (any role) |
| `/employees` | Searchable/filterable employee table; row → detail drawer | Yes |
| `/employees/new` | Add employee form → triggers seat suggestion (admin) | Yes (admin) |
| `/employees/:id` | Employee detail: profile, project, current seat, allocate/release actions | Yes |
| `/seats` | Seat table with floor/zone/status filters; allocate/release actions | Yes |
| `/projects` | Project list + per-project employee count and seat footprint | Yes |
| `/assistant` | Natural-language AI assistant chat panel over `/ai/query` | Yes |
| `/import` | CSV bulk import of employees/allocations (admin) | Yes (admin) |

## Navigation

- **Desktop / large**: fixed left sidebar (Dashboard, Employees, Seats, Projects, Assistant, Import) + top bar with search shortcut, current user, role badge, logout.
- **Mobile / small**: sidebar collapses to a hamburger drawer; top bar persists; tables become horizontally scrollable cards.

## Entry points

- **First-time visitor lands on**: `/login` (unauthenticated → redirect).
- **Returning logged-out user**: `/login`.
- **Returning logged-in user**: `/` (Dashboard), token restored from localStorage.
- **Deep link to a resource without session**: redirect to `/login?next=<path>`, then back after login.

## Auth flow

```
Login  → validate → store JWT → redirect to `next` or `/`
Logout → clear JWT → `/login`
Token expired / 401 mid-action → clear JWT → `/login?next=<current>`
Forbidden (employee hits admin action) → 403 toast, action blocked (no redirect)
```

## Core journeys

### Journey 1 — Employee finds their own seat
1. User intent: "Where do I sit and what project am I on?"
2. Starts at: `/assistant` (or `/employees` search).
3. Steps: type "Where is my seat? My email is amit@ethara.ai" → assistant calls `POST /ai/query` → renders answer with floor/zone/bay/seat + project. Alternatively search their name in `/employees` and open the detail drawer.
4. End state: employee sees exact seat + project.

### Journey 2 — HR onboards a new joiner
1. User intent: "Add a new hire and give them a desk near their team."
2. Starts at: `/employees/new`.
3. Steps: fill name/email/department/role/joining date/project → submit (`POST /employees`) → system shows **suggested available seats near the project team** (proximity service) with alternate-zone fallback → admin picks a seat → `POST /seats/allocate` → confirmation toast; dashboard counts update.
4. End state: employee has an active seat; pending-allocation count drops by one.

### Journey 3 — HR releases a leaver's seat
1. User intent: "This person left; free their desk."
2. Starts at: `/employees/:id` or `/seats`.
3. Steps: open employee/seat → "Release seat" → `POST /seats/release` → seat status flips to Available; allocation `released_date` set.
4. End state: seat is Available and re-suggestable; dashboard available count rises.

### Journey 4 — HR audits utilization
1. User intent: "How full are we, by project and floor?"
2. Starts at: `/` (Dashboard).
3. Steps: read summary tiles; scan project-wise allocation bar chart and floor-wise occupancy chart; click "Pending allocation" tile → filtered `/employees` list of the ≥50 unseated.
4. End state: HR knows exactly where capacity is and who still needs a seat.

### Journey 5 — Anyone filters free seats on a floor
1. User intent: "Show all available seats on Floor 3."
2. Starts at: `/seats` or `/assistant`.
3. Steps: set floor=3 + status=Available filter (or ask the assistant) → table lists free seats.
4. End state: user sees every free desk on that floor.

## States

### Empty states
- Employees table with no matches: "No employees match these filters" + Clear filters CTA.
- Assistant before first query: example prompts as clickable chips.
- Pending-allocation tile at zero: "All employees are seated 🎉".

### Loading states
- Dashboard: skeleton tiles + chart placeholders.
- Tables: skeleton rows (10) while the page query resolves.
- Assistant: typing indicator while `/ai/query` is in flight.

### Error states
- **Network failure**: inline retry banner on the affected panel.
- **Auth expired**: clear token, redirect `/login?next=…`, toast "Session expired".
- **Forbidden (wrong role)**: toast "Admins only" — action button disabled for employees.
- **Not found (404)**: employee/seat detail shows "Not found" empty card + back link.
- **Server error (5xx)**: app-root error boundary with reload CTA; toast on action failures.
- **Business-rule rejection (409/400)**: precise toast, e.g. "Seat B4-23 is already occupied" / "Reserved seats can't be allocated".

### Success states
- After create/allocate/release: green toast + optimistic list refresh (React Query invalidation).
- After CSV import: summary toast "Imported N employees, M allocations, K skipped".

## Redirects

| Action | Goes to |
|---|---|
| Login success | `next` param or `/` |
| Logout | `/login` |
| Auth required, no session | `/login?next=<path>` |
| Session expired mid-action | `/login?next=<current>` |

## Modal / drawer / overlay inventory

- Confirm-release dialog (destructive style) before freeing a seat.
- Employee detail drawer (from `/employees` rows).
- Seat-suggestion modal in the new-joiner flow.
- Global toast stack (top-right, 4s).
