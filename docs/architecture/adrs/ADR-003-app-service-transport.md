# ADR-003: App Service Transport

- Status: Accepted

## Context

The current UI/backend contract is tied to a string-based webview bridge. This makes the boundary weak, hard to type, and awkward for browser-first tooling.

## Decision

The future application boundary will be:

- Python FastAPI as the app-service layer;
- HTTP for commands and queries;
- SSE for one-way status, log, and progress streams.

## Consequences

Positive:

- explicit and testable API contracts;
- same backend path for browser dev, Playwright, and desktop shell;
- simpler operational model than a desktop-only IPC path;
- SSE is easy to debug and fits the current one-way event stream need.

Negative:

- introduces another runtime boundary to manage;
- WebSocket may still be needed later for richer bidirectional flows.

## Rejected Alternatives

- Keep the webview bridge as the primary contract:
  - rejected because it is too shell-specific and weakly typed.
- Use desktop-only IPC for all product communication:
  - rejected because it hurts browser-based testing and future agent workflows.
- Start with WebSocket everywhere:
  - rejected for Stage 1 because it adds complexity without immediate need.

## Implications for Tests and Agents

- tests can talk to a predictable local service;
- agents can reason about typed contracts and observable state;
- failure logging and artifacts become easier to standardize.
