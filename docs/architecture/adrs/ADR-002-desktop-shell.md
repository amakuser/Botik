# ADR-002: Desktop Shell

- Status: Accepted

## Context

The current desktop experience is tightly coupled to Python UI shell implementations. That coupling makes browser-first testing harder and mixes product concerns with shell concerns.

## Decision

The future desktop shell will be Tauri.

Tauri will be responsible only for host and shell concerns:

- window lifecycle;
- tray and menu integration;
- application paths;
- folder and file dialogs;
- packaging and shell-specific integration.

Tauri will not own business orchestration for trading, training, backfill, or other user-facing jobs.

## Consequences

Positive:

- clearer boundary between UI and shell;
- shell-specific code stays narrow;
- browser dev mode and desktop mode can share the same app-service path.

Negative:

- adds Rust/Tauri build complexity;
- requires a dedicated desktop smoke layer for integration tests.

## Rejected Alternatives

- Continue with pywebview as the long-term shell:
  - rejected because it keeps the product tied to a fragile bridge-oriented architecture.
- Move business logic into shell IPC:
  - rejected because it couples the UI to the desktop container and hurts browser-first automation.

## Implications for Tests and Agents

- most product behavior can be verified headlessly in a browser;
- desktop automation can remain small and focused on shell smoke checks;
- agents do not need system-level desktop control for ordinary feature validation.
