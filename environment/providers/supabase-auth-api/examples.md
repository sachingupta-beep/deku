# Supabase Auth (GoTrue) Mock API — Example Requests and Responses

Captured from a clean container against the committed seed data. Requests are
shown against `$SUPABASE_AUTH_API_URL`; responses are verbatim (long objects
elided with `…`). Examples assume:

```bash
export ANON_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.anon.orbit-labs-selfhost'
export SERVICE_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.service_role.orbit-labs-selfhost'
export AMELIA='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.amelia-session.orbit-labs'
```

`$AMELIA` is a seeded access token — the mock keeps three live sessions so a
request can quote a bearer without first signing in.

## Health

```bash
curl -s "$SUPABASE_AUTH_API_URL/health"
```
```json
{"status": "ok"}
```

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/health"
```
```json
{"version": "v2.158.1", "name": "GoTrue",
 "description": "GoTrue is a user registration and authentication API"}
```

## Instance settings

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/settings"
```
```json
{
  "external": {"email": true, "phone": true, "anonymous_users": true,
               "github": true, "google": true, "gitlab": false,
               "apple": false, "azure": false, "saml": false},
  "disable_signup": false,
  "mailer_autoconfirm": false,
  "phone_autoconfirm": false,
  "sms_provider": "twilio",
  "mfa_enabled": true,
  "saml_enabled": false,
  "security": {"refresh_token_rotation_enabled": true,
               "refresh_token_reuse_interval_seconds": 10,
               "manual_linking_enabled": true, "max_frequency_seconds": 60,
               "otp_length": 6, "otp_expiry_seconds": 3600}
}
```

## Sign in with a password

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email": "amelia.ortega@orbit-labs.com", "password": "OrbitSupabase2026!"}'
```
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.6d9a56a5dc50498794b195c23bdcae8d.sig",
  "token_type": "bearer",
  "expires_in": 3600,
  "expires_at": 1785936415,
  "refresh_token": "e49ec0b97dad4efcba0260df",
  "user": {
    "id": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901",
    "aud": "authenticated",
    "role": "authenticated",
    "email": "amelia.ortega@orbit-labs.com",
    "phone": "+14155550101",
    "email_confirmed_at": "2024-01-10T10:05:00Z",
    "confirmed_at": "2024-01-10T10:05:00Z",
    "banned_until": null,
    "is_anonymous": false,
    "app_metadata": {"provider": "email", "providers": ["email", "github"]},
    "user_metadata": {"full_name": "Amelia Ortega", "role": "owner"},
    "identities": [
      {"identity_id": "8f2c1b40-5e93-4a17-9d26-71c0e84b3f52",
       "id": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901",
       "user_id": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901", "provider": "email",
       "identity_data": {"email": "amelia.ortega@orbit-labs.com",
                         "sub": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901"},
       "last_sign_in_at": "2026-05-26T08:12:00Z",
       "created_at": "2024-01-10T10:00:00Z"},
      {"identity_id": "c41d7a68-2b95-4e30-8f71-6a2d9c05e713", "id": "1840221",
       "provider": "github", "…": "…"}
    ],
    "factors": [{"id": "e97d2b40-5c81-4f36-a729-1b6e0d94c8f5",
                 "friendly_name": "Authenticator app", "factor_type": "totp",
                 "status": "verified", "…": "…"}],
    "created_at": "2024-01-10T10:00:00Z",
    "updated_at": "2026-08-05T12:26:55Z"
  },
  "weak_password": null,
  "mfa": {"current_level": "aal1", "next_level": "aal2",
          "current_authentication_methods": [{"method": "password"}],
          "factors": [{"id": "e97d2b40-5c81-4f36-a729-1b6e0d94c8f5",
                       "friendly_name": "Authenticator app",
                       "factor_type": "totp"}],
          "note": "a verified factor is enrolled; challenge and verify it to reach aal2"}
}
```

## The four ways sign-in fails

A wrong password, an unknown address and an OAuth-only account are deliberately
indistinguishable — the endpoint must not enumerate accounts. A ban and an
unconfirmed email are reported only after the password itself checks out.

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email": "helena.park@orbit-labs.com", "password": "OrbitHelena2026!"}'
```
```json
{"code": 400, "error_code": "invalid_credentials",
 "msg": "Invalid login credentials"}
```

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email": "noor.aziz@orbit-labs.com", "password": "OrbitNoor2026!"}'
```
```json
{"code": 403, "error_code": "user_banned", "msg": "User is banned"}
```

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email": "rohit.bansal@orbit-labs.com", "password": "OrbitRohit2026!"}'
```
```json
{"code": 400, "error_code": "email_not_confirmed", "msg": "Email not confirmed"}
```

## Refresh a session

Rotation is on, so the presented token is revoked and a descendant is issued.

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=refresh_token" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"refresh_token": "71b09e4c6a2d48f5c803"}'
```
```json
{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.a0694e6a….sig",
 "token_type": "bearer", "expires_in": 3600, "expires_at": 1785936099,
 "refresh_token": "a741386973ec4bcd81c31bfe", "user": {"…": "…"}}
```

Replaying a revoked token fails:

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/token?grant_type=refresh_token" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"refresh_token": "3a6d80e5b1c74927f0ae"}'
```
```json
{"code": 400, "error_code": "refresh_token_not_found",
 "msg": "Invalid Refresh Token: Refresh Token Not Found"}
```

## Sign up

`mailer_autoconfirm` is off, so no session is issued until the address is
confirmed.

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/signup" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email": "iris.tanaka@orbit-labs.com", "password": "OrbitIris2026!",
       "data": {"full_name": "Iris Tanaka", "role": "analyst"}}'
```
```json
{
  "user": {
    "id": "0a72c6e7-fd2f-4a13-8b60-cfb4bef1896e",
    "aud": "authenticated",
    "role": "authenticated",
    "email": "iris.tanaka@orbit-labs.com",
    "email_confirmed_at": null,
    "confirmed_at": null,
    "app_metadata": {"provider": "email", "providers": ["email"]},
    "user_metadata": {"full_name": "Iris Tanaka", "role": "analyst"},
    "identities": [{"identity_id": "c00ec7f0-03eb-4896-81d5-0bc030002169",
                    "provider": "email", "…": "…"}],
    "factors": [],
    "created_at": "2026-08-05T12:27:12Z",
    "updated_at": "2026-08-05T12:27:12Z"
  },
  "session": null
}
```

## Password recovery

No mail is delivered, so the mock hands back the token it would have emailed.

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/recover" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email": "jonas.pereira@orbit-labs.com"}'
```
```json
{"message": "Recovery email sent", "email": "jonas.pereira@orbit-labs.com",
 "otp": "613932", "token": "6e5653246ddc4902ab9ce07111ee1238",
 "note": "the OTP and token are returned because no mail is actually delivered by the mock"}
```

An unknown address gets the same 200, minus the token:

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/recover" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"email": "nobody@orbit-labs.com"}'
```
```json
{"message": "Recovery email sent", "email": "nobody@orbit-labs.com"}
```

## Confirm a signup token

The seed carries an unused confirmation token for the unconfirmed account.
Verifying it confirms the email and issues a session.

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/verify" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"type": "confirmation", "token": "1f6b0d9c47a3428eb5710c82d64fa395"}'
```
```json
{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.76b84faa….sig",
 "token_type": "bearer", "expires_in": 3600, "refresh_token": "e0e3a85119734203a10ec427",
 "user": {"id": "c72e5a94-1d38-4b6f-ae90-2f4b8c07d532",
          "email": "rohit.bansal@orbit-labs.com",
          "email_confirmed_at": "2026-08-05T12:21:39Z", "…": "…"}}
```

Replaying a spent token is refused:

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/verify" \
  -H "apikey: $ANON_KEY" -H "Content-Type: application/json" \
  -d '{"type": "magiclink", "token": "47d9e01b6c3f4a82b95c0d716ef23a48"}'
```
```json
{"code": 403, "error_code": "otp_expired",
 "msg": "Token has expired or is invalid"}
```

## OAuth authorize

The mock returns the provider URL instead of a 302 so the flow stays
inspectable.

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/authorize?provider=github&redirect_to=https://app.orbit-labs.com/callback" \
  -H "apikey: $ANON_KEY"
```
```json
{"provider": "github", "state": "488095adee794b6e87a6a6d5728111f2",
 "url": "https://github.example.com/login/oauth/authorize?client_id=orbit-labs&state=488095adee794b6e87a6a6d5728111f2&redirect_uri=https://orbitlabsselfhost01.supabase.co/auth/v1/callback",
 "redirect_to": "https://app.orbit-labs.com/callback",
 "note": "the mock returns the URL rather than issuing a 302 so the flow stays inspectable"}
```

A provider that is off in `settings.external` is refused:

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/authorize?provider=apple" -H "apikey: $ANON_KEY"
```
```json
{"code": 400, "error_code": "provider_disabled",
 "msg": "Unsupported provider: provider is not enabled"}
```

## MFA

Enrol a TOTP factor:

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/factors" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $AMELIA" \
  -H "Content-Type: application/json" \
  -d '{"factor_type": "totp", "friendly_name": "Backup key"}'
```
```json
{"id": "cbb4faf1-ddd9-4285-a5a5-a4dc4b8b1a40", "type": "totp",
 "friendly_name": "Backup key",
 "totp": {"qr_code": "otpauth://totp/OrbitLabs:amelia.ortega@orbit-labs.com?secret=JBSWY3DPEHPK3PXP&issuer=OrbitLabs",
          "secret": "JBSWY3DPEHPK3PXP",
          "uri": "otpauth://totp/OrbitLabs:amelia.ortega@orbit-labs.com?secret=JBSWY3DPEHPK3PXP"},
 "verification_code": "294071",
 "note": "the verification code is returned because no authenticator app is actually enrolled"}
```

Challenge the seeded verified factor:

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/factors/e97d2b40-5c81-4f36-a729-1b6e0d94c8f5/challenge" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $AMELIA"
```
```json
{"id": "c1078022-f516-4c72-84d4-b8cacab0aad0", "type": "totp",
 "expires_at": "2026-08-05T13:27:12Z", "expected_code": "482913",
 "note": "the expected code is returned because no authenticator app is actually enrolled"}
```

Verifying promotes the session to `aal2`; a wrong code does not:

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/factors/e97d2b40-5c81-4f36-a729-1b6e0d94c8f5/verify" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $AMELIA" \
  -H "Content-Type: application/json" \
  -d '{"challenge_id": "b7d1e6c4-08a3-4f52-9e7b-2c60d81f4a93", "code": "000000"}'
```
```json
{"code": 400, "error_code": "mfa_verification_failed",
 "msg": "Invalid TOTP code entered"}
```

## Admin: the service key is required

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/users" -H "apikey: $ANON_KEY"
```
```json
{"code": 403, "error_code": "not_admin", "msg": "User not allowed"}
```

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/users?page=1&per_page=2" \
  -H "apikey: $SERVICE_KEY"
```
```json
{"users": [{"id": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901",
            "email": "amelia.ortega@orbit-labs.com",
            "user_metadata": {"full_name": "Amelia Ortega", "role": "owner"},
            "…": "…"},
           {"id": "6b2d4e10-77c3-4a9b-8f52-1d9e6c02a445", "…": "…"}],
 "aud": "authenticated", "total": 7, "page": 1, "per_page": 2, "next_page": 2}
```

## Admin: ban and unban

```bash
curl -s -X PUT "$SUPABASE_AUTH_API_URL/auth/v1/admin/users/d05b3f61-9c27-4e8a-b134-6a8d0e52f7c3" \
  -H "apikey: $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"ban_duration": "none"}'
```
```json
{"id": "d05b3f61-9c27-4e8a-b134-6a8d0e52f7c3",
 "email": "noor.aziz@orbit-labs.com", "banned_until": null, "…": "…"}
```

```bash
curl -s -X PUT "$SUPABASE_AUTH_API_URL/auth/v1/admin/users/c72e5a94-1d38-4b6f-ae90-2f4b8c07d532" \
  -H "apikey: $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"ban_duration": "forever"}'
```
```json
{"code": 422, "error_code": "validation_failed",
 "msg": "ban_duration must be a duration such as 24h, or 'none' to unban"}
```

## Admin: generate an action link

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/admin/generate_link" \
  -H "apikey: $SERVICE_KEY" -H "Content-Type: application/json" \
  -d '{"type": "recovery", "email": "jonas.pereira@orbit-labs.com"}'
```
```json
{"action_link": "https://orbitlabsselfhost01.supabase.co/auth/v1/verify?token=99bae9a5df2045ddb6f22f77e574cf8c&type=recovery&redirect_to=https://app.orbit-labs.com",
 "email_otp": "273605", "hashed_token": "99bae9a5df2045ddb6f22f77e574cf8c",
 "verification_type": "recovery", "redirect_to": "https://app.orbit-labs.com",
 "user": {"id": "6b2d4e10-77c3-4a9b-8f52-1d9e6c02a445",
          "email": "jonas.pereira@orbit-labs.com", "…": "…"}}
```

## Admin: audit log and sessions

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/audit?action=login&per_page=3" \
  -H "apikey: $SERVICE_KEY"
```
```json
{"logs": [{"id": 1, "action": "login",
           "actor_id": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901",
           "actor_username": "amelia.ortega@orbit-labs.com",
           "log_type": "account", "traits_provider": "email",
           "ip_address": "203.0.113.41", "created_at": "2026-05-26T08:12:00Z"},
          {"id": 2, "action": "login", "traits_provider": "github", "…": "…"},
          {"id": 7, "action": "login", "traits_provider": "anonymous", "…": "…"}],
 "total": 3, "page": 1, "per_page": 3}
```

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/admin/sessions?user_id=3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901" \
  -H "apikey: $SERVICE_KEY"
```
```json
{"sessions": [{"id": "4b1e7d92-3a05-4c68-9f31-8d2b0e75c614",
               "user_id": "3f1c9b52-8a44-4f6e-9d21-0a7c5e13b901",
               "aal": "aal1", "provider": "email",
               "created_at": "2026-05-26T08:12:00Z",
               "refreshed_at": "2026-05-26T08:12:00Z",
               "not_after": "2027-05-26T08:12:00Z", "ip": "203.0.113.41",
               "user_agent": "orbit-app/4.8.1", "revoked": false}],
 "total": 1}
```

Tokens are stripped from this view — the admin plane can see that a session
exists, not impersonate it.

## Sign out

```bash
curl -s -X POST "$SUPABASE_AUTH_API_URL/auth/v1/logout?scope=global" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $AMELIA"
```
```json
{"signed_out": true, "scope": "global", "sessions_revoked": 1}
```

The token is dead immediately afterwards:

```bash
curl -s "$SUPABASE_AUTH_API_URL/auth/v1/user" \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $AMELIA"
```
```json
{"code": 401, "error_code": "no_authorization",
 "msg": "This endpoint requires a Bearer token"}
```
