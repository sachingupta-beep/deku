# PocketBase Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$POCKETBASE_API_URL`; responses are verbatim (long arrays elided
with `…`). Authenticated examples assume:

```bash
export PB_SUPERUSER='eyJhbGciOiJIUzI1NiJ9.superuser.orbit-labs-status'
export PB_USER='eyJhbGciOiJIUzI1NiJ9.users_amelia.orbit-labs-status'
```

## Health

```bash
curl -s "$POCKETBASE_API_URL/health"
curl -s "$POCKETBASE_API_URL/api/health"
```
```json
{"status": "ok"}
{"code": 200, "message": "API is healthy.",
 "data": {"canBackup": true, "version": "v0.24.4", "appName": "Orbit Labs Status"}}
```

## Collections

```bash
curl -s "$POCKETBASE_API_URL/api/collections/incidents" -H "Authorization: $PB_SUPERUSER"
```
```json
{"id": "colincidents001", "name": "incidents", "type": "base", "system": false,
 "fields": [{"name": "title", "type": "text", "required": true},
            {"name": "service", "type": "relation", "required": true},
            {"name": "severity", "type": "number", "required": true}, "…"],
 "indexes": ["CREATE INDEX idx_incidents_service ON incidents (service)"],
 "created": "2024-02-10 09:52:00.000Z", "updated": "2026-01-20 12:00:00.000Z",
 "listRule": "", "viewRule": "", "createRule": null, "updateRule": null, "deleteRule": null}
```

`""` is a public rule; `null` is superuser-only. Without the superuser token the
same request answers 403 `Only superusers can perform this action.`

## Records — list, filter, sort

```bash
curl -s "$POCKETBASE_API_URL/api/collections/services/records?sort=sort_order&perPage=10"
```
```json
{"page": 1, "perPage": 10, "totalItems": 5, "totalPages": 1,
 "items": [{"id": "svcauthapi00001", "collectionId": "colservices0001",
            "collectionName": "services", "key": "auth-api",
            "name": "Authentication API", "status": "degraded",
            "uptime_30d": 99.61, "sort_order": 1, "monitored": true,
            "created": "2024-04-12 10:00:00.000Z", "updated": "2026-05-26 06:40:00.000Z"}, "…"]}
```

```bash
curl -s --get "$POCKETBASE_API_URL/api/collections/incidents/records" \
  --data-urlencode 'filter=status!="resolved"' --data-urlencode 'sort=-started'
```
```json
{"page": 1, "perPage": 30, "totalItems": 2, "totalPages": 1,
 "items": [{"id": "incident0000001", "title": "Elevated refresh-token latency",
            "status": "monitoring", "severity": 2, "…": "…"},
           {"id": "incident0000002", "title": "Scheduled Postgres minor-version upgrade",
            "status": "identified", "severity": 4, "…": "…"}]}
```

`&&` binds tighter than `||`, and operators inside quoted strings are ignored:

```bash
curl -s --get "$POCKETBASE_API_URL/api/collections/incidents/records" \
  --data-urlencode 'filter=title~"latency" || impact~"outage"' --data-urlencode 'sort=-started'
# -> totalItems: 2  (incident0000001 by title, incident0000004 by impact)
```

## Records — expand and fields

```bash
curl -s --get "$POCKETBASE_API_URL/api/collections/incidents/records" \
  --data-urlencode 'filter=severity<=2 && status="monitoring"' \
  --data-urlencode 'expand=service,assignee'
```
```json
{"page": 1, "perPage": 30, "totalItems": 1, "totalPages": 1,
 "items": [{"id": "incident0000001", "title": "Elevated refresh-token latency",
            "service": "svcauthapi00001", "assignee": "usrjonas0000002",
            "attachments": ["latency_p95_7Kd2.png", "flamegraph_2Qb9.svg"],
            "expand": {"service": {"id": "svcauthapi00001", "key": "auth-api",
                                   "name": "Authentication API", "status": "degraded", "…": "…"},
                       "assignee": {"id": "usrjonas0000002", "username": "jonas",
                                    "email": "", "oncall": true, "…": "…"}}}]}
```

```bash
curl -s "$POCKETBASE_API_URL/api/collections/incidents/records?fields=id,title,status,severity&perPage=3&skipTotal=true"
```
```json
{"page": 1, "perPage": 3, "totalItems": -1, "totalPages": -1,
 "items": [{"id": "incident0000001", "title": "Elevated refresh-token latency",
            "status": "monitoring", "severity": 2},
           {"id": "incident0000002", "title": "Scheduled Postgres minor-version upgrade",
            "status": "identified", "severity": 4},
           {"id": "incident0000003", "title": "Invoice PDF generation backlog",
            "status": "resolved", "severity": 3}]}
```

## Collection rules in action

```bash
curl -s "$POCKETBASE_API_URL/api/collections/subscribers/records"
```
```json
{"error": "Only superusers can perform this action.", "code": 403,
 "message": "Only superusers can perform this action.", "data": {}}
```

```bash
curl -s --get "$POCKETBASE_API_URL/api/collections/subscribers/records" \
  --data-urlencode 'filter=confirmed=false' -H "Authorization: $PB_SUPERUSER"
```
```json
{"page": 1, "perPage": 30, "totalItems": 1, "totalPages": 1,
 "items": [{"id": "subscriber00004", "email": "finance@pelagicfreight.com",
            "name": "Pelagic Freight Finance", "services": ["svcbillingapi02"],
            "confirmed": false, "subscribed": "2026-05-19 16:30:00.000Z", "…": "…"}]}
```

The `users` collection hides `email` unless the caller owns the record, is a
superuser, or the record sets `emailVisibility: true`:

```bash
curl -s "$POCKETBASE_API_URL/api/collections/users/records?filter=oncall=true" \
  -H "Authorization: $PB_USER"
```
```json
{"page": 1, "perPage": 30, "totalItems": 1, "totalPages": 1,
 "items": [{"id": "usrjonas0000002", "username": "jonas", "email": "",
            "emailVisibility": false, "verified": true, "name": "Jonas Pereira",
            "avatar": "jonas_4bQ7x.png", "role": "engineer", "oncall": true, "…": "…"}]}
```

## Create, update, delete

`subscribers` has a public create rule, so the status page can subscribe visitors
without a token. Record creates return **200**, not 201.

```bash
curl -s -X POST "$POCKETBASE_API_URL/api/collections/subscribers/records" \
  -H 'Content-Type: application/json' \
  -d '{"email": "ops@nimbus.coffee", "name": "Nimbus Coffee Ops",
       "services": ["svcauthapi00001"], "confirmed": false,
       "subscribed": "2026-05-26 09:00:00.000Z"}'
```
```json
{"id": "d2da19b3ee3642f", "collectionId": "colsubscribers1",
 "collectionName": "subscribers", "email": "ops@nimbus.coffee",
 "name": "Nimbus Coffee Ops", "services": ["svcauthapi00001"], "confirmed": false,
 "subscribed": "2026-05-26 09:00:00.000Z", "created": "…", "updated": "…"}
```

```bash
curl -s -X PATCH "$POCKETBASE_API_URL/api/collections/incidents/records/incident0000001" \
  -H 'Content-Type: application/json' -H "Authorization: $PB_SUPERUSER" \
  -d '{"status": "resolved", "resolved": "2026-05-26 08:45:00.000Z"}'
```
```json
{"id": "incident0000001", "title": "Elevated refresh-token latency",
 "status": "resolved", "resolved": "2026-05-26 08:45:00.000Z", "…": "…"}
```

```bash
curl -s -X DELETE "$POCKETBASE_API_URL/api/collections/subscribers/records/subscriber00004" \
  -H "Authorization: $PB_SUPERUSER"
```
```json
{"deleted": "subscriber00004"}
```

## Error paths

| Request | Status | Body |
|---------|--------|------|
| `POST /api/collections/subscribers/records` without `email` | 400 | `{"code": 400, "message": "Failed to create record.", "data": {"email": {"code": "validation_required", "message": "Missing required value."}}}` |
| `POST /api/collections/incidents/records` with `service: "svcdoesnotexist"` | 400 | `{"code": 400, "message": "Failed to create record.", "data": {"service": {"code": "validation_missing_rel_records", "message": "Failed to find records from field service: svcdoesnotexist."}}}` |
| `POST /api/collections/incidents/records` as guest | 403 | `{"code": 403, "message": "Only superusers can perform this action.", "data": {}}` |
| `GET /api/collections/incidents/records/incident0000099` | 404 | `{"code": 404, "message": "The requested resource wasn't found.", "data": {}}` |
| `POST /api/realtime` with `subscriptions: ["deployments"]` | 400 | `{"code": 400, "data": {"subscriptions": {"code": "validation_unknown_collection", "message": "Unknown topic(s): deployments."}}}` |

## Files

`GET /api/files/...` returns the descriptor rather than the bytes; `size` is
derived from the filename so it is identical on every run.

```bash
curl -s "$POCKETBASE_API_URL/api/files/incidents/incident0000001/flamegraph_2Qb9.svg?thumb=100x100"
```
```json
{"collectionId": "colincidents001", "collectionName": "incidents",
 "recordId": "incident0000001", "field": "attachments",
 "filename": "flamegraph_2Qb9.svg", "thumb": "100x100",
 "mimeType": "image/svg+xml", "size": 71066,
 "url": "/api/files/incidents/incident0000001/flamegraph_2Qb9.svg"}
```

```bash
curl -s -X POST "$POCKETBASE_API_URL/api/files/token" -H "Authorization: $PB_USER"
```
```json
{"token": "a538ab86eeb64f34b880851ddd4ae744"}
```

## Logs, backups, crons

```bash
curl -s --get "$POCKETBASE_API_URL/api/logs" --data-urlencode 'filter=status>=400' \
  --data-urlencode 'perPage=5' -H "Authorization: $PB_SUPERUSER"
```
```json
{"page": 1, "perPage": 5, "totalItems": 2, "totalPages": 1,
 "items": [{"id": "log000000000003", "level": 4, "message": "Failed to authenticate request",
            "method": "GET", "url": "/api/collections/subscribers/records", "status": 403,
            "execTime": 0.611, "userIp": "192.0.2.77", "created": "2026-05-26 07:31:47.900Z"}, "…"]}
```

```bash
curl -s "$POCKETBASE_API_URL/api/logs/stats" -H "Authorization: $PB_SUPERUSER"
```
```json
[{"date": "2026-05-25 00:00:00.000Z", "total": 3},
 {"date": "2026-05-26 00:00:00.000Z", "total": 5}]
```

```bash
curl -s "$POCKETBASE_API_URL/api/backups" -H "Authorization: $PB_SUPERUSER"
curl -s "$POCKETBASE_API_URL/api/crons" -H "Authorization: $PB_SUPERUSER"
```
```json
[{"key": "pb_backup_orbit_status_20260526020000.zip", "size": 48213504,
  "modified": "2026-05-26 02:00:04.021Z"}, "…"]
[{"id": "__pbDBOptimize__", "expression": "0 0 * * *"},
 {"id": "__pbAutoBackup__", "expression": "0 2 * * *"},
 {"id": "digestStatusEmail", "expression": "0 8 * * 1"}, "…"]
```

## Realtime

`GET /api/realtime` lists recorded subscriptions instead of holding an SSE stream.

```bash
curl -s -X POST "$POCKETBASE_API_URL/api/realtime" -H 'Content-Type: application/json' \
  -d '{"clientId": "statuspageclient1", "subscriptions": ["incidents", "services"]}'
```
```json
{"clientId": "statuspageclient1", "subscriptions": ["incidents", "services"],
 "identity": "", "created": "…"}
```

## Settings

```bash
curl -s "$POCKETBASE_API_URL/api/settings" -H "Authorization: $PB_SUPERUSER"
```
```json
{"meta": {"appName": "Orbit Labs Status", "appURL": "https://status.orbit-labs.com",
          "senderAddress": "status@orbit-labs.com", "hideControls": false},
 "logs": {"maxDays": 7, "minLevel": 0, "logIP": true, "logAuthId": false},
 "backups": {"cron": "0 2 * * *", "cronMaxKeep": 3, "s3": {"enabled": false, "…": "…"}},
 "smtp": {"enabled": true, "host": "mailpit", "port": 1025, "tls": false, "authMethod": "PLAIN"},
 "rateLimits": {"enabled": true, "rules": [{"label": "*:auth", "maxRequests": 5, "duration": 10}, "…"]},
 "version": "v0.24.4",
 "database": {"driver": "sqlite3", "file": "pb_data/data.db", "sizeBytes": 20971520}}
```

The `tokens` block from `settings.json` is stripped from this response.
