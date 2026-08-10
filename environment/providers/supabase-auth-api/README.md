# supabase-auth-api

Mock of GoTrue, the Supabase authentication service, mounted at `/auth/v1`:
sign-up, the `password` and `refresh_token` grants, the current-user endpoints,
one-time tokens (recovery, magic link, OTP, verify, resend), OAuth authorize,
MFA and the `service_role`-only admin surface.

It models the *same* self-hosted project as `supabase-api`: identical `anon` and
`service_role` keys, and `auth.users` ids that match the `public.profiles` rows
there, so the two services can be exercised as one system.

Run it as its own container (build context is the environment root):
```
docker compose up -d supabase-auth-api
curl http://localhost:8113/health
```

To debug locally:
```
cd environment/
PYTHONPATH=. python -m uvicorn server:app --app-dir supabase-auth-api --port 8113
```

Passwords are verified for real — `sha256(password_salt + password)` — and the
hash is never returned. Seed credentials are listed in `settings.json` under
`seed_credentials`; the accounts carry the failure modes an auth service needs:
an unconfirmed email, a banned user, an OAuth-only identity with no password, a
verified TOTP factor and an unverified one, and an anonymous user.

Seeded sessions have fixed access tokens (for example
`eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.amelia-session.orbit-labs`) so a request
can quote a bearer literally instead of chaining one from a prior response.

See `api_test_results.md` for the endpoint matrix and seed summary,
`examples.md` for captured request/response pairs, and
`supabase_auth_api_postman_collection.json` for the runnable collection.
