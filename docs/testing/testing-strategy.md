# Testing Strategy

This document defines the permanent testing platform for the next-generation Botik application.

## Principles

- Tests are part of the product platform.
- User-facing features must be testable without active control of the desktop session.
- The main E2E path is browser-first and headless.
- Desktop shell validation is a smaller smoke layer, not the main regression suite.
- Failure artifacts are mandatory for critical-path tests.

## Test Pyramid

### Unit

Purpose:

- validate pure logic quickly;
- verify reducers, selectors, adapters, serializers, and low-level utilities.

Primary tools:

- Vitest for frontend logic
- pytest for Python logic

### Integration

Purpose:

- validate app-service contracts and job manager behavior;
- validate frontend integration against typed API boundaries.

Primary tools:

- pytest for Python integration paths
- React Testing Library and Vitest for UI integration

### E2E

Purpose:

- validate critical user flows through the real UI;
- validate status, logs, progress, and failure handling without shell shortcuts.

Primary tool:

- Playwright headless

### Desktop Smoke

Purpose:

- validate desktop shell boot and basic attach/navigation behavior;
- verify that packaged shell behavior stays connected to the new foundation.

Primary tool:

- tauri-driver or equivalent WebDriver-level automation

## Prohibited Primary Approaches

The following may not be used as the main testing strategy:

- pyautogui
- pynput
- SendInput-based tools
- coordinate-based clicking
- tests that require the window to become foreground-active

## Critical Path Expectations

Every migrated user-facing feature must have:

- at least one headless E2E flow, or
- a written exception documenting why the feature is not yet suitable for E2E and what temporary coverage exists.

Background-job surfaces must cover:

- start;
- running state;
- progress/log visibility;
- stop;
- completion and failure paths;
- cleanup behavior.

## Artifact Rules

Critical-path failures must retain:

- screenshot;
- trace;
- HTML report;
- structured service logs;
- job logs where relevant;
- cleanup summary.

See [artifact-retention.md](./artifact-retention.md) for retention rules.

## Stability Rules

- Reuse shared fixtures and launchers.
- Reuse selector conventions.
- Do not create screen-specific test harnesses when shared tooling can be extended.
- Prefer role and label selectors before adding test ids.
- Keep traces and videos cost-aware.

## Definition of Done for User-Facing Features

A new user-facing feature is not done unless:

- it fits the existing test platform or extends it;
- it exposes stable selectors;
- it is observable headlessly;
- it does not require system mouse or focus capture;
- its tests and selectors are documented in the PR.
