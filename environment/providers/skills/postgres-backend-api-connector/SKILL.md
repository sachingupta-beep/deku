---
name: postgres-backend-api-connector
description: >
  Orbit Back-office API (Mock) — a plain PostgreSQL backend. Base URL is provided
  via the `POSTGRES_BACKEND_API_URL` environment variable. 29 endpoint(s) across
  GET, POST, PATCH, DELETE.
metadata: {"clawdbot":{"emoji":"🔌"}}
---

# Orbit Back-office API (Mock)

Mock HTTP API for a hand-rolled REST backend over PostgreSQL — no BaaS
framework, so the conventions are the service's own. **All requests go to the
base URL in `$POSTGRES_BACKEND_API_URL`.** Auth is a bearer token (any token is
accepted; the documented ones select a specific role). Responses are
deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `POSTGRES_BACKEND_API_URL` | Base URL for all requests (e.g. `http://postgres-backend-api:8107`) |

## Tokens and roles

| Token | User | Role |
|-------|------|------|
| `at_static_admin_9f3c1a7e` | Amelia Ortega | admin |
| `at_static_manager_2b90d7fc` | Jonas Pereira | manager |
| `at_static_viewer_c81b7e05` | Rohit Bansal | viewer |

Send as `Authorization: Bearer <token>`. `POST /api/v1/auth/login` also mints a
session: `amelia.ortega@orbit-labs.com` / `OrbitAdmin2026!`,
`jonas.pereira@orbit-labs.com` / `OrbitManager2026!`,
`rohit.bansal@orbit-labs.com` / `OrbitViewer2026!`.

Ranked viewer < manager < admin. Reads need viewer; asset moves, employee
updates and access decisions need manager; employee create/delete, the audit log
and `_meta/*` need admin.

## Endpoints

| Method | Path |
|--------|------|
| GET | `/health/db` |
| GET | `/health/ready` |
| GET | `/metrics` |
| POST | `/api/v1/auth/login` |
| POST | `/api/v1/auth/refresh` |
| GET | `/api/v1/auth/me` |
| POST | `/api/v1/auth/logout` |
| GET | `/api/v1/employees` |
| POST | `/api/v1/employees` |
| GET | `/api/v1/employees/{employee_id}` |
| PATCH | `/api/v1/employees/{employee_id}` |
| DELETE | `/api/v1/employees/{employee_id}` |
| GET | `/api/v1/teams` |
| GET | `/api/v1/teams/{team_id}` |
| GET | `/api/v1/teams/{team_id}/employees` |
| GET | `/api/v1/assets` |
| POST | `/api/v1/assets` |
| GET | `/api/v1/assets/{asset_id}` |
| POST | `/api/v1/assets/{asset_id}/assign` |
| POST | `/api/v1/assets/{asset_id}/return` |
| GET | `/api/v1/access-requests` |
| POST | `/api/v1/access-requests` |
| GET | `/api/v1/access-requests/{request_id}` |
| POST | `/api/v1/access-requests/{request_id}/approve` |
| POST | `/api/v1/access-requests/{request_id}/deny` |
| GET | `/api/v1/audit-log` |
| GET | `/api/v1/_meta/migrations` |
| GET | `/api/v1/_meta/schema` |

## Conventions

Collections return `{"data": [...], "meta": {page, per_page, total, total_pages},
"links": {self, first, last, prev, next}}`; single resources return
`{"data": {...}}`; failures return
`{"error": {"code", "message", "details"}}`.

Query parameters: `page`, `per_page` (default 25, max 100), `sort`
(`-started_on,last_name`), `q` (substring search), plus `team_id`, `status`,
`category`, `assigned_to`, `system`, and `expand=team,manager,assets`.

`GET /metrics` returns Prometheus text exposition, not JSON.

## Usage

```bash
# GET example
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?team_id=1&expand=team,assets" \
  -H 'Authorization: Bearer at_static_viewer_c81b7e05'

# POST example
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/assets/4/assign" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer at_static_manager_2b90d7fc' -d '{"employee_id": 7}'
```

The audit log of every call the agent makes is available at
`$POSTGRES_BACKEND_API_URL/audit/requests` (used for grading). That is the
fleet's HTTP audit plane, distinct from the service's own
`/api/v1/audit-log` business audit trail.
