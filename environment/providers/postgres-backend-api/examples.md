# Orbit Back-office API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$POSTGRES_BACKEND_API_URL`; responses are verbatim (long arrays
elided with `…`). The examples assume:

```bash
export PB_ADMIN='Bearer at_static_admin_9f3c1a7e'
export PB_MANAGER='Bearer at_static_manager_2b90d7fc'
export PB_VIEWER='Bearer at_static_viewer_c81b7e05'
```

## Operational endpoints

```bash
curl -s "$POSTGRES_BACKEND_API_URL/health"
curl -s "$POSTGRES_BACKEND_API_URL/health/db"
curl -s "$POSTGRES_BACKEND_API_URL/health/ready"
```
```json
{"status": "ok"}
{"status": "ok", "engine": "postgresql", "version": "15.6", "latency_ms": 3.1,
 "pool": {"min": 2, "max": 20, "in_use": 3, "idle": 5}, "replica_lag_ms": 42}
{"status": "ok", "version": "2.7.3", "commit": "9f3c1a7e5b2d",
 "checks": {"database": "ok", "migrations": "ok", "cache": "ok"},
 "migrations_applied": 7, "current_migration": "20260211091400"}
```

`GET /metrics` answers Prometheus text exposition, not JSON:

```
# HELP http_requests_total Total HTTP requests served.
# TYPE http_requests_total counter
http_requests_total{service="orbit-backoffice-api"} 1284315
# HELP db_pool_connections Connections in the PostgreSQL pool.
# TYPE db_pool_connections gauge
db_pool_connections{state="in_use"} 3
db_pool_connections{state="idle"} 5
# HELP table_rows Rows currently stored per table.
# TYPE table_rows gauge
table_rows{table="teams"} 4
table_rows{table="employees"} 8
table_rows{table="users"} 4
table_rows{table="assets"} 10
table_rows{table="access_requests"} 7
table_rows{table="audit_log"} 8
```

The `table_rows` gauges read the live store, so they move as a run mutates data.

## Authentication

```bash
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "OrbitAdmin2026!"}'
```
```json
{"access_token": "at_9b6f433dbdac4ef9aac9b6cadbdfb0f5",
 "refresh_token": "rt_0292b013c41d4daeaa4da8a4d0fe3bac",
 "token_type": "Bearer", "expires_in": 900,
 "user": {"id": 1, "email": "amelia.ortega@orbit-labs.com", "role": "admin",
          "status": "active", "employee_id": 1,
          "last_login_at": "2026-05-26T08:12:00Z"}}
```

A wrong password increments `failed_logins` and returns 401; the fifth failure
locks the account. `noor.aziz@orbit-labs.com` is seeded at the limit:

```json
{"error": {"code": "account_locked",
           "message": "Account is locked after too many failed sign-in attempts",
           "details": {"failed_logins": 5}}}
```

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/auth/me" -H "Authorization: $PB_MANAGER"
```
```json
{"data": {"id": 2, "email": "jonas.pereira@orbit-labs.com", "role": "manager",
          "status": "active", "employee_id": 2,
          "last_login_at": "2026-05-25T17:40:00Z",
          "employee": {"id": 2, "first_name": "Jonas", "last_name": "Pereira",
                       "title": "Staff Engineer, Billing", "team_id": 2, "…": "…"}}}
```

## Pagination, sorting, search

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?per_page=3&sort=last_name" \
  -H "Authorization: $PB_VIEWER"
```
```json
{"data": [{"id": 5, "first_name": "Noor", "last_name": "Aziz", "status": "on_leave", "…": "…"},
          {"id": 4, "first_name": "Rohit", "last_name": "Bansal", "…": "…"},
          {"id": 8, "first_name": "Tobias", "last_name": "Krause", "status": "offboarded", "…": "…"}],
 "meta": {"page": 1, "per_page": 3, "total": 8, "total_pages": 3},
 "links": {"self": "/api/v1/employees?page=1&per_page=3",
           "first": "/api/v1/employees?page=1&per_page=3",
           "last": "/api/v1/employees?page=3&per_page=3",
           "prev": null,
           "next": "/api/v1/employees?page=2&per_page=3"}}
```

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?q=engineer&sort=-started_on" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?team_id=1&status=active" \
  -H "Authorization: $PB_VIEWER"
```

Sorting by a column the resource does not have is a client error that names the
alternatives:

```json
{"error": {"code": "invalid_sort", "message": "Cannot sort by unknown column 'salary'",
           "details": {"allowed": ["email", "employment_type", "ended_on", "first_name",
                                   "id", "last_name", "location", "manager_id", "started_on",
                                   "status", "team_id", "title"]}}}
```

## Expansions

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?team_id=1&expand=team,manager,assets" \
  -H "Authorization: $PB_VIEWER"
```
```json
{"data": [{"id": 1, "first_name": "Amelia", "last_name": "Ortega",
           "title": "Head of Platform", "team_id": 1, "manager_id": null,
           "team": {"id": 1, "name": "Platform", "slug": "platform",
                    "cost_centre": "CC-1000", "headcount_budget": 8, "…": "…"},
           "manager": null,
           "assets": [{"id": 1, "asset_tag": "OL-LT-0041", "category": "laptop",
                       "model": "MacBook Pro 14 M4", "status": "assigned", "…": "…"}]}, "…"],
 "meta": {"page": 1, "per_page": 25, "total": 3, "total_pages": 1}, "links": {"…": "…"}}
```

Teams carry a computed `headcount` that excludes offboarded staff:

```json
{"data": {"id": 1, "name": "Platform", "cost_centre": "CC-1000",
          "headcount_budget": 8, "headcount": 3,
          "lead": {"id": 1, "first_name": "Amelia", "last_name": "Ortega", "…": "…"}}}
```

## Writes and role checks

```bash
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/employees" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_ADMIN" \
  -d '{"first_name": "Mira", "last_name": "Castellanos",
       "email": "mira.castellanos@orbit-labs.com", "title": "Platform Engineer",
       "team_id": 1, "manager_id": 1, "location": "Madrid", "started_on": "2026-06-01"}'
```
```json
{"data": {"id": 9, "first_name": "Mira", "last_name": "Castellanos",
          "email": "mira.castellanos@orbit-labs.com", "title": "Platform Engineer",
          "team_id": 1, "manager_id": 1, "location": "Madrid",
          "employment_type": "full_time", "status": "active",
          "started_on": "2026-06-01", "ended_on": null}}
```

The same call as a manager is refused:

```json
{"error": {"code": "insufficient_role",
           "message": "Role 'manager' cannot perform this action",
           "details": {"required_role": "admin"}}}
```

Validation reports every offending field at once:

```json
{"error": {"code": "validation_error", "message": "Request body failed validation",
           "details": [{"field": "last_name", "issue": "required"},
                       {"field": "title", "issue": "required"},
                       {"field": "team_id", "issue": "required"}]}}
```

## Referential integrity

Deleting an employee is refused three different ways, each naming the real
Postgres constraint:

```bash
curl -s -X DELETE "$POSTGRES_BACKEND_API_URL/api/v1/employees/3" -H "Authorization: $PB_ADMIN"
```
```json
{"error": {"code": "conflict", "message": "Employee still holds assigned assets",
           "details": [{"field": "assets", "issue": "must_be_returned",
                        "asset_tags": ["OL-LT-0043", "OL-LC-0301"]}]}}
```

```bash
curl -s -X DELETE "$POSTGRES_BACKEND_API_URL/api/v1/employees/6" -H "Authorization: $PB_ADMIN"
```
```json
{"error": {"code": "conflict",
           "message": "update or delete on table \"employees\" violates foreign key constraint \"access_requests_employee_id_fkey\"",
           "details": [{"field": "employee_id", "issue": "referenced",
                        "table": "access_requests", "request_ids": [2]}]}}
```

An employee with no dependencies deletes cleanly and returns **204** with no body.

## Asset lifecycle

```bash
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/assets/4/assign" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_MANAGER" \
  -d '{"employee_id": 7}'
```
```json
{"data": {"id": 4, "asset_tag": "OL-LT-0044", "category": "laptop",
          "model": "ThinkPad X1 Carbon G12", "status": "assigned",
          "assigned_to": 7, "purchase_cost_cents": 189900, "…": "…"}}
```

```bash
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/assets/5/return" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_MANAGER" \
  -d '{"condition": "repair", "note": "Cracked screen, RMA 90114 raised."}'
```
```json
{"data": {"id": 5, "asset_tag": "OL-PH-0012", "status": "repair",
          "assigned_to": null, "notes": "Cracked screen, RMA 90114 raised."}}
```

| Attempt | Result |
|---------|--------|
| Assign an asset already held by someone else | 409, naming the current holder |
| Assign a `retired` asset | 409 `Asset OL-LT-0045 is 'retired' and cannot be assigned` |
| Assign to an offboarded employee | 409 |
| Return an asset that is not assigned | 409 |
| Assign as a viewer | 403 `insufficient_role` |
| `condition` outside in_stock / repair / retired | 422, listing the allowed values |

## Access-request workflow

```bash
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/access-requests" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_VIEWER" \
  -d '{"employee_id": 7, "system": "grafana", "access_level": "read_only",
       "justification": "Support triage needs dashboard access.",
       "expires_on": "2026-08-31"}'
```
```json
{"data": {"id": 8, "employee_id": 7, "system": "grafana",
          "access_level": "read_only", "status": "pending",
          "requested_at": "…", "decided_at": null, "decided_by": null,
          "decision_note": "", "expires_on": "2026-08-31"}}
```

```bash
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/access-requests/1/approve" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_MANAGER" \
  -d '{"note": "Approved for the cutover window only."}'
```
```json
{"data": {"id": 1, "employee_id": 3, "system": "production-database",
          "access_level": "read_write", "status": "approved",
          "decided_at": "…", "decided_by": 2,
          "decision_note": "Approved for the cutover window only."}}
```

Nobody may decide their own request — request 7 belongs to Jonas, so the manager
token is refused even though the role is sufficient:

```json
{"error": {"code": "self_approval_forbidden",
           "message": "You cannot decide your own access request"}}
```

Deciding an already-decided request, or filing a second pending request for the
same (employee, system), both return 409.

## Audit trail

Every write appends an entry. After the writes above:

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/audit-log?per_page=5" -H "Authorization: $PB_ADMIN"
```
```json
{"data": [{"id": 11, "actor_user_id": 1, "action": "employee.created",
           "entity_type": "employee", "entity_id": "9",
           "summary": "Created Mira Castellanos", "ip": "203.0.113.41", "created_at": "…"},
          {"id": 10, "actor_user_id": 2, "action": "auth.login_failed",
           "entity_type": "user", "entity_id": "2",
           "summary": "Bad password (attempt 1 of 5)", "…": "…"}, "…"],
 "meta": {"page": 1, "per_page": 5, "total": 16, "total_pages": 4}, "links": {"…": "…"}}
```

Reading the audit log requires the admin role; a manager gets 403.

## Schema and migrations

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/_meta/migrations" -H "Authorization: $PB_ADMIN"
```
```json
{"data": [{"version": "20240108090000", "name": "create_teams",
           "applied_at": "2024-01-08T09:00:00Z", "checksum": "9d3f01a6c47b5e28",
           "execution_ms": 41}, "…"],
 "meta": {"applied": 7, "current_version": "20260211091400", "pending": 0}}
```

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/_meta/schema" -H "Authorization: $PB_ADMIN"
```
```json
{"data": {"database": "orbit_backoffice", "schema": "public",
          "engine": "postgresql 15.6",
          "tables": [{"table": "teams", "primary_key": "id", "row_count": 4,
                      "columns": [{"name": "id", "type": "integer", "nullable": false},
                                  {"name": "name", "type": "text", "nullable": false}, "…"],
                      "foreign_keys": [{"column": "lead_employee_id",
                                        "references": "employees(id)"}]}, "…"]}}
```
