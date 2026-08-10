# Supabase (self-host) — simulated

Base path `/supabase` · category `backend` · **the reference implementation**

Reproduces the self-hosted Supabase **data plane**: PostgREST, Storage, Edge Functions,
Realtime, and the project read model. GoTrue — sign-up, sign-in, admin users — is a separate
service in the catalog (`supabase-auth`), exactly as the self-hosted stack splits them.

```bash
curl localhost:8080/supabase/health
curl localhost:8080/supabase/rest/v1/projects
curl localhost:8080/supabase/docs          # interactive
```

16 paths / 21 operations — [`openapi.json`](openapi.json) · worked calls in
[`examples.md`](examples.md) · 70 tests in [`tests`](tests/).

---

## Authentication

The `apikey` header — or `Authorization: Bearer <token>` — selects the Postgres role that
row-level security is evaluated against.

| Credential | Role | Can |
|------------|------|-----|
| *(absent)* or the anon key | `anon` | read public rows only; no writes |
| any other non-empty token | `authenticated` | read everything; insert; update |
| the project service key | `service_role` | all of the above, plus **delete** |

Keys are in `GET /supabase/v1/projects/orbitlabsselfhost01`. The anon key is returned in
full — it is public by design; the service key comes back masked, as the dashboard shows it.

**An unfamiliar token maps to `authenticated` rather than being rejected.** That is a
deliberate fleet-wide rule: a simulator that 401s an unrecognised credential turns every task
into a credential hunt instead of the task it was meant to be. The auth layer stays
observable — the three roles produce visibly different responses — without becoming a wall.

---

## Endpoints

### PostgREST — `/rest/v1`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/rest/v1/` | exposed schema |
| GET | `/rest/v1/{table}` | filters, `select`, `order`, `limit`/`offset`, `Content-Range` |
| POST | `/rest/v1/{table}` | object or array; `Prefer: return=minimal` |
| PATCH | `/rest/v1/{table}` | filters select the rows to update |
| DELETE | `/rest/v1/{table}` | `service_role` only; refuses an unfiltered delete |
| POST | `/rest/v1/rpc/{fn}` | `project_stats`, `search_documents`, `publish_document` |

Tables: `profiles`, `projects`, `documents`, `comments`.

**Filters.** Any unreserved query parameter is a filter, `?column=op.value`:

```
eq neq gt gte lt lte like ilike in is cs        each negatable with not.

?status=eq.published          ?star_count=gt.100        ?title=ilike.*rotation*
?id=in.(101,103)              ?published_at=is.null     ?tags=cs.{security}
?status=not.eq.draft
```

Operands are coerced to the stored column's type, so `?star_count=gt.100` compares integers
rather than strings. A filter with no operator is `PGRST100`, as upstream.

**Embedding**, one level, with the relationship inferred:

```
?select=id,name,documents(id,title)      one-to-many
?select=id,title,profiles(username)      many-to-one
```

The join key is read from the source row, so a column projected away still resolves — and
embedded rows are RLS-filtered, so an embed is not a back door into invisible data.

### Row-level security

| Role | `projects` | `documents` | `comments` |
|------|-----------|-------------|------------|
| `anon` | `visibility = public` (2 of 5) | `status = published` (5 of 8) | those on published documents |
| `authenticated` / `service_role` | all | all | all |

### Storage — `/storage/v1`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/storage/v1/bucket` | anon sees public buckets only |
| GET | `/storage/v1/bucket/{id}` | a private bucket is **404** to anon, not 403 |
| POST | `/storage/v1/bucket` | 409 on duplicate |
| DELETE | `/storage/v1/bucket/{id}` | `service_role`; **409 if not empty** |
| POST | `/storage/v1/object/list/{bucket}` | prefix, limit, offset |
| GET | `/storage/v1/object/info/{bucket}/{path}` | metadata |
| POST | `/storage/v1/object/sign/{bucket}/{path}` | signed URL with a token |
| DELETE | `/storage/v1/object/{bucket}/{path}` | `service_role` |

### Edge Functions — `/functions/v1`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/functions/v1` | four seeded functions |
| POST | `/functions/v1/{slug}` | 401 if `verify_jwt` and caller is anon; 429 if `THROTTLED` |

`send-welcome-email` and `generate-report` require a JWT; `billing-webhook` does not;
`resize-avatar` is `THROTTLED` and always 429s — a reachable rate-limit path.

### Realtime — `/realtime/v1`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/realtime/v1/channels` | three channels |
| POST | `/realtime/v1/api/broadcast` | 202; anon cannot broadcast to a private channel |

### Project — `/v1/projects`

| Method | Path | Notes |
|--------|------|-------|
| GET | `/v1/projects` | one project |
| GET | `/v1/projects/{ref}` | settings; service key masked |

---

## Error codes

Upstream's own codes, mapped in one table in [`routes.py`](routes.py) so a code cannot mean
404 on one endpoint and 401 on the next.

| Code | HTTP | Meaning |
|------|------|---------|
| `42P01` | 404 | undefined table |
| `PGRST116` | 404 | no rows where one was required |
| `PGRST202` | 404 | function not found / missing argument |
| `FunctionNotFound` | 404 | unknown edge function |
| `42501` | 401 | RLS denial or insufficient privilege |
| `23503` | 409 | foreign-key violation |
| `Duplicate` | 409 | bucket already exists |
| `409` | 409 | bucket not empty |
| `429` | 429 | function throttled |
| `PGRST100` | 400 | malformed filter |
| `PGRST102` | 400 | malformed body |
| `PGRST109` | 400 | unfiltered delete |
| `P0001` | 400 | `raise exception` from a function |

---

## Seeded data

Orbit Labs, late May 2026.

| Table | Rows | Shape |
|-------|------|-------|
| `profiles` | 6 | amelia, jonas, helena, rohit, noor, orbit_sync_bot |
| `projects` | 5 | 3 private, 2 public; one archived |
| `documents` | 8 | 5 published, 2 draft, 1 archived |
| `comments` | 7 | 4 unresolved; one on a draft document |
| `buckets` | 4 | 1 public (`avatars`), 3 private |
| `objects` | 9 | across all four buckets |
| `functions` | 4 | 3 require JWT, 1 throttled |
| `channels` | 3 | 1 private (`project:101`) |
| `signed_urls`, `invocations` | 0 | born empty — runtime rows only |

Every error path has data behind it: a draft document for the RLS boundary, a non-empty
bucket for the 409, a throttled function for the 429, a private channel for the broadcast
denial. An error path with no data behind it is untestable.

---

## Deviations from upstream

Two, both deliberate:

1. **`DELETE /rest/v1/{table}` refuses an unfiltered delete** with `PGRST109`. Real PostgREST
   will happily empty a table. A benchmark fixture that can be wiped by one malformed request
   is a bad fixture, so the guard rail is here and the response says why.
2. **`api.url` in project settings reads `http://service-hub:8080/supabase`** — the hub's
   address rather than a standalone Supabase host, matching the compose service name.

Everything else matches upstream semantics: SQLSTATEs, `Content-Range`, `Prefer:
return=minimal`, bare-array responses, `signedURL` casing, and the 404-not-403 on a private
bucket.

Not implemented: WebSocket realtime (only the channel list and the broadcast REST endpoint),
object upload/download of actual bytes, GoTrue (see `supabase-auth`), and `on_conflict` upsert.

---

## Files

| File | Role |
|------|------|
| [`service.toml`](service.toml) | manifest — the only file the hub reads at boot |
| [`service.py`](service.py) | `ServiceModule`: lifecycle hooks and wiring (~55 lines) |
| [`routes.py`](routes.py) | HTTP surface; status mapping; no business logic |
| [`data.py`](data.py) | the data layer — PostgREST grammar, RLS, storage, functions |
| [`models.py`](models.py) | request bodies (responses stay raw dicts, on purpose) |
| [`openapi.json`](openapi.json) | exported schema; `tools/export_openapi.py --check` keeps it current |
| [`examples.md`](examples.md) | captured request/response pairs |
| [`tests/`](tests/) | 70 tests, run through the hub |
