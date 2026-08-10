# pocketbase-auth-api

Mock of the auth half of the self-hosted PocketBase instance `pocketbase-api`
backs — the Orbit Labs Status page. Record ids and collection ids are the ones
used there, so the two services describe one `pb_data/data.db`.

PocketBase authenticates *per collection*, not globally: `users` and the system
`_superusers` collection each carry their own identity fields, password rules,
OTP/MFA switches and OAuth2 providers.

Run it as its own container (build context is the environment root):
```
docker compose up -d pocketbase-auth-api
curl http://localhost:8114/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir pocketbase-auth-api --port 8114
```

Tokens are `<header>.<recordId>.<tokenKey>` and resolve only while the record
still carries that `tokenKey`. That reproduces PocketBase's real revocation
model: there is no session table to delete from — changing a password or an
email rotates the key and every token already issued stops verifying. Three are
seeded (`…usramelia000001.tk_amelia_5f1c`, `…usrjonas0000002.tk_jonas_2b90`,
`…sup0admin000001.tk_ops_e64a`), so a request can quote a bearer literally.

Passwords are verified for real — `sha256(passwordSalt + password)` — and
neither the hash nor the salt is returned. Seed credentials are listed in
`settings.json` under `seed_credentials`.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`pocketbase_auth_api_postman_collection.json` for the runnable collection.
