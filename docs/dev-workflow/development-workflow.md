# Development Workflow

This document defines how the long-term Botik platform should be developed once the new foundation starts landing.

## Guiding Rules

- No big bang rewrite.
- The legacy UI becomes bugfix-only once foundation work begins.
- New architecture work lands through foundation, then a single vertical slice, then stabilization, then additional migrations.
- Test tooling is not optional and is not deferred.

## Future Repository Areas

- `frontend/`
- `app-service/`
- `apps/desktop/`
- `tests/unit/`
- `tests/integration/`
- `tests/e2e/`
- `tests/desktop-smoke/`
- `test-utils/`
- `docs/architecture/`
- `docs/testing/`
- `docs/dev-workflow/`
- `docs/migration/`
- `docs/ci/`

## Expected Workflow

1. Start from typed contracts and boundaries.
2. Add or extend shared test tooling before or alongside the feature.
3. Implement one small, testable vertical feature slice.
4. Add or extend the headless E2E path if the feature is user-facing.
5. Keep shell-specific logic out of product code.
6. Keep process ownership inside the Job Manager model.

## Feature Delivery Rules

A user-facing feature is only complete when:

- it uses the current architecture boundaries;
- it has stable selectors;
- it has test coverage in the permanent test platform;
- it does not introduce a new ad-hoc subprocess launch path;
- it documents any temporary gaps honestly.

## Job-Related Feature Rules

If a feature starts or stops background work, it must:

- go through the app-service layer;
- use the Job Manager;
- expose status, progress, and logs;
- define cleanup behavior;
- fit into headless validation.

## PR Expectations

PRs for user-facing features should answer:

- what selectors were added or changed;
- what tests were added;
- how the feature is observable in headless mode;
- whether any job lifecycle behavior was introduced or changed.

## Local Commands

The migrated stack now has stable local commands:

- primary local desktop entry: `pwsh ./scripts/run-primary-desktop.ps1`
- frontend only: `pwsh ./scripts/dev-frontend.ps1`
- app-service only: `pwsh ./scripts/dev-app-service.ps1`
- shell only: `pwsh ./scripts/dev-desktop.ps1`
- unit: `pwsh ./scripts/test-unit.ps1`
- integration: `pwsh ./scripts/test-integration.ps1`
- headless E2E: `pwsh ./scripts/test-e2e.ps1`
- desktop smoke: `pwsh ./scripts/test-desktop-smoke.ps1`

During the quarantine period, the legacy pywebview launcher remains available only as a quarantined fallback path.
