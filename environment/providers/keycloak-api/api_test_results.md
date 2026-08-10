# Keycloak Mock API — Test Results

Base URL: `http://localhost:8117` (in docker-compose: `http://keycloak-api:8117`)

## Endpoints covered

### OIDC (per realm)

| Method | Path                                                     | Status      |
|--------|----------------------------------------------------------|-------------|
| GET    | /realms/{realm}                                          | 200/404     |
| GET    | /realms/{realm}/.well-known/openid-configuration         | 200/404     |
| GET    | /realms/{realm}/protocol/openid-connect/certs            | 200/404     |
| POST   | /realms/{realm}/protocol/openid-connect/token            | 200/400/401 |
| POST   | /realms/{realm}/protocol/openid-connect/token/introspect | 200         |
| GET    | /realms/{realm}/protocol/openid-connect/userinfo         | 200/401     |
| POST   | /realms/{realm}/protocol/openid-connect/logout           | 204/400     |

### Admin REST API

| Method | Path                                                           | Status              |
|--------|----------------------------------------------------------------|---------------------|
| GET    | /admin/serverinfo                                              | 200/401             |
| GET    | /admin/realms                                                  | 200/401             |
| GET/PUT| /admin/realms/{realm}                                          | 200/401/403/404     |
| GET    | /admin/realms/{realm}/clients                                  | 200/403             |
| GET    | /admin/realms/{realm}/clients/{uuid}                           | 200/403/404         |
| GET    | /admin/realms/{realm}/clients/{uuid}/client-secret             | 200/400/403/404     |
| GET    | /admin/realms/{realm}/clients/{uuid}/roles                     | 200/403/404         |
| GET    | /admin/realms/{realm}/clients/{uuid}/user-sessions             | 200/403/404         |
| GET/POST | /admin/realms/{realm}/roles                                  | 200/201/403/409     |
| GET/DELETE | /admin/realms/{realm}/roles/{roleName}                     | 200/204/403/404     |
| GET    | /admin/realms/{realm}/roles/{roleName}/composites              | 200/403/404         |
| GET/POST | /admin/realms/{realm}/users                                  | 200/201/400/403/409 |
| GET    | /admin/realms/{realm}/users/count                              | 200/403             |
| GET/PUT/DELETE | /admin/realms/{realm}/users/{id}                       | 200/204/403/404/409 |
| PUT    | /admin/realms/{realm}/users/{id}/reset-password                | 204/400/403/404     |
| PUT    | /admin/realms/{realm}/users/{id}/execute-actions-email         | 200/400/403/404     |
| GET    | /admin/realms/{realm}/users/{id}/sessions · /offline-sessions  | 200/403/404         |
| POST   | /admin/realms/{realm}/users/{id}/logout                        | 204/403/404         |
| GET    | /admin/realms/{realm}/users/{id}/role-mappings                 | 200/403/404         |
| GET    | /admin/realms/{realm}/users/{id}/role-mappings/effective       | 200/403/404         |
| POST/DELETE | /admin/realms/{realm}/users/{id}/role-mappings/realm      | 204/403/404         |
| GET/POST | /admin/realms/{realm}/users/{id}/role-mappings/clients/{uuid}| 200/204/403/404     |
| GET/POST | /admin/realms/{realm}/groups                                 | 200/201/403/409     |
| GET/DELETE | /admin/realms/{realm}/groups/{id}                          | 200/204/400/403/404 |
| POST   | /admin/realms/{realm}/groups/{id}/children                     | 201/403/404/409     |
| GET    | /admin/realms/{realm}/groups/{id}/members · /role-mappings      | 200/403/404         |
| GET    | /admin/realms/{realm}/users/{id}/groups                        | 200/403/404         |
| PUT/DELETE | /admin/realms/{realm}/users/{id}/groups/{groupId}          | 204/403/404         |
| GET    | /admin/realms/{realm}/identity-provider/instances[/{alias}]     | 200/403/404         |
| GET    | /admin/realms/{realm}/authentication/required-actions          | 200/403             |
| GET/DELETE | /admin/realms/{realm}/attack-detection/brute-force/users[/{id}] | 200/204/403/404 |
| GET    | /admin/realms/{realm}/events · /admin-events                   | 200/403             |

Collection run: **PASS 82 / WARN 47 / FAIL 0 / SKIP 0**. Every WARN is an
intentional error-path request, labelled `(N expected)` in the collection.

## The direct grant fails four different ways

`grant_type=password` is Keycloak's first-class login, and the collection walks
each refusal with the message Keycloak actually returns:

| User | Password | Result |
|------|----------|--------|
| amelia | wrong | `401 invalid_grant` — *Invalid user credentials* |
| noor | correct | `400 invalid_grant` — *Account disabled* (`enabled: false`) |
| rohit | correct | `400 invalid_grant` — *Account is not fully set up* (pending `UPDATE_PASSWORD`, `VERIFY_EMAIL`) |
| dmitri | correct | `401 invalid_grant` — *Invalid user credentials* (brute-force locked; deliberately worded like a wrong password so the response cannot confirm the lock) |
| helena | any | `401` — federated account, no local credential |
| priya | correct | `401` — she exists, but in the **other realm** |

Clearing the lock (`DELETE .../attack-detection/brute-force/users/{id}`) makes
dmitri's login succeed; clearing rohit's `requiredActions` makes his succeed.
The collection does both, so the cause of each refusal is demonstrated rather
than asserted.

## Direct vs effective roles

Amelia's *direct* mappings are one realm role and one client role. Her
*effective* set is six realm roles and four client roles, because:

- `realm-admin` (client role) is **composite** → `manage-users`, `view-users`,
  `manage-realm`
- she is in `/platform`, which grants `platform-operator`
- `platform-operator` is **composite** → `incident-responder`, `status-viewer`
  and the client role `realm-management:view-users`
- `default-roles-orbit-labs` is composite → `offline_access`,
  `uma_authorization`

Jonas is in `/platform` but has no client-role mapping of his own, so he ends up
with `view-users` and nothing more — which is why he can list users through the
Admin API and cannot create one.

## Seed data summary

- **Realms**: 2. `orbit-labs` is brute-force protected (`failureFactor` 5) with
  password policy `length(12) and upperCase(1) and digits(1) and notUsername`;
  `orbit-partners` is not, with `length(8)`.
- **Clients**: 5 — a public SPA (`orbit-status-ui`, standard flow + direct
  grant), a confidential CLI (`orbit-admin-cli`, direct grant only), a service
  account (`orbit-backup-service`, client credentials only), the bearer-only
  `realm-management`, and `partner-portal` in the other realm.
- **Realm roles**: 9 across both realms, including two composites.
- **Client roles**: 5, including the composite `realm-management:realm-admin`.
- **Groups**: 4, with `/platform/on-call` as a subgroup of `/platform`.
- **Users**: 8 — amelia (realm-admin, TOTP configured), jonas (group-inherited
  `view-users`), helena (**federated**, no credential), rohit (**pending
  required actions**), noor (**disabled**), dmitri (**brute-force locked**), the
  backup service account, and priya in `orbit-partners`.
- **Sessions**: 6, including one **offline** session and one **expired** one.
- **Identity providers**: 3 (GitHub OIDC and Acme SAML enabled, Google
  link-only and disabled).
- **Required actions**: 7 across both realms.
- **Events**: 8 login/register/token events, 5 admin events.

Seed passwords: `amelia OrbitKeycloak2026!`, `jonas OrbitJonas2026!`,
`rohit OrbitRohit2026!`, `noor OrbitNoor2026!`, `dmitri OrbitDmitri2026!`,
`priya OrbitPriya2026!`. Helena has none.

## Notes

- **Realm isolation is real.** A `orbit-labs` token administering
  `orbit-partners` is 403; a `orbit-labs` user fetched through the
  `orbit-partners` path is 404; userinfo with a foreign-realm token is 401; and
  introspecting a token in the wrong realm reports `{"active": false}`.
- **The Admin API gate has three distinct refusals**: no live bearer (401),
  a bearer for a different realm (403) and a bearer missing the required
  `realm-management` role (403).
- **The password policy string is parsed, not hard-coded.** `length(12)`,
  `upperCase(1)`, `digits(1)` and `notUsername` each produce Keycloak's own
  error code (`invalidPasswordMinLength`, `invalidPasswordMinUpperCaseChars`,
  `invalidPasswordMinDigits`, `invalidPasswordNotUsername`).
- A **temporary** password reset adds `UPDATE_PASSWORD` to the user's required
  actions, so the next direct grant returns *Account is not fully set up*.
- Resetting a password, disabling a user and deleting a user all drop that
  user's sessions; the collection shows a token going dead right after.
- Client-type rules are enforced: a public client must not send a secret, a
  confidential one must, a client with `directAccessGrantsEnabled: false`
  refuses the password grant, and one without `serviceAccountsEnabled` refuses
  client credentials.
- A service-account token carries **no refresh token**, matching Keycloak's
  default.
- Deleting a group that still has subgroups is refused.
- `GET .../role-mappings/effective` is not a Keycloak path verbatim — the real
  API spreads the same information across `composite=true` parameters. It is
  collapsed into one endpoint here so the difference from `/role-mappings` is
  visible in a single request.
- Mutations (new users, roles, groups, sessions, cleared locks) are held in
  process memory and reset on container restart.
