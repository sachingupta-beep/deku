# Orbit Back-office API (Plain PostgreSQL Backend) — Test Results

Base URL: `http://localhost:8107` (in docker-compose: `http://postgres-backend-api:8107`)

## Endpoints covered

| Method | Path                                            | Status          |
|--------|-------------------------------------------------|-----------------|
| GET    | /health                                         | 200             |
| GET    | /health/db                                      | 200             |
| GET    | /health/ready                                   | 200             |
| GET    | /metrics                                        | 200 (text)      |
| POST   | /api/v1/auth/login                              | 200/401/423     |
| POST   | /api/v1/auth/refresh                            | 200/401         |
| GET    | /api/v1/auth/me                                 | 200/401         |
| POST   | /api/v1/auth/logout                             | 200/401         |
| GET    | /api/v1/employees                               | 200/400/401     |
| POST   | /api/v1/employees                               | 201/403/409/422 |
| GET    | /api/v1/employees/{id}                          | 200/401/404     |
| PATCH  | /api/v1/employees/{id}                          | 200/403/404/422 |
| DELETE | /api/v1/employees/{id}                          | 204/403/404/409 |
| GET    | /api/v1/teams                                   | 200/401         |
| GET    | /api/v1/teams/{id}                              | 200/404         |
| GET    | /api/v1/teams/{id}/employees                    | 200/404         |
| GET    | /api/v1/assets                                  | 200/400/401     |
| POST   | /api/v1/assets                                  | 201/403/409/422 |
| GET    | /api/v1/assets/{id}                             | 200/404         |
| POST   | /api/v1/assets/{id}/assign                      | 200/403/404/409/422 |
| POST   | /api/v1/assets/{id}/return                      | 200/403/404/409/422 |
| GET    | /api/v1/access-requests                         | 200/400/401     |
| POST   | /api/v1/access-requests                         | 201/409/422     |
| GET    | /api/v1/access-requests/{id}                    | 200/404         |
| POST   | /api/v1/access-requests/{id}/approve            | 200/403/404/409 |
| POST   | /api/v1/access-requests/{id}/deny               | 200/403/404/409 |
| GET    | /api/v1/audit-log                               | 200/403         |
| GET    | /api/v1/_meta/migrations                        | 200/403         |
| GET    | /api/v1/_meta/schema                            | 200/403         |

Collection run: **PASS 36 / WARN 26 / FAIL 0 / SKIP 0**. All twenty-six WARNs are
intentional error-path requests. The high count is the point: a hand-rolled
backend is mostly validation, authorization and conflict handling, and each of
those paths is exercised.

## Seed data summary

- Teams: 4 (Platform, Billing, Content, Support)
- Employees: 8 — active / on_leave / offboarded, with self-referencing `manager_id`
- Users: 4 — one admin, one manager, two viewers; one **locked** after 5 failed logins
- Assets: 10 across laptop / phone / license / monitor, in
  assigned / in_stock / repair / retired
- Access requests: 7 — pending / approved / denied / revoked
- Audit log: 8 seeded entries, appended to by every write
- Migrations: 7 applied, current version `20260211091400`

## Authentication and roles

`Authorization: Bearer <token>`. Three long-lived static service tokens map onto
the three roles so a client can exercise each without logging in first:

| Token | User | Role |
|-------|------|------|
| `at_static_admin_9f3c1a7e` | Amelia Ortega | admin |
| `at_static_manager_2b90d7fc` | Jonas Pereira | manager |
| `at_static_viewer_c81b7e05` | Rohit Bansal | viewer |

`POST /api/v1/auth/login` mints a real session; passwords are verified as
`sha256(salt + password)` against `users.json`. Seed logins:

| Email | Password | Role |
|-------|----------|------|
| amelia.ortega@orbit-labs.com | `OrbitAdmin2026!` | admin |
| jonas.pereira@orbit-labs.com | `OrbitManager2026!` | manager |
| rohit.bansal@orbit-labs.com | `OrbitViewer2026!` | viewer |

Any other bearer token resolves to the admin account, keeping the fleet
convention that any token is accepted.

Role requirements, ranked viewer < manager < admin:

| Action | Minimum role |
|--------|--------------|
| Read anything, create an access request | viewer |
| Update an employee, manage assets, decide access requests | manager |
| Create or delete employees, read the audit log, read `_meta/*` | admin |

Failed logins increment `failed_logins` and lock the account at 5, which is why
`noor.aziz@orbit-labs.com` answers 423 `account_locked` for any password.

## Conventions

This service deliberately uses **its own** conventions rather than a vendor's.

Collections return an envelope with pagination metadata and links:

```json
{"data": [...],
 "meta": {"page": 1, "per_page": 3, "total": 8, "total_pages": 3},
 "links": {"self": "...", "first": "...", "last": "...", "prev": null, "next": "..."}}
```

Single resources return `{"data": {...}}`. Failures return:

```json
{"error": {"code": "validation_error", "message": "Request body failed validation",
           "details": [{"field": "team_id", "issue": "foreign_key"}]}}
```

Query parameters: `page`, `per_page` (default 25, max 100), `sort`
(`-started_on,last_name`), `q` (substring search over the resource's text
columns), plus per-resource filters (`team_id`, `status`, `category`,
`assigned_to`, `system`). `expand=team,manager,assets` inlines related rows.
Sorting by a column the resource does not have is a 400 `invalid_sort` that
lists the allowed columns.

## Business rules enforced

- **Referential integrity.** Deleting an employee is refused while they hold
  assets (`409`, listing the asset tags), are referenced by an access request,
  or still have direct reports — each with the Postgres constraint name in the
  message.
- **Asset lifecycle.** An asset can only be assigned from `in_stock`; assigning a
  `retired` or `repair` asset is a conflict, as is assigning one already held by
  someone else or assigning to an offboarded employee. Returning takes a
  `condition` of `in_stock`, `repair` or `retired`.
- **Access-request workflow.** A request can only be decided once, a duplicate
  pending request for the same (employee, system) is rejected, and **nobody can
  decide their own request** (`403 self_approval_forbidden`).
- **Audit trail.** Every login, employee change, asset movement and access
  decision appends to `audit_log` with the actor, entity and a human summary.

## Notes

- `GET /metrics` returns Prometheus text exposition
  (`text/plain; version=0.0.4`), not JSON. Counters come from `config.json`;
  the `table_rows` gauges are computed from the live store, so they move as the
  run mutates data.
- `GET /api/v1/_meta/schema` introspects the tables this service owns, with
  column types, nullability, primary keys, foreign keys and live row counts.
- `DELETE` returns 204 with an empty body.
- Mutations (created/updated/deleted rows, sessions, audit entries, lock
  counters) are held in process memory and reset on container restart.
