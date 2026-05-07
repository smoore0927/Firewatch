# Changelog

All notable changes to Firewatch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
