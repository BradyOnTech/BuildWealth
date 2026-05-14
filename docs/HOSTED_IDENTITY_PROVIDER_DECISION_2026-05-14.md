# Hosted Identity Provider Decision

**Date:** 2026-05-14

**Status:** Recommended first hosted provider; pending real tenant configuration.

## Purpose

BuildWealth now has a generic OIDC authorization-code login adapter, workspace-scoped sessions, local-login disablement in hosted mode, secure session cookies, ID-token validation, provider-managed account security links, and hosted logout support.

The next decision is not "which SDK do we add?" The next decision is which hosted identity provider best fits BuildWealth's product boundary:

- users sign into a private household workspace
- BuildWealth owns workspace authorization and financial-data boundaries
- the identity provider owns sign-in, password reset, MFA, passkeys, and account-security screens
- BuildWealth stays provider-portable through OIDC claims, not vendor-specific user objects

## Recommendation

Use **Auth0** as the first hosted identity provider for the private beta.

Auth0 is the best fit for this stage because BuildWealth already has a server-side OIDC authorization-code flow and Auth0's regular web application model maps directly onto it:

- Authorization Code Flow for confidential web applications
- OIDC discovery and JWKS-backed ID-token verification
- hosted Universal Login instead of BuildWealth-owned password screens
- MFA policy and factor management in the provider
- passkey support for database connections
- OIDC logout endpoint support
- account/security links can remain provider-managed while BuildWealth keeps the household workspace UI focused

This is a first hosted-beta decision, not a permanent vendor lock. BuildWealth product code should continue to depend on `RequestContext`, `User`, `Membership`, `Workspace`, and `Session`, not Auth0-specific SDK objects.

## Alternatives Considered

### Auth0

Best fit for the current BuildWealth adapter.

Strengths:

- Mature OIDC support and discovery metadata.
- Clean authorization-code flow for confidential apps.
- Hosted login and account-security posture.
- MFA factors include OTP, WebAuthn security keys, WebAuthn biometrics, push, SMS/voice, email, Duo, and recovery codes.
- Passkeys are supported as a database-connection authentication method.
- OIDC logout endpoint exists.

Tradeoffs:

- Some MFA/passkey/adaptive controls may depend on plan and tenant configuration.
- User self-service factor-management UX may require Auth0-hosted pages or future Management/MFA API work if BuildWealth wants deeper in-app controls.

### Clerk

Good productized auth UX, but less ideal for this first slice because the product tends to shine when using Clerk SDKs/components. BuildWealth should stay OIDC-first for now.

Use later if:

- we decide hosted account/profile widgets are more valuable than strict OIDC portability
- we want a richer drop-in account-management UI

### WorkOS

Strong enterprise identity platform, especially for B2B/SSO/org-heavy products. It is probably more than BuildWealth needs for a 1-9 user private beta.

Use later if:

- advisor-firm/client-organization workflows become primary
- SAML/enterprise SSO becomes a near-term requirement

### Supabase Auth

Good if BuildWealth also moves hosted persistence to Supabase/Postgres/RLS. Less direct for this slice because BuildWealth currently owns its control plane and workspace authorization locally.

Use later if:

- hosted data storage moves into Supabase
- BuildWealth wants Postgres/RLS as the primary authorization substrate

## Auth0 Tenant Contract

Create one Auth0 tenant/application for the first hosted beta:

- Application type: Regular Web Application
- Flow: Authorization Code Flow with PKCE
- Token endpoint auth method: `client_secret_basic` unless tenant setup requires `client_secret_post`
- Signing algorithm: `RS256`
- Callback URL:
  - local tunnel/staging: `https://<host>/api/auth/hosted/callback`
  - production: `https://<production-host>/api/auth/hosted/callback`
- Allowed logout URL:
  - local tunnel/staging: `https://<host>/v2`
  - production: `https://<production-host>/v2`
- Allowed web origins:
  - local tunnel/staging host
  - production host

BuildWealth environment values:

```bash
AUTH_MODE=hosted
AUTH_OIDC_PROVIDER_NAME=Auth0
AUTH_OIDC_ISSUER_URL=https://<tenant>.<region>.auth0.com
AUTH_OIDC_CLIENT_ID=<auth0-application-client-id>
AUTH_OIDC_CLIENT_SECRET=<auth0-application-client-secret>
AUTH_OIDC_REDIRECT_URI=https://<buildwealth-host>/api/auth/hosted/callback
AUTH_OIDC_TOKEN_AUTH_METHOD=client_secret_basic
AUTH_OIDC_SCOPES="openid email profile"
AUTH_OIDC_REQUIRE_ID_TOKEN=true
AUTH_OIDC_ALLOWED_ID_TOKEN_ALGS=RS256
AUTH_OIDC_REQUIRE_MFA=false
AUTH_OIDC_LOGOUT_URL=https://<tenant>.<region>.auth0.com/oidc/logout
AUTH_POST_LOGOUT_REDIRECT_URI=https://<buildwealth-host>/v2
AUTH_ACCOUNT_MANAGEMENT_URL=
AUTH_PASSWORD_RESET_URL=
AUTH_MFA_ENROLLMENT_URL=
AUTH_PASSKEY_ENROLLMENT_URL=
```

Notes:

- Auth0 discovery should provide authorization, token, userinfo, issuer, and JWKS metadata.
- Leave explicit endpoint overrides empty unless discovery is unavailable in the selected tenant.
- Leave account-management, password-reset, MFA, and passkey links empty until the exact tenant-supported user-facing URLs are validated. Auth0's user-facing management/reset paths can vary by Universal Login, connection, and tenant configuration; BuildWealth should hide unavailable links rather than ship dead controls.
- BuildWealth should not store Auth0 access tokens or refresh tokens for this first hosted beta.

## MFA Policy

Start with **MFA encouraged, not required** for the first private hosted beta.

Reasoning:

- This avoids locking out early test users while we validate tenant setup, callback handling, and account linking.
- BuildWealth still displays whether MFA was present when the provider includes `amr`, `acr`, or equivalent claims.
- After the real tenant is tested, we can flip to `AUTH_OIDC_REQUIRE_MFA=true` for production or for selected beta users.

Minimum Auth0 tenant setup:

- Enable at least one independent MFA factor.
- Prefer WebAuthn security keys and OTP for early beta.
- Enable passkeys for the database connection if passwordless/passkey sign-in is part of the beta.
- Keep SMS as optional rather than primary if possible.

## BuildWealth User Workflow

### Sign In

1. User opens `/v2`.
2. BuildWealth detects hosted mode and shows `Continue with Auth0`.
3. User completes Universal Login.
4. Auth0 redirects to `/api/auth/hosted/callback`.
5. BuildWealth validates state, PKCE, ID token, nonce, issuer, audience, expiry, signing algorithm, and UserInfo subject.
6. BuildWealth creates or links a BuildWealth user and opens that user's household workspace.

### Account Security

Settings should continue to show:

- provider-managed password reset
- provider-managed MFA
- provider-managed passkeys
- provider-managed account/security page when available

If a provider URL is not available, the UI should say the control is managed by the identity provider instead of showing a dead link.

### Logout

1. User chooses Sign out from the BuildWealth account menu.
2. BuildWealth revokes the local BuildWealth session.
3. If `AUTH_OIDC_LOGOUT_URL` is configured, BuildWealth redirects to Auth0's OIDC logout endpoint.
4. Auth0 returns to `AUTH_POST_LOGOUT_REDIRECT_URI`.

## Local Development And Migration

Keep `AUTH_MODE=local` for local development that needs local register/login.

Use `AUTH_MODE=hosted` only when validating the hosted tenant.

Local-user migration policy:

- If a hosted user signs in with the same verified email as an active local BuildWealth user, BuildWealth links the hosted provider subject to that user.
- If the email is already linked to a different hosted provider subject, BuildWealth rejects sign-in.
- Hosted users must have verified email.
- Demo workspace remains separate from real household workspace.

## Validation Checklist

Before inviting real hosted users:

- [ ] Auth0 tenant and Regular Web Application created.
- [ ] Callback URL configured exactly.
- [ ] Logout return URL configured exactly.
- [ ] Universal Login enabled and branded enough for a private beta.
- [ ] Database connection enabled for email/password or passwordless/passkey beta path.
- [ ] MFA factors selected.
- [ ] Passkeys enabled if included in beta.
- [ ] `AUTH_MODE=hosted` tested locally through a tunnel or staging host.
- [ ] `/api/auth/config` reports hosted auth enabled, local auth disabled, ID-token validation required.
- [ ] Hosted sign-in succeeds with a verified email.
- [ ] Hosted sign-in fails cleanly for callback replay or invalid state.
- [ ] Hosted sign-in fails cleanly for unverified email.
- [ ] Hosted logout revokes BuildWealth session and exits the provider session as expected.
- [ ] Settings account-security links are either valid or intentionally hidden.
- [ ] Existing local user can link by verified email.
- [ ] Conflicting provider subject is rejected.
- [ ] Browser test covers the visible v2 sign-in, error, Settings account-security, and logout paths.

## Implementation Notes

Do not add Auth0 SDKs unless a future requirement cannot be met with OIDC.

Keep this boundary:

- Auth0 authenticates the person.
- BuildWealth authorizes workspace access.
- BuildWealth stores only provider name, provider subject, email, display name, MFA status signal, and session metadata.
- BuildWealth does not store provider refresh tokens in the first hosted beta.

If deeper provider account management is needed later, add it as an optional provider-management service behind BuildWealth-owned routes, not directly in v2 views.

## Sources

- Auth0 Authorization Code Flow: https://dev.auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow
- Auth0 OIDC logout: https://auth0.com/docs/authenticate/login/logout/log-users-out-of-auth0
- Auth0 MFA overview: https://auth0.com/docs/secure/multi-factor-authentication
- Auth0 MFA factors: https://auth0.com/docs/multifactor-authentication/factors
- Auth0 passkeys: https://auth0.com/docs/authenticate/database-connections/passkeys
- Clerk OAuth/OIDC metadata: https://clerk.com/docs/guides/configure/auth-strategies/oauth/how-clerk-implements-oauth
- WorkOS docs overview: https://workos.com/docs
- Supabase Auth overview: https://supabase.com/docs/guides/auth/
- Supabase custom OAuth/OIDC providers: https://supabase.com/docs/guides/auth/custom-oauth-providers
