# Changelog

All notable changes to Firewatch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Outbound webhook subscriptions — admin-managed integrations that receive HMAC-SHA256 signed HTTP POST notifications. Supports `risk.assigned` (fires when a risk's owner changes), `review.overdue` (daily per-owner digest of risks past their next review date), and `response.overdue` (fires the day after a response's target date passes without completion). Each event type is subscribable independently. Admin settings page at `/settings/webhooks` provides subscription CRUD, a test-fire button, and a per-subscription delivery history panel with retry tracking.
- Webhook delivery reliability — up to three delivery attempts per event with 1 s / 5 s / 25 s exponential backoff. Every attempt is persisted to `webhook_deliveries` for debugging. Consecutive-failure counter tracks unreliable endpoints.
- Internal event bus (`services/events.py`) — lightweight pub/sub backbone decoupling event producers (risk service, daily scheduler) from delivery subscribers. New channels (e.g. email) can subscribe without touching existing code.
- Daily asyncio scheduler — fires at 09:00 UTC, guarded by an atomic `UPDATE scheduler_state` so multi-replica deployments do not double-send. Also invocable via `POST /api/internal/tick` (admin-only) for ops and test purposes.
- Webhook HMAC secrets encrypted at rest with Fernet keyed off `WEBHOOK_KEK` (HKDF-from-`SECRET_KEY` dev fallback). `WEBHOOK_KEK_PREVIOUS` enables zero-downtime key rotation via `MultiFernet`.
- Pluggable secrets provider (`SECRETS_BACKEND`) — sensitive settings (`SECRET_KEY`, `WEBHOOK_KEK`, `OIDC_CLIENT_SECRET`, `SCIM_BEARER_TOKEN`, `DATABASE_URL`) can be resolved at startup from environment variables (default), Docker / Kubernetes file mounts (`file`), HashiCorp Vault KV v2 (`vault`), Azure Key Vault (`azure_keyvault`), or AWS Secrets Manager (`aws`). Existing deployments require no configuration changes.
- System-wide audit log that captures auth sign-in/sign-out, SSO login, user creation/deactivation, and all risk CRUD operations with actor, IP, resource type, resource ID, and action metadata.
- Audit log API (`GET /api/audit/logs`, `GET /api/audit/actions`) — admin-only, with filters for action, user, resource type, and date range, plus pagination.
- Admin Settings page (`/settings`) in the frontend with a filterable, paginated audit log panel; protected by `AdminRoute` so non-admins are redirected to the dashboard.
- `SearchableSelect` component for filtering the audit log by action or user.
- Alembic migration adding the `audit_log` table.
- Backend test suite additions: audit service unit tests, audit API integration tests, audit instrumentation tests across auth/SSO/risks/users endpoints (163 tests total, up from 128).
- Frontend Vitest + React Testing Library harness (`vitest.config.ts`, `src/test/setup.ts`) with component and service-layer tests.
- Server-side session revocation: `last_logout_at` timestamp on `User`; logout immediately invalidates all tokens (access and refresh) issued before that time. Tokens are checked on every authenticated request and on the `/refresh` endpoint.
- SCIM 2.0 provisioning endpoints (`/api/scim/v2/*`) — bearer-token authenticated, supports full user lifecycle (create, read, list, update, replace, deactivate, delete). `PATCH active=false` deactivates the user and stamps `last_logout_at`, immediately killing active sessions. Controlled by `SCIM_ENABLED` / `SCIM_BEARER_TOKEN` env vars.
- CAEP receiver endpoint (`POST /api/auth/sso/caep`) — accepts IdP-pushed Security Event Tokens (SETs) signed by the configured OIDC provider's JWKS. Handles `session-revoked`, `credential-change` (stamps `last_logout_at`), `account-disabled`, and `account-purged` (deactivates user). Controlled by `CAEP_ENABLED` / `CAEP_AUDIENCE` env vars.

### Fixed
- Dashboard `score-history` and `score-totals-by-severity` endpoints now use UTC-anchored datetime bounds instead of server-local time, preventing risks created near midnight UTC from being silently excluded from date-range queries on non-UTC hosts.
- Test suite no longer leaks real OIDC credentials from the developer's `.env` into tests that assert SSO is unconfigured; an autouse fixture resets all OIDC and SCIM settings to defaults before each test.

### Security
- `POST /api/auth/refresh` now enforces `last_logout_at`: refresh tokens issued before the user's last logout are rejected with 401, closing a 7-day post-logout window where a stolen refresh token could still mint new access tokens.
- `iat` (issued-at) claim added to all JWTs to support token revocation comparisons.

## [0.1.0] - 2026-05-07

### Added
- NIST 800-30 aligned risk register with full CRUD, likelihood/impact scoring, owner assignment, status tracking, and soft-delete.
- Risk assessments (point-in-time scoring snapshots) and treatments (remediation tracking) as sub-resources on each risk.
- Review workflow for periodic re-evaluation of risks.
- CSV import and export for risks, including a downloadable import template.
- OIDC / SSO login with PKCE, JWKS-based ID token verification, group-to-role mapping, and JIT user provisioning.
- Local username/password authentication with bcrypt-hashed credentials and HTTP-only cookie sessions.
- Role-based access control with four roles: admin, analyst, risk owner, viewer.
- Admin user management endpoints (list, create, deactivate, list assignable owners).
- Dashboard endpoints for summary statistics and historical score trends.
- Docker Compose development environment for backend and frontend.
- Backend test suite (128 tests) covering OIDC utilities, SSO API, risks API, local auth, user management, and dashboard.

### Changed
- Modernized dependencies, removing end-of-life and unmaintained packages.
- Bumped Vite from 5.4.x to 8.0.x on the frontend.
- Hardened Docker setup and improved first-user bootstrap flow.
- README rewritten for clarity, with an updated architecture diagram.

### Fixed
- OIDC IdP signing-key rotation now refreshes the JWKS cache instead of failing token verification.
- Stale "current score" on risks when two assessments were written in the same second (added `id desc` tiebreaker on the assessments and history relationships).
- Login page now surfaces a clear error message on failed authentication.

### Security
- Email-verified claim is now required for OIDC sign-in.
- ID token `at_hash` is validated against the access token.
- Rate limiting applied to authentication endpoints.
- Auth tokens stored in HTTP-only, SameSite cookies (not accessible to JavaScript).

[Unreleased]: https://github.com/smoore0927/Firewatch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/smoore0927/Firewatch/releases/tag/v0.1.0
