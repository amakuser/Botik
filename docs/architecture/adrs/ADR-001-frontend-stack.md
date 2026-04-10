# ADR-001: Frontend Stack

- Status: Accepted

## Context

The current dashboard UI is implemented as a giant HTML and script bundle with imperative DOM updates, manual routing, manual polling, and mixed business actions. This structure is not sustainable for a long-lived product with automated testing and modular feature growth.

## Decision

The next-generation frontend stack will be:

- Vite
- React
- TypeScript
- React Router
- TanStack Query
- Zustand

## Consequences

Positive:

- feature-oriented modularity;
- better separation of rendering and state;
- predictable DOM for Playwright;
- easier component and integration testing;
- stronger type-safety and refactorability.

Negative:

- introduces a JavaScript/TypeScript toolchain;
- requires discipline around module boundaries and state ownership;
- temporary coexistence with the legacy UI.

## Rejected Alternatives

- Keep extending the giant HTML/script:
  - rejected because it does not scale, is hard to test, and increases drift.
- Keep using template-only pywebview pages:
  - rejected because it couples product UI architecture to desktop shell implementation.

## Implications for Tests and Agents

- browser-first automation becomes practical;
- selectors can become stable contracts;
- future agents can interact with the product through a predictable DOM tree instead of shell-focused workarounds.
