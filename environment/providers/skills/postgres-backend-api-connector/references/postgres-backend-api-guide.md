# Orbit Back-office API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$POSTGRES_BACKEND_API_URL`.** Auth is a bearer token (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `POSTGRES_BACKEND_API_URL` | Base URL for all requests |

Set the tokens once to follow the examples:

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
curl -s "$POSTGRES_BACKEND_API_URL/metrics"
```

## Auth

```bash
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "OrbitAdmin2026!"}'
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/auth/refresh" \
  -H 'Content-Type: application/json' -d '{"refresh_token": "rt_..."}'
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/auth/me" -H "Authorization: $PB_MANAGER"
curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/auth/logout" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_ADMIN" -d '{}'
```

## Employees

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?per_page=3&sort=last_name" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?q=engineer&sort=-started_on" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?team_id=1&status=active" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees?expand=team,manager,assets" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/employees/3?expand=team,assets" \
  -H "Authorization: $PB_VIEWER"

curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/employees" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_ADMIN" \
  -d '{"first_name": "Mira", "last_name": "Castellanos",
       "email": "mira.castellanos@orbit-labs.com", "title": "Platform Engineer",
       "team_id": 1, "manager_id": 1}'

curl -s -X PATCH "$POSTGRES_BACKEND_API_URL/api/v1/employees/7" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_MANAGER" \
  -d '{"title": "Senior Support Engineer"}'

curl -s -X DELETE "$POSTGRES_BACKEND_API_URL/api/v1/employees/9" -H "Authorization: $PB_ADMIN"
```

Deleting is refused (409) while the employee holds assets, is referenced by an
access request, or has direct reports.

## Teams

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/teams?sort=name" -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/teams/1" -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/teams/4/employees?status=active" \
  -H "Authorization: $PB_VIEWER"
```

## Assets

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/assets?sort=asset_tag&per_page=5" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/assets?status=in_stock&category=laptop" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/assets?q=thinkpad" -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/assets/5" -H "Authorization: $PB_VIEWER"

curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/assets" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_MANAGER" \
  -d '{"asset_tag": "OL-LT-0046", "category": "laptop", "model": "MacBook Pro 16 M4"}'

curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/assets/4/assign" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_MANAGER" \
  -d '{"employee_id": 7}'

curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/assets/5/return" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_MANAGER" \
  -d '{"condition": "repair", "note": "Cracked screen, RMA 90114 raised."}'
```

## Access requests

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/access-requests?sort=-requested_at" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/access-requests?status=pending&system=production-database" \
  -H "Authorization: $PB_VIEWER"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/access-requests/2" -H "Authorization: $PB_VIEWER"

curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/access-requests" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_VIEWER" \
  -d '{"employee_id": 7, "system": "grafana", "access_level": "read_only",
       "justification": "Support triage needs dashboard access."}'

curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/access-requests/1/approve" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_MANAGER" \
  -d '{"note": "Approved for the cutover window only."}'

curl -s -X POST "$POSTGRES_BACKEND_API_URL/api/v1/access-requests/5/deny" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_ADMIN" \
  -d '{"note": "Use the shared on-call schedule instead."}'
```

Access levels are `read_only`, `read_write` and `admin`. A request can only be
decided once, duplicate pending requests for the same (employee, system) are
rejected, and nobody may decide their own request.

## Audit log and meta

```bash
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/audit-log?per_page=5" -H "Authorization: $PB_ADMIN"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/audit-log?entity_type=asset" -H "Authorization: $PB_ADMIN"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/_meta/migrations" -H "Authorization: $PB_ADMIN"
curl -s "$POSTGRES_BACKEND_API_URL/api/v1/_meta/schema" -H "Authorization: $PB_ADMIN"
```
