# Minimal CI Plan

This document describes the minimum CI quality pipeline required once the new foundation begins landing.

## Goals

- validate architecture boundaries;
- preserve the permanent testing platform;
- keep desktop quality checks separate from browser-first product validation;
- prevent regressions back to shell-coupled UI and ad-hoc process launching.

## Required CI Stages

### backend-fast

Runs:

- Python unit tests;
- contract tests;
- process-ownership checks for app-service and job-manager modules.

### frontend-fast

Runs:

- typecheck;
- lint;
- unit and component tests;
- forbidden-import checks for shell or process launch APIs in frontend code.

### integration

Runs:

- app-service integration tests;
- Job Manager lifecycle tests;
- worker contract and cleanup checks.

### e2e-headless

Runs:

- Playwright critical-path tests for migrated features;
- artifact upload for failures.

### desktop-smoke-windows

Runs:

- desktop shell launch smoke;
- attach and basic navigation checks;
- no-visible-console-window validation where supported;
- failure artifact upload.

### package-smoke

Runs:

- packaging sanity checks for protected branches or release flows.

## Branch Policy

Pull requests:

- `backend-fast`
- `frontend-fast`
- `integration`
- `e2e-headless`

Main and nightly:

- all PR stages
- `desktop-smoke-windows`

Release:

- all main stages
- packaging and release checks

## Enforcement Ideas

- fail frontend CI if business code imports process launch APIs;
- fail backend CI if user-facing jobs are launched outside approved Job Manager ownership;
- require test declaration for user-facing route changes.
