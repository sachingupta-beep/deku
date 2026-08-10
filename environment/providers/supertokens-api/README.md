# supertokens-api

Mock of the SuperTokens **core** — the service a backend SDK talks to over HTTP
with an `api-key` header, not the SDK's own frontend routes.

Run it as its own container (build context is the environment root):
```
docker compose up -d supertokens-api
curl http://localhost:8115/health
curl http://localhost:8115/hello
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir supertokens-api --port 8115
```

Two conventions run through every endpoint:

- **Domain outcomes ride in the body, not the status line.** A wrong password is
  `200 {"status": "WRONG_CREDENTIALS_ERROR"}`. Non-2xx is reserved for transport
  problems: a missing or wrong `api-key` (401), an unsupported `cdi-version`
  (400), an unknown tenant (404) and deleting the public tenant (403).
- **Everything is tenant-scoped.** Both `/recipe/...` and the explicit
  `/appid-{appId}/{tenantId}/recipe/...` form are served; the short form resolves
  to `public`. The two seeded tenants enable different recipes on purpose, so the
  same request succeeds on one and is refused on the other.

The API key is `orbit-labs-supertokens-core-key`; send `cdi-version: 5.1`.

Recipes covered: emailpassword, thirdparty, passwordless, session,
emailverification, usermetadata, userroles, multitenancy and account linking.
Passwords are verified for real — `sha256(passwordSalt + password)` — and the
hash is never returned.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`supertokens_api_postman_collection.json` for the runnable collection.
