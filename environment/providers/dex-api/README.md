# dex-api

Mock of Dex, the OIDC federator.

Run it as its own container (build context is the environment root):
```
docker compose up -d dex-api
curl http://localhost:8120/health
curl http://localhost:8120/dex/.well-known/openid-configuration
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir dex-api --port 8120
```

**Dex is a federator, not an identity provider.** It has no user database: real
identities live behind *connectors*, and the only thing Dex stores locally is
the set of static passwords belonging to the built-in `local` connector.
Everything else it knows about a person exists only because a refresh token
remembers it — which is why `/api/v2/refresh/{user_id}` and
`/api/v2/offline-sessions` are the closest thing this API has to a user list.

Three consequences shape the surface:

- **Connectors decide what is possible.** The password grant works through
  `local` and `ldap`; `github` refuses it and tells you to use the browser flow;
  a disabled connector is refused outright.
- **The device authorization grant (RFC 8628) is first-class.** Polling a
  pending code returns `authorization_pending`, polling too eagerly returns
  `slow_down`, and denied, expired and already-redeemed codes each have their
  own error.
- **Cross-client audiences need a trusted peer.** A client may request
  `audience:server:client_id:<other>` only if it is listed on that other
  client's `trustedPeers`.

The gRPC API is served over HTTP under `/api/v2` and keeps Dex's distinctive
**success-with-flag** envelopes: creating a client that already exists is 200
with `already_exists: true`, not 409, and deleting one that does not is 200 with
`not_found: true`, not 404.

Connectors, clients and identities that can be quoted literally:

| Connector | Password grant | Note |
|-----------|----------------|------|
| `local` | yes | the static-password store |
| `ldap` | yes | same credentials, identity keyed by DN |
| `github` | **no** | browser flow only |
| `orbit-saml` | — | **disabled** |

| Client | Secret | Grants |
|--------|--------|--------|
| `orbit-status-web` | `dex-secret-status-web-9f14c73e0b2a` | code, refresh, **password** |
| `orbit-cli` | _(public)_ | code, refresh, **device** |
| `orbit-grafana` | `dex-secret-grafana-5b07d21f8c64` | code, refresh; trusts `orbit-kubectl` |
| `orbit-kubectl` | `dex-secret-kubectl-1c84f065` | code, refresh, **device** |

| Identity | Password | Connector |
|----------|----------|-----------|
| `amelia.ortega@orbit-labs.com` | `OrbitDex2026!` | local |
| `jonas.pereira@orbit-labs.com` | `OrbitJonas2026!` | local |
| `rohit.bansal@orbit-labs.com` | `OrbitRohit2026!` | local |
| `sync-bot@orbit-labs.com` | `OrbitSyncBot2026!` | local |
| `helena.park@orbit-labs.com` | — | **github only** |
| `noor.aziz@orbit-labs.com` | — | **ldap only** (remembered by a refresh token) |

Passwords are verified for real — `sha256(salt + password)`; Dex stores bcrypt.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`dex_api_postman_collection.json` for the runnable collection.
