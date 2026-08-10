# keycloak-api

Mock of Keycloak. Two realms are seeded — `orbit-labs` and `orbit-partners` —
and nothing crosses the boundary between them.

Run it as its own container (build context is the environment root):
```
docker compose up -d keycloak-api
curl http://localhost:8117/health
curl http://localhost:8117/realms/orbit-labs/.well-known/openid-configuration
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir keycloak-api --port 8117
```

Two URL families, both realm-scoped:

- **`/realms/{realm}/protocol/openid-connect/...`** — what a client talks to.
  `POST .../token` supports `password` (Keycloak's direct grant),
  `refresh_token` and `client_credentials`. Errors are RFC 6749.
- **`/admin/realms/{realm}/...`** — the Admin REST API. It takes the master
  admin token, or any live session token *for that realm*, and checks the
  caller's `realm-management` client roles. Errors are Keycloak's
  `{"error", "errorMessage"}`.

Three things are modelled properly rather than flattened:

- **The direct grant fails four different ways**, each with the message
  Keycloak actually returns: a wrong password (`401 Invalid user credentials`),
  a disabled account (`400 Account disabled`), pending required actions
  (`400 Account is not fully set up`) and a brute-force lock (401, deliberately
  worded identically to a wrong password so the response cannot confirm the
  account exists).
- **Composite roles** expand transitively across realm *and* client roles.
  `platform-operator` drags in `incident-responder`, `status-viewer` and the
  client role `realm-management:view-users`.
- **Groups carry role mappings and subgroups inherit them.** Amelia's *direct*
  mappings are one realm role and one client role; her *effective* set is six
  realm roles and four client roles.

Tokens, so a request can quote one literally:

| Token | Who |
|-------|-----|
| `kc-at-master-admin-cli-8f0c31d47a92` | master `admin-cli` — administers any realm |
| `kc-at-amelia-ui-6b40d2a97f15` | amelia, `orbit-labs` — holds `realm-admin` |
| `kc-at-jonas-ui-2f83b0e6c194` | jonas, `orbit-labs` — only `view-users`, inherited via `/platform` |
| `kc-at-priya-portal-1d75a0e934bc` | priya, `orbit-partners` |
| `kc-at-amelia-cli-revoked-0e47c95b` | expired |

Passwords are verified for real — `sha256(credentialSalt + password)`; Keycloak
uses PBKDF2, and the credential representation says so. The realm's
`passwordPolicy` string (`length(12) and upperCase(1) and digits(1) and
notUsername`) is parsed and enforced on create and reset.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`keycloak_api_postman_collection.json` for the runnable collection.
