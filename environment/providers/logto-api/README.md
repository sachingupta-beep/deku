# logto-api

Mock of Logto, the OIDC-first identity service.

Run it as its own container (build context is the environment root):
```
docker compose up -d logto-api
curl http://localhost:8116/health
curl http://localhost:8116/oidc/.well-known/openid-configuration
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir logto-api --port 8116
```

There are two planes, and the boundary between them is the point of the service:

- **`/oidc/*`** is a real OAuth 2.0 authorization server. `POST /oidc/token`
  takes a `grant_type` (`authorization_code`, `refresh_token`,
  `client_credentials`), a `resource` indicator and a `scope`, and mints an
  access token *bound to that resource*. PKCE is required for public clients,
  authorization codes are single-use, and refresh tokens rotate. Errors follow
  RFC 6749 (`error` / `error_description`).
- **`/api/*`** is the Management API, which is itself just another protected
  resource. A bearer works there only if it was issued **for**
  `https://default.logto.app/api` *and* carries a wide enough scope. A perfectly
  valid token minted for the Orbit Status API gets 403, not 401. Errors use
  Logto's `{"code", "message"}` shape.

Seeded bearers, so a request can quote one literally:

| Token | Audience | Scope |
|-------|----------|-------|
| `logto_at_ci_full_9f14c73e0b2a` | Management API | `all` |
| `logto_at_reporting_ro_5b07d21f8c64` | Management API | `read:user` |
| `logto_at_amelia_status_c8e05a1976b3` | Orbit Status API | `read:incidents write:incidents read:services` |
| `logto_at_amelia_org_platform_7a63f04c9e21` | `urn:logto:organization:org5platform1` | `org:read org:write org:invite org:billing` |
| `logto_at_jonas_revoked_1e94c7a305df` | Orbit Status API | revoked |

Passwords are verified for real — `sha256(passwordSalt + password)`; the seed
records `passwordEncryptionMethod` accordingly (Logto itself uses Argon2i). The
password policy in `sign_in_experience.json` is enforced on create and update,
including its rejected-word list.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`logto_api_postman_collection.json` for the runnable collection.
