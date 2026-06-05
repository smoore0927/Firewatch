# Changelog

All notable changes to Firewatch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Risk↔control framework mapping — map risks to compliance controls and back. New tables (Alembic migration `20260529_3f5a921133a6`, down_revision `b8e62d2cace1`): `control_frameworks`, `controls`, and `risk_controls` (many-to-many of risks↔controls with `mapping_type` one of `mitigates`/`monitors`/`detects`, optional `notes`, and creator tracking); ORM models in `app/models/control.py`. Endpoints `GET /api/risks/{id}/controls`, `POST /api/risks/{id}/controls`, and `DELETE /api/risks/{id}/controls/{mapping_id}` manage the mappings; create/delete each writes a `RiskHistory` row and emits a `risk.control.mapped` / `risk.control.unmapped` audit event. The Risk Detail page gains a "Mapped Controls" card (gated by the existing edit permission) for mapping/unmapping controls.
- Compliance control catalog with importer — read endpoints `GET /api/frameworks` (list frameworks) and `GET /api/frameworks/{framework_id}/controls` (list/search a framework's controls), available to any authenticated user. A built-in catalog (NIST 800-53 Rev 5 and NIST CSF 2.0) is seeded on startup from vendored files in `firewatch-backend/app/data/frameworks/`; the seed (`app/services/control_seed.py`) upserts idempotently and never duplicates. Admin-only importers `POST /api/frameworks/import` (multipart upload with optional `framework_name`/`version` query params and a 25 MB guard) and `POST /api/frameworks/import-from-url` (fetches a remote catalog) accept CSV and NIST OSCAL-JSON (including nested control enhancements), upsert by `(framework_name, control_id)` so re-importing never duplicates or disturbs existing risk mappings, and record a `framework.imported` audit event. Migration `20260530_a1b2c3d4e5f6` adds `source_url` + `last_imported_at` to `control_frameworks`; the admin settings page at `/settings/frameworks` drives file/URL import.
- Framework deletion — admin-only `DELETE /api/frameworks/{framework_id}` returns 204 and cascades to the framework's controls, but BLOCKS with 409 (reporting the number of mappings and affected risks) when any of its controls are mapped to a risk, requiring the admin to unmap first; emits a `framework.deleted` audit event. Permanent deletion of built-in (seeded) frameworks is backed by a new `deleted_framework_seeds` tombstone table (Alembic migration `b2c3d4e5f6a7`, down_revision `a1b2c3d4e5f6`): deleting writes a tombstone so the startup seed will not re-create the framework, and re-importing a framework of the same name clears its tombstone (natural undo). The `/settings/frameworks` page adds a per-row, admin-only delete button with a confirmation dialog that surfaces the 409 "in use" message.
- Control category tier in the risk→control picker — the "Add control" flow on the Risk Detail page is now Framework → Category → Control, so controls are browsed within their family instead of one flat list. New `control_families` table (Alembic migration `20260531_c3d4e5f6a7b8`, down_revision `b2c3d4e5f6a7`; ORM model `ControlFamily` in `app/models/control.py` with `framework_id`, `name`, `display_label`, `description`, `sort_order` and a unique `(framework_id, name)`) holds authored, human-readable category prose, decoupled from `controls` and matched by string against `Control.family` so importing/reimporting a framework never disturbs the authored descriptions. Endpoint `GET /api/frameworks/{framework_id}/families` returns each family with a computed `control_count` (synthesizing derived families for any `Control.family` lacking an authored row), and `GET /api/frameworks/{framework_id}/controls` gains an optional `?family=` filter that composes with the existing search. The startup seed (`app/services/control_seed.py`, idempotent and tombstone-aware) authors the NIST CSF 2.0 categories and all 20 NIST 800-53 families. In the picker, the selected category's and control's descriptions render inline beneath each dropdown, and the category list is grouped by NIST CSF Function via `<optgroup>` headers (e.g. "Govern (GV)") so the six Govern categories are no longer indistinguishable.
- Bulk actions on the risk register — select multiple risks via checkboxes and apply one of three operations: reassign owner (admin/security_analyst only), close (sets status to `closed`), or re-score (applies a new likelihood × impact assessment to all selected risks). Capped at 200 risks per request with per-item error capture so a single failure doesn't abort the batch. Backend endpoints at `POST /api/risks/bulk/reassign`, `/bulk/status`, and `/bulk/rescore`; each writes a single summary audit row and fires the existing `risk.assigned` event per reassigned risk.
- Risk register dashboard scoping for risk owners — the dashboard summary and score-history endpoints now filter to only the risks owned by the requesting user when the caller has the `risk_owner` role, matching the existing list-endpoint scoping behaviour.
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
- In-app notifications — per-user notification feed accessible via a bell icon in the top nav. Backed by a new `notifications` table (`Notification` ORM model with `NotificationType` enum covering `risk_assigned`, `review_overdue`, `response_overdue`, and `risk_changed`) and exposed through `GET /api/notifications` (with `unread_only`, `limit`, `offset` query params), `GET /api/notifications/unread-count`, `POST /api/notifications/{id}/read`, and `POST /api/notifications/mark-all-read`. A new `notification_service` subscribes to the existing internal event bus alongside the webhook dispatcher (registered at startup via a side-effect import in `main.py`), listening to `risk.assigned`, `review.overdue`, and `response.overdue` channels plus emitting `risk_changed` notifications, and persists one row per affected user. A nullable `dedup_key` with a partial unique index on `(user_id, dedup_key) WHERE dedup_key IS NOT NULL` prevents duplicate notifications when the same event fires repeatedly. The frontend `NotificationBell` component polls `/api/notifications/unread-count` every 60 s, shows an unread badge, and renders a dropdown of recent notifications with a "mark all read" action. Schema lives in `app/schemas/notification.py`; Alembic migration `20260522_b8e62d2cace1_add_notifications_table.py` adds the table.
- Response edit and delete endpoints — `PATCH /api/risks/{risk_id}/responses/{response_id}` and `DELETE /api/risks/{risk_id}/responses/{response_id}` lift the long-standing append-only restriction on a risk's responses/mitigation plans. The PATCH emits a `risk.response.updated` audit event whose details include the list of changed field names; the DELETE emits `risk.response.deleted`. Backed by a new `ResponseUpdate` Pydantic schema and `update_response` / `delete_response` methods on `RiskService`.
- Light, dark, and system theme support — new `ThemeProvider` (`firewatch-frontend/src/context/ThemeContext.tsx`) wraps the app, toggles the `dark` class on `<html>` based on the user's choice, and persists the preference in `localStorage` under `firewatch.theme`. The `system` option subscribes to `(prefers-color-scheme: dark)` via `matchMedia` and follows OS-level changes live. New `/settings/account/appearance` page exposes the toggle. Tailwind's `popover` color tokens were added to `tailwind.config.js` and severity badge classes now include matching `dark:` variants for legible contrast in dark mode. Settings routes were restructured so account-scoped pages live under `/settings/account/*` (password, appearance) while admin-only pages (users, webhooks, api-keys, audit) remain at the top level; the `/account` redirect now points to `/settings/account/password`.
- `tzdata>=2024.1` added to `requirements.txt` — stdlib `zoneinfo` has no built-in tz data on Windows and may be absent on minimal Linux images, and it is required for tz-aware day boundaries used by the daily scheduler, the new notification dedup logic, and the dashboard's per-user timezone bucketing.

### Fixed
- Dashboard `score-history` and `score-totals-by-severity` endpoints now use UTC-anchored datetime bounds instead of server-local time, preventing risks created near midnight UTC from being silently excluded from date-range queries on non-UTC hosts.
- Test suite no longer leaks real OIDC credentials from the developer's `.env` into tests that assert SSO is unconfigured; an autouse fixture resets all OIDC and SCIM settings to defaults before each test.
- Datetime fields on every API response now serialize as UTC ISO 8601 strings with an explicit `+00:00` offset, fixing a one-day-off bug for users east of UTC. A shared helper (`app/schemas/_datetime.py`) is wired into `risk.py`, `auth.py`, `user.py`, `audit_log.py`, `api_key.py`, `report.py`, `scim.py`, and `webhook.py` via `@field_serializer` decorators on every datetime field. The root cause: SQLite silently strips tzinfo from `DateTime(timezone=True)` columns, so values came back as naive datetimes and Pydantic v2 serialized them with no offset (`"2026-05-26T03:00:00"`), which JavaScript's `new Date(...)` interprets as local time.
- Dashboard `score-history` and `score-totals-by-severity` endpoints now accept an optional `tz` IANA timezone query parameter and bucket assessments by the caller's local calendar date instead of the UTC date returned by SQL `func.date()`, so points near midnight no longer land in the wrong day for non-UTC users. Invalid or unset values fall back to UTC.

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
