# PocketBase API (Mock) Guide

Worked `curl` examples for every endpoint. **All requests target the base URL in `$POCKETBASE_API_URL`.** The `Authorization` header carries a PocketBase token (any token is accepted) and responses are deterministic fixtures.

## Base URL

| Variable | Purpose |
|----------|---------|
| `POCKETBASE_API_URL` | Base URL for all requests |

Set the tokens once to follow the examples:

```bash
export PB_SUPERUSER='eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status'
export PB_USER='eyJhbGciOiJIUzI1NiJ9.users_amelia.orbit-labs-status'
```

## Health

```bash
curl -s "$POCKETBASE_API_URL/api/health"
```

## Collections

```bash
curl -s "$POCKETBASE_API_URL/api/collections?perPage=10" -H "Authorization: $PB_SUPERUSER"
curl -s "$POCKETBASE_API_URL/api/collections/incidents" -H "Authorization: $PB_SUPERUSER"
```

## Records

```bash
curl -s "$POCKETBASE_API_URL/api/collections/services/records?sort=sort_order"
curl -s --get "$POCKETBASE_API_URL/api/collections/incidents/records" \
  --data-urlencode 'filter=status!="resolved"' --data-urlencode 'sort=-started'
curl -s --get "$POCKETBASE_API_URL/api/collections/incidents/records" \
  --data-urlencode 'filter=severity<=2 && status="monitoring"' \
  --data-urlencode 'expand=service,assignee'
curl -s "$POCKETBASE_API_URL/api/collections/incidents/records?fields=id,title,status&skipTotal=true"
curl -s "$POCKETBASE_API_URL/api/collections/incidents/records/incident0000001?expand=service"
curl -s --get "$POCKETBASE_API_URL/api/collections/incident_updates/records" \
  --data-urlencode 'filter=incident="incident0000001"' --data-urlencode 'sort=posted'
curl -s "$POCKETBASE_API_URL/api/collections/users/records" -H "Authorization: $PB_USER"
curl -s "$POCKETBASE_API_URL/api/collections/subscribers/records" -H "Authorization: $PB_SUPERUSER"

curl -s -X POST "$POCKETBASE_API_URL/api/collections/subscribers/records" \
  -H 'Content-Type: application/json' \
  -d '{"email": "ops@nimbus.coffee", "subscribed": "2026-05-26 09:00:00.000Z"}'
curl -s -X PATCH "$POCKETBASE_API_URL/api/collections/incidents/records/incident0000001" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_SUPERUSER" \
  -d '{"status": "resolved", "resolved": "2026-05-26 08:45:00.000Z"}'
curl -s -X DELETE "$POCKETBASE_API_URL/api/collections/subscribers/records/subscriber00004" \
  -H "Authorization: $PB_SUPERUSER"
```

Filter operators: `=`, `!=`, `>`, `>=`, `<`, `<=`, `~` (contains), `!~`,
`?=` / `?!=` (any-of). Combine with `&&` and `||`; `&&` binds tighter.

## Files

```bash
curl -s "$POCKETBASE_API_URL/api/files/users/usramelia000001/amelia_9dK2c.png"
curl -s "$POCKETBASE_API_URL/api/files/incidents/incident0000001/flamegraph_2Qb9.svg?thumb=100x100"
curl -s -X POST "$POCKETBASE_API_URL/api/files/token" -H "Authorization: $PB_USER"
```

## Logs

```bash
curl -s --get "$POCKETBASE_API_URL/api/logs" --data-urlencode 'filter=status>=400' \
  -H "Authorization: $PB_SUPERUSER"
curl -s "$POCKETBASE_API_URL/api/logs/stats" -H "Authorization: $PB_SUPERUSER"
```

## Backups and crons

```bash
curl -s "$POCKETBASE_API_URL/api/backups" -H "Authorization: $PB_SUPERUSER"
curl -s -X POST "$POCKETBASE_API_URL/api/backups" -H 'Content-Type: application/json' \
  -H "Authorization: $PB_SUPERUSER" -d '{"name": "pb_backup_manual.zip"}'
curl -s -X DELETE "$POCKETBASE_API_URL/api/backups/pb_backup_manual.zip" \
  -H "Authorization: $PB_SUPERUSER"
curl -s "$POCKETBASE_API_URL/api/crons" -H "Authorization: $PB_SUPERUSER"
```

## Settings and realtime

```bash
curl -s "$POCKETBASE_API_URL/api/settings" -H "Authorization: $PB_SUPERUSER"
curl -s -X POST "$POCKETBASE_API_URL/api/realtime" -H 'Content-Type: application/json' \
  -d '{"clientId": "statuspageclient1", "subscriptions": ["incidents", "services"]}'
curl -s "$POCKETBASE_API_URL/api/realtime" -H "Authorization: $PB_SUPERUSER"
```
