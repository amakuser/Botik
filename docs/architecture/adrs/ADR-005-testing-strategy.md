# ADR-005: Testing Strategy

- Status: Accepted

## Context

Previous UI testing attempts relied on unsafe desktop interactions and did not create a durable product test platform.

## Decision

The permanent test strategy will be:

- Playwright headless for primary product E2E;
- Vitest and React Testing Library for frontend component and integration tests;
- pytest for Python service, job manager, workers, and contract tests;
- tauri-driver or equivalent WebDriver-level automation for narrow desktop smoke coverage.

The following approaches are explicitly prohibited as the main strategy:

- pyautogui
- pynput
- SendInput-based desktop automation
- coordinate-click automation
- foreground-required tests

## Consequences

Positive:

- safer background execution for tests;
- reusable platform for future features;
- CI-friendly and agent-friendly validation path.

Negative:

- requires testability conventions in the product;
- desktop smoke is a separate test tier rather than the main regression layer.

## Rejected Alternatives

- System mouse/keyboard automation as the main strategy:
  - rejected because it interferes with the user session and is brittle.
- Rely only on unit tests:
  - rejected because user-facing flows and lifecycle behavior would remain unproven.

## Implications for Tests and Agents

- headless automation becomes the default path;
- stable selectors and artifacts become first-class engineering requirements;
- future agents can validate product flows without stealing focus.
