# zitadel-api

Mock of Zitadel. Three organizations are seeded — `Orbit Labs`,
`Orbit Partners` and an inactive `Orbit Archive` — and nothing crosses the
boundary between them.

Run it as its own container (build context is the environment root):
```
docker compose up -d zitadel-api
curl http://localhost:8118/health
curl http://localhost:8118/management/v1/orgs/me \
  -H 'Authorization: Bearer zt-pat-orbit-ci-9f14c73e0b2a'
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir zitadel-api --port 8118
```

Two things shape this API, and both are modelled rather than flattened.

**The organization is a header.** `x-zitadel-orgid` selects it for the whole
request; absent, the instance default (Orbit Labs) is used. A user in one org is
not found from another, and a token minted for one org cannot administer another.

**Sessions are built up factor by factor.** There is no login call.
`POST /v2/sessions` records a *factor* for each `check` that passes — `user`,
`password`, `webAuthN`, `totp` — each with its own `verifiedAt`, and `PATCH`
adds more as the user completes them. Every update rotates the session token.
The org's login policy is enforced at the *end*: exchanging a session for an
OIDC callback fails if the accumulated factors do not satisfy it. Orbit Labs
sets `forceMfa`, so a password-only session is refused there and the identical
request succeeds in the partner org.

Personal access tokens, so a request can quote one literally:

| Token | Scope |
|-------|-------|
| `zt-pat-instance-admin-5b07d21f8c64` | `IAM_OWNER` — any org, plus instance endpoints |
| `zt-pat-orbit-ci-9f14c73e0b2a` | Orbit Labs, `ORG_USER_MANAGER` — may write |
| `zt-pat-readonly-c8e05a1976b3` | Orbit Labs, `ORG_OWNER_VIEWER` — reads only |
| `zt-pat-partners-2d47b9e01f5c` | Orbit Partners |
| `zt-pat-revoked-1e94c7a305df` | revoked |

Every write returns Zitadel's `details` envelope with a monotonic `sequence`,
which is what the eventstore actually exposes; errors carry a gRPC status code
in the body next to the HTTP status.

Passwords are verified for real — `sha256(passwordSalt + password)`; Zitadel
uses bcrypt. The password complexity policy (8 characters, an upper-case
letter, a digit and a symbol) is enforced on create and on reset.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`zitadel_api_postman_collection.json` for the runnable collection.
